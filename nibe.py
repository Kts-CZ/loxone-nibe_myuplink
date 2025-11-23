#!/usr/bin/env python3
import os
import json
import time
import argparse
from datetime import datetime
from configparser import ConfigParser

import requests

TOKEN_URL = "https://api.myuplink.com/oauth/token"
API_BASE = "https://api.myuplink.com/v2"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.ini")
POINTS_MAP_PATH = os.path.join(BASE_DIR, "points_map.json")
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")

# ---------- util ----------

def load_config(path=CONFIG_PATH):
    cfg = ConfigParser()
    if not os.path.exists(path):
        raise RuntimeError(f"config.ini not found at {path}")
    cfg.read(path)
    # myuplink
    client_id     = cfg.get("myuplink", "CLIENT_ID")
    client_secret = cfg.get("myuplink", "CLIENT_SECRET")
    device_id     = cfg.get("myuplink", "DEVICE_ID")
    fallback_refresh = cfg.get("myuplink", "REFRESH_TOKEN", fallback="")

    # loxone
    lox_ip   = cfg.get("loxone", "IP")
    lox_user = cfg.get("loxone", "USER", fallback="")
    lox_pass = cfg.get("loxone", "PASS", fallback="")

    # runtime
    update_interval = cfg.getint("runtime", "UPDATE_INTERVAL", fallback=60)
    log_enabled     = cfg.getboolean("runtime", "LOG_ENABLED", fallback=True)
    log_file        = cfg.get("runtime", "LOG_FILE", fallback=os.path.join(BASE_DIR, "nibe.log"))

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "device_id": device_id,
        "fallback_refresh": fallback_refresh,
        "lox_ip": lox_ip,
        "lox_user": lox_user,
        "lox_pass": lox_pass,
        "update_interval": update_interval,
        "log_enabled": log_enabled,
        "log_file": log_file,
    }

def load_points_map(path=POINTS_MAP_PATH):
    if not os.path.exists(path):
        raise RuntimeError(f"points_map.json not found at {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def log_setup(log_enabled, log_file):
    def _log(msg):
        if not log_enabled:
            return
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
        print(line, flush=True)
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass
    return _log

def load_refresh_token(fallback):
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("refresh_token") or fallback
    return fallback

def save_refresh_token(new_token):
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump({"refresh_token": new_token}, f)

# ---------- myUplink ----------

class TokenCache:
    def __init__(self):
        self.access_token = None
        self.expiry_epoch = 0

def get_access_token(cfg, log, cache: TokenCache):
    now = time.time()
    if cache.access_token and now < cache.expiry_epoch:
        return cache.access_token

    current_refresh = load_refresh_token(cfg["fallback_refresh"])
    resp = requests.post(TOKEN_URL, data={
        "grant_type": "refresh_token",
        "refresh_token": current_refresh,
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"]
    }, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    cache.access_token = data["access_token"]
    cache.expiry_epoch = now + data.get("expires_in", 3600) - 60

    if "refresh_token" in data and data["refresh_token"]:
        save_refresh_token(data["refresh_token"])

    log("Access token refreshed")
    return cache.access_token

def get_points(cfg, log, cache: TokenCache):
    token = get_access_token(cfg, log, cache)
    url = f"{API_BASE}/devices/{cfg['device_id']}/points"
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=20)
    resp.raise_for_status()
    return resp.json()  # list of dicts

# ---------- Loxone ----------

def push_to_loxone(cfg, log, io_name, value, dry_run=False):
    # Loxone endpoint: /dev/sps/io/<name>/<value>
    if dry_run:
        log(f"[dry-run] Would send {io_name} = {value}")
        return
    user = cfg["lox_user"]
    pwd  = cfg["lox_pass"]
    auth_prefix = f"{user}:{pwd}@" if (user and pwd) else ""
    url = f"http://{auth_prefix}{cfg['lox_ip']}/dev/sps/io/{io_name}/{value}"
    try:
        requests.get(url, timeout=5)
        log(f"Sent {io_name} = {value} → Loxone")
    except Exception as e:
        log(f"Error sending {io_name}: {e}")

# ---------- CLI režimy ----------

def print_params(cfg, log, cache: TokenCache):
    pts = get_points(cfg, log, cache)
    # hezky zarovnaný výpis
    maxn = max((len(p.get("parameterName","")) for p in pts), default=0)
    print("\nDostupné parametry (parameterName | parameterId | unit):\n")
    for p in pts:
        name = p.get("parameterName","")
        pid  = p.get("parameterId","")
        unit = p.get("parameterUnit","")
        print(f"{name.ljust(maxn)}  | {str(pid).rjust(6)} | {unit}")
    print("\nPožadované názvy přidej do points_map.json (vlevo je Nibe jméno, vpravo název VI v Loxone).")

def generate_xml_from_map(cfg, log):
    """
    Vytvoří jednoduchou šablonu VirtualInHttp pro hromadný import VI do Loxone
    (VI názvy musí odpovídat těm, které skript používá při push).
    """
    points_map = load_points_map()
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<VirtualInHttp Title="Nibe Tepelné čerpadlo" Comment="" Address="http://dummy/" PollingTime="60">'
    ]
    for nibe_name, lox_name in points_map.items():
        # pro push varianta stačí Check="\v" (hodnota se do VI tlačí přímo)
        lines.append(f'  <VirtualInHttpCmd Title="{lox_name}" Comment="" Check="\\v" Signed="true" Analog="true" '
                     f'SourceValLow="0" DestValLow="0" SourceValHigh="100" DestValHigh="100" DefVal="0" MinVal="-10000" MaxVal="10000"/>')
    lines.append('</VirtualInHttp>')
    out = os.path.join(BASE_DIR, "nibe_inputs.xml")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    log(f"Vytvořeno: {out}")

