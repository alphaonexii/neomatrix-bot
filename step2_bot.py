import os
import logging
import random
from datetime import datetime, timedelta
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

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

# ---------- Команды бота ----------
# (весь код команд, который у тебя уже есть, остаётся без изменений)
# Я не буду его дублировать здесь, чтобы не загромождать ответ,
# но ты должен вставить сюда все свои обработчики (@dp.message_handler и @dp.callback_query_handler)
# из предыдущего файла. Они у тебя уже есть, просто скопируй их.

# ВНИМАНИЕ: вставь сюда весь блок команд, который был в твоём последнем сообщении
# (от @dp.message_handler(commands=['start']) до последнего обработчика перед комментарием # ---------- Вебхук ----------)

# ---------- Вебхук (обработчик POST-запросов) ----------
async def webhook_handler(request):
    """Принимает POST-запросы от Telegram и передаёт их диспетчеру"""
    try:
        update_data = await request.json()
        update = types.Update(**update_data)
        await dp.process_update(update)
        return web.Response(status=200)
    except Exception as e:
        logging.error(f"Ошибка при обработке вебхука: {e}")
        return web.Response(status=500)

# ---------- Запуск приложения ----------
async def on_startup(app):
    # Устанавливаем вебхук и проверяем результат
    result = await bot.set_webhook(WEBHOOK_URL)
    if result:
        print(f"✅ Webhook успешно установлен на {WEBHOOK_URL}")
    else:
        print(f"❌ Ошибка при установке вебхука!")
    # Дополнительно выводим информацию о вебхуке для проверки
    info = await bot.get_webhook_info()
    print(f"📊 Информация о вебхуке: url={info.url}, pending_updates={info.pending_update_count}")

async def on_shutdown(app):
    await bot.delete_webhook()
    print("👋 Webhook удалён")

app = web.Application()
app.router.add_post(WEBHOOK_PATH, webhook_handler)  # только POST на /webhook
app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

if __name__ == '__main__':
    print(f"🚀 Запуск сервера на порту {PORT}")
    web.run_app(app, host='0.0.0.0', port=PORT)