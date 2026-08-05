#!/usr/bin/env python3
"""Signal-Bot Bridge: eingehende Signal-Nachrichten -> Freigabe-Popup -> Antwort.

Ablauf:
  1. Pollt signal-cli receive (WSL2) in einer Schleife
  2. Filtert: nur echte Chat-Nachrichten (dataMessage) von Whitelist-Absendern
  3. Oeffnet das Freigabe-Popup (signal_popup.run_popup) mit Absender + Text
  4. Bei 'gesendet': sendet die Antwort via signal-cli send zurueck

Konfiguration: signal_bot_config.json (whitelist, poll_interval_seconds)
Start:        python signal_bridge.py
"""
import json
import os
import re
import subprocess
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "signal_bot_config.json")

WSL_BIN = "wsl.exe"
SIGNAL_CLI = "$HOME/.local/bin/signal-cli"

with open(CONFIG_FILE, encoding="utf-8") as f:
    CONFIG = json.load(f)

WHITELIST = set(CONFIG.get("whitelist", []))
POLL_INTERVAL = CONFIG.get("poll_interval_seconds", 5)
OWN_NUMBER = CONFIG.get("own_number", "")


def load_whitelist():
    """Liest die Whitelist frisch aus der Config (wird pro Poll aufgerufen)."""
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cfg = json.load(f)
        return set(cfg.get("whitelist", []))
    except (OSError, ValueError):
        return set(WHITELIST)  # Fallback auf den Startwert


def wsl_run(args, timeout=60):
    """Fuehrt ein signal-cli-Kommando in WSL2 aus, liefert (returncode, stdout).
    Mit CREATE_NO_WINDOW, damit kein schwarzes Konsolenfenster aufpoppt."""
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    cmd = [WSL_BIN, "-e", "bash", "-lc",
           f"export PATH=$HOME/.local/bin:$PATH && {SIGNAL_CLI} {args}"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout,
                           creationflags=creationflags)
        return r.returncode, r.stdout
    except subprocess.TimeoutExpired:
        return 124, ""


def receive_messages():
    """Holt alle neuen Nachrichten als Liste von JSON-Objekten."""
    rc, out = wsl_run("-o json receive", timeout=90)
    messages = []
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            messages.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return messages


def extract_chat(msg):
    """Extrahiert (sender, text) aus einem Envelope - nur echte Chat-Nachrichten."""
    env = msg.get("envelope") or {}
    # Nur echte Nachrichten (kein Kontakte-Sync, keine Block-Sync etc.)
    if not env.get("dataMessage"):
        return None
    # Eigene Nachrichten (andere Geraete) ignorieren
    sender = env.get("sourceNumber") or env.get("source") or ""
    if not sender or sender == OWN_NUMBER:
        return None
    text = (env.get("dataMessage") or {}).get("message") or ""
    if not text.strip():
        return None
    return sender, text.strip()


def send_message(number, text):
    """Sendet eine Nachricht zurueck via signal-cli (Text ueber stdin, quoting-sicher)."""
    print(f"  -> Sende an {number}: {text[:60]}...")
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    cmd = [WSL_BIN, "-e", "bash", "-lc",
           f"export PATH=$HOME/.local/bin:$PATH && {SIGNAL_CLI} send --message-from-stdin {number}"]
    try:
        r = subprocess.run(cmd, input=text + "\n", capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60,
                           creationflags=creationflags)
        if r.returncode == 0:
            print("  -> Gesendet OK")
        else:
            print(f"  -> SEND-FEHLER (rc={r.returncode}): {r.stdout[-300:]}")
    except subprocess.TimeoutExpired:
        print("  -> SEND-FEHLER: Timeout")


def main():
    print("=" * 60)
    print("Signal-Bot Bridge gestartet")
    print(f"  Whitelist: {sorted(WHITELIST)}")
    print(f"  Poll-Intervall: {POLL_INTERVAL}s")
    print("  Warte auf eingehende Signal-Nachrichten ... (Strg+C zum Beenden)")
    print("=" * 60)

    while True:
        try:
            # Whitelist bei jedem Durchlauf neu laden (Panel-Aenderungen greifen sofort)
            whitelist = load_whitelist()
            messages = receive_messages()
            for msg in messages:
                parsed = extract_chat(msg)
                if not parsed:
                    continue
                sender, text = parsed
                print(f"\n[NEUE NACHRICHT] von {sender}: {text[:80]}...")
                if sender not in whitelist:
                    print(f"  ! Absender {sender} ist NICHT in der Whitelist - ignoriert")
                    continue

                # Freigabe-Popup oeffnen (blockiert, bis entschieden)
                from signal_popup import run_popup
                result = run_popup(sender, text)

                if result["entscheidung"] == "gesendet" and result["antwort"]:
                    send_message(sender, result["antwort"])
                else:
                    print("  Antwort verworfen - nichts gesendet")

        except KeyboardInterrupt:
            print("\nBridge beendet.")
            sys.exit(0)
        except Exception as e:  # noqa: BLE001 - Bridge darf nie abstuerzen
            print(f"Fehler in Bridge-Schleife: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
