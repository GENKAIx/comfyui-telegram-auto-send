import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

app.registerExtension({
    name: "Comfy.TelegramAutoSend",

    async setup() {

        // ── Settings (Settings → Telegram AutoSend) ──────────────────────────

        app.ui.settings.addSetting({
            id: "TelegramAutoSend.Enabled",
            name: "🤖 Telegram AutoSend: Enable auto-send",
            type: "boolean",
            defaultValue: false,
            tooltip: "When enabled, all SaveImage results are automatically sent to Telegram",
        });

        app.ui.settings.addSetting({
            id: "TelegramAutoSend.BotToken",
            name: "🤖 Telegram AutoSend: Bot token",
            type: "text",
            defaultValue: "",
            tooltip: "Your Telegram bot token (get one from @BotFather)",
        });

        app.ui.settings.addSetting({
            id: "TelegramAutoSend.ChatId",
            name: "🤖 Telegram AutoSend: Chat ID / Channel ID",
            type: "text",
            defaultValue: "",
            tooltip: "Target chat or channel ID (e.g. -1001234567890)",
        });

        app.ui.settings.addSetting({
            id: "TelegramAutoSend.Caption",
            name: "🤖 Telegram AutoSend: Image caption",
            type: "text",
            defaultValue: "Generation {time}",
            tooltip: "Caption template. Supports {time} and {date} placeholders",
        });

        app.ui.settings.addSetting({
            id: "TelegramAutoSend.SendAsFile",
            name: "🤖 Telegram AutoSend: Send as file (no Telegram compression)",
            type: "boolean",
            defaultValue: false,
            tooltip: "Enable to receive original PNG without Telegram re-compression",
        });

        app.ui.settings.addSetting({
            id: "TelegramAutoSend.Silent",
            name: "🤖 Telegram AutoSend: Silent send (no notification sound)",
            type: "boolean",
            defaultValue: false,
            tooltip: "Message is delivered silently — no sound or vibration",
        });

        // ── Intercept node execution ─────────────────────────────────────────
        // SaveImage outputs type="output"; PreviewImage outputs type="temp" — filtered out

        api.addEventListener("executed", async (e) => {
            try {
                const enabled = app.ui.settings.getSettingValue("TelegramAutoSend.Enabled", false);
                if (!enabled) return;

                const output = e.detail?.output;
                if (!output?.images) return;

                const outputImages = output.images.filter(img => img.type === "output");
                if (outputImages.length === 0) return;

                const botToken = app.ui.settings.getSettingValue("TelegramAutoSend.BotToken", "").trim();
                const chatId   = app.ui.settings.getSettingValue("TelegramAutoSend.ChatId", "").trim();

                if (!botToken || !chatId) {
                    console.warn("[TelegramAutoSend] ⚠️ Bot token and Chat ID must be set in Settings → Telegram AutoSend");
                    return;
                }

                const now     = new Date();
                const timeStr = now.toLocaleTimeString("en-US", { hour12: false });
                const dateStr = now.toLocaleDateString("en-US");
                let caption   = app.ui.settings.getSettingValue("TelegramAutoSend.Caption", "Generation {time}");
                caption = caption.replace(/\{time\}/g, timeStr).replace(/\{date\}/g, dateStr);

                const sendAsFile = app.ui.settings.getSettingValue("TelegramAutoSend.SendAsFile", false);
                const silent     = app.ui.settings.getSettingValue("TelegramAutoSend.Silent",     false);

                console.log(`[TelegramAutoSend] Sending ${outputImages.length} image(s) as ${sendAsFile ? "file" : "photo"}${silent ? " (silent)" : ""}`);

                const response = await fetch("/telegram_auto/send", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        images:       outputImages,
                        bot_token:    botToken,
                        chat_id:      chatId,
                        caption:      caption,
                        send_as_file: sendAsFile,
                        silent:       silent,
                    }),
                });

                const result = await response.json();
                if (result.ok) {
                    console.log(`[TelegramAutoSend] ✅ Queued: ${result.queued} image(s)`);
                } else {
                    console.error("[TelegramAutoSend] ❌ Error:", result.error);
                }

            } catch (err) {
                console.error("[TelegramAutoSend] ❌ Unexpected error:", err);
            }
        });

        console.log("[TelegramAutoSend] ✅ Extension loaded");
    },
});
