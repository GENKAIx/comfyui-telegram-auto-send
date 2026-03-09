import os
import json
import queue
import threading
import requests as req_lib
import folder_paths
import server
from aiohttp import web
from PIL import Image


# ── Постоянная очередь отправки ──────────────────────────────────────────────
# Все задачи кладутся в _send_queue и обрабатываются одним фоновым потоком
# последовательно — так нет гонок, нет зависших daemon-потоков.

_send_queue: queue.Queue = queue.Queue()


def _worker_loop():
    print("[TelegramAutoSend] Worker thread started")
    while True:
        task = _send_queue.get()          # блокируемся, пока нет задачи
        try:
            task()
        except Exception as exc:
            print(f"[TelegramAutoSend] ❌ Task error: {exc}")
            import traceback
            traceback.print_exc()
        finally:
            _send_queue.task_done()


_worker = threading.Thread(
    target=_worker_loop,
    daemon=True,
    name="TelegramAutoSend-Worker",
)
_worker.start()


# ── Чтение метаданных из PNG ──────────────────────────────────────────────────

def _read_png_info(img_path: str) -> dict:
    """Читает PNG-чанки ComfyUI (prompt / workflow) через Pillow."""
    try:
        with Image.open(img_path) as img:
            # Pillow кладёт tEXt/iTXt в .info и иногда в .text
            info: dict = dict(img.info or {})
            if hasattr(img, "text") and isinstance(img.text, dict):
                info.update(img.text)
        return info
    except Exception as exc:
        print(f"[TelegramAutoSend] ⚠️ Cannot open {img_path}: {exc}")
        return {}


def _resolve_text(ref, nodes: dict, depth: int = 6) -> str:
    """
    Рекурсивно идёт по графу ComfyUI и ищет текст промпта.
    ref — либо строка с текстом, либо ссылка ["node_id", output_idx].
    """
    if depth <= 0:
        return ""
    if isinstance(ref, str):
        return ref
    if not (isinstance(ref, list) and len(ref) == 2):
        return ""

    node = nodes.get(str(ref[0]))
    if not node:
        return ""

    cls = node.get("class_type", "")
    inp = node.get("inputs", {})

    # Узлы, которые непосредственно содержат текст
    if cls in ("CLIPTextEncode", "CLIPTextEncodeSDXL", "Text Multiline",
               "CR Text", "smZ CLIPTextEncode"):
        text = inp.get("text") or inp.get("text_g") or inp.get("text_l", "")
        return _resolve_text(text, nodes, depth - 1) if isinstance(text, list) else str(text)

    # Узлы-прокси — идём по их входам в поисках текста
    for val in inp.values():
        if isinstance(val, list) and len(val) == 2:
            result = _resolve_text(val, nodes, depth - 1)
            if result:
                return result
    return ""


def _build_metadata_caption(user_caption: str, img_path: str) -> str:
    """
    Собирает финальную подпись: пользовательский текст + метаданные.
    Укладывается в 1024 символа (лимит Telegram).
    """
    LIMIT = 1024

    info = _read_png_info(img_path)
    prompt_raw = info.get("prompt", "")

    # Размер изображения
    try:
        with Image.open(img_path) as img:
            w, h = img.size
        size_str = f"{w}×{h}"
    except Exception:
        size_str = "?"

    # Собираем части подписи
    parts: list[str] = []
    if user_caption:
        parts.append(user_caption)

    if not prompt_raw:
        # Метаданных нет — просто добавляем размер
        parts.append(f"🖼 {size_str}")
        return "\n".join(parts)[:LIMIT]

    try:
        nodes: dict = json.loads(prompt_raw)
    except Exception:
        parts.append(f"🖼 {size_str}")
        return "\n".join(parts)[:LIMIT]

    def find_first(*class_types):
        for node in nodes.values():
            if node.get("class_type") in class_types:
                return node
        return None

    meta_lines: list[str] = [f"🖼 {size_str}"]

    # Модель
    ckpt_node = find_first(
        "CheckpointLoaderSimple", "CheckpointLoader",
        "CheckpointLoaderNF4", "unCLIPCheckpointLoader",
    )
    if ckpt_node:
        model = ckpt_node["inputs"].get("ckpt_name", "")
        if model:
            meta_lines.append(f"🤖 {os.path.basename(model)}")

    # LoRA (первая найденная)
    lora_node = find_first("LoraLoader", "LoraLoaderModelOnly")
    if lora_node:
        lora_inp = lora_node["inputs"]
        lora_name = lora_inp.get("lora_name", "")
        strength  = lora_inp.get("strength_model", "")
        if lora_name:
            meta_lines.append(f"🎨 LoRA: {os.path.basename(lora_name)} ({strength})")

    # KSampler
    ks_node = find_first("KSampler", "KSamplerAdvanced")
    pos_text = neg_text = ""
    if ks_node:
        inp = ks_node["inputs"]
        seed      = inp.get("seed") if inp.get("seed") is not None else inp.get("noise_seed", "?")
        steps     = inp.get("steps", "?")
        cfg       = inp.get("cfg", "?")
        sampler   = inp.get("sampler_name", "?")
        scheduler = inp.get("scheduler", "?")
        denoise   = inp.get("denoise", 1.0)

        meta_lines.append(f"🎲 {seed}  📈 {steps} шаг.  ⚙️ CFG {cfg}")
        meta_lines.append(f"🎰 {sampler} / {scheduler}" +
                          (f"  🔧 {denoise}" if float(denoise) < 1.0 else ""))

        pos_text = _resolve_text(inp.get("positive"), nodes)
        neg_text = _resolve_text(inp.get("negative"), nodes)

    # Склеиваем метаданные
    meta_block = "\n".join(meta_lines)

    # Резервируем место под промпты
    base = ("\n".join(parts) + "\n" + meta_block).strip()
    remaining = LIMIT - len(base) - 4   # 4 = запас на переносы

    if pos_text and remaining > 30:
        pos_cut = pos_text[:min(len(pos_text), max(30, int(remaining * 0.65)))]
        if len(pos_cut) < len(pos_text):
            pos_cut += "…"
        base += f"\n✏️ {pos_cut}"
        remaining = LIMIT - len(base) - 2

    if neg_text and remaining > 20:
        neg_cut = neg_text[:min(len(neg_text), max(20, remaining))]
        if len(neg_cut) < len(neg_text):
            neg_cut += "…"
        base += f"\n🚫 {neg_cut}"

    return base[:LIMIT]


