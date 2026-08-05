#!/usr/bin/env python3
"""signal-cli Link-Assistent: koppelt signal-cli als 'Linked Device' an Signal.

Ablauf:
  1. Startet `signal-cli link -n "Helfer01-Bot"` in WSL2 (laeuft im Hintergrund,
     WSL2-Distro bleibt dadurch am Leben bis zum Abschluss)
  2. Liest die tsdevice/sgnl-URI aus der Ausgabe
  3. Erzeugt ein QR-PNG (qrcode + Pillow) und oeffnet es im Bildbetrachter
  4. Wartet, bis der Nutzer den QR gescannt hat (Prozess endet dann automatisch)
"""
import os
import re
import subprocess
import sys
import time

QR_PNG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "signal-link-qr.png")
FINISH_FLAG = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".link-finished")

WSL_BIN = "wsl.exe"
SIGNAL_CLI = "$HOME/.local/bin/signal-cli"
URI_RE = re.compile(r"(sgnl://linkdevice\?[^\s\r\n]+|tsdevice:[^\s\r\n]+)")


def main():
    if os.path.exists(FINISH_FLAG):
        os.remove(FINISH_FLAG)

    print("[1/4] Starte signal-cli link in WSL2 ...")
    proc = subprocess.Popen(
        [WSL_BIN, "-e", "bash", "-lc",
         f"export PATH=$HOME/.local/bin:$PATH && exec {SIGNAL_CLI} link -n 'Helfer01-Bot'"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    # [2/4] URI aus der Ausgabe lesen
    print("[2/4] Warte auf Link-URI ...")
    uri = None
    deadline = time.time() + 30
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        print("  Ausgabe:", line[:120])
        m = URI_RE.search(line)
        if m:
            uri = m.group(1)
            break

    if not uri:
        print("FEHLER: Keine Link-URI erhalten.")
        proc.terminate()
        sys.exit(1)

    print(f"[2/4] URI erhalten ({len(uri)} Zeichen)")

    # [3/4] QR-PNG erzeugen
    print("[3/4] Erzeuge QR-Bild ...")
    import qrcode
    qr = qrcode.QRCode(box_size=10, border=4)
    qr.add_data(uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(QR_PNG)
    print(f"      QR-Bild gespeichert: {QR_PNG}")

    # Bild im Standard-Bildbetrachter oeffnen
    os.startfile(QR_PNG)  # noqa: S606 - gewolltes Oeffnen fuer den Nutzer

    # [4/4] Auf Scan warten: signal-cli beendet sich nach erfolgreicher Kopplung
    print("[4/4] Warte auf QR-Scan ... (Prozess endet automatisch nach Kopplung)")
    try:
        proc.wait(timeout=300)
        print("Kopplung abgeschlossen! signal-cli ist jetzt 'Helfer01-Bot' an deinem Konto.")
        open(FINISH_FLAG, "w").write(time.strftime("%Y-%m-%d %H:%M:%S"))
    except subprocess.TimeoutExpired:
        print("Timeout (5 Min). Prozess wird beendet - bitte erneut starten.")
        proc.terminate()
        sys.exit(2)


if __name__ == "__main__":
    main()
