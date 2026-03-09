# ComfyUI Telegram Auto Send

ComfyUI extension that automatically sends all **SaveImage** node results to a Telegram channel/chat — without adding any nodes to your workflow.

## Features

- Toggle on/off directly from ComfyUI **Settings** panel
- Sends images as **photo** (Telegram-compressed) or as **file** (original PNG, no re-compression)
- Asynchronous sending — does **not** block the next generation
- Caption supports `{time}` and `{date}` placeholders
- Works with all existing workflows — no node changes needed

## Installation

1. Clone into your ComfyUI custom nodes folder:
   ```bash
   cd ComfyUI/custom_nodes
   git clone https://github.com/GENKAIx/comfyui-telegram-auto-send
   ```
2. Restart ComfyUI

## Setup

1. Open **Settings** (gear icon) in ComfyUI
2. Scroll to the **🤖 Telegram AutoSend** section
3. Fill in:
   - **Токен бота** — your Telegram bot token (get from [@BotFather](https://t.me/BotFather))
   - **Chat ID** — your channel or chat ID (e.g. `-1001234567890`)
   - **Подпись** — caption template, supports `{time}` and `{date}`
   - **Отправлять как файл** — send as file (no Telegram compression) instead of photo
   - **Включить автоотправку** — master on/off toggle

## How it works

- Listens to ComfyUI's `executed` event
- Filters outputs with `type = "output"` (SaveImage only, not PreviewImage)
- Reads the saved file from the ComfyUI output directory
- Sends to Telegram in a background thread

## Requirements

- ComfyUI (any recent version)
- Python packages: `requests` (included with ComfyUI)
