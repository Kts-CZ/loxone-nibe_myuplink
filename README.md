# loxone-nibe_myuplink
Integrace tepelného čerpadla **Nibe** přes **myUplink API** do systému **Loxone** (Synology, Python).

---

## 📌 Co projekt dělá
Python skript:

- načítá data z Nibe přes myUplink API (v2),
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

V DSM:

- Centrum balíčků → Vše → Python → Instalovat

Ověření verze v SSH:

    python3 --version

---

## 🖥 Připojení k Synology přes SSH

V DSM:

- Ovládací panel → Terminál & SNMP → Povolit SSH

Připojení z PC (Windows / Linux / macOS):

    ssh UZIVATEL@IP_NAS

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
      -d "grant_type=authorization_code&code=SEM_CODE&client_id=CLIENT_ID&client_secret=CLIENT_SECRET&redirect_uri=http%3A%2F%2Flocalhost%2F"

Nahradíte:

- `SEM_CODE` – hodnotou z `code=...`
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

## ⚙ Konfigurace `config.ini`

V adresáři `/volume1/nibe` vytvořte/otevřete soubor `config.ini` např.:

    [myuplink]
    CLIENT_ID = CLIENT_ID_Z_PORTALU
    CLIENT_SECRET = CLIENT_SECRET_Z_PORTALU
    REFRESH_TOKEN = REFRESH_TOKEN_Z_CURL
    DEVICE_ID = emmy-r-xxxxxxxxxxxxxxxxxxxxxxxxxx

    [loxone]
    IP = 192.168.2.5
    USER = admin
    PASS = "heslo"

    [runtime]
    UPDATE_INTERVAL = 60
    LOG_ENABLED = true
    LOG_FILE = /volume1/nibe/nibe.log

Poznámky:

- `DEVICE_ID` najdete v API nebo v aplikaci myUplink (ID vašeho zařízení).
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

## 🔌 Loxone – vytvoření proměnných (Virtual Inputs)

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

    sleep 60 && cd /volume1/nibe && nohup /bin/python3 nibe.py >> /volume1/nibe/nibe.log 2>&1 &

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
