#!/usr/bin/env python3
"""signal-bot Freigabe-Popup — TESTVERSION mit ECHTEM Ollama-Modell (qwen2.5:14b)

Ablauf:
  1. "Eingehende Nachricht" kommt rein (simuliert, fest verdrahtet)
  2. Popup oeffnet sich SOFORT, zeigt "Antwort wird generiert ..."
  3. qwen2.5:14b (lokal, Ollama auf 127.0.0.1:11434) generiert die Antwort
     im Hintergrund-Thread; sobald fertig, wird sie ins editierbare Feld
     eingefuegt
  4. Du entscheidest: Senden / Verwerfen / Antwort neu generieren
  5. Entscheidung wird in logs/approval.log geschrieben

Voraussetzung: ollama.exe laeuft und `qwen2.5:14b` ist installiert
(ollama list). Start:  python signal_bot_popup_test.py
"""
import datetime as _dt
import json
import os
import sys
import threading
import urllib.request

# --- DPI-Awareness (Windows): scharfe Darstellung bei 175 %-Skalierung ------
# Muss VOR tk.Tk() passieren, sonst skaliert Windows das Fenster per Bitmap
# hoch (matschig). SetProcessDpiAwareness(1) = system DPI aware.
if os.name == "nt":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001 - aeltere Windows-API als Fallback
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:  # noqa: BLE001
            pass

try:
    import tkinter as tk
    from tkinter import scrolledtext
except ImportError:
    sys.exit("FEHLER: tkinter nicht verfuegbar. (Python muss mit Tcl/Tk installiert sein.)")

# --- Konfiguration -----------------------------------------------------------
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL = "qwen2.5:14b"
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "approval.log")
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "popup_state.json")


def load_window_size():
    """Liest die zuletzt gespeicherte Fenstergroesse (WxH)."""
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f).get("window_size")
    except (OSError, ValueError):
        return None


def save_window_size(geometry):
    """Speichert die aktuelle Fenstergroesse (WxH) fuer den naechsten Start."""
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"window_size": geometry}, f)
    except OSError:
        pass  # nicht kritisch - Fenster oeffnet dann mit Default-Groesse

SYSTEM_PROMPT = (
    "Du bist ein hilfsbereiter persoenlicher Assistent, der Nachrichten "
    "im Namen des Nutzers beantwortet. Antworte IMMER auf Deutsch, "
    "praezise und natuerlich. Antworte nur mit der eigentlichen Antwort, "
    "ohne Einleitung wie 'Hier ist meine Antwort'. Halte die Antwort kurz "
    "und freundlich (max. 2-3 Saetze, es sei denn, die Frage verlangt mehr)."
)

# --- Simulierte Eingabe (spaeter: echte Signal-Nachricht) --------------------
SIM_SENDER = "Max Mustermann (+49 170 1234567)"
SIM_NACHRICHT = (
    "Hallo! Ich wollte fragen, ob wir uns morgen um 15 Uhr treffen koennen. "
    "Ich wuerde gerne das Projekt besprechen. Passt dir das?"
)


def log_decision(sender, antwort, entscheidung):
    """Schreibt eine Log-Zeile (nur Metadaten, keine Inhalte)."""
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(
            f"{_dt.datetime.now().isoformat(timespec='seconds')} | {sender} | "
            f"{entscheidung} | chars={len(antwort)}\n"
        )


def generate_antwort(nachricht, neu=False):
    """Ruft Ollama auf und liefert die generierte Antwort (Blocking!)."""
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Der Kontakt schreibt:\n{nachricht}"},
        ],
        "stream": False,
    }
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
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
        self._generating = False

        self.root = tk.Tk()
        self.root.title("Signal-Bot: Antwort freigeben")
        # Fenstergroesse DPI-abhaengig skalieren (175 %-Skalierung = groesser)
        dpi_scale = max(1.0, self.root.winfo_fpixels("1i") / 96.0)
        w = int(560 * dpi_scale)
        h = int(520 * dpi_scale)
        # Gespeicherte Fenstergroesse (vom letzten Lauf) bevorzugen
        saved = load_window_size()
        if saved:
            self.root.geometry(saved)
        else:
            self.root.geometry(f"{w}x{h}")
        self.root.attributes("-topmost", True)
        self.root.minsize(int(480 * dpi_scale), int(380 * dpi_scale))
        # Beim Schliessen (X-Button) die Fenstergroesse merken
        self.root.protocol("WM_DELETE_WINDOW", self.verwerfen)

        # Absender
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

        # Antwort sofort im Hintergrund generieren
        self._start_generation()

    # --- Ollama im Hintergrund-Thread --------------------------------------
    def _start_generation(self):
        if self._generating:
            return
        self._generating = True
        self.antwort_box.config(state="normal")
        self.antwort_box.delete("1.0", "end")
        self.antwort_box.insert("1.0", "Antwort wird generiert ...")
        threading.Thread(target=self._generate_worker, daemon=True).start()

    def _generate_worker(self):
        try:
            antwort = generate_antwort(self.nachricht)
            self.root.after(0, lambda: self._set_antwort(antwort))
        except Exception as e:  # noqa: BLE001 - UI darf nie abstuerzen
            self.root.after(0, lambda: self._set_antwort(f"[FEHLER bei Ollama: {e}]"))

    def _set_antwort(self, text):
        self.antwort_box.config(state="normal")
        self.antwort_box.delete("1.0", "end")
        self.antwort_box.insert("1.0", text)
        self._generating = False

    # --- Aktionen ------------------------------------------------------------
    def get_antwort(self):
        return self.antwort_box.get("1.0", "end").strip()

    def senden(self):
        if self._generating:
            return  # Antwort ist noch nicht fertig
        antwort = self.get_antwort()
        if not antwort or antwort.startswith("[FEHLER") or antwort == "Antwort wird generiert ...":
            return
        self.entscheidung = "gesendet"
        log_decision(self.sender, antwort, "GESENDET")
        self.close()

    def verwerfen(self):
        self.entscheidung = "verworfen"
        log_decision(self.sender, self.get_antwort(), "VERWORFEN")
        self.close()

    def regenerate(self):
        self._start_generation()

    def close(self):
        # Fenstergroesse merken (nur Breite x Hoehe, ohne Position)
        try:
            geo = self.root.geometry()  # z. B. "980x910+100+50"
            size = geo.split("+")[0]   # -> "980x910"
            save_window_size(size)
        except Exception:  # noqa: BLE001
            pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    print("Signal-Bot Freigabe-Popup TEST (mit Ollama)")
    print(f"Modell: {OLLAMA_MODEL}  |  Server: {OLLAMA_URL}")
    print(f"Simulierte Nachricht von: {SIM_SENDER}")
    print("Fenster wird geoeffnet - Antwort wird live generiert.")
    print(f"Log: {LOG_FILE}")
    popup = FreigabePopup(SIM_SENDER, SIM_NACHRICHT)
    popup.run()
    print(f"Entscheidung: {popup.entscheidung}")
