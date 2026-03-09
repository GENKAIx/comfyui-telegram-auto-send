import os
import json
import threading
import requests as req_lib
import folder_paths
import server
from aiohttp import web


@server.PromptServer.instance.routes.post("/telegram_auto/send")
async def telegram_auto_send(request):
    try:
        data = await request.json()

        images       = data.get("images", [])
        bot_token    = data.get("bot_token", "").strip()
        chat_id      = data.get("chat_id", "").strip()
        caption      = data.get("caption", "").strip()
        send_as_file = data.get("send_as_file", False)
        send_as_file = send_as_file in (True, "true", "True", 1, "1")

        if not bot_token or not chat_id:
            return web.json_response({"ok": False, "error": "Не указан bot_token или chat_id"})

        output_dir = folder_paths.get_output_directory()

        def _send(img_path, filename):
            try:
                with open(img_path, "rb") as f:
                    img_bytes = f.read()

                method = "sendDocument" if send_as_file else "sendPhoto"
                field  = "document"     if send_as_file else "photo"
                url    = f"https://api.telegram.org/bot{bot_token}/{method}"

                ext  = os.path.splitext(filename)[1].lower()
                mime = "image/png" if ext == ".png" else "image/jpeg"

                form = {"chat_id": chat_id}
                if caption:
                    form["caption"] = caption

                r = req_lib.post(
                    url,
                    files={field: (filename, img_bytes, mime)},
                    data=form,
                    timeout=60,
                )
                resp = r.json()
                if resp.get("ok"):
                    msg_id = resp["result"]["message_id"]
                    print(f"✅ [TelegramAutoSend] {filename} → отправлено (Message ID: {msg_id})")
                else:
                    print(f"❌ [TelegramAutoSend] {filename} → ошибка API:")
                    print(json.dumps(resp, indent=2, ensure_ascii=False))

            except Exception as e:
                print(f"💥 [TelegramAutoSend] Ошибка при отправке {filename}: {e}")
                import traceback
                traceback.print_exc()

        sent = 0
        for img_info in images:
            filename  = img_info.get("filename", "")
            subfolder = img_info.get("subfolder", "")

            if not filename:
                continue

            img_path = os.path.join(output_dir, subfolder, filename) if subfolder else os.path.join(output_dir, filename)

            if not os.path.exists(img_path):
                print(f"⚠️ [TelegramAutoSend] Файл не найден: {img_path}")
                continue

            threading.Thread(target=_send, args=(img_path, filename), daemon=True).start()
            sent += 1

        print(f"🚀 [TelegramAutoSend] Поставлено в очередь: {sent} изображений")
        return web.json_response({"ok": True, "queued": sent})

    except Exception as e:
        print(f"💥 [TelegramAutoSend] API ошибка: {e}")
        return web.json_response({"ok": False, "error": str(e)})


WEB_DIRECTORY = "./js"
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
