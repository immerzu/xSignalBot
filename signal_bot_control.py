#!/usr/bin/env python3
"""Signal-Bot — ALL-IN-ONE (ein Fenster, ein Prozess).

Empfaengt eingehende Signal-Nachrichten, zeigt die Freigabe direkt im
Hauptfenster an (kein separates Popup mehr), generiert Antworten lokal
via Ollama und sendet nach Freigabe zurueck.

Layout (oben nach unten):
  1. Status-Zeile (Empfang an/aus) + Test-Button
  2. Freigabe-Bereich  (eingeblendet, wenn eine Nachricht eintrifft)
  3. Whitelist-Verwaltung
  4. Log der letzten Freigaben
  5. Tray: Minimieren -> System-Tray; bei Nachricht poppt das Fenster auf

Start:  python signal_bot_control.py   (Desktop-Verknuepfung vorhanden)
"""
import datetime as _dt
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request

# --- DPI-Awareness -----------------------------------------------------------
if os.name == "nt":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:  # noqa: BLE001
            pass

import tkinter as tk  # noqa: E402
from tkinter import scrolledtext, ttk  # noqa: E402

import chat_history  # noqa: E402
import signal_daemon  # noqa: E402

import pystray  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "signal_bot_config.json")
LOG_FILE = os.path.join(BASE_DIR, "logs", "approval.log")
STATE_FILE = os.path.join(BASE_DIR, "control_state.json")

WSL_BIN = "wsl.exe"
SIGNAL_CLI = "$HOME/.local/bin/signal-cli"

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL = os.environ.get("SIGNAL_BOT_MODEL", "qwen2.5:14b")

SYSTEM_PROMPT = (
    "Du bist der Nutzer dieses Geraets und antwortest in seinem Namen "
    "auf eingehende Nachrichten. Sprich IMMER in der ersten Person "
    "(ich/mir/mein) — formuliere die Antwort genau so, wie der Nutzer "
    "selbst sie tippen wuerde, nicht als Assistent oder aus der "
    "Aussenperspektive. Antworte IMMER auf Deutsch, praezise und "
    "natuerlich. Antworte nur mit der eigentlichen Antwort, ohne "
    "Einleitung wie 'Hier ist meine Antwort'. Halte die Antwort kurz "
    "und freundlich (max. 2-3 Saetze, es sei denn, die Frage verlangt mehr)."
)

STIMMUNGEN = {
    "Standard": "",
    "Traurig": "Verfasse die Antwort in einem traurigen, wehmuetigen Ton. Druecke Bedauern oder Niedergeschlagenheit dezent aus, bleibe aber hoeflich und natuerlich.",
    "Froehlich": "Verfasse die Antwort in einem froehlichen, begeisterten Ton. Zeige Freude und positive Energie, bleibe aber natuerlich und nicht uebertrieben.",
    "Zurueckhaltend": "Verfasse die Antwort in einem zurueckhaltenden, ruhigen und sachlichen Ton. Halte dich kurz, bleibe hoeflich und ohne emotionale Ausschweifungen.",
    "Lustig": "Verfasse die Antwort mit einem humorvollen, lustigen Unterton. Baue einen passenden Scherz oder eine lockere Bemerkung ein, bleibe aber freundlich und nicht verletzend. Setze dazu passende Smileys/Emojis ein (z. B. 😄 😂 😉 🙂 🥳 😜 😆 🙃), auch am Anfang oder Ende der Antwort. Nutze dabei ruhig eine abwechslungsreiche Auswahl aus dem gesamten Emoji-Spektrum (Gesichter, Gesten, Symbole), nicht nur immer dieselben.",
    "Witzig": "Verfasse die Antwort UEBERSCHWAENGLICH LANG und richtig witzig. Die eingehende Nachricht ist haeufig nur kurz (z. B. 'ok', 'hey', 'ja' oder ein einzelnes Wort) — antworte trotzdem (oder gerade deshalb) mit einer ausufernden, komisch uebertriebenen Antwort: dramatische Vergleiche, absurde Szenarien, ulkige Details und Uebertreibungen erwuenscht. Diese Anweisung setzt die Laengen-Begrenzung des Basis-Prompts AUSSER KRAFT: Antworte bewusst lang (mindestens 5-8 Saetze), auch wenn die Nachricht nur ein Wort ist. Setze dabei grosszuegig passende Smileys/Emojis ein (z. B. 🤣 😂 😜 🙃 🤪 😝 🫠 💀 😭🔥), am Anfang, am Ende und zwischen den Saetzen. Nutze eine abwechslungsreiche Mischung aus dem gesamten Emoji-Spektrum — Gesichter, Gesten, Symbole, Tiere, Essen, Gegenstaende — je nachdem, was zum Witz passt, und nicht nur immer dieselben. Bleibe dabei freundlich und nicht verletzend.",
    "Finanzberater": "Verfasse die Antwort wie ein serioes auftretender Finanzberater, der aber totalen, absurden Quatsch ueber Boerse, Aktien, Kurswechsel, Bitcoin, ETFs und Finanzkrisen erzaehlt. Benutze Fachbegriffe und Berater-Sprech (z. B. 'Portfolio-Diversifikation', 'Marktvolatilitaet', 'Sonderkonditionen', 'Hebelwirkung', 'Abwaertstrend', 'Liquiditaet'), aber fachlich voellig sinnlos und wunderbar uebertrieben. ERFINDE konkreten absurden Quatsch: wilde Bitcoin-Kursprognosen (z. B. 'Bitcoin wird naechste Woche auf 2,5 Millionen steigen, weil ein Hamster in Singapur ihn kauft'), dramatische Marktanalysen, seltsame Indikatoren, fiktive Boersengaenge und komische Anlagetipps. Beziehe dich IMMER auf die eingehende Nachricht und verpacke sie in deinen Finanz-Quatsch. Antworte ausfuehrlich (3-5 Saetze). Setze dabei passende Finanz-Emojis ein (z. B. 📈 💰 📉 🚀 😉 🤑 💸 🏦 📊 🪙) und nutze abwechslungsreich das ganze Spektrum, das zum Thema passt. Bleibe freundlich, locker und mit einem zwinkernden Unterton.",
}
TON_LABELS = {
    "Standard": "Standard",
    "Traurig": "\U0001f622 Traurig",
    "Froehlich": "\U0001f604 Froehlich",
    "Zurueckhaltend": "\U0001f910 Zurueckhaltend",
    "Lustig": "\U0001f602 Lustig",
    "Witzig": "\U0001f923 Witzig (lang)",
    "Finanzberater": "\U0001f4c8 Finanzberater",
}
LABEL_TO_STIMMUNG = {v: k for k, v in TON_LABELS.items()}

