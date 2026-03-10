import os
import json
import queue
import threading
import requests as req_lib
import folder_paths
import server
from aiohttp import web


# ── Persistent send queue ────────────────────────────────────────────────────
# All send tasks are processed by a single background worker thread,
# one at a time, in order — no race conditions, no dangling daemon threads.

_send_queue: queue.Queue = queue.Queue()


def _worker_loop():
    print("[TelegramAutoSend] Worker thread started")
    while True:
        task = _send_queue.get()
        try:
            task()
        except Exception as exc:
            print(f"[TelegramAutoSend] Task error: {exc}")
            import traceback
            traceback.print_exc()
        finally:
            _send_queue.task_done()


_worker_thread = threading.Thread(
    target=_worker_loop,
    daemon=True,
    name="TelegramAutoSend-Worker",
)
_worker_thread.start()


# ── API route ────────────────────────────────────────────────────────────────

@server.PromptServer.instance.routes.post("/telegram_auto/send")
async def telegram_auto_send(request):
    try:
        data = await request.json()

        images       = data.get("images", [])
        bot_token    = data.get("bot_token", "").strip()
        chat_id      = data.get("chat_id", "").strip()
        caption      = data.get("caption", "").strip()
        send_as_file = data.get("send_as_file", False)
        silent       = data.get("silent", False)

        send_as_file = send_as_file in (True, "true", "True", 1, "1")
        silent       = silent       in (True, "true", "True", 1, "1")

        if not bot_token or not chat_id:
            return web.json_response({"ok": False, "error": "bot_token or chat_id is missing"})

        output_dir = folder_paths.get_output_directory()

        def make_task(img_path: str, filename: str):
            def task():
                try:
                    with open(img_path, "rb") as f:
                        img_bytes = f.read()

                    method = "sendDocument" if send_as_file else "sendPhoto"
                    field  = "document"     if send_as_file else "photo"
                    url    = f"https://api.telegram.org/bot{bot_token}/{method}"

                    ext  = os.path.splitext(filename)[1].lower()
                    mime = "image/png" if ext == ".png" else "image/jpeg"

                    form = {
                        "chat_id":              chat_id,
                        "disable_notification": "true" if silent else "false",
                    }
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
                        print(f"[TelegramAutoSend] ✅ {filename} sent (msg {msg_id})")
                    else:
                        print(f"[TelegramAutoSend] ❌ {filename} — API error:")
                        print(json.dumps(resp, indent=2, ensure_ascii=False))

                except Exception as exc:
                    print(f"[TelegramAutoSend] ❌ Failed to send {filename}: {exc}")
                    import traceback
                    traceback.print_exc()

            return task

        queued = 0
        for img_info in images:
            filename  = img_info.get("filename", "")
            subfolder = img_info.get("subfolder", "")

            if not filename:
                continue

            img_path = (
                os.path.join(output_dir, subfolder, filename)
                if subfolder
                else os.path.join(output_dir, filename)
            )

            if not os.path.exists(img_path):
                print(f"[TelegramAutoSend] ⚠️ File not found: {img_path}")
                continue

            _send_queue.put(make_task(img_path, filename))
            queued += 1

        print(f"[TelegramAutoSend] Queued: {queued} | Queue size: {_send_queue.qsize()}")
        return web.json_response({"ok": True, "queued": queued})

    except Exception as exc:
        print(f"[TelegramAutoSend] ❌ API error: {exc}")
        return web.json_response({"ok": False, "error": str(exc)})


WEB_DIRECTORY = "./js"
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
