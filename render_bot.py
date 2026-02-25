# render_bot.py - ИСПРАВЛЕННАЯ ВЕРСИЯ ДЛЯ RENDER

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
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8689690200:AAH7rUhbaqh1RjBz-dqmJCyGE0wcDj3uGmw')
DATABASE_URL = os.environ.get('DATABASE_URL', None)

logging.basicConfig(level=logging.INFO)

# Создаем Flask приложение
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

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# ========== ХРАНИЛИЩА ==========
active_battles = {}
pvp_queue = []
pvp_battles = []

# ========== ПОДКЛЮЧЕНИЕ К БАЗЕ ==========
async def get_db():
    """Подключение к базе данных Render"""
    if DATABASE_URL:
        # Подключаемся через URL от Render
        return await asyncpg.connect(DATABASE_URL)
    else:
        # Если нет URL, пробуем локальное подключение (для теста)
        return await asyncpg.connect(
            user='postgres',
            password=os.environ.get('DB_PASSWORD', '1234567890'),
            database='postgres',
            host='localhost',
            port=5432
        )

async def init_db():
    """Создание таблиц при первом запуске"""
    try:
        conn = await get_db()
        
        # Создаем таблицу players
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS players (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                username TEXT,
                level INTEGER DEFAULT 1,
                experience INTEGER DEFAULT 0,
                health INTEGER DEFAULT 100,
                max_health INTEGER DEFAULT 100,
                energy INTEGER DEFAULT 100,
                max_energy INTEGER DEFAULT 100,
                credits INTEGER DEFAULT 1000,
                monsters_killed INTEGER DEFAULT 0,
                last_daily TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        print("✅ Таблица players создана или уже существует")
        
        # Создаем таблицу battles
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS battles (
                id SERIAL PRIMARY KEY,
                player_id INTEGER REFERENCES players(id),
                won BOOLEAN,
                enemy_name TEXT,
                damage_dealt INTEGER,
                damage_taken INTEGER,
                fought_at TIMESTAMP DEFAULT NOW()
            )
        """)
        print("✅ Таблица battles создана или уже существует")
        
        await conn.close()
        print("✅ База данных инициализирована")
    except Exception as e:
        print(f"⚠️ Ошибка инициализации БД: {e}")
        print("⚠️ Бот будет работать без сохранения прогресса")

# ========== СТАРТ ==========
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    user = message.from_user
    
    try:
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
            """, user.id, user.username or "Player")
            
            await message.reply(
                f"🌟 Добро пожаловать в NEOMATRIX, {user.first_name}!\n"
                f"Ты зарегистрирован как новый игрок.\n"
                f"Получено 1000 стартовых кредов!\n\n"
                f"⚔️ /battle - Начать битву\n"
                f"🎁 /daily - Бонус"
            )
        await conn.close()
    except Exception as e:
        print(f"Ошибка в start: {e}")
        await message.reply(
            f"🌟 Добро пожаловать, {user.first_name}!\n"
            f"База данных временно недоступна, но ты можешь играть!\n\n"
            f"⚔️ /battle - Битва с монстрами\n"
            f"🎁 /daily - Бонус"
        )

# ========== БИТВА ==========
@dp.message_handler(commands=['battle'])
async def cmd_battle(message: types.Message):
    user = message.from_user
    
    try:
        conn = await get_db()
        player = await conn.fetchrow(
            "SELECT * FROM players WHERE telegram_id = $1",
            user.id
        )
        
        if not player:
            await message.reply("Сначала введи /start")
            await conn.close()
            return
        
        if player['energy'] < 10:
            await message.reply("⚡ Недостаточно энергии! Используй /daily")
            await conn.close()
            return
        
        # Списываем энергию
        await conn.execute(
            "UPDATE players SET energy = energy - 10 WHERE telegram_id = $1",
            user.id
        )
        await conn.close()
        
        # Создаем битву
        enemy = {"name": "🛡️ Дрон-охранник", "health": 50, "damage": 10, "exp": 15, "credits": 40}
        battle_id = f"{user.id}_{datetime.now().timestamp()}"
        
        active_battles[battle_id] = {
            'player_id': user.id,
            'enemy': enemy,
            'enemy_hp': enemy['health']
        }
        
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("⚔️ Атака", callback_data=f"monster_attack_{battle_id}"),
            InlineKeyboardButton("🏃 Убежать", callback_data=f"monster_run_{battle_id}")
        )
        
        await message.reply(
            f"⚔️ **БИТВА**\n\nВраг: {enemy['name']}\n❤️ {enemy['health']}",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Ошибка в battle: {e}")
        await message.reply("⚠️ Временная ошибка, попробуй позже")

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('monster_attack_'))
async def process_monster_attack(callback_query: types.CallbackQuery):
    await callback_query.answer()
    
    battle_id = callback_query.data.replace('monster_attack_', '')
    
    if battle_id not in active_battles:
        await callback_query.message.reply("⚠️ Битва уже закончена!")
        return
    
    battle = active_battles[battle_id]
    user_id = battle['player_id']
    
    # Наносим урон
    damage = random.randint(15, 25)
    battle['enemy_hp'] -= damage
    
    if battle['enemy_hp'] <= 0:
        # Победа
        try:
            conn = await get_db()
            await conn.execute("""
                UPDATE players 
                SET experience = experience + 15, 
                    credits = credits + 40,
                    monsters_killed = monsters_killed + 1
                WHERE telegram_id = $1
            """, user_id)
            await conn.close()
        except:
            pass
        
        del active_battles[battle_id]
        await callback_query.message.edit_text("🎉 **ПОБЕДА!** +15✨ +40💰")
    else:
        await callback_query.message.edit_text(
            f"⚔️ Ты нанес {damage} урона!\n"
            f"❤️ У врага осталось: {battle['enemy_hp']}"
        )

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('monster_run_'))
async def process_monster_run(callback_query: types.CallbackQuery):
    await callback_query.answer()
    
    battle_id = callback_query.data.replace('monster_run_', '')
    
    if battle_id in active_battles:
        del active_battles[battle_id]
    
    await callback_query.message.edit_text("🏃 Ты убежал с поля боя!")

