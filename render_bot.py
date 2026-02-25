# render_bot.py - ПОЛНАЯ ВЕРСИЯ ДЛЯ RENDER

import asyncio
import logging
import random
import os
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import asyncpg
from flask import Flask, jsonify
import threading

# ========== НАСТРОЙКИ ==========
# Берем токен из переменных окружения (так безопаснее)
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8689690200:AAGkYm61FQntnn7yScMnzdHzMgxVKBeEndM')  # ЗАМЕНИ НА СВОЙ!
DB_PASSWORD = os.environ.get('DB_PASSWORD', '1234567890')  # ТВОЙ ПАРОЛЬ!

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Создаем Flask приложение для health check
app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({"status": "Bot is running!", "time": datetime.now().isoformat()})

@app.route('/health')
def health():
    return jsonify({"status": "healthy"}), 200

# Создаем цикл событий
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# Создаем бота и диспетчер
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# ========== ХРАНИЛИЩА ==========
active_battles = {}
pvp_queue = []
pvp_battles = []

# ========== ПОДКЛЮЧЕНИЕ К БАЗЕ ==========
async def get_db():
    return await asyncpg.connect(
        user='postgres',
        password=DB_PASSWORD,
        database='postgres',
        host='localhost',
        port=5432
    )

# ========== СТАРТ ==========
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    user = message.from_user
    conn = await get_db()
    
    player = await conn.fetchrow(
        "SELECT * FROM players WHERE telegram_id = $1",
        user.id
    )
    
    if player:
        await message.reply(
            f"🌟 С возвращением, {user.first_name}!\n"
            f"Уровень: {player['level']} | Креды: {player['credits']}\n\n"
            f"⚔️ /battle - Битва с монстрами\n"
            f"🤺 /pvp - PvP арена\n"
            f"🏰 /dungeon - Подземелья\n"
            f"🏪 /shop - Магазин\n"
            f"🎁 /daily - Бонус\n"
            f"🏆 /top - Топ игроков"
        )
    else:
        await conn.execute("""
            INSERT INTO players (telegram_id, username, last_daily) 
            VALUES ($1, $2, NOW())
        """, user.id, user.username)
        
        await message.reply(
            f"🌟 Добро пожаловать в NEOMATRIX, {user.first_name}!\n"
            f"Ты зарегистрирован как новый игрок.\n"
            f"Получено 1000 стартовых кредов!\n\n"
            f"⚔️ /battle - Начать битву\n"
            f"🎁 /daily - Бонус"
        )
    await conn.close()

# ========== БИТВА ==========
@dp.message_handler(commands=['battle'])
async def cmd_battle(message: types.Message):
    user = message.from_user
    conn = await get_db()
    
    player = await conn.fetchrow(
        "SELECT * FROM players WHERE telegram_id = $1",
        user.id
    )
    
    if not player or player['energy'] < 10:
        await message.reply("⚡ Недостаточно энергии! Используй /daily")
        await conn.close()
        return
    
    enemy = {"name": "🛡️ Дрон-охранник", "health": 50, "damage": 10, "exp": 15, "credits": 40}
    battle_id = f"{user.id}_{datetime.now().timestamp()}"
    
    active_battles[battle_id] = {
        'player_id': user.id,
        'player_hp': player['health'],
        'enemy': enemy,
        'enemy_hp': enemy['health']
    }
    
    await conn.execute(
        "UPDATE players SET energy = energy - 10 WHERE telegram_id = $1",
        user.id
    )
    
    await conn.close()
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("⚔️ Атака", callback_data=f"monster_attack_{battle_id}"),
        InlineKeyboardButton("🛡️ Защита", callback_data=f"monster_defend_{battle_id}")
    )
    
    await message.reply(
        f"⚔️ **БИТВА**\n\nВраг: {enemy['name']}\n❤️ {enemy['health']}",
        reply_markup=keyboard
    )

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('monster_'))
async def process_monster_battle(callback_query: types.CallbackQuery):
    await callback_query.answer()
    action = callback_query.data.split('_')[1]
    battle_id = callback_query.data.split('_')[2]
    
    if battle_id not in active_battles:
        await callback_query.message.reply("⚠️ Битва закончена!")
        return
    
    battle = active_battles[battle_id]
    user_id = battle['player_id']
    
    if action == "attack":
        damage = random.randint(15, 25)
        battle['enemy_hp'] -= damage
        await callback_query.message.edit_text(f"⚔️ Ты нанес {damage} урона!\n❤️ Враг: {battle['enemy_hp']}")
    
    if battle['enemy_hp'] <= 0:
        conn = await get_db()
        
        await conn.execute("""
            UPDATE players 
            SET experience = experience + $1, 
                credits = credits + $2,
                monsters_killed = monsters_killed + 1
            WHERE telegram_id = $3
        """, 15, 40, user_id)
        
        await conn.close()
        await callback_query.message.edit_text("🎉 **ПОБЕДА!** +15✨ +40💰")
        del active_battles[battle_id]