def run_once(cfg, log, cache: TokenCache, dry_run=False):
    points_map = load_points_map()
    pts = get_points(cfg, log, cache)
    # vytvoříme slovník name->value
    values = {p.get("parameterName"): p.get("value") for p in pts if "parameterName" in p}
    # projdeme mapu a posíláme jen definované položky
    for nibe_name, lox_name in points_map.items():
        if nibe_name in values and isinstance(values[nibe_name], (int, float)):
            push_to_loxone(cfg, log, lox_name, values[nibe_name], dry_run=dry_run)

def loop(cfg, log, cache: TokenCache, dry_run=False):
    log("Skript spuštěn (loop).")
    interval = max(5, int(cfg["update_interval"]))
    while True:
        try:
            run_once(cfg, log, cache, dry_run=dry_run)
        except Exception as e:
            log(f"Error in loop: {e}")
        time.sleep(interval)

# ---------- main ----------

def main():
    parser = argparse.ArgumentParser(description="Nibe → Loxone bridge (myUplink v2)")
    parser.add_argument("--print-params", action="store_true", help="vypíše všechny dostupné parametry z Nibe")
    parser.add_argument("--generate-xml", action="store_true", help="vygeneruje nibe_inputs.xml podle points_map.json")
    parser.add_argument("--once", action="store_true", help="provede jeden cyklus (bez nekonečné smyčky)")
    parser.add_argument("--dry-run", action="store_true", help="neposílat do Loxone, jen logovat co by se poslalo")
    args = parser.parse_args()

    cfg = load_config()
    log = log_setup(cfg["log_enabled"], cfg["log_file"])
    cache = TokenCache()

    if args.print_params:
        print_params(cfg, log, cache)
        return

    if args.generate-xml:
        generate_xml_from_map(cfg, log)
        return

    if args.once:
        run_once(cfg, log, cache, dry_run=args.dry_run)
        return

    loop(cfg, log, cache, dry_run=args.dry_run)

if __name__ == "__main__":
    main()