# Auto-Senden: Nachricht nach fester Wartezeit automatisch senden (Checkbox im Panel)
AUTO_SEND_SECONDS = 3

# Antwort-Sperre: so viele ms Ruhe abwarten, bevor eine Nachrichten-Salve
# beantwortet wird (verhindert Robotik bei 'Hallo? Bist du da? ?')
BOUNCE_MS = 2500


# --- Config-Hilfen -----------------------------------------------------------
def load_config():
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


OWN_NUMBER = load_config().get("own_number", "")
POLL_INTERVAL = load_config().get("poll_interval_seconds", 5)


def load_whitelist():
    return set(load_config().get("whitelist", []))


def load_manual_names():
    return dict(load_config().get("contact_names", {}))


def update_config_whitelist(whitelist):
    try:
        cfg = load_config()
        cfg["whitelist"] = sorted(whitelist)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except (OSError, ValueError):
        pass


def update_config_contact_name(number, name):
    try:
        cfg = load_config()
        names = dict(cfg.get("contact_names", {}))
        name = name.strip()
        if name:
            names[number] = name
        else:
            names.pop(number, None)
        cfg["contact_names"] = names
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except (OSError, ValueError):
        pass


def load_window_size():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f).get("window_size")
    except (OSError, ValueError):
        return None


def is_valid_geometry(geo):
    """Prueft, ob eine Geometry 'WxH+X+Y' plausibel ist (Fenster auf dem Bildschirm).

    Verwirft kaputte Werte (z. B. -32000 von minimierten Fenstern) und
    Positionen, die komplett ausserhalb des Bildschirms liegen.
    """
    if not geo or "+" not in geo:
        return False
    try:
        size_part, pos_part = geo.split("+", 1)
        w, h = size_part.split("x")
        w, h = int(w), int(h)
        # Position kann negativ sein: "+-32000+-32000" -> x=-32000, y=-32000
        if pos_part.startswith("-"):
            rest = pos_part[1:]
            if "+-" not in rest:
                return False
            xs = rest.split("+-", 1)
            x, y = -int(xs[0]), -int(xs[1])
        else:
            xs = pos_part.split("+")
            if len(xs) != 2:
                return False
            x, y = int(xs[0]), int(xs[1])
    except (ValueError, IndexError):
        return False
    if w <= 0 or h <= 0 or x <= -32000 or y <= -32000:
        return False
    # Grob pruefen: Fenster muss den Bildschirm (mindestens teilweise) treffen
    if x > 10000 or y > 10000:
        return False
    return True


def save_window_size(geometry):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"window_size": geometry}, f)
    except OSError:
        pass


def tail_file(path, n=8, max_line_len=100):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        out = []
        for line in lines[-n:]:
            line = line.rstrip()
            out.append(line[:max_line_len] if len(line) > max_line_len else line)
        return "\n".join(out) if out else "(noch keine Eintraege)"
    except OSError:
        return "(Log noch nicht vorhanden)"


# --- signal-cli (WSL) --------------------------------------------------------
def wsl_run(args, timeout=60):
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


def load_contacts():
    """Signal-Kontaktliste als Liste 'Nummer | Name'."""
    rc, out = wsl_run("-o json listContacts", timeout=60)
    if rc != 0:
        return []
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return []
    contacts = data if isinstance(data, list) else data.get("contacts", [])
    result = []
    for c in contacts:
        num = c.get("number") or ""
        name = c.get("name") or c.get("profileName") or ""
        if num and num != OWN_NUMBER:
            result.append(f"{num} | {name}" if name else num)
    return sorted(result)


def receive_messages():
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
    env = msg.get("envelope") or {}
    if not env.get("dataMessage"):
        return None
    sender = env.get("sourceNumber") or env.get("source") or ""
    if not sender or sender == OWN_NUMBER:
        return None
    text = (env.get("dataMessage") or {}).get("message") or ""
    if not text.strip():
        return None
    return sender, text.strip()


def send_message(number, text):
    """Sendet ueber den persistenten Daemon (kein JVM-Neustart, kein Konflikt)."""
    return signal_daemon.daemon_send(number, text)


def send_typing(number, stop=False):
    """Sendet den Tipp-Indikator ueber den Daemon. Feuer-und-vergiss."""
    signal_daemon.daemon_send_typing(number, stop=stop)


def health_check():
    """Prueft Ollama + Daemon und liefert {ollama: bool, signal: bool}."""
    result = {"ollama": False, "signal": False}
    try:
        with urllib.request.urlopen(OLLAMA_URL.replace("/api/chat", "/api/tags"),
                                    timeout=5) as resp:
            result["ollama"] = resp.status == 200
    except Exception:  # noqa: BLE001
        pass
    result["signal"] = signal_daemon.daemon_running()
    return result


