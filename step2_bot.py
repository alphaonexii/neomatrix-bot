import os
import logging
import random
from datetime import datetime, timedelta
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.executor import setup_webhook

# ---------- Настройки ----------
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8689690200:AAH7rUhbaqh1RjBz-dqmJCyGE0wcDj3uGmw')
WEBHOOK_HOST = os.environ.get('RENDER_EXTERNAL_URL', 'https://neomatrix-bot-docker.onrender.com')
WEBHOOK_PATH = '/webhook'
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
PORT = int(os.environ.get('PORT', 10000))

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# Временное хранилище
players = {}
active_battles = {}

# ---------- Команды бота (полностью из предыдущего кода) ----------
# Вставь сюда все команды (start, profile, battle, daily, top, shop и колбэки)
# (я не буду повторять их здесь, чтобы не загромождать ответ, но в твоём файле они уже есть)

# ---------- Обработчик вебхука ----------
async def webhook_handler(request):
    """Принимает POST-запросы от Telegram и передаёт их диспетчеру"""
    try:
        update = types.Update(**(await request.json()))
        await dp.process_update(update)
        return web.Response(status=200)
    except Exception as e:
        logging.error(f"Ошибка при обработке вебхука: {e}")
        return web.Response(status=500)

# ---------- Запуск приложения ----------
async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL)
    print(f"✅ Webhook установлен на {WEBHOOK_URL}")

async def on_shutdown(app):
    await bot.delete_webhook()
    print("👋 Webhook удалён")

app = web.Application()
app.router.add_post(WEBHOOK_PATH, webhook_handler)
app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

if __name__ == '__main__':
    print(f"🚀 Запуск сервера на порту {PORT}")
    web.run_app(app, host='0.0.0.0', port=PORT)