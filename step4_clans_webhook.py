import os
import sys
import logging
import random
import asyncio
import asyncpg
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.executor import start_webhook

# ---------- Диагностика ----------
print("=== ЗАПУСК БОТА ===", file=sys.stderr)

BOT_TOKEN = os.environ.get('BOT_TOKEN', '8689690200:AAH7rUhbaqh1RjBz-dqmJCyGE0wcDj3uGmw')
DATABASE_URL = os.environ.get('DATABASE_URL')
WEBHOOK_HOST = os.environ.get('RENDER_EXTERNAL_URL', 'https://neomatrix-bot-docker.onrender.com')
WEBHOOK_PATH = '/webhook'
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
PORT = int(os.environ.get('PORT', 10000))

if not DATABASE_URL:
    print("⚠️ DATABASE_URL не задана – работа без сохранения данных", file=sys.stderr)

print(f"🔗 WEBHOOK_URL = {WEBHOOK_URL}", file=sys.stderr)
print(f"📡 PORT = {PORT}", file=sys.stderr)

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# ---------- Хранилища ----------
active_battles = {}
pvp_queue = []
active_pvp_battles = {}
memory_players = {}
memory_pvp_ratings = {}
memory_clans = {}
memory_clan_members = {}
memory_clan_messages = {}

# ---------- Шаблоны врагов ----------
ENEMY_TEMPLATES = [ ... ]  # (весь код шаблонов – без изменений, вставь сюда)

def generate_enemy(player_level): ...  # (без изменений)

# ---------- Работа с БД ----------
# (все функции для БД, PvP и кланов – остаются без изменений, вставь их сюда)

# ---------- Вебхук с корректным ожиданием ----------
async def on_startup(dp):
    print(">>> on_startup начат", file=sys.stderr)
    try:
        await bot.set_webhook(WEBHOOK_URL)
        print(f"✅ Webhook установлен на {WEBHOOK_URL}", file=sys.stderr)
        info = await bot.get_webhook_info()
        print(f"ℹ️ Текущий вебхук: {info.url}", file=sys.stderr)
    except Exception as e:
        print(f"❌ Ошибка при установке вебхука: {e}", file=sys.stderr)

async def on_shutdown(dp):
    print(">>> on_shutdown начат", file=sys.stderr)
    try:
        await bot.delete_webhook()
        print("👋 Webhook удалён", file=sys.stderr)
    except Exception as e:
        print(f"❌ Ошибка при удалении вебхука: {e}", file=sys.stderr)

if __name__ == '__main__':
    print("=== Запуск main ===", file=sys.stderr)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(init_db())
        print("=== init_db завершён, запускаем вебхук ===", file=sys.stderr)
        # Запускаем вебхук и ЖДЁМ его завершения (он будет работать, пока не остановят)
        start_webhook(
            dispatcher=dp,
            webhook_path=WEBHOOK_PATH,
            on_startup=on_startup,
            on_shutdown=on_shutdown,
            skip_updates=True,
            host='0.0.0.0',
            port=PORT
        )
        # Этот код выполнится только после остановки вебхука
        print("⚠️ Вебхук остановлен", file=sys.stderr)
    except Exception as e:
        print(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)