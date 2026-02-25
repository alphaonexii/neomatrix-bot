import os
import logging
import random
import threading
import asyncpg
from datetime import datetime, timedelta
from flask import Flask, jsonify
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import executor

# ---------- Настройки ----------
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8689690200:AAH7rUhbaqh1RjBz-dqmJCyGE0wcDj3uGmw')
DATABASE_URL = os.environ.get('DATABASE_URL')
PORT = int(os.environ.get('PORT', 10000))

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

active_battles = {}  # для временных битв (в памяти)

# ---------- Работа с БД ----------
async def init_db():
    """Создаёт таблицы, если их нет"""
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS players (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            level INT DEFAULT 1,
            exp INT DEFAULT 0,
            health INT DEFAULT 100,
            max_health INT DEFAULT 100,
            energy INT DEFAULT 100,
            max_energy INT DEFAULT 100,
            credits INT DEFAULT 1000,
            monsters_killed INT DEFAULT 0,
            last_daily TIMESTAMP
        )
    ''')
    await conn.close()
    print("✅ Таблицы созданы/проверены")

async def get_player(user_id):
    conn = await asyncpg.connect(DATABASE_URL)
    row = await conn.fetchrow('SELECT * FROM players WHERE user_id = $1', user_id)
    await conn.close()
    return row

async def create_player(user_id, username):
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute('''
        INSERT INTO players (user_id, username, last_daily) VALUES ($1, $2, NOW())
    ''', user_id, username)
    await conn.close()

async def update_player(user_id, **kwargs):
    set_clause = ', '.join(f"{k} = ${i+2}" for i, k in enumerate(kwargs))
    values = [user_id] + list(kwargs.values())
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute(f'UPDATE players SET {set_clause} WHERE user_id = $1', *values)
    await conn.close()

# ---------- Команды бота (адаптированы под БД) ----------
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "NoName"
    player = await get_player(user_id)
    if not player:
        await create_player(user_id, username)
        player = await get_player(user_id)
    await message.reply(
        f"🌟 Добро пожаловать, {message.from_user.first_name}!\n"
        f"Уровень: {player['level']} | Креды: {player['credits']}\n\n"
        f"⚔️ /battle - Битва с монстрами\n"
        f"📊 /profile - Профиль\n"
        f"🎁 /daily - Бонус\n"
        f"🏆 /top - Топ игроков\n"
        f"🏪 /shop - Магазин"
    )

@dp.message_handler(commands=['profile'])
async def cmd_profile(message: types.Message):
    user_id = message.from_user.id
    player = await get_player(user_id)
    if not player:
        await message.reply("Сначала введи /start")
        return
    await message.reply(
        f"📊 **ПРОФИЛЬ**\n\n"
        f"Уровень: {player['level']}\n"
        f"Опыт: {player['exp']}/100\n"
        f"❤️ HP: {player['health']}/{player['max_health']}\n"
        f"⚡ Энергия: {player['energy']}/{player['max_energy']}\n"
        f"💰 Креды: {player['credits']}\n"
        f"👾 Убито монстров: {player['monsters_killed']}",
        parse_mode="Markdown"
    )

@dp.message_handler(commands=['battle'])
async def cmd_battle(message: types.Message):
    user_id = message.from_user.id
    player = await get_player(user_id)
    if not player:
        await message.reply("Сначала введи /start")
        return
    if player['energy'] < 10:
        await message.reply("⚡ Недостаточно энергии! Используй /daily")
        return

    enemy = {"name": "🛡️ Дрон-охранник", "health": 50, "damage": 10, "exp": 15, "credits": 40}
    battle_id = f"{user_id}_{datetime.now().timestamp()}"
    active_battles[battle_id] = {
        'player_id': user_id,
        'enemy': enemy,
        'enemy_hp': enemy['health']
    }

    await update_player(user_id, energy=player['energy'] - 10)

    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("⚔️ Атака", callback_data=f"attack_{battle_id}"),
        InlineKeyboardButton("🏃 Убежать", callback_data=f"run_{battle_id}")
    )
    await message.reply(
        f"⚔️ **БИТВА**\n\nВраг: {enemy['name']}\n❤️ {enemy['health']}",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@dp.callback_query_handler(lambda c: c.data.startswith('attack_'))
async def attack(callback: types.CallbackQuery):
    battle_id = callback.data.replace('attack_', '')
    if battle_id not in active_battles:
        await callback.message.reply("⚠️ Битва уже закончена")
        await callback.answer()
        return
    battle = active_battles[battle_id]
    user_id = battle['player_id']
    damage = random.randint(15, 25)
    battle['enemy_hp'] -= damage

    if battle['enemy_hp'] <= 0:
        # Победа
        player = await get_player(user_id)
        new_exp = player['exp'] + 15
        new_level = player['level']
        new_credits = player['credits'] + 40
        if new_exp >= 100:
            new_level += 1
            new_exp -= 100
            new_max_health = player['max_health'] + 10
            new_health = new_max_health
            await update_player(user_id,
                exp=new_exp,
                level=new_level,
                credits=new_credits,
                max_health=new_max_health,
                health=new_health,
                monsters_killed=player['monsters_killed'] + 1
            )
            level_up = "\n📈 **УРОВЕНЬ ПОВЫШЕН!**"
        else:
            await update_player(user_id,
                exp=new_exp,
                credits=new_credits,
                monsters_killed=player['monsters_killed'] + 1
            )
            level_up = ""
        del active_battles[battle_id]
        await callback.message.edit_text(f"🎉 **ПОБЕДА!** +15✨ +40💰{level_up}")
    else:
        await callback.message.edit_text(
            f"⚔️ Ты нанёс {damage} урона!\n❤️ У врага осталось: {battle['enemy_hp']}"
        )
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('run_'))
async def run(callback: types.CallbackQuery):
    battle_id = callback.data.replace('run_', '')
    if battle_id in active_battles:
        del active_battles[battle_id]
    await callback.message.edit_text("🏃 Ты убежал с поля боя")
    await callback.answer()

@dp.message_handler(commands=['daily'])
async def cmd_daily(message: types.Message):
    user_id = message.from_user.id
    player = await get_player(user_id)
    if not player:
        await message.reply("Сначала введи /start")
        return
    now = datetime.now()
    last = player['last_daily']
    if last and (now - last) < timedelta(days=1):
        left = timedelta(days=1) - (now - last)
        hours = left.seconds // 3600
        await message.reply(f"⏳ Бонус через {hours}ч")
    else:
        bonus = 100 + player['level'] * 10
        await update_player(user_id,
            credits=player['credits'] + bonus,
            energy=player['max_energy'],
            health=player['max_health'],
            last_daily=now
        )
        await message.reply(f"🎁 Получено {bonus}💰 и полная энергия!")

@dp.message_handler(commands=['top'])
async def cmd_top(message: types.Message):
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch('SELECT username, level, monsters_killed FROM players ORDER BY level DESC, monsters_killed DESC LIMIT 5')
    await conn.close()
    if not rows:
        await message.reply("Пока нет игроков")
        return
    text = "🏆 **ТОП ИГРОКОВ**\n\n"
    for i, r in enumerate(rows, 1):
        name = r['username'] or f"Игрок{i}"
        text += f"{i}. {name} - Ур.{r['level']} (👾 {r['monsters_killed']})\n"
    await message.reply(text, parse_mode="Markdown")

@dp.message_handler(commands=['shop'])
async def cmd_shop(message: types.Message):
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("❤️ Лечение (50💰)", callback_data="buy_heal"),
        InlineKeyboardButton("⚡ Энергия (30💰)", callback_data="buy_energy")
    )
    await message.reply(
        "🏪 **МАГАЗИН**\n\n"
        "❤️ Лечение - +50 HP (50💰)\n"
        "⚡ Энергия - +30 энергии (30💰)",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@dp.callback_query_handler(lambda c: c.data.startswith('buy_'))
async def buy(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    player = await get_player(user_id)
    if not player:
        await callback.message.reply("Сначала введи /start")
        await callback.answer()
        return
    action = callback.data.split('_')[1]
    if action == "heal":
        if player['credits'] >= 50:
            new_health = min(player['max_health'], player['health'] + 50)
            await update_player(user_id,
                credits=player['credits'] - 50,
                health=new_health
            )
            await callback.message.reply("❤️ Здоровье восстановлено!")
        else:
            await callback.message.reply("❌ Недостаточно кредов!")
    elif action == "energy":
        if player['credits'] >= 30:
            new_energy = min(player['max_energy'], player['energy'] + 30)
            await update_player(user_id,
                credits=player['credits'] - 30,
                energy=new_energy
            )
            await callback.message.reply("⚡ Энергия восстановлена!")
        else:
            await callback.message.reply("❌ Недостаточно кредов!")
    await callback.answer()

# ---------- Flask для health check ----------
app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({"status": "Bot is running!", "time": datetime.now().isoformat()})

@app.route('/health')
def health():
    return jsonify({"status": "healthy"}), 200

def run_flask():
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)

# ---------- Запуск ----------
if __name__ == '__main__':
    # Инициализация БД
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init_db())

    # Запуск Flask в фоне
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print(f"🚀 Flask запущен в фоновом потоке на порту {PORT}")

    # Запуск бота
    print("🚀 Запуск бота в режиме polling...")
    executor.start_polling(dp, skip_updates=True, loop=loop)