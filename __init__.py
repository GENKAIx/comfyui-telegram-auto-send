import os
import json
import threading
import requests as req_lib
import folder_paths
import server
from aiohttp import web
from PIL import Image


# ── Метаданные ──────────────────────────────────────────────────────────────

def _extract_metadata_text(img_path):
    """Читает ComfyUI-метаданные из PNG и возвращает отформатированный HTML-текст."""
    try:
        with Image.open(img_path) as img:
            info   = img.info
            width, height = img.size

        lines = [f"📊 <b>Метаданные генерации</b>", f"🖼 Размер: <code>{width}×{height}</code>"]

        prompt_raw = info.get("prompt", "")
        if not prompt_raw:
            lines.append("ℹ️ Метаданные в файле отсутствуют (не PNG или не ComfyUI SaveImage)")
            return "\n".join(lines)

        prompt = json.loads(prompt_raw)

        def find_nodes(*class_types):
            return [v for v in prompt.values() if v.get("class_type") in class_types]

        def resolve(ref):
            if isinstance(ref, list) and len(ref) == 2:
                return prompt.get(str(ref[0]))
            return None

        def trunc(text, n=300):
            text = str(text).strip()
            return text[:n] + "…" if len(text) > n else text

        # Модель
        for node in find_nodes("CheckpointLoaderSimple", "CheckpointLoader", "UNETLoader"):
            model = node["inputs"].get("ckpt_name") or node["inputs"].get("unet_name", "")
            if model:
                lines.append(f"🤖 Модель: <code>{model}</code>")
            break

        # LoRA
        for node in find_nodes("LoraLoader", "LoraLoaderModelOnly"):
            lora = node["inputs"].get("lora_name", "")
            strength = node["inputs"].get("strength_model", "")
            if lora:
                lines.append(f"🎨 LoRA: <code>{lora}</code> (сила: {strength})")

        # KSampler / KSamplerAdvanced
        for node in find_nodes("KSampler", "KSamplerAdvanced"):
            inp = node["inputs"]

            seed      = inp.get("seed") or inp.get("noise_seed", "?")
            steps     = inp.get("steps", "?")
            cfg       = inp.get("cfg", "?")
            sampler   = inp.get("sampler_name", "?")
            scheduler = inp.get("scheduler", "?")
            denoise   = inp.get("denoise", 1.0)

            lines.append(f"🎲 Seed: <code>{seed}</code>")
            lines.append(f"📈 Шаги: <code>{steps}</code>  |  ⚙️ CFG: <code>{cfg}</code>")
            lines.append(f"🎰 Сэмплер: <code>{sampler} / {scheduler}</code>")
            if float(denoise) < 1.0:
                lines.append(f"🔧 Denoise: <code>{denoise}</code>")

            # Промпты
            pos_node = resolve(inp.get("positive"))
            neg_node = resolve(inp.get("negative"))

            if pos_node and pos_node.get("class_type") == "CLIPTextEncode":
                txt = pos_node["inputs"].get("text", "")
                if txt:
                    lines.append(f"\n✏️ <b>Позитивный промпт:</b>\n<code>{trunc(txt)}</code>")

            if neg_node and neg_node.get("class_type") == "CLIPTextEncode":
                txt = neg_node["inputs"].get("text", "")
                if txt:
                    lines.append(f"\n🚫 <b>Негативный промпт:</b>\n<code>{trunc(txt, 200)}</code>")
            break

        # Размер латента (если нет из изображения)
        for node in find_nodes("EmptyLatentImage", "EmptySD3LatentImage"):
            inp = node["inputs"]
            lw  = inp.get("width")
            lh  = inp.get("height")
            if lw and lh:
                lines[1] = f"🖼 Размер: <code>{lw}×{lh}</code>"
            break

        return "\n".join(lines)

    except Exception as e:
        return f"⚠️ Не удалось извлечь метаданные: {e}"


# ── API-маршрут ──────────────────────────────────────────────────────────────

@server.PromptServer.instance.routes.post("/telegram_auto/send")
async def telegram_auto_send(request):
    try:
        data = await request.json()

        images        = data.get("images", [])
        bot_token     = data.get("bot_token", "").strip()
        chat_id       = data.get("chat_id", "").strip()
        caption       = data.get("caption", "").strip()
        send_as_file  = data.get("send_as_file", False)
        silent        = data.get("silent", False)
        send_metadata = data.get("send_metadata", False)

        send_as_file  = send_as_file in (True, "true", "True", 1, "1")
        silent        = silent       in (True, "true", "True", 1, "1")
        send_metadata = send_metadata in (True, "true", "True", 1, "1")

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

                form = {
                    "chat_id":             chat_id,
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

                if not resp.get("ok"):
                    print(f"❌ [TelegramAutoSend] {filename} → ошибка API:")
                    print(json.dumps(resp, indent=2, ensure_ascii=False))
                    return

                msg_id = resp["result"]["message_id"]
                mode   = "🔕 тихо" if silent else "🔔"
                print(f"✅ [TelegramAutoSend] {filename} → отправлено {mode} (Message ID: {msg_id})")

                # Отправка метаданных как ответ на сообщение с изображением
                if send_metadata:
                    meta_text = _extract_metadata_text(img_path)
                    meta_url  = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                    meta_resp = req_lib.post(
                        meta_url,
                        data={
                            "chat_id":              chat_id,
                            "text":                 meta_text,
                            "parse_mode":           "HTML",
                            "reply_to_message_id":  msg_id,
                            "disable_notification": "true" if silent else "false",
                        },
                        timeout=30,
                    ).json()
                    if meta_resp.get("ok"):
                        print(f"📋 [TelegramAutoSend] Метаданные {filename} → отправлены")
                    else:
                        print(f"⚠️ [TelegramAutoSend] Метаданные ошибка: {json.dumps(meta_resp, ensure_ascii=False)}")

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
