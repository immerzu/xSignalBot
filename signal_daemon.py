#!/usr/bin/env python3
"""Persistenter signal-cli-Daemon fuer den Signal-Bot.

Startet `signal-cli daemon` einmalig in WSL (JSON-RPC auf 0.0.0.0:7583)
und kommuniziert darueber - kein JVM-Neustart pro Befehl, keine
Prozess-Kollision zwischen receive und send, und (wichtig) die
eigenen Signal-Geraete (Desktop-App/Handy) bekommen den sentMessage-Sync.

Architektur:
  - Daemon bindet 0.0.0.0:7583 INNERHALB von WSL (NAT - nur vom Host
    erreichbar, nicht aus dem LAN).
  - Windows-Python verbindet sich ueber die dynamische WSL-IP
    (hostname -I) per TCP-Socket, JSON-RPC Zeilenprotokoll.
  - Empfang: subscribeReceive -> der Daemon pusht eingehende Nachrichten
    als JSON-RPC Notifications an den verbundenen Client.
"""
import json
import os
import socket
import subprocess
import threading
import time

WSL_BIN = "wsl.exe"
SIGNAL_CLI = "$HOME/.local/bin/signal-cli"
DAEMON_PORT = 7583
DAEMON_BIND = "0.0.0.0"

_lock = threading.Lock()
_daemon_proc = None       # subprocess.Popen des wsl.exe-Daemons
_wsl_ip = None            # gecachte WSL-IP


# --- WSL-Hilfen ---------------------------------------------------------------
def get_wsl_ip():
    """Ermittelt die aktuelle WSL-IP (dynamisch, aendert sich pro Boot)."""
    global _wsl_ip
    if _wsl_ip:
        return _wsl_ip
    try:
        r = subprocess.run(
            [WSL_BIN, "-e", "bash", "-lc", "hostname -I"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        ip = (r.stdout or "").strip().split()[0] if r.stdout else ""
        if ip:
            _wsl_ip = ip
        return ip
    except Exception:  # noqa: BLE001
        return ""


def clear_wsl_ip():
    global _wsl_ip
    _wsl_ip = None


# --- Daemon-Lebenszyklus -------------------------------------------------------
def daemon_running():
    """Prueft, ob der Daemon erreichbar ist (Port offen)."""
    ip = get_wsl_ip()
    if not ip:
        return False
    try:
        s = socket.create_connection((ip, DAEMON_PORT), timeout=3)
        s.close()
        return True
    except OSError:
        return False


def start_daemon():
    """Startet den signal-cli-Daemon in WSL (einmalig, persistent)."""
    global _daemon_proc
    if daemon_running():
        return True
    with _lock:
        if daemon_running():
            return True
        try:
            # Alte Rest-Prozesse in WSL entfernen (falls haengen geblieben)
            subprocess.run(
                [WSL_BIN, "-e", "bash", "-lc", "pkill -9 -f signal-cli 2>/dev/null; true"],
                capture_output=True, timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            time.sleep(1)
            cmd = [WSL_BIN, "-e", "bash", "-lc",
                   f"export PATH=$HOME/.local/bin:$PATH && exec {SIGNAL_CLI} daemon "
                   f"--tcp {DAEMON_BIND}:{DAEMON_PORT} --receive-mode manual "
                   "--no-receive-stdout --ignore-attachments --ignore-stories "
                   "--ignore-avatars --ignore-stickers"]
            _daemon_proc = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            # Bis zu 25 s auf den Port warten (JVM-Start)
            for _ in range(25):
                time.sleep(1)
                if daemon_running():
                    return True
            return False
        except Exception:  # noqa: BLE001
            return False


def stop_daemon():
    """Beendet den Daemon (Prozess + WSL-Reste)."""
    global _daemon_proc, _wsl_ip
    if _daemon_proc:
        try:
            _daemon_proc.terminate()
        except Exception:  # noqa: BLE001
            pass
        _daemon_proc = None
    try:
        subprocess.run(
            [WSL_BIN, "-e", "bash", "-lc", "pkill -9 -f signal-cli 2>/dev/null; true"],
            capture_output=True, timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    except Exception:  # noqa: BLE001
        pass
    _wsl_ip = None


# --- JSON-RPC (ein Request, eine Antwort) --------------------------------------
def rpc_call(method, params=None, timeout=60):
    """Sendet einen JSON-RPC-Request an den Daemon und liefert das Result.

    Bei Fehlern wird None geliefert (Aufrufer entscheidet ueber Fallback).
    """
    ip = get_wsl_ip()
    if not ip:
        return None
    try:
        s = socket.create_connection((ip, DAEMON_PORT), timeout=timeout)
        req = {"jsonrpc": "2.0", "id": 1, "method": method}
        if params:
            req["params"] = params
        s.sendall((json.dumps(req) + "\n").encode("utf-8"))
        s.settimeout(timeout)
        buf = b""
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
            if b"\n" in buf:
                break
        s.close()
        resp = json.loads(buf.decode("utf-8"))
        if "error" in resp:
            return None
        return resp.get("result")
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def daemon_send(number, text):
    """Sendet eine Nachricht ueber den Daemon. Liefert True bei Erfolg."""
    result = rpc_call("send", {"recipient": [number], "message": text}, timeout=60)
    return result is not None


def daemon_send_typing(number, stop=False):
    """Sendet den Tipp-Indikator ueber den Daemon (feuer-und-vergiss)."""
    rpc_call("sendTyping", {"recipient": [number], "stop": bool(stop)}, timeout=20)


# --- Empfang (Notification-Stream) ----------------------------------------------
class DaemonReceiver(threading.Thread):
    """Verbindet sich, abonniert receive und ruft on_message(envelope) auf."""

    def __init__(self, on_message, on_error=None, reconnect_secs=5):
        super().__init__(daemon=True)
        self.on_message = on_message
        self.on_error = on_error
        self.reconnect_secs = reconnect_secs
        self._active = True
        self._sock = None
        self._seen = set()          # (timestamp, source) -> dedupliziert
        self._seen_max = 200        # Ringpuffer-Groesse fuer gesehene IDs

    def _dedup(self, env):
        """Liefert False, wenn dieser Envelope schon verarbeitet wurde."""
        try:
            key = (env.get("timestamp"), env.get("source"))
            if key in self._seen:
                return False
            self._seen.add(key)
            if len(self._seen) > self._seen_max:
                # aelteste Eintraege entfernen (Ringpuffer)
                for old in list(self._seen)[:50]:
                    self._seen.discard(old)
            return True
        except Exception:  # noqa: BLE001
            return True  # im Zweifel durchlassen

    def stop(self):
        self._active = False
        # Verbindung schliessen, damit ein blockierendes recv() sofort
        # aufwacht und der Thread sich beendet (kein Doppel-Empfang mehr)
        s = self._sock
        if s is not None:
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                s.close()
            except OSError:
                pass
            self._sock = None

    def run(self):
        while self._active:
            ip = get_wsl_ip()
            if not ip or not daemon_running():
                self._sleep()
                continue
            try:
                s = socket.create_connection((ip, DAEMON_PORT), timeout=15)
                self._sock = s
                s.sendall((json.dumps(
                    {"jsonrpc": "2.0", "id": 1, "method": "subscribeReceive"})
                    + "\n").encode("utf-8"))
                # Subscriptions-Antwort lesen (eine Zeile)
                s.settimeout(30)
                s.recv(65536)
                # Endlosschleife: Notifications lesen
                while self._active:
                    try:
                        chunk = s.recv(65536)
                    except socket.timeout:
                        continue
                    if not chunk:
                        break  # Verbindung zu - Reconnect
                    for line in chunk.decode("utf-8", errors="replace").splitlines():
                        line = line.strip()
                        if not line.startswith("{"):
                            continue
                        try:
                            msg = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        params = msg.get("params") or {}
                        # Notification-Form: params.envelope ODER
                        # params.subscription.result.envelope
                        env = params.get("envelope")
                        if env is None and isinstance(params.get("result"), dict):
                            env = params.get("result", {}).get("envelope")
                        if env and self._dedup(env):
                            self.on_message(env)
                try:
                    s.close()
                except OSError:
                    pass
                self._sock = None
            except OSError:
                pass
            except Exception as e:  # noqa: BLE001
                if self.on_error:
                    try:
                        self.on_error(e)
                    except Exception:  # noqa: BLE001
                        pass
            self._sleep()

    def _sleep(self):
        for _ in range(self.reconnect_secs):
            if not self._active:
                return
            time.sleep(1)
