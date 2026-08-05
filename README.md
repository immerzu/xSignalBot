# xSignalBot 🤖📱

Ein persönlicher **Auto-Antwort-Bot für Signal**, der eingehende Nachrichten mit einer lokal laufenden KI (Ollama) beantwortet — **100 % kostenlos und datenschutzfreundlich** (keine Nachricht verlässt deinen Computer).

## Features

- ⚡ **Auto-Antworten auf Signal-Nachrichten** — mit wählbarem Tonfall (Standard, Traurig, Fröhlich, Zurückhaltend, Lustig, Witzig, Finanzberater)
- 🤖 **Lokale KI** via Ollama (z. B. `qwen2.5:14b`) — 0 € Kosten, Nachrichten bleiben auf deinem Rechner
- 🧠 **Chatverlauf pro Kontakt** (letzte 100 Nachrichten als Kontext)
- ⏱️ **Auto-Senden** nach wählbarer Zeit (3 s) mit sichtbarem Countdown
- 🛡️ **Sicherheit:** Test-Modus sendet niemals, Einzelinstanz-Schutz, Antwort-Sperre bei Nachrichten-Salven
- 🖥️ **Kontroll-Panel** (Tkinter): Empfang starten/stoppen, Whitelist verwalten, Töne wählen, Gesundheits-Check
- 💬 **Tipp-Indikator** („… schreibt") während der Generierung
- 🔄 **Persistenter Daemon** (signal-cli JSON-RPC) — kein JVM-Neustart pro Befehl, Sync an eigene Geräte

## Architektur

```
Signal-Nachricht → signal-cli Daemon (WSL) → Python-Bridge → Ollama (lokal)
                        ↑                          ↓
                  Antwort wird angezeigt → Freigabe → gesendet
```

| Datei | Zweck |
|---|---|
| `signal_bot_control.py` | Kontroll-Panel (Tkinter) — Hauptprogramm |
| `signal_daemon.py` | Persistenter signal-cli-Daemon (JSON-RPC, Empfang/Notification) |
| `signal_popup.py` | Freigabe-Popup + Ollama-Aufruf |
| `signal_bridge.py` | Nachrichten-Bridge (Empfang, Whitelist-Prüfung) |
| `signal_cli_link.py` | Geräte-Kopplung (QR-Code) |
| `chat_history.py` | Chatverlauf pro Kontakt (JSON) |

## Voraussetzungen

- **Windows** mit **WSL2** (Ubuntu) + `signal-cli` ([AsamK/signal-cli](https://github.com/AsamK/signal-cli))
- **Ollama** lokal ([ollama.com](https://ollama.com)) mit einem Modell, z. B. `ollama pull qwen2.5:14b`
- **Python 3.10+** (Windows) mit `tkinter`
- Ein Signal-Konto als **Linked Device** (QR-Code via `signal_cli_link.py`)

> Hinweis: `signal-cli` wird unter `$HOME/.local/bin/signal-cli` in WSL erwartet (Pfad in `SIGNAL_CLI` anpassbar).

## Schnellstart

```bash
# 1. Signal-Konto koppeln (QR-Code mit Signal-App scannen)
python signal_cli_link.py

# 2. Ollama-Modell installieren (einmalig)
ollama pull qwen2.5:14b

# 3. Whitelist in signal_bot_config.json eintragen (NUR diese Kontakte
#    werden automatisch beantwortet!) - wird beim ersten Start generiert

# 4. Panel starten
python signal_bot_control.py
```

Im Panel: **„Empfang starten"** klicken → eingehende Nachrichten von Whitelist-Kontakten werden generiert und (optional automatisch) beantwortet.

## Konfiguration

Die Konfiguration liegt in `signal_bot_config.json` (wird beim ersten Start automatisch erzeugt):

```json
{
  "own_number": "+491234567890",
  "poll_interval_seconds": 5,
  "whitelist": ["+491234567890"],
  "contact_names": {},
  "auto_send_enabled": false,
  "last_tone": "Standard"
}
```

- `whitelist`: Nur diese Nummern werden beantwortet
- `contact_names`: Anzeigenamen (werden in den KI-Prompt eingebaut)
- `auto_send_enabled`: Antwort nach 3 s automatisch senden
- `last_tone`: Zuletzt gewählter Tonfall (bleibt über Neustarts erhalten)

## Sicherheit & Datenschutz

- 🔒 **Keine sensiblen Daten im Repository** — Whitelist, Chatverläufe, Logs und Kopplungs-QR werden durch `.gitignore` ausgeschlossen
- 🏠 Alles läuft **lokal** — Nachrichten und Antworten verlassen deinen Rechner nicht
- 🧪 **Test-Modus:** Antworten werden generiert, aber **niemals** gesendet
- 🔄 **Einzelinstanz-Schutz:** Es kann nur eine Bot-Instanz gleichzeitig laufen

## Lizenz

MIT — frei verwendbar, anpassbar und weiterverbreitbar.

---

# xSignalBot 🤖📱 (English)

A personal **auto-reply bot for Signal** that answers incoming messages with a locally running AI (Ollama) — **100 % free and privacy-friendly** (no message ever leaves your computer).

## Features

- ⚡ **Auto-replies to Signal messages** — with selectable tone (Standard, Sad, Cheerful, Reserved, Funny, Silly, Financial Advisor)
- 🤖 **Local AI** via Ollama (e.g. `qwen2.5:14b`) — 0 € cost, messages stay on your machine
- 🧠 **Per-contact chat history** (last 100 messages as context)
- ⏱️ **Auto-send** after a configurable delay (3 s) with visible countdown
- 🛡️ **Safety:** test mode never sends, single-instance protection, reply debounce for message bursts
- 🖥️ **Control panel** (Tkinter): start/stop receiving, manage whitelist, pick tones, health check
- 💬 **Typing indicator** ("… is typing") while generating
- 🔄 **Persistent daemon** (signal-cli JSON-RPC) — no JVM restart per command, sync to own devices

## Architecture

```
Signal message → signal-cli daemon (WSL) → Python bridge → Ollama (local)
                       ↑                        ↓
              Reply is shown → approval → sent
```

| File | Purpose |
|---|---|
| `signal_bot_control.py` | Control panel (Tkinter) — main program |
| `signal_daemon.py` | Persistent signal-cli daemon (JSON-RPC, receive/notifications) |
| `signal_popup.py` | Approval popup + Ollama call |
| `signal_bridge.py` | Message bridge (receive, whitelist check) |
| `signal_cli_link.py` | Device linking (QR code) |
| `chat_history.py` | Per-contact chat history (JSON) |

## Requirements

- **Windows** with **WSL2** (Ubuntu) + `signal-cli` ([AsamK/signal-cli](https://github.com/AsamK/signal-cli))
- **Ollama** locally ([ollama.com](https://ollama.com)) with a model, e.g. `ollama pull qwen2.5:14b`
- **Python 3.10+** (Windows) with `tkinter`
- A Signal account as a **linked device** (QR code via `signal_cli_link.py`)

> Note: `signal-cli` is expected at `$HOME/.local/bin/signal-cli` inside WSL (path adjustable via `SIGNAL_CLI`).

## Quick start

```bash
# 1. Link the Signal account (scan QR code with the Signal app)
python signal_cli_link.py

# 2. Install the Ollama model (once)
ollama pull qwen2.5:14b

# 3. Add numbers to the whitelist in signal_bot_config.json (ONLY these
#    contacts get auto-replies!) - generated on first start

# 4. Start the panel
python signal_bot_control.py
```

In the panel click **"Empfang starten"** — incoming messages from whitelisted contacts are generated and (optionally) auto-replied.

## Configuration

Configuration lives in `signal_bot_config.json` (auto-created on first start):

```json
{
  "own_number": "+491234567890",
  "poll_interval_seconds": 5,
  "whitelist": ["+491234567890"],
  "contact_names": {},
  "auto_send_enabled": false,
  "last_tone": "Standard"
}
```

- `whitelist`: only these numbers get replies
- `contact_names`: display names (injected into the AI prompt)
- `auto_send_enabled`: send the reply automatically after 3 s
- `last_tone`: last selected tone (persists across restarts)

## Security & privacy

- 🔒 **No sensitive data in this repository** — whitelist, chat logs, and linking QR codes are excluded via `.gitignore`
- 🏠 Everything runs **locally** — messages and replies never leave your machine
- 🧪 **Test mode:** replies are generated but **never** sent
- 🔄 **Single-instance protection:** only one bot instance can run at a time

## License

MIT — free to use, modify, and distribute.

---

# xSignalBot 🤖📱 (Русский)

Персональный **бот автоответчик для Signal**, отвечающий на входящие сообщения с помощью локальной ИИ-модели (Ollama) — **100 % бесплатно и конфиденциально** (ни одно сообщение не покидает ваш компьютер).

## Возможности

- ⚡ **Автоответы на сообщения Signal** — с выбором тона (Стандартный, Грустный, Весёлый, Сдержанный, Смешной, Уморительный, Финансовый советник)
- 🤖 **Локальный ИИ** через Ollama (например, `qwen2.5:14b`) — 0 €, сообщения остаются на вашем устройстве
- 🧠 **История переписки по контактам** (последние 100 сообщений как контекст)
- ⏱️ **Автоотправка** через настраиваемую задержку (3 с) с видимым отсчётом
- 🛡️ **Безопасность:** тестовый режим никогда не отправляет, защита от повторных запусков, задержка ответа при потоке сообщений
- 🖥️ **Панель управления** (Tkinter): запуск/остановка приёма, управление белым списком, выбор тона, проверка состояния
- 💬 **Индикатор набора текста** («…печатает») во время генерации
- 🔄 **Постоянный демон** (signal-cli JSON-RPC) — без перезапуска JVM на каждую команду, синхронизация с собственными устройствами

## Архитектура

```
Сообщение Signal → демон signal-cli (WSL) → Python-мост → Ollama (локально)
                        ↑                             ↓
           Ответ показывается → подтверждение → отправка
```

| Файл | Назначение |
|---|---|
| `signal_bot_control.py` | Панель управления (Tkinter) — главная программа |
| `signal_daemon.py` | Постоянный демон signal-cli (JSON-RPC, приём/уведомления) |
| `signal_popup.py` | Окно подтверждения + вызов Ollama |
| `signal_bridge.py` | Мост сообщений (приём, проверка белого списка) |
| `signal_cli_link.py` | Привязка устройства (QR-код) |
| `chat_history.py` | История переписки по контактам (JSON) |

## Требования

- **Windows** с **WSL2** (Ubuntu) + `signal-cli` ([AsamK/signal-cli](https://github.com/AsamK/signal-cli))
- **Ollama** локально ([ollama.com](https://ollama.com)) с моделью, например: `ollama pull qwen2.5:14b`
- **Python 3.10+** (Windows) с `tkinter`
- Аккаунт Signal как **связанное устройство** (QR-код через `signal_cli_link.py`)

> Примечание: `signal-cli` ожидается по пути `$HOME/.local/bin/signal-cli` внутри WSL (путь настраивается через `SIGNAL_CLI`).

## Быстрый старт

```bash
# 1. Привяжите аккаунт Signal (отсканируйте QR-код приложением Signal)
python signal_cli_link.py

# 2. Установите модель Ollama (один раз)
ollama pull qwen2.5:14b

# 3. Добавьте номера в белый список в signal_bot_config.json (только эти
#    контакты получат автоответы!) - файл создаётся при первом запуске

# 4. Запустите панель
python signal_bot_control.py
```

В панели нажмите **«Empfang starten»** — входящие сообщения из белого списка будут генерироваться и (по желанию) отправляться автоматически.

## Конфигурация

Конфигурация хранится в `signal_bot_config.json` (создаётся автоматически при первом запуске):

```json
{
  "own_number": "+491234567890",
  "poll_interval_seconds": 5,
  "whitelist": ["+491234567890"],
  "contact_names": {},
  "auto_send_enabled": false,
  "last_tone": "Standard"
}
```

- `whitelist`: только эти номера получают ответы
- `contact_names`: отображаемые имена (встраиваются в промпт ИИ)
- `auto_send_enabled`: отправлять ответ автоматически через 3 с
- `last_tone`: последний выбранный тон (сохраняется между перезапусками)

## Безопасность и конфиденциальность

- 🔒 **В этом репозитории нет конфиденциальных данных** — белый список, истории переписки и QR-коды привязки исключены через `.gitignore`
- 🏠 Всё работает **локально** — сообщения и ответы не покидают ваш компьютер
- 🧪 **Тестовый режим:** ответы генерируются, но **никогда** не отправляются
- 🔄 **Защита от повторных запусков:** одновременно может работать только один экземпляр бота

## Лицензия

MIT — можно свободно использовать, изменять и распространять.
