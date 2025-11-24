# loxone-nibe_myuplink
Integrace tepelného čerpadla **Nibe** přes **myUplink API** do systému **Loxone** (Synology, Python).

---

## 📌 Co projekt dělá
Python skript:

- načítá data z Nibe přes myUplink API,
- mapuje hodnoty podle `points_map.json`,
- odesílá je do Loxone jako Virtual Inputs,
- běží typicky na Synology v adresáři `/volume1/nibe`,
- zapisuje log do souboru.

Dá se použít i na jiném Linuxu / VM, nejen na Synology.

---

## 🧱 Požadavky

- Tepelné čerpadlo **Nibe** připojené k myUplink
- Účet na **https://dev.myuplink.com**
- **Loxone Miniserver**
- **Synology NAS** (DSM 7.x) nebo jiný Linux
- **Python 3.8+** (na Synology instalován přes Centrum balíčků)
- Skripty z tohoto repozitáře:
  - `nibe.py`
  - `config.ini`
  - `points_map.json`

Doporučená struktura na Synology:

    /volume1/nibe/
      nibe.py
      config.ini
      points_map.json
      nibe.log

---

## 🐍 Instalace Pythonu na Synology

Než cokoli spustíte, nainstalujte **Python** z *Centra balíčků*.

**Postup:**
DSM → Centrum balíčků → Hledat: Python → Nainstalovat Python 3.9

### Ověření instalace
```bash
which python3
python3 --version
```

### Správný výstup
```bash
/bin/python3
Python 3.9.13
```

> Pokud se zobrazí pouze:
> ```bash
> /bin/python3
> ```
> jde o vestavěný systémový Python **bez podpory pip**, a skript nebude fungovat.


---

## 🔑 Připojení na Synology přes SSH

Než budete pokračovat v instalaci a konfiguraci, je potřeba přihlásit se na NAS přes SSH.

### Aktivace SSH v DSM
1. Otevřete **Ovládací panel**
2. Přejděte na **Terminál & SNMP**
3. Zaškrtněte volbu **Povolit službu SSH**
4. **Port ponechte 22**
5. Klikněte **Použít**

### Připojení z Windows (PuTTY)
- Stáhněte PuTTY: https://www.putty.org
- **Host Name:** IP_vašeho_NAS
- **Port:** 22
- **Connection type:** SSH
- Přihlaste se uživatelem s oprávněním **sudo** nebo **admin**

### Připojení z macOS / Linux
```bash
ssh admin@192.168.x.x
```

### Přepnutí do root režimu
```bash
sudo -i
```

### Ověření
```bash
whoami
```

### Správný výstup
```bash
root
```


> **Doporučení:** Pro vyšší bezpečnost je možné po dokončení konfigurace SSH opět vypnout:  
> **Ovládací panel → Terminál & SNMP → vypnout SSH**


---

## 🔐 Získání OAuth `refresh_token` (myUplink)

### 1️⃣ Vytvoření aplikace na developer portálu

Přejděte na:

- https://dev.myuplink.com

Vytvořte novou aplikaci a vyplňte:

- Name: `loxone`
- Callback URL: `http://localhost/`

> ⚠ Callback URL **musí přesně odpovídat** parametru `redirect_uri`, který použijeme níže  
> (včetně `http` vs. `https` a koncového `/`).

---

### 2️⃣ Získání kódu (`code`)

V prohlížeči otevřete (CLIENT_ID nahraďte vlastním):

    https://api.myuplink.com/oauth/authorize?response_type=code&client_id=CLIENT_ID&redirect_uri=http%3A%2F%2Flocalhost%2F&scope=READSYSTEM%20offline_access&state=xyz

Po přihlášení a potvrzení práv budete přesměrováni na URL:

    http://localhost/?code=XXXXXXXXXXXX&scope=READSYSTEM offline_access&state=xyz

Zkopírujte hodnotu `code=XXXXXXXXXXXX`.

> ⚠ Kód `code` je:
> - platný **jen krátkou dobu** (cca 1–2 minuty),
> - použitelný **jen jednou**.  
> Pokud použijete stejný `code` vícekrát, dostanete chybu `invalid_grant`.

---

### 3️⃣ Získání `refresh_token` přes curl

Na NASu (v SSH) spusťte:

    curl -X POST "https://api.myuplink.com/oauth/token" \
      -H "Content-Type: application/x-www-form-urlencoded" \
      -d "grant_type=authorization_code&code=CODE&client_id=CLIENT_ID&client_secret=CLIENT_SECRET&redirect_uri=http%3A%2F%2Flocalhost%2F"