# ── API-маршрут ──────────────────────────────────────────────────────────────

@server.PromptServer.instance.routes.post("/telegram_auto/send")
async def telegram_auto_send(request):
    try:
        data = await request.json()

        images         = data.get("images", [])
        bot_token      = data.get("bot_token", "").strip()
        chat_id        = data.get("chat_id", "").strip()
        caption        = data.get("caption", "").strip()
        send_as_file   = data.get("send_as_file",  False)
        silent         = data.get("silent",         False)
        send_metadata  = data.get("send_metadata",  False)

        send_as_file  = send_as_file  in (True, "true", "True", 1, "1")
        silent        = silent        in (True, "true", "True", 1, "1")
        send_metadata = send_metadata in (True, "true", "True", 1, "1")

        if not bot_token or not chat_id:
            return web.json_response({"ok": False, "error": "Не указан bot_token или chat_id"})

        output_dir = folder_paths.get_output_directory()

        def make_task(img_path: str, filename: str):
            """Замыкание — создаёт задачу для конкретного файла."""
            def task():
                try:
                    # Строим подпись (с метаданными или без)
                    final_caption = (
                        _build_metadata_caption(caption, img_path)
                        if send_metadata
                        else caption
                    )

                    with open(img_path, "rb") as f:
                        img_bytes = f.read()

                    method = "sendDocument" if send_as_file else "sendPhoto"
                    field  = "document"     if send_as_file else "photo"
                    url    = f"https://api.telegram.org/bot{bot_token}/{method}"
                    ext    = os.path.splitext(filename)[1].lower()
                    mime   = "image/png" if ext == ".png" else "image/jpeg"

                    form = {
                        "chat_id":              chat_id,
                        "disable_notification": "true" if silent else "false",
                    }
                    if final_caption:
                        form["caption"] = final_caption

                    r = req_lib.post(
                        url,
                        files={field: (filename, img_bytes, mime)},
                        data=form,
                        timeout=60,
                    )
                    resp = r.json()

                    if resp.get("ok"):
                        msg_id = resp["result"]["message_id"]
                        flags  = " ".join(filter(None, [
                            "🔕" if silent else "🔔",
                            "📋" if send_metadata else "",
                        ]))
                        print(f"✅ [TelegramAutoSend] {filename} → msg {msg_id} {flags}")
                    else:
                        print(f"❌ [TelegramAutoSend] {filename} ошибка API:")
                        print(json.dumps(resp, indent=2, ensure_ascii=False))

                except Exception as exc:
                    print(f"💥 [TelegramAutoSend] {filename}: {exc}")
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
                print(f"⚠️ [TelegramAutoSend] Файл не найден: {img_path}")
                continue

            _send_queue.put(make_task(img_path, filename))
            queued += 1

        print(f"🚀 [TelegramAutoSend] Добавлено в очередь: {queued} | В очереди сейчас: {_send_queue.qsize()}")
        return web.json_response({"ok": True, "queued": queued})

    except Exception as exc:
        print(f"💥 [TelegramAutoSend] API ошибка: {exc}")
        return web.json_response({"ok": False, "error": str(exc)})


WEB_DIRECTORY = "./js"
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