def generate_antwort(nachricht, stimmung="Standard", history=None, sender_name=""):
    """Ruft Ollama auf und liefert die generierte Antwort (Blocking!).

    history: optionale Liste vorheriger Nachrichten [{"role", "content"}, ...]
    (chronologisch, OHNE die aktuelle Nachricht).
    sender_name: Anzeigename des Absenders (wird in den Prompt eingebaut).
    """
    ton_zusatz = STIMMUNGEN.get(stimmung, "")
    system = SYSTEM_PROMPT
    if ton_zusatz:
        system = system + "\n" + ton_zusatz
    system = system + (
        "\nAchtung: Verfasse die Antwort IMMER in der ersten Person "
        "(ich/mir/mein) — in jedem Ton, auch bei humorvollen oder "
        "ueberschwaenglichen Varianten."
    )
    messages = [{"role": "system", "content": system}]
    if history:
        messages.extend(history)
    absender = sender_name.strip() or "Der Kontakt"
    messages.append(
        {"role": "user", "content": f"{absender} schreibt:\n{nachricht}"})
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
    }
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    antwort = (data.get("message") or {}).get("content", "").strip()
    if not antwort:
        raise RuntimeError("Ollama lieferte eine leere Antwort.")
    return antwort


def log_decision(sender, antwort, entscheidung):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(
            f"{_dt.datetime.now().isoformat(timespec='seconds')} | {sender} | "
            f"{entscheidung} | chars={len(antwort)}\n"
        )


def create_tray_image():
    img = Image.new("RGB", (64, 64), color="#2d7dd2")
    d = ImageDraw.Draw(img)
    d.ellipse([6, 6, 58, 58], fill="#1a7a1a", outline="white", width=4)
    d.rectangle([26, 18, 38, 46], fill="white")
    d.rectangle([18, 26, 46, 38], fill="white")
    return img


# --- Einzelinstanz-Schutz (benannte Mutex) ------------------------------------
_MUTEX_HANDLE = None
MUTEX_NAME = "Local\\SignalBotHelfer01"  # Local = nur diese Benutzersitzung


def acquire_single_instance():
    """Sorgt dafuer, dass nur EINE Signal-Bot-Instanz laeuft.

    Nutzt eine benannte Windows-Mutex. Die zweite Instanz erhaelt
    ERROR_ALREADY_EXISTS und beendet sich sofort (kein Doppel-Empfang).
    Liefert True, wenn diese Instanz die Mutex bekommen hat.
    """
    global _MUTEX_HANDLE
    if os.name != "nt":
        return True  # Nicht-Windows: kein Schutz noetig (kein Desktop-Betrieb)
    try:
        import ctypes
        # use_last_error=True ist WICHTIG: ctypes.windll setzt es nicht,
        # sonst liefert get_last_error() immer 0 und die Erkennung versagt
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool,
                                          ctypes.c_wchar_p]
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        # CreateMutexW(NULL, FALSE, NAME) -> HANDLE
        handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        if not handle:
            return True  # Unbekannter Fehler - nicht blockieren
        already_exists = ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS
        if already_exists:
            kernel32.CloseHandle(handle)
            return False
        _MUTEX_HANDLE = handle
        return True
    except Exception:  # noqa: BLE001
        return True  # Schutz ist optional - nie den Start blockieren


def release_single_instance():
    """Gibt die Mutex frei (beim Beenden)."""
    global _MUTEX_HANDLE
    if _MUTEX_HANDLE:
        try:
            import ctypes
            ctypes.windll.kernel32.CloseHandle(_MUTEX_HANDLE)
        except Exception:  # noqa: BLE001
            pass
        _MUTEX_HANDLE = None