# ========== ЕЖЕДНЕВНЫЙ БОНУС ==========
@dp.message_handler(commands=['daily'])
async def cmd_daily(message: types.Message):
    user = message.from_user
    
    try:
        conn = await get_db()
        player = await conn.fetchrow(
            "SELECT * FROM players WHERE telegram_id = $1",
            user.id
        )
        
        if not player:
            await message.reply("Сначала введи /start")
            await conn.close()
            return
        
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
    except:
        await message.reply("🎁 Бонус получен! +100💰")

# ========== ПРОФИЛЬ ==========
@dp.message_handler(commands=['profile'])
async def cmd_profile(message: types.Message):
    user = message.from_user
    
    try:
        conn = await get_db()
        player = await conn.fetchrow(
            "SELECT * FROM players WHERE telegram_id = $1",
            user.id
        )
        await conn.close()
        
        if not player:
            await message.reply("Сначала введи /start")
            return
        
        await message.reply(
            f"📊 **ПРОФИЛЬ {user.first_name}**\n\n"
            f"Уровень: {player['level']}\n"
            f"❤️ HP: {player['health']}/{player['max_health']}\n"
            f"⚡ Энергия: {player['energy']}/{player['max_energy']}\n"
            f"💰 Креды: {player['credits']}\n"
            f"👾 Убито монстров: {player['monsters_killed']}",
            parse_mode="Markdown"
        )
    except:
        await message.reply("📊 Профиль временно недоступен")

# ========== ТОП ==========
@dp.message_handler(commands=['top'])
async def cmd_top(message: types.Message):
    try:
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
    except:
        await message.reply("🏆 Топ временно недоступен")

# ========== PvP ==========
@dp.message_handler(commands=['pvp'])
async def cmd_pvp(message: types.Message):
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("🔍 Найти противника", callback_data="pvp_find"),
        InlineKeyboardButton("📊 Мой рейтинг", callback_data="pvp_rating")
    )
    
    await message.reply(
        "🤺 **PvP АРЕНА**\n\n"
        "Скоро здесь будут PvP битвы!\n"
        "А пока сражайся с монстрами через /battle",
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
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('buy_'))
async def process_buy(callback_query: types.CallbackQuery):
    await callback_query.answer()
    
    action = callback_query.data.split('_')[1]
    user_id = callback_query.from_user.id
    
    try:
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
    except:
        await callback_query.message.reply("✅ Покупка выполнена!")

# ========== ЗАПУСК ==========
def run_bot():
    try:
        from aiogram import executor
        print("🚀 Запускаем бота в фоновом потоке...")
        executor.start_polling(dp, skip_updates=True, loop=loop)
        print("✅ Бот успешно запущен и работает")
    except Exception as e:
        print(f"❌ КРИТИЧЕСКАЯ ОШИБКА В ПОТОКЕ БОТА: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    # Инициализируем базу данных
    loop.run_until_complete(init_db())
    
    # Запускаем бота в фоне
    thread = threading.Thread(target=run_bot)
    thread.start()
    
    # Запускаем Flask
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 NEOMATRIX запущен на порту {port}")
    print(f"🤖 Бот работает в фоновом режиме")
    app.run(host='0.0.0.0', port=port)