Nahradíte:

- `CODE` – hodnotou z `code=...`
- `CLIENT_ID` – ID aplikace
- `CLIENT_SECRET` – secret z developer portálu

Správná odpověď obsahuje mimo jiné:

    "refresh_token": "ZDE_REFRESH_TOKEN",
    "scope": "READSYSTEM offline_access"

Tento `refresh_token` si uložte – budete ho potřebovat do `config.ini`.

---

### ❗ Typická chyba: `invalid_grant`

Pokud místo tokenu vrátí API něco jako:

    {"error":"invalid_grant","error_description":"check authorization server configuration","code":"invalid_grant"}

nejčastější příčiny jsou:

- byl použit **starý nebo už jednou použitý** `code`
- `redirect_uri` v curlu se **liší** od `Callback URL` (např. chybí `/` na konci)
- chybí `offline_access` ve scope při získávání kódu
- změnil se `CLIENT_SECRET`, ale nepoužil se nový

Řešení:

1. Zkontrolujte, že `Callback URL` = `http://localhost/`
2. Ověřte, že v curlu používáte `redirect_uri=http%3A%2F%2Flocalhost%2F`
3. Získejte **nový** `code` (znovu krok 2) a ihned ho použijte v curlu

---







## 🔍 Získání `access_token` a `deviceId` pro myUplink API

Pro správnou funkci skriptu je potřeba znát `deviceId` tepelného čerpadla.  
Nejprve si z `refresh_token` vygenerujeme krátkodobý `access_token` a pak z API vyčteme `deviceId`.

---

### 1️⃣ Získání `access_token` z myUplink API


Na Synology (nebo kdekoliv, kde máte `curl`) spusťte:

```bash
curl -X POST "https://api.myuplink.com/oauth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=authorization_code" \
  -d "code=CODE" \
  -d "redirect_uri=http://localhost/" \
  -d "client_id=CLIENT_ID" \
  -d "client_secret=CLIENT_SECRET"
```

Výsledek bude JSON, např.:

```json
{
  "access_token": " TVŮJ_ACCESS_TOKEN",
  "expires_in": 3600,
  "token_type": "Bearer",
  "refresh_token": "REFRESH_TOKEN_ZDE",
  "scope": "READSYSTEM"
}
```
---

### 2️⃣ Použití `TVŮJ_ACCESS_TOKEN` pro zjištění `deviceId`

```bash
curl -H "Authorization: Bearer TVŮJ_ACCESS_TOKEN" https://api.myuplink.com/v2/systems/me
```

---

### 3️⃣ Ve výsledku najděte `deviceId`
Ukázka anonymizovaného JSON výstupu:

```json
{
  "systems": [{
    "name": "Nibe",
    "devices": [{
      "id": "emmy-r-xxxxxxxx-xxxxxxxxxxxxxxxxxx",
      "connectionState": "Connected"
    }]
  }]
}
```

➡️ Hodnotu v `id` vložte do `config.ini`:

```ini
DEVICE_ID = emmy-r-xxxxxxxx-xxxxxxxxxxxxxxxxxx
```

---


💡 **Poznámka:**  
- `TVŮJ_ACCESS_TOKEN` = krátkodobý token používaný pro volání API (platí minuty až hodinu)  
- `refresh_token` je dlouhodobější a skript z něj token obnovuje automaticky



## ⚙ Konfigurace `config.ini`

V adresáři `/volume1/nibe` vytvořte nebo otevřete soubor `config.ini`, například takto:

```ini
[myuplink]
CLIENT_ID = 00000000-0000-0000-0000-000000000000
CLIENT_SECRET = your_client_secret_here
# Fallback refresh token jen pro 1. spuštění (pak se přepíše do token.json):
REFRESH_TOKEN = paste_initial_refresh_token_here
DEVICE_ID = emmy-r-xxxxxxxx-xxxxxxxxxxxxxxxxxx

# údaje o loxone
[loxone]
IP = ip-adresa-miniserveru-zde
USER = admin
PASS = ********

[runtime]
# obnova dat default 60 sekund
UPDATE_INTERVAL = 60
# logování - zapnuto=true, vypnuto=false
LOG_ENABLED = true
# můj log file například /volume1/nibe/nibe.log
LOG_FILE = cesta_k_logu
```



Poznámky:

- `LOG_FILE` můžete změnit na jinou cestu, pokud nechcete logovat do `/volume1/nibe`.

---

## 🧪 Test skriptu (ruční spuštění)

V SSH:

    cd /volume1/nibe
    python3 nibe.py --once --dry-run

Pokud je vše správně, uvidíte podobný výstup:

    [2025-11-23 16:07:31] Access token refreshed
    [2025-11-23 16:07:32] [dry-run] Would send Nibe_OutdoorTemp = -2.5
    [2025-11-23 16:07:32] [dry-run] Would send Nibe_SupplyTemp = 25.6
    ...

Pokud odstraníte `--dry-run`, budou hodnoty odesílány do Loxone.

---

## 🔌 Loxone – vytvoření proměnných (Virtual Inputs) - Není nutné měnit, ale v pravé části si můžete upravit názvy proměnných nebo přidat další, pokud se nové objeví

Skript používá mapování v `points_map.json`, např.:

    {
      "Outdoor temperature": "Nibe_OutdoorTemp",
      "Average outdoor temp (BT1)": "Nibe_OutdoorTempAvg",
      "Supply line (BT2)": "Nibe_SupplyTemp",
      "Return line (BT3)": "Nibe_ReturnTemp",
      "Hot water top (BT7)": "Nibe_HotWaterTop",
      "Flow sensor (BF1)": "Nibe_Flow",
      "Heating medium pump speed (GP1)": "Nibe_PumpSpeed",
      "number of starts:": "Nibe_CompressorStarts",
      "total operating time:": "Nibe_CompressorHours",
      "Heating, com­pressor only": "Nibe_EnergyHeatingComp",
      "Hot water, com­pressor only": "Nibe_EnergyHWComp",
      "Heating, includ­ing int. add. heat": "Nibe_EnergyHeatingTot",
      "Hot water, includ­ing int. add. heat": "Nibe_EnergyHWTot"
    }

Na straně Loxone je potřeba vytvořit odpovídající Virtual Inputs.  
Doporučený postup:

1. V Loxone Config otevřete svůj projekt
2. V levém stromu najděte **Virtuální vstupy**
3. Přidejte nové HTTP vstupy s názvy shodnými s pravou stranou (`Nibe_OutdoorTemp`, `Nibe_Flow`, …)
4. Alternativně využijte generování XML, pokud máte v projektu podporu pro import (zatím není součástí tohoto repozitáře).

---

## 🔁 Automatický start na Synology (Plánovač úloh)

V DSM:

- Ovládací panel → Plánovač úloh → Vytvořit → Naplánovaná úloha → Skript uživatele `root`
- V záložce **Nastavení úloh** vložte např.:
```bash
  sleep 60 && cd /volume1/nibe && nohup /bin/python3 nibe.py >> /volume1/nibe/nibe.log 2>&1 &
```
Poznámky:

- `sleep 60` dá systému čas po restartu (síť, DNS…)
- `nohup` zajistí běh i po odhlášení
- Pokud máte Python jinde (např. `/usr/local/bin/python3`), upravte cestu

---

## 🛠 Troubleshooting – shrnutí

**1) Chyba `invalid_client`**

- Zkontrolujte, že v `config.ini` nejsou u `CLIENT_ID` a `CLIENT_SECRET` navíc mezery nebo chybný znak
- Ověřte, že Callback URL v dev.myuplink je `http://localhost/`
- Ověřte, že `redirect_uri` v URL i curlu odpovídá `http://localhost/` (zakódovaně)

**2) Chyba `invalid_grant` při získávání tokenu**

- Použili jste `code` více než jednou
- `code` expiroval – získejte nový (znovu krok 2)
- Špatná hodnota `redirect_uri`

**3) `requests` modul – chyba typu „module 'requests' has no attribute 'post'“**

- Nainstalujte requests pro použitý Python:

    python3 -m pip install requests

**4) Hodnoty se v Loxone neukazují**

- Zkontrolujte:
  - že skript neběží v `--dry-run` režimu
  - že názvy proměnných v Loxone odpovídají pravé straně v `points_map.json`
  - že Loxone nemá blokované HTTP API (Firewall / Režim uživatelů)

---

## 📄 Licence a přispění

Projekt je určen pro komunitu.  
Pokud chcete přispět:

- můžete poslat Pull Request s rozšířeným `points_map.json`
- nebo vylepšit README, přidat zkušenosti z konkrétních instalací

Licence:  
Pokud není uvedeno jinak, používá se standardní otevřená licence (MIT / BSD-like – dle dohody autora).

---