# --- Hauptfenster ------------------------------------------------------------
class ControlPanel:
    def __init__(self):
        self.contact_names = {}
        self.polling = False
        self.poll_thread = None
        self.current_sender = None
        self._generating = False
        self.test_mode = False
        self._auto_timer_id = None
        self._auto_remaining = 0
        self._pending = {}          # Kontakt -> [wartende Nachrichten]
        self._bounce_id = None      # Debounce-Timer fuer Nachrichten-Salven
        self.receiver = None        # DaemonReceiver (Notification-Stream)

        self.root = tk.Tk()
        self.root.title("Signal-Bot")
        dpi = max(1.0, self.root.winfo_fpixels("1i") / 96.0)
        self._last_geometry = None  # zuletzt bekannte, gueltige Position/Groesse
        saved = load_window_size()
        if is_valid_geometry(saved):
            # Volle Geometry inkl. Position -> exakt wiederherstellen
            self.root.geometry(saved)
            self._last_geometry = saved
        else:
            # Default (oder alte/kaputte State-Datei): Groesse setzen
            # und Fenster auf dem Bildschirm zentrieren statt kaskadieren
            size = saved if saved and "x" in saved else "808x986"
            self.root.geometry(size)
            self.root.update_idletasks()
            w = self.root.winfo_width()
            h = self.root.winfo_height()
            x = max(0, (self.root.winfo_screenwidth() - w) // 2)
            y = max(0, (self.root.winfo_screenheight() - h) // 2)
            self.root.geometry(f"{size}+{x}+{y}")
        # Bei jeder Groessen-/Positions-Aenderung des sichtbaren Fensters
        # die letzte gueltige Geometry festhalten (robust gegen Minimieren)
        self.root.bind("<Configure>", self._on_configure)
        # KEIN permanentes -topmost: das Fenster soll NICHT immer im
        # Vordergrund bleiben. Kurzes Nach-vorn-Holen nur bei eingehender
        # Nachricht (show_message) oder Tray-Oeffnen (_show_window).
        # Feste Mindestgroesse: vom Nutzer am Bildschirm eingestellt (808x986),
        # darunter verdecken sich die Button-Beschriftungen (physische Pixel)
        self.root.minsize(808, 986)
        self.root.resizable(True, True)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # Tray
        self.tray_icon = pystray.Icon(
            "signal-bot", create_tray_image(), "Signal-Bot",
            menu=pystray.Menu(
                # default=True => wird beim DOPPELKLICK auf das Tray-Icon ausgefuehrt
                pystray.MenuItem("Signal-Bot oeffnen", self._tray_open, default=True),
                pystray.MenuItem("Beenden", self._tray_quit),
            ),
        )
        self.root.bind("<Unmap>", self._on_unmap)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

        # 1) Status-Zeile
        status_row = tk.Frame(self.root)
        status_row.pack(fill="x", padx=10, pady=(8, 2))
        tk.Label(status_row, text="Empfang:", font=("Segoe UI", 10, "bold")).pack(side="left")
        self.status_label = tk.Label(status_row, text="AUS", fg="#c00000",
                                     font=("Segoe UI", 10, "bold"))
        self.status_label.pack(side="left", padx=6)
        self.btn_toggle = tk.Button(status_row, text="▶ Empfang starten", width=18,
                                    command=self.toggle_polling)
        self.btn_toggle.pack(side="left", padx=6)
        self.health_label = tk.Label(status_row, text="", font=("Segoe UI", 9),
                                     fg="#555555")
        self.health_label.pack(side="left", padx=4)
        tk.Button(status_row, text="Test", width=15,
                  command=self.test_message).pack(side="right")
        tk.Button(status_row, text="☑ Tray", width=6,
                  command=self.hide_to_tray).pack(side="right", padx=4)

        # 2) Freigabe-Bereich (im Hauptfenster eingebettet)
        self.msg_frame = tk.LabelFrame(self.root, text=" Eingehende Nachricht ",
                                       font=("Segoe UI", 10, "bold"), padx=8, pady=6)
        self.msg_frame.pack(fill="x", padx=10, pady=6)

        self.msg_from_label = tk.Label(self.msg_frame, text="(warte auf Nachricht)",
                                       font=("Segoe UI", 9, "bold"), anchor="w")
        self.msg_from_label.pack(fill="x")

        self.msg_text = scrolledtext.ScrolledText(self.msg_frame, height=4, wrap="word",
                                                  font=("Segoe UI", 10))
        self.msg_text.pack(fill="x", pady=4)
        self.msg_text.config(state="disabled")

        tk.Label(self.msg_frame, text="Antwort-Vorschlag (editierbar):",
                 font=("Segoe UI", 9)).pack(anchor="w")

        self.answer_text = scrolledtext.ScrolledText(self.msg_frame, height=5, wrap="word",
                                                     font=("Segoe UI", 10))
        self.answer_text.pack(fill="x", pady=4)

        ans_row = tk.Frame(self.msg_frame)
        ans_row.pack(fill="x")
        tk.Label(ans_row, text="Ton:", font=("Segoe UI", 9)).pack(side="left")
        # Zuletzt gewaehlten Tonfall aus der Config laden (persistiert ueber Neustarts)
        last_tone = load_config().get("last_tone", "Standard")
        if last_tone not in TON_LABELS:
            last_tone = "Standard"
        self.stimmung_var = tk.StringVar(value=TON_LABELS[last_tone])
        self.stimmung_combo = ttk.Combobox(ans_row, textvariable=self.stimmung_var,
                                           values=list(TON_LABELS.values()),
                                           state="readonly", width=12)
        self.stimmung_combo.pack(side="left", padx=4)
        self.stimmung_combo.bind("<<ComboboxSelected>>",
                                 lambda e: self._on_tone_selected())
        tk.Button(ans_row, text="Senden", width=12, bg="#2d7dd2", fg="white",
                  command=self.send_answer).pack(side="right", padx=2)
        tk.Button(ans_row, text="Verwerfen", width=12,
                  command=self.discard_message).pack(side="right", padx=2)
        # Button als Attribut, um den Balken exakt darunter zu positionieren
        self.btn_generate = tk.Button(ans_row, text="Neu generieren", width=16,
                                      command=self.regenerate_answer)
        self.btn_generate.pack(side="left", padx=4)

        # Ladeanzeige unter dem Button "Neu generieren": Canvas-Balken, fuellt
        # sich sichtbar von links nach rechts, solange die Antwort generiert
        # wird (ttk.Progressbar ist auf manchen Themes fast unsichtbar -
        # Canvas ist garantiert klar sichtbar).
        prog_row = tk.Frame(self.msg_frame)
        prog_row.pack(fill="x", pady=(2, 0))
        # Unsichtbarer Platzhalter: schiebt den Balken exakt unter den Button
        # (Breite = alles links vom Button: "Ton:" + Combobox + Abstaende).
        # pack_propagate(False) ist WICHTIG: sonst schrumpft ein leerer
        # Frame trotz config(width=...) immer auf Breite 0 zurueck.
        self._prog_spacer = tk.Frame(prog_row)
        self._prog_spacer.pack_propagate(False)
        self._prog_spacer.pack(side="left")
        self.gen_canvas = tk.Canvas(prog_row, width=110, height=16,
                                    bg="#f0f0f0", highlightthickness=1,
                                    highlightbackground="#999999")
        self.gen_canvas.pack(side="left")
        self._prog_val = 0
        self._prog_timer = None

        # Auto-Senden (neue Zeile unter den Buttons)
        auto_row = tk.Frame(self.msg_frame)
        auto_row.pack(fill="x", pady=(2, 0))
        self.auto_send_var = tk.BooleanVar(
            value=bool(load_config().get("auto_send_enabled", False)))
        self.auto_check = tk.Checkbutton(
            auto_row, text=f"Auto-Senden nach {AUTO_SEND_SECONDS} s",
            variable=self.auto_send_var, command=self._on_auto_send_change,
            font=("Segoe UI", 9))
        self.auto_check.pack(side="left")
        self.auto_label = tk.Label(auto_row, text="",
                                   font=("Segoe UI", 9, "bold"), fg="#c00000")
        self.auto_label.pack(side="left", padx=6)

        # 3) Whitelist-Verwaltung
        wl_frame = tk.LabelFrame(self.root, text=" Whitelist (erlaubte Kontakte) ",
                                 font=("Segoe UI", 9), padx=8, pady=4)
        wl_frame.pack(fill="both", expand=True, padx=10, pady=4)

        contact_row = tk.Frame(wl_frame)
        contact_row.pack(fill="x")
        self.contact_var = tk.StringVar()
        self.contact_combo = ttk.Combobox(contact_row, textvariable=self.contact_var,
                                          state="normal", width=32)
        self.contact_combo.pack(side="left")
        tk.Button(contact_row, text="\u27f3", width=3,
                  command=self.refresh_contacts).pack(side="left", padx=4)
        tk.Button(contact_row, text="+ Hinzufügen", width=13,
                  command=self.add_whitelist).pack(side="left", padx=4)

        wl_scroll_frame = tk.Frame(wl_frame)
        wl_scroll_frame.pack(fill="both", expand=True, pady=(4, 0))
        wl_scroll_frame.rowconfigure(0, weight=1)
        wl_scroll_frame.columnconfigure(0, weight=1)
        self.wl_listbox = tk.Text(wl_scroll_frame, height=3, font=("Consolas", 9),
                                  wrap="none", state="disabled", bg="white",
                                  relief="solid", borderwidth=1)
        vbar = tk.Scrollbar(wl_scroll_frame, orient="vertical",
                            command=self.wl_listbox.yview)
        hbar = tk.Scrollbar(wl_scroll_frame, orient="horizontal",
                            command=self.wl_listbox.xview)
        self.wl_listbox.configure(yscrollcommand=vbar.set, xscrollcommand=hbar.set)
        self.wl_listbox.grid(row=0, column=0, sticky="nsew")
        vbar.grid(row=0, column=1, sticky="ns")
        hbar.grid(row=1, column=0, sticky="ew")
        self.wl_listbox.bind("<Control-c>", lambda e: self._copy_selection())
        self.wl_menu = tk.Menu(self.root, tearoff=0)
        self.wl_menu.add_command(label="Kopieren", command=self._copy_selection)
        self.wl_listbox.bind("<Button-3>", self._show_wl_menu)

        wl_list_row = tk.Frame(wl_frame)
        wl_list_row.pack(fill="x")
        tk.Button(wl_list_row, text="\u2212 Entfernen", width=13,
                  command=self.remove_whitelist).pack(side="left", padx=4, pady=2)
        tk.Label(wl_list_row, text="Name:", font=("Segoe UI", 9)).pack(side="left", padx=(10, 2))
        self.name_entry = tk.Entry(wl_list_row, width=14)
        self.name_entry.pack(side="left")
        tk.Button(wl_list_row, text="Name setzen", width=12,
                  command=self.set_contact_name).pack(side="left", padx=4)
        tk.Button(wl_list_row, text="Verlauf l\u00f6schen", width=16,
                  command=self.clear_selected_history).pack(side="left", padx=4)

        # Init
        self.refresh_whitelist_display()
        self.refresh_contacts()
        # Platzhalter auf die Breite der Elemente links vom "Neu generieren"-
        # Button setzen (Ton-Label + Combobox), damit der Fortschrittsbalken
        # exakt unter dem Button sitzt statt am linken Rand. WICHTIG: erst
        # NACH dem Fenster-Mapping messen - im __init__ ist winfo_x() noch 0.
        self.root.after(300, self._align_progress)

    def _align_progress(self):
        """Setzt die Platzhalter-Breite auf die Position des Buttons."""
        try:
            x = self.btn_generate.winfo_x()
            if x > 0:
                self._prog_spacer.config(width=x)
        except Exception:  # noqa: BLE001
            pass

    # --- Empfang (persistenter signal-cli-Daemon) -----------------------------
    def toggle_polling(self):
        if self.polling:
            self.stop_polling()
        else:
            self.start_polling()

    def start_polling(self):
        if self.polling:
            return
        # Sicherheitshalber alten Receiver stoppen (verhindert Doppel-Empfang)
        if getattr(self, "receiver", None):
            try:
                self.receiver.stop()
            except Exception:  # noqa: BLE001
                pass
            self.receiver = None
        self.polling = True
        self.status_label.config(text="AKTIV (starte Daemon ...)", fg="#1a7a1a")
        self.btn_toggle.config(text="\u25a0 Empfang stoppen")
        threading.Thread(target=self._start_daemon_worker, daemon=True).start()
        threading.Thread(target=self._health_worker, daemon=True).start()

    def _start_daemon_worker(self):
        """Startet den Daemon und danach den Notification-Receiver."""
        ok = signal_daemon.start_daemon()
        if not ok:
            self.root.after(0, lambda: self._daemon_start_failed())
            return
        # Waehrend des Daemon-Starts (JVM, bis 25 s) kann der Nutzer gestoppt
        # haben - dann hier NICHT weiter einen Receiver starten
        if not self.polling:
            return
        # Alten Receiver (falls waehrend des Starts doch entstanden) stoppen
        if getattr(self, "receiver", None):
            try:
                self.receiver.stop()
            except Exception:  # noqa: BLE001
                pass
        self.receiver = signal_daemon.DaemonReceiver(
            on_message=self._on_daemon_envelope)
        self.receiver.start()
        self.root.after(0, lambda: self.status_label.config(
            text="AKTIV", fg="#1a7a1a"))

    def _daemon_start_failed(self):
        self.polling = False
        self.status_label.config(text="DAEMON-FEHLER", fg="#c00000")
        self.btn_toggle.config(text="\u25b6 Empfang starten")

    def _on_daemon_envelope(self, env):
        """Callback aus dem DaemonReceiver: Envelope -> Chat-Nachricht."""
        try:
            parsed = extract_chat({"envelope": env})
            if not parsed:
                return
            sender, text = parsed
            if sender not in load_whitelist():
                return
            self.root.after(0, lambda s=sender, t=text: self._queue_message(s, t))
        except Exception as e:  # noqa: BLE001
            print(f"Daemon-Envelope-Fehler: {e}")

    def stop_polling(self):
        self.polling = False
        self._cancel_bounce()
        if getattr(self, "receiver", None):
            try:
                self.receiver.stop()
            except Exception:  # noqa: BLE001
                pass
            self.receiver = None
        # Daemon laeuft weiter (wiederverwendbar) - wird erst beim Beenden gestoppt
        self.status_label.config(text="AUS", fg="#c00000")
        self.btn_toggle.config(text="\u25b6 Empfang starten")

    # --- Nachrichten-Queue + Antwort-Sperre ------------------------------------
    def _queue_message(self, sender, text):
        """Reiht ECHTE eingehende Nachrichten ein (test_mode wird zurueckgesetzt)."""
        self.test_mode = False
        self._pending.setdefault(sender, []).append(text)
        self._cancel_bounce()
        if self.current_sender is None:
            # Erst wenn 2.5 s Ruhe herrschen, wird die aelteste Nachricht angezeigt
            self._bounce_id = self.root.after(
                BOUNCE_MS, lambda s=sender: self._process_next(s))

    def _cancel_bounce(self):
        if getattr(self, "_bounce_id", None):
            try:
                self.root.after_cancel(self._bounce_id)
            except Exception:  # noqa: BLE001
                pass
            self._bounce_id = None

    def _process_next(self, sender=None):
        """Zeigt die aelteste anstehende Nachricht an (eine zur Zeit)."""
        self._cancel_bounce()
        if self.current_sender is not None:
            return
        if sender is None:
            # Kontakt mit der aeltesten Nachricht finden
            for s, queue in self._pending.items():
                if queue:
                    sender = s
                    break
        queue = self._pending.get(sender) or []
        if not queue:
            return
        text = queue.pop(0)
        if not queue:
            self._pending.pop(sender, None)
        self.show_message(sender, text)

    def show_message(self, sender, text, test=False):
        """Zeigt die eingehende Nachricht im Freigabe-Bereich an.

        test=True: Test-Modus - Antwort wird generiert, aber NIE gesendet.
        """
        self._cancel_auto_timer()
        self.current_sender = sender
        self.test_mode = test
        name = load_manual_names().get(sender) or self.contact_names.get(sender, "")
        if test:
            self.msg_from_label.config(
                text=f"TEST-MODUS (Antwort wird NICHT gesendet) - von: {name or sender}")
        else:
            self.msg_from_label.config(text=f"Von: {name or sender}  ({sender})")
        self.msg_text.config(state="normal")
        self.msg_text.delete("1.0", "end")
        self.msg_text.insert("1.0", text)
        self.msg_text.config(state="disabled")
        self.answer_text.delete("1.0", "end")
        self.answer_text.insert("1.0", "Antwort wird generiert ...")
        self._generating = False
        # Fenster in den Vordergrund holen (auch aus dem Tray)
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(400, lambda: self.root.attributes("-topmost", False))
        self.regenerate_answer()

    def _health_worker(self):
        """Gesundheits-Check (Ollama + signal-cli) und Anzeige in Status-Zeile."""
        h = health_check()
        o = "\u2713" if h["ollama"] else "\u2717"
        s = "\u2713" if h["signal"] else "\u2717"
        self.root.after(0, lambda: self._set_health(o, s))

    def _set_health(self, o, s):
        self.health_label.config(text=f"  Ollama {o}  |  signal-cli {s}")

    def regenerate_answer(self):
        if self._generating or not self.current_sender:
            return
        self._cancel_auto_timer()
        self._generating = True
        # Ladeanzeige starten: Balken fuellt sich von links nach rechts
        self._start_progress()
        # Tipp-Indikator zeigen, waehrend die Antwort generiert wird
        threading.Thread(target=send_typing,
                         args=(self.current_sender, False), daemon=True).start()
        nachricht = self.msg_text.get("1.0", "end").strip()
        stimmung = LABEL_TO_STIMMUNG.get(self.stimmung_var.get(), "Standard")
        threading.Thread(target=self._answer_worker,
                         args=(nachricht, stimmung), daemon=True).start()

    def _start_progress(self):
        """Startet den Canvas-Fortschrittsbalken (0 -> 100, dann wiederholt)."""
        self._stop_progress()
        self._prog_val = 0
        self._progress_tick()

    def _progress_tick(self):
        """Ein Tick: Balken ein Stueck weiter fuellen, dann neu planen."""
        self._prog_val += 5
        if self._prog_val > 100:
            self._prog_val = 0
        self.gen_canvas.delete("all")
        # Feste Breite (110) statt winfo_width(): die liefert im Test/bei
        # noch nicht gerenderten Fenstern 0/1 und der Balken waere unsichtbar
        self.gen_canvas.create_rectangle(
            0, 0, int(110 * self._prog_val / 100),
            16, fill="#2d7dd2", outline="")
        self._prog_timer = self.root.after(60, self._progress_tick)

    def _stop_progress(self):
        """Stoppt den Balken und leert ihn."""
        if self._prog_timer is not None:
            try:
                self.root.after_cancel(self._prog_timer)
            except Exception:  # noqa: BLE001
                pass
            self._prog_timer = None
        try:
            self.gen_canvas.delete("all")
        except Exception:  # noqa: BLE001
            pass

    def _answer_worker(self, nachricht, stimmung):
        try:
            # Vorherige Runden dieses Kontakts als Kontext mitschicken
            history = chat_history.get_messages(self.current_sender)
            name = load_manual_names().get(self.current_sender) \
                or self.contact_names.get(self.current_sender, "")
            antwort = generate_antwort(nachricht, stimmung, history=history,
                                       sender_name=name)
            self.root.after(0, lambda: self._set_answer(antwort))
        except Exception as e:  # noqa: BLE001
            self.root.after(0, lambda: self._set_answer(f"[FEHLER bei Ollama: {e}]"))

    def _set_answer(self, text):
        self._stop_progress()
        self.answer_text.delete("1.0", "end")
        self.answer_text.insert("1.0", text)
        self._generating = False
        self._restart_auto_timer()

    def send_answer(self):
        if not self.current_sender:
            return
        self._cancel_auto_timer()
        antwort = self.answer_text.get("1.0", "end").strip()
        if not antwort or antwort.startswith("[FEHLER") or antwort == "Antwort wird generiert ...":
            return
        if self.test_mode:
            # Sicherheit: Test-Nachrichten werden NIE echt versendet
            log_decision(self.current_sender, antwort, "TEST-MODUS (nicht gesendet)")
            self.clear_message_area()
            return
        ok = send_message(self.current_sender, antwort)
        # Tipp-Indikator stoppen (egal ob senden ok war)
        threading.Thread(target=send_typing,
                         args=(self.current_sender, True), daemon=True).start()
        if ok:
            # Gesendete Runde ins Gedaechtnis: eingehende Nachricht + Antwort
            nachricht = self.msg_text.get("1.0", "end").strip()
            chat_history.append_message(self.current_sender, "user", nachricht)
            chat_history.append_message(self.current_sender, "assistant", antwort)
        log_decision(self.current_sender, antwort, "GESENDET" if ok else "SEND-FEHLER")
        self.clear_message_area()

    def discard_message(self):
        self._cancel_auto_timer()
        if self.current_sender:
            log_decision(self.current_sender, self.answer_text.get("1.0", "end").strip(),
                         "VERWORFEN")
        self.clear_message_area()

    def clear_message_area(self):
        self._cancel_auto_timer()
        self._stop_progress()
        self.current_sender = None
        self.test_mode = False
        self.msg_from_label.config(text="(warte auf Nachricht)")
        self.msg_text.config(state="normal")
        self.msg_text.delete("1.0", "end")
        self.msg_text.config(state="disabled")
        self.answer_text.delete("1.0", "end")
        # Naechste wartende Nachricht (anderer Kontakt) anzeigen
        self._process_next()

    def _on_tone_selected(self):
        """Speichert den gewaehlten Tonfall in der Config und generiert neu."""
        key = LABEL_TO_STIMMUNG.get(self.stimmung_var.get(), "Standard")
        cfg = load_config()
        cfg["last_tone"] = key
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
        except (OSError, ValueError):
            pass
        self.regenerate_answer()

    # --- Auto-Senden ------------------------------------------------------------
    def _on_auto_send_change(self):
        """Speichert die Checkbox in der Config und startet/stoppt den Timer."""
        cfg = load_config()
        cfg["auto_send_enabled"] = bool(self.auto_send_var.get())
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
        except (OSError, ValueError):
            pass
        self._restart_auto_timer()

    def _cancel_auto_timer(self):
        if self._auto_timer_id is not None:
            try:
                self.root.after_cancel(self._auto_timer_id)
            except Exception:  # noqa: BLE001
                pass
            self._auto_timer_id = None
        if hasattr(self, "auto_label"):
            self.auto_label.config(text="")

    def _restart_auto_timer(self):
        """Startet den Auto-Senden-Countdown, wenn die Checkbox aktiv ist."""
        self._cancel_auto_timer()
        if not self.current_sender:
            return
        if self.test_mode:
            return  # Test-Modus: NIE automatisch senden
        if not self.auto_send_var.get() or self._generating:
            return
        antwort = self.answer_text.get("1.0", "end").strip()
        if not antwort or antwort.startswith("[FEHLER") or antwort == "Antwort wird generiert ...":
            return
        self._auto_remaining = AUTO_SEND_SECONDS
        self.auto_label.config(
            text=f"\u23f3 Auto-Senden in {AUTO_SEND_SECONDS} s \u2026")
        self._auto_timer_id = self.root.after(1000, self._auto_tick)

    def _auto_tick(self):
        self._auto_timer_id = None
        self._auto_remaining -= 1
        if self._auto_remaining <= 0:
            self.auto_label.config(text="")
            self.send_answer()
            return
        self.auto_label.config(
            text=f"\u23f3 Auto-Senden in {self._auto_remaining} s \u2026")
        self._auto_timer_id = self.root.after(1000, self._auto_tick)

    def test_message(self):
        """Simulierte eingehende Nachricht im TEST-MODUS (wird NIE gesendet).

        Testet mit dem ersten Whitelist-Kontakt (oder Platzhalter-Nummer),
        damit keine echten Telefonnummern im Code stehen.
        """
        whitelist = load_whitelist()
        test_sender = whitelist[0] if whitelist else "+0000000000000"
        self.show_message(
            test_sender,
            "Hallo! Das ist eine Testnachricht fuer das Signal-Bot-Fenster.",
            test=True)

    # --- Whitelist -------------------------------------------------------------
    def refresh_contacts(self):
        def _load():
            contacts = load_contacts()
            names = {}
            for c in contacts:
                parts = c.split("|", 1)
                num = parts[0].strip()
                name = parts[1].strip() if len(parts) > 1 else ""
                names[num] = name
            self.contact_names = names
            self.root.after(0, lambda: self.contact_combo.config(values=contacts))
            self.root.after(0, self.refresh_whitelist_display)
        threading.Thread(target=_load, daemon=True).start()

    def add_whitelist(self):
        entry = self.contact_var.get().strip()
        if not entry:
            return
        num = entry.split("|")[0].strip()
        if not num.startswith("+"):
            return
        wl = load_whitelist()
        wl.add(num)
        update_config_whitelist(wl)
        self.refresh_whitelist_display()
        self.contact_var.set("")

    def remove_whitelist(self):
        try:
            pos = self.wl_listbox.index("sel.first")
        except tk.TclError:
            pos = self.wl_listbox.index("insert")
        line = int(pos.split(".")[0])
        entry = self.wl_listbox.get(f"{line}.0", f"{line}.end")
        num = entry.split()[0].strip()
        wl = load_whitelist()
        wl.discard(num)
        update_config_whitelist(wl)
        self.refresh_whitelist_display()

    def set_contact_name(self):
        try:
            pos = self.wl_listbox.index("sel.first")
        except tk.TclError:
            pos = self.wl_listbox.index("insert")
        line = int(pos.split(".")[0])
        entry = self.wl_listbox.get(f"{line}.0", f"{line}.end")
        if not entry.strip():
            return
        num = entry.split()[0].strip()
        name = self.name_entry.get()
        update_config_contact_name(num, name)
        self.refresh_whitelist_display()
        self.name_entry.delete(0, "end")

    def clear_selected_history(self):
        """Loescht den Chatverlauf des markierten Kontakts aus der Whitelist."""
        try:
            pos = self.wl_listbox.index("sel.first")
        except tk.TclError:
            pos = self.wl_listbox.index("insert")
        line = int(pos.split(".")[0])
        entry = self.wl_listbox.get(f"{line}.0", f"{line}.end")
        num = entry.split()[0].strip()
        if not num:
            return
        chat_history.clear_history(num)
        self.refresh_whitelist_display()

    def refresh_whitelist_display(self):
        self.wl_listbox.config(state="normal")
        self.wl_listbox.delete("1.0", "end")
        manual = load_manual_names()
        for num in sorted(load_whitelist()):
            name = manual.get(num) or self.contact_names.get(num, "")
            if name:
                self.wl_listbox.insert("end", f"{num:<20}{name}\n")
            else:
                self.wl_listbox.insert("end", num + "\n")
        self.wl_listbox.config(state="disabled")
        self.wl_listbox.yview_moveto(0)

    def _copy_selection(self):
        try:
            text = self.wl_listbox.get("sel.first", "sel.last")
            if text:
                self.root.clipboard_clear()
                self.root.clipboard_append(text)
        except tk.TclError:
            pass

    def _show_wl_menu(self, event):
        try:
            self.wl_listbox.index("sel.first")
            has_sel = True
        except tk.TclError:
            has_sel = False
        self.wl_menu.entryconfig("Kopieren", state="normal" if has_sel else "disabled")
        self.wl_menu.tk_popup(event.x_root, event.y_root)

    # --- Log / Refresh ----------------------------------------------------------
    # --- Tray --------------------------------------------------------------------
    def hide_to_tray(self):
        self.root.withdraw()

    def _on_unmap(self, event):
        if self.root.state() == "iconic":
            self.root.withdraw()

    def _on_configure(self, event):
        """Merkt sich die letzte gueltige Fenster-Geometry.

        Nur speichern, wenn das Fenster wirklich sichtbar ist und eine
        plausible Groesse hat (temporaere Mini-Zustaende beim Start wie
        erscheinen mit 100x50 und wuerden sonst als letzter Wert landen).
        """
        try:
            if self.root.state() != "normal" or not self.root.winfo_viewable():
                return
            w, h = event.width, event.height
            # Mindestgroesse des Panels als Schwelle (temporaere Start-Werte
            # sind deutlich kleiner und werden so verworfen)
            if w < 300 or h < 300:
                return
            x, y = self.root.winfo_x(), self.root.winfo_y()
            geo = f"{w}x{h}+{x}+{y}"
            if is_valid_geometry(geo):
                self._last_geometry = geo
        except Exception:  # noqa: BLE001
            pass

    def _tray_open(self, icon=None, item=None):
        self.root.after(0, self._show_window)

    def _show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(300, lambda: self.root.attributes("-topmost", False))

    def _tray_quit(self, icon=None, item=None):
        self.root.after(0, self.quit_app)

    def _snapshot_geometry(self):
        """Liefert die aktuelle, echte Fenster-Geometry (nur wenn sichtbar).

        Nutzt winfo_*-Werte statt geometry()-String: bei minimierten oder
        versteckten Fenstern liefert geometry() kaputte -32000-Werte, und
        die tatsaechliche Groesse weicht von der Wunschgroesse ab.
        """
        try:
            if self.root.state() != "normal" or not self.root.winfo_viewable():
                return self._last_geometry
            w, h = self.root.winfo_width(), self.root.winfo_height()
            x, y = self.root.winfo_x(), self.root.winfo_y()
            geo = f"{w}x{h}+{x}+{y}"
            if is_valid_geometry(geo):
                self._last_geometry = geo
                return geo
            return self._last_geometry
        except Exception:  # noqa: BLE001
            return self._last_geometry

    def quit_app(self):
        self.stop_polling()
        try:
            self.tray_icon.stop()
        except Exception:  # noqa: BLE001
            pass
        try:
            geo = self._snapshot_geometry()
            if geo and is_valid_geometry(geo):
                save_window_size(geo)
        except Exception:  # noqa: BLE001
            pass
        signal_daemon.stop_daemon()
        release_single_instance()
        self.root.destroy()

    def on_close(self):
        self.quit_app()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    if not acquire_single_instance():
        # Bereits eine Instanz aktiv -> Meldung anzeigen und beenden
        try:
            import tkinter as _tk
            _root = _tk.Tk()
            _root.withdraw()
            _tk.messagebox.showwarning(
                "Signal-Bot",
                "Der Signal-Bot laeuft bereits (Tray-Icon prüfen).\n"
                "Es kann nur eine Instanz gleichzeitig laufen.")
            _root.destroy()
        except Exception:  # noqa: BLE001
            pass
        raise SystemExit(0)
    ControlPanel().run()
