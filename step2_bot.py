import os
import logging
import random
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.executor import start_webhook

# ---------- Настройки ----------
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8689690200:AAH7rUhbaqh1RjBz-dqmJCyGE0wcDj3uGmw')
# Важно: Render автоматически подставляет внешний URL в переменную RENDER_EXTERNAL_URL
WEBHOOK_HOST = os.environ.get('RENDER_EXTERNAL_URL', 'https://neomatrix-bot-docker.onrender.com')
WEBHOOK_PATH = '/webhook'  # Путь, на который Telegram будет отправлять обновления
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
PORT = int(os.environ.get('PORT', 10000))  # Render ожидает порт 10000

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# Временное хранилище (без базы данных)
players = {}
active_battles = {}

# ---------- Команды бота ----------
# (весь код команд остаётся таким же, как ты уже вставил)

# ... (вставь сюда все команды из предыдущего рабочего кода, я их не меняю)

# ---------- Вебхук ----------
async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)
    print(f"✅ Webhook установлен на {WEBHOOK_URL}")

async def on_shutdown(dp):
    await bot.delete_webhook()
    print("👋 Webhook удалён")

if __name__ == '__main__':
    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True,
        host='0.0.0.0',
        port=PORT
    )