# ========== ПРОФИЛЬ ==========
@dp.message_handler(commands=['profile'])
async def cmd_profile(message: types.Message):
    user = message.from_user
    conn = await get_db()
    
    player = await conn.fetchrow(
        "SELECT * FROM players WHERE telegram_id = $1",
        user.id
    )
    
    if not player:
        await message.reply("Сначала введи /start")
        await conn.close()
        return
    
    battles = await conn.fetch(
        "SELECT COUNT(*) as total, SUM(CASE WHEN won THEN 1 ELSE 0 END) as wins FROM battles WHERE player_id = $1",
        player['id']
    )
    await conn.close()
    
    total = battles[0]['total'] or 0
    wins = battles[0]['wins'] or 0
    
    profile_text = f"""
🎮 **ПРОФИЛЬ {user.first_name}**
═══════════════════
📊 Уровень: {player['level']}
❤️ HP: {player['health']}/{player['max_health']}
⚡ Энергия: {player['energy']}/{player['max_energy']}
═══════════════════
💰 Креды: {player['credits']}
👾 Убито монстров: {player['monsters_killed']}
═══════════════════
⚔️ Битв: {total}
🏆 Побед: {wins}
📈 Винрейт: {(wins/total*100) if total>0 else 0:.1f}%
═══════════════════
    """
    await message.reply(profile_text, parse_mode="Markdown")

# ========== МАГАЗИН ==========
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
        reply_markup=keyboard
    )

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('buy_'))
async def process_buy(callback_query: types.CallbackQuery):
    await callback_query.answer()
    action = callback_query.data.split('_')[1]
    user_id = callback_query.from_user.id
    
    conn = await get_db()
    player = await conn.fetchrow(
        "SELECT * FROM players WHERE telegram_id = $1",
        user_id
    )
    
    if action == "heal" and player['credits'] >= 50:
        await conn.execute("""
            UPDATE players 
            SET credits = credits - 50,
                health = LEAST(max_health, health + 50)
            WHERE telegram_id = $1
        """, user_id)
        await callback_query.message.reply("❤️ Здоровье восстановлено!")
    
    elif action == "energy" and player['credits'] >= 30:
        await conn.execute("""
            UPDATE players 
            SET credits = credits - 30,
                energy = LEAST(max_energy, energy + 30)
            WHERE telegram_id = $1
        """, user_id)
        await callback_query.message.reply("⚡ Энергия восстановлена!")
    
    else:
        await callback_query.message.reply("❌ Недостаточно кредов!")
    
    await conn.close()

# ========== ЕЖЕДНЕВНЫЙ БОНУС ==========
@dp.message_handler(commands=['daily'])
async def cmd_daily(message: types.Message):
    user = message.from_user
    conn = await get_db()
    
    player = await conn.fetchrow(
        "SELECT * FROM players WHERE telegram_id = $1",
        user.id
    )
    
    last_daily = player['last_daily']
    now = datetime.now()
    
    if last_daily and (now - last_daily) < timedelta(days=1):
        time_left = timedelta(days=1) - (now - last_daily)
        hours = time_left.seconds // 3600
        await message.reply(f"⏳ Бонус через {hours}ч")
    else:
        bonus = 100 + player['level'] * 10
        await conn.execute("""
            UPDATE players 
            SET credits = credits + $1,
                energy = max_energy,
                last_daily = NOW()
            WHERE telegram_id = $2
        """, bonus, user.id)
        await message.reply(f"🎁 Получено {bonus}💰 и полная энергия!")
    
    await conn.close()

# ========== ТОП ==========
@dp.message_handler(commands=['top'])
async def cmd_top(message: types.Message):
    conn = await get_db()
    
    top = await conn.fetch("""
        SELECT username, level, monsters_killed 
        FROM players 
        ORDER BY level DESC, monsters_killed DESC 
        LIMIT 10
    """)
    await conn.close()
    
    text = "🏆 **ТОП ИГРОКОВ**\n\n"
    for i, p in enumerate(top, 1):
        name = p['username'] or f"Игрок{i}"
        text += f"{i}. {name} - Ур.{p['level']} (👾 {p['monsters_killed']})\n"
    
    await message.reply(text, parse_mode="Markdown")

# ========== PvP (упрощенно) ==========
@dp.message_handler(commands=['pvp'])
async def cmd_pvp(message: types.Message):
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("🔍 Найти противника", callback_data="pvp_find"),
        InlineKeyboardButton("📊 Мой рейтинг", callback_data="pvp_rating"),
        InlineKeyboardButton("🏆 Топ PvP", callback_data="pvp_top")
    )
    
    await message.reply(
        "🤺 **PvP АРЕНА**\n\n"
        "Сражайся с другими игроками!\n"
        "Победа +20 рейтинга, поражение -10\n\n"
        "Выбери действие:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

# ========== ПОДЗЕМЕЛЬЯ ==========
@dp.message_handler(commands=['dungeon'])
async def cmd_dungeon(message: types.Message):
    await message.reply(
        "🏰 **ПОДЗЕМЕЛЬЯ**\n\n"
        "Скоро здесь можно будет исследовать подземелья!\n"
        "А пока сражайся с монстрами через /battle"
    )

# ========== ЗАПУСК БОТА В ОТДЕЛЬНОМ ПОТОКЕ ==========
def run_bot():
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True, loop=loop)

# Запускаем бота в фоновом потоке
thread = threading.Thread(target=run_bot)
thread.start()

# ========== ЗАПУСК FLASK ==========
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 NEOMATRIX запущен на порту {port}")
    print(f"🤖 Бот работает в фоновом режиме")
    app.run(host='0.0.0.0', port=port)