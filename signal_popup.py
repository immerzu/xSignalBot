#!/usr/bin/env python3
"""Freigabe-Popup fuer den Signal-Bot (wiederverwendbares Modul).

Oeffnet ein DPI-scharfes Tkinter-Fenster mit Absender, Original-Nachricht,
editierbarem Antwort-Vorschlag und den Buttons Senden/Verwerfen/Neu generieren.
Die Antwort wird per Ollama (lokal, qwen2.5:14b) generiert.

run_popup(sender, nachricht) -> dict {entscheidung, antwort}
"""
import datetime as _dt
import json
import os
import threading
import urllib.request

# --- DPI-Awareness (Windows): scharfe Darstellung bei 175 %-Skalierung ------
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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "logs", "approval.log")
STATE_FILE = os.path.join(BASE_DIR, "popup_state.json")

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

# Tonlagen fuer die Antwort-Generierung (Dropdown im Popup)
STIMMUNGEN = {
    "Standard": "",
    "Traurig": (
        "Verfasse die Antwort in einem traurigen, wehmuetigen Ton. "
        "Druecke Bedauern oder Niedergeschlagenheit dezent aus, bleibe "
        "aber hoeflich und natuerlich."
    ),
    "Froehlich": (
        "Verfasse die Antwort in einem froehlichen, begeisterten Ton. "
        "Zeige Freude und positive Energie, bleibe aber natuerlich und "
        "nicht uebertrieben."
    ),
    "Zurueckhaltend": (
        "Verfasse die Antwort in einem zurueckhaltenden, ruhigen und "
        "sachlichen Ton. Halte dich kurz, bleibe hoeflich und ohne "
        "emotionale Ausschweifungen."
    ),
    "Lustig": (
        "Verfasse die Antwort mit einem humorvollen, lustigen Unterton. "
        "Baue einen passenden Scherz oder eine lockere Bemerkung ein, "
        "bleibe aber freundlich und nicht verletzend. Setze dazu passende "
        "Smileys/Emojis ein (z. B. \U0001f604 \U0001f602 \U0001f609 \U0001f642 "
        "\U0001f973 \U0001f61c \U0001f606 \U0001f643), auch am Anfang oder "
        "Ende der Antwort. Nutze dabei ruhig eine abwechslungsreiche "
        "Auswahl aus dem gesamten Emoji-Spektrum (Gesichter, Gesten, "
        "Symbole), nicht nur immer dieselben."
    ),
    "Witzig": (
        "Verfasse die Antwort UEBERSCHWAENGLICH LANG und richtig witzig. "
        "Die eingehende Nachricht ist haeufig nur kurz (z. B. 'ok', 'hey', "
        "'ja' oder ein einzelnes Wort) — antworte trotzdem (oder gerade "
        "deshalb) mit einer ausufernden, komisch uebertriebenen Antwort: "
        "dramatische Vergleiche, absurde Szenarien, ulkige Details und "
        "Uebertreibungen erwuenscht. Diese Anweisung setzt die "
        "Laengen-Begrenzung des Basis-Prompts AUSSER KRAFT: Antworte "
        "bewusst lang (mindestens 5-8 Saetze), auch wenn die Nachricht "
        "nur ein Wort ist. Setze dabei grosszuegig passende Smileys/Emojis "
        "ein (z. B. \U0001f923 \U0001f602 \U0001f61c \U0001f643 \U0001f92a "
        "\U0001f61d \U0001fae1 \U0001f480 \U0001f62d \U0001f525), am Anfang, "
        "am Ende und zwischen den Saetzen. Nutze eine abwechslungsreiche "
        "Mischung aus dem gesamten Emoji-Spektrum — Gesichter, Gesten, "
        "Symbole, Tiere, Essen, Gegenstaende — je nachdem, was zum Witz "
        "passt, und nicht nur immer dieselben. Bleibe dabei freundlich und "
        "nicht verletzend."
    ),
    "Finanzberater": (
        "Verfasse die Antwort wie ein serioes auftretender Finanzberater, "
        "der aber totalen, absurden Quatsch ueber Boerse, Aktien, "
        "Kurswechsel, Bitcoin, ETFs und Finanzkrisen erzaehlt. Benutze "
        "Fachbegriffe und Berater-Sprech (z. B. 'Portfolio-Diversifikation', "
        "'Marktvolatilitaet', 'Sonderkonditionen', 'Hebelwirkung', "
        "'Abwaertstrend', 'Liquiditaet'), aber fachlich voellig sinnlos "
        "und wunderbar uebertrieben. ERFINDE konkreten absurden Quatsch: "
        "wilde Bitcoin-Kursprognosen (z. B. 'Bitcoin wird naechste Woche "
        "auf 2,5 Millionen steigen, weil ein Hamster in Singapur ihn "
        "kauft'), dramatische Marktanalysen, seltsame Indikatoren, "
        "fiktive Boersengaenge und komische Anlagetipps. Beziehe dich "
        "IMMER auf die eingehende Nachricht und verpacke sie in deinen "
        "Finanz-Quatsch. Antworte ausfuehrlich (3-5 Saetze). Setze dabei "
        "passende Finanz-Emojis ein (z. B. \U0001f4c8 \U0001f4b0 \U0001f4c9 "
        "\U0001f680 \U0001f609 \U0001f911 \U0001f4b8 \U0001f3e6 \U0001f4ca "
        "\U0001fa99) und nutze abwechslungsreich das ganze Spektrum, das "
        "zum Thema passt. Bleibe freundlich, locker und mit einem "
        "zwinkernden Unterton."
    ),
}

