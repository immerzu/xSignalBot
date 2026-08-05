#!/usr/bin/env python3
"""Chatverlauf pro Kontakt (lokal, JSON) fuer den Signal-Bot.

Speichert die letzten MAX_PER_CONTACT Nachrichten je Kontakt in
chat_history.json. Wird von signal_bot_control.py (Panel) und
signal_popup.py (Popup) gemeinsam genutzt, damit beide dasselbe
Gedaechtnis verwenden.
"""
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(BASE_DIR, "chat_history.json")
MAX_PER_CONTACT = 100


def load_history():
    """Liest die gesamte Historie {nummer: [{"role", "content"}, ...]}."""
    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_history(history):
    """Schreibt die Historie atomar (tmp + rename) zurueck."""
    tmp = HISTORY_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
    os.replace(tmp, HISTORY_FILE)


def get_messages(number, limit=MAX_PER_CONTACT):
    """Letzte max. `limit` Nachrichten fuer einen Kontakt (chronologisch)."""
    conv = load_history().get(number, [])
    return conv[-limit:]


def append_message(number, role, content):
    """Haengt eine Nachricht an (role: 'user' = Kontakt, 'assistant' = Bot)."""
    content = content.strip()
    if not content:
        return
    history = load_history()
    conv = history.get(number, [])
    conv.append({"role": role, "content": content})
    # Nur die letzten MAX_PER_CONTACT behalten
    history[number] = conv[-MAX_PER_CONTACT:]
    save_history(history)


def clear_history(number=None):
    """Loescht die Historie eines Kontakts (oder aller, wenn number=None)."""
    history = load_history()
    if number is None:
        history = {}
    else:
        history.pop(number, None)
    save_history(history)
