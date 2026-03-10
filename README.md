# ComfyUI Telegram Auto Send

**Language / Язык:** 🇺🇸 English | [🇷🇺 Русский](README.ru.md)

---

Automatically sends all **SaveImage** node results to a Telegram channel or chat — no workflow changes required.

## Features

- **Zero workflow changes** — works with any existing workflow
- Toggle on/off directly from the **ComfyUI Settings** panel
- Send as **photo** (Telegram-compressed) or as **file** (original PNG, no re-compression)
- **Silent send** — deliver without sound or vibration
- **Asynchronous queue** — sending never blocks the next generation
- Caption supports `{time}` and `{date}` placeholders

## Installation

Clone into your ComfyUI custom nodes folder and restart ComfyUI:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/GENKAIx/comfyui-telegram-auto-send
```

## Setup

1. Open **Settings** (gear icon ⚙️) in ComfyUI
2. Scroll to the **🤖 Telegram AutoSend** section
3. Fill in the fields:

| Setting | Description |
|---|---|
| **Enable auto-send** | Master on/off toggle |
| **Bot token** | Your bot token from [@BotFather](https://t.me/BotFather) |
| **Chat ID / Channel ID** | Target chat or channel (e.g. `-1001234567890`) |
| **Image caption** | Caption template — supports `{time}` and `{date}` |
| **Send as file** | Send original PNG without Telegram re-compression |
| **Silent send** | Deliver without notification sound |

## How it works

1. Listens for ComfyUI's `executed` event after each node run
2. Filters outputs with `type = "output"` — **SaveImage only**, PreviewImage is ignored
3. Reads the saved file from ComfyUI's output directory
4. Puts the send task into a **persistent background queue** — one worker thread processes tasks in order

## Requirements

- ComfyUI (any recent version)
- `requests` Python package (bundled with ComfyUI)