# Anzeige-Labels der Töne (mit Emoji) -> interne Stimmungs-Keys
TON_LABELS = {
    "Standard": "Standard",
    "Traurig": "😢 Traurig",
    "Froehlich": "😄 Froehlich",
    "Zurueckhaltend": "🤐 Zurueckhaltend",
    "Lustig": "😂 Lustig",
    "Witzig": "🤣 Witzig (lang)",
    "Finanzberater": "📈 Finanzberater",
}

# Rueckwaerts-Mapping Label -> Key
LABEL_TO_STIMMUNG = {v: k for k, v in TON_LABELS.items()}


def log_decision(sender, antwort, entscheidung):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(
            f"{_dt.datetime.now().isoformat(timespec='seconds')} | {sender} | "
            f"{entscheidung} | chars={len(antwort)}\n"
        )


def load_window_size():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f).get("window_size")
    except (OSError, ValueError):
        return None


def save_window_size(geometry):
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"window_size": geometry}, f)
    except OSError:
        pass


def generate_antwort(nachricht, stimmung="Standard", history=None):
    """Ruft Ollama auf und liefert die generierte Antwort (Blocking!).

    history: optionale Liste vorheriger Nachrichten [{"role", "content"}, ...]
    (chronologisch, OHNE die aktuelle Nachricht).
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
    messages.append(
        {"role": "user", "content": f"Der Kontakt schreibt:\n{nachricht}"})
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


class FreigabePopup:
    def __init__(self, sender, nachricht):
        self.sender = sender
        self.nachricht = nachricht
        self.entscheidung = None
        self.antwort = ""
        self._generating = False

        self.root = tk.Tk()
        self.root.title("Signal-Bot: Antwort freigeben")
        dpi_scale = max(1.0, self.root.winfo_fpixels("1i") / 96.0)
        saved = load_window_size()
        if saved:
            self.root.geometry(saved)
        else:
            self.root.geometry(f"{int(560 * dpi_scale)}x{int(520 * dpi_scale)}")
        self.root.attributes("-topmost", True)
        self.root.minsize(int(480 * dpi_scale), int(380 * dpi_scale))
        self.root.protocol("WM_DELETE_WINDOW", self.verwerfen)

        tk.Label(self.root, text=f"Absender: {sender}", font=("Segoe UI", 11, "bold"),
                 anchor="w", padx=12, pady=10).pack(fill="x")
        tk.Label(self.root, text="Eingehende Nachricht:", font=("Segoe UI", 9),
                 anchor="w", padx=12).pack(fill="x")

        nachricht_box = scrolledtext.ScrolledText(self.root, height=6, wrap="word",
                                                  font=("Segoe UI", 10))
        nachricht_box.insert("1.0", nachricht)
        nachricht_box.config(state="disabled")
        nachricht_box.pack(fill="x", padx=12, pady=8)

        tk.Label(self.root, text="Antwort-Vorschlag (editierbar):", font=("Segoe UI", 9),
                 anchor="w", padx=12).pack(fill="x")

        self.antwort_box = scrolledtext.ScrolledText(self.root, height=8, wrap="word",
                                                     font=("Segoe UI", 10))
        self.antwort_box.insert("1.0", "Antwort wird generiert ...")
        self.antwort_box.pack(fill="both", expand=True, padx=12, pady=8)

        # Stimmungs-Auswahl fuer die Antwort-Generierung (VOR den Buttons,
        # damit sie auch bei kleiner Fenstergroesse sichtbar bleibt).
        # ttk.Combobox (readonly) statt tk.OptionMenu: OptionMenu zeigt auf
        # Windows/Vista-Style den gewaehlten Wert nicht an (leere Klappe).
        # Die Auswahl startet die Generierung automatisch (kein Extra-Button).
        stim_frame = tk.Frame(self.root)
        stim_frame.pack(fill="x", padx=12, pady=6)
        tk.Label(stim_frame, text="Ton:", font=("Segoe UI", 9)).pack(side="left")
        self.stimmung_var = tk.StringVar(value=TON_LABELS["Standard"])
        stimmung_combo = ttk.Combobox(
            stim_frame, textvariable=self.stimmung_var,
            values=list(TON_LABELS.values()), state="readonly", width=22,
        )
        stimmung_combo.pack(side="left", padx=6)
        stimmung_combo.bind("<<ComboboxSelected>>", lambda e: self.regenerate())

        btn_frame = tk.Frame(self.root)
        btn_frame.pack(fill="x", padx=12, pady=12)

        tk.Button(btn_frame, text="Antwort neu generieren", width=22,
                  command=self.regenerate).pack(side="left")
        tk.Button(btn_frame, text="Verwerfen (Esc)", width=18,
                  command=self.verwerfen).pack(side="right")
        tk.Button(btn_frame, text="Senden (Enter)", width=18, bg="#2d7dd2", fg="white",
                  command=self.senden).pack(side="right", padx=8)

        self.root.bind("<Return>", lambda e: self.senden())
        self.root.bind("<Escape>", lambda e: self.verwerfen())

        self._start_generation()

    def _start_generation(self):
        if self._generating:
            return
        self._generating = True
        self.antwort_box.config(state="normal")
        self.antwort_box.delete("1.0", "end")
        self.antwort_box.insert("1.0", "Antwort wird generiert ...")
        threading.Thread(target=self._generate_worker, daemon=True).start()

    def _selected_stimmung(self):
        """Liefert den internen Stimmungs-Key zum gewaehlten Combo-Label."""
        return LABEL_TO_STIMMUNG.get(self.stimmung_var.get(), "Standard")

    def _generate_worker(self):
        try:
            history = chat_history.get_messages(self.sender)
            antwort = generate_antwort(self.nachricht, stimmung=self._selected_stimmung(),
                                       history=history)
            self.root.after(0, lambda: self._set_antwort(antwort))
        except Exception as e:  # noqa: BLE001
            self.root.after(0, lambda: self._set_antwort(f"[FEHLER bei Ollama: {e}]"))

    def _set_antwort(self, text):
        self.antwort_box.config(state="normal")
        self.antwort_box.delete("1.0", "end")
        self.antwort_box.insert("1.0", text)
        self._generating = False

    def get_antwort(self):
        return self.antwort_box.get("1.0", "end").strip()

    def senden(self):
        if self._generating:
            return
        antwort = self.get_antwort()
        if not antwort or antwort.startswith("[FEHLER") or antwort == "Antwort wird generiert ...":
            return
        self.entscheidung = "gesendet"
        self.antwort = antwort
        chat_history.append_message(self.sender, "user", self.nachricht)
        chat_history.append_message(self.sender, "assistant", antwort)
        log_decision(self.sender, antwort, "GESENDET")
        self.close()

    def verwerfen(self):
        self.entscheidung = "verworfen"
        self.antwort = self.get_antwort()
        log_decision(self.sender, self.antwort, "VERWORFEN")
        self.close()

    def regenerate(self):
        self._start_generation()

    def close(self):
        try:
            geo = self.root.geometry()
            save_window_size(geo.split("+")[0])
        except Exception:  # noqa: BLE001
            pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def run_popup(sender, nachricht):
    """Blockierend: oeffnet das Popup, liefert {entscheidung, antwort}."""
    popup = FreigabePopup(sender, nachricht)
    popup.run()
    return {"entscheidung": popup.entscheidung, "antwort": popup.antwort}
