import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

app.registerExtension({
    name: "Comfy.TelegramAutoSend",

    async setup() {

        // ── Настройки ────────────────────────────────────────────────────────

        app.ui.settings.addSetting({
            id: "TelegramAutoSend.Enabled",
            name: "🤖 Telegram AutoSend: Включить автоотправку",
            type: "boolean",
            defaultValue: false,
            tooltip: "Если включено — все результаты SaveImage автоматически отправляются в Telegram",
        });

        app.ui.settings.addSetting({
            id: "TelegramAutoSend.BotToken",
            name: "🤖 Telegram AutoSend: Токен бота",
            type: "text",
            defaultValue: "",
            tooltip: "Токен вашего Telegram-бота (получить у @BotFather)",
        });

        app.ui.settings.addSetting({
            id: "TelegramAutoSend.ChatId",
            name: "🤖 Telegram AutoSend: Chat ID / Channel ID",
            type: "text",
            defaultValue: "",
            tooltip: "ID чата или канала (например -1001234567890)",
        });

        app.ui.settings.addSetting({
            id: "TelegramAutoSend.Caption",
            name: "🤖 Telegram AutoSend: Подпись к изображению",
            type: "text",
            defaultValue: "Генерация {time}",
            tooltip: "Подпись. Поддерживает {time} и {date}",
        });

        app.ui.settings.addSetting({
            id: "TelegramAutoSend.SendAsFile",
            name: "🤖 Telegram AutoSend: Отправлять как файл (без сжатия Telegram)",
            type: "boolean",
            defaultValue: false,
            tooltip: "Включить, чтобы получать оригинальный PNG без пережатия Telegram",
        });

        app.ui.settings.addSetting({
            id: "TelegramAutoSend.Silent",
            name: "🤖 Telegram AutoSend: Бесшумная отправка (без уведомления)",
            type: "boolean",
            defaultValue: false,
            tooltip: "Сообщение придёт без звука и вибрации — как в режиме без звука",
        });

        app.ui.settings.addSetting({
            id: "TelegramAutoSend.SendMetadata",
            name: "🤖 Telegram AutoSend: Отправлять метаданные (модель, сид, промпт…)",
            type: "boolean",
            defaultValue: false,
            tooltip: "После изображения отправляется отдельное сообщение с параметрами генерации",
        });

        // ── Перехват выполнения нод ──────────────────────────────────────────

        api.addEventListener("executed", async (e) => {
            try {
                const enabled = app.ui.settings.getSettingValue("TelegramAutoSend.Enabled", false);
                if (!enabled) return;

                const output = e.detail?.output;
                if (!output?.images) return;

                // Только SaveImage пишет type="output"; PreviewImage пишет type="temp"
                const outputImages = output.images.filter(img => img.type === "output");
                if (outputImages.length === 0) return;

                const botToken = app.ui.settings.getSettingValue("TelegramAutoSend.BotToken", "").trim();
                const chatId   = app.ui.settings.getSettingValue("TelegramAutoSend.ChatId", "").trim();

                if (!botToken || !chatId) {
                    console.warn("[TelegramAutoSend] ⚠️ Укажите Токен бота и Chat ID в настройках (Settings → Telegram AutoSend)");
                    return;
                }

                // Форматируем подпись
                const now     = new Date();
                const timeStr = now.toLocaleTimeString("ru-RU");
                const dateStr = now.toLocaleDateString("ru-RU");
                let caption   = app.ui.settings.getSettingValue("TelegramAutoSend.Caption", "Генерация {time}");
                caption = caption.replace(/\{time\}/g, timeStr).replace(/\{date\}/g, dateStr);

                const sendAsFile  = app.ui.settings.getSettingValue("TelegramAutoSend.SendAsFile",  false);
                const silent      = app.ui.settings.getSettingValue("TelegramAutoSend.Silent",      false);
                const sendMetadata = app.ui.settings.getSettingValue("TelegramAutoSend.SendMetadata", false);

                const modeLabel = [
                    sendAsFile   ? "📄 файл" : "🖼 фото",
                    silent       ? "🔕 тихо" : "🔔",
                    sendMetadata ? "📋 +метаданные" : "",
                ].filter(Boolean).join(" | ");

                console.log(`[TelegramAutoSend] 📤 ${outputImages.length} изображений (${modeLabel})`);

                const response = await fetch("/telegram_auto/send", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        images:        outputImages,
                        bot_token:     botToken,
                        chat_id:       chatId,
                        caption:       caption,
                        send_as_file:  sendAsFile,
                        silent:        silent,
                        send_metadata: sendMetadata,
                    }),
                });

                const result = await response.json();
                if (result.ok) {
                    console.log(`[TelegramAutoSend] ✅ Поставлено в очередь: ${result.queued} изображений`);
                } else {
                    console.error("[TelegramAutoSend] ❌ Ошибка:", result.error);
                }

            } catch (err) {
                console.error("[TelegramAutoSend] 💥 Неожиданная ошибка:", err);
            }
        });

        console.log("[TelegramAutoSend] ✅ Расширение загружено");
    },
});
