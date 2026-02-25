import os
import logging
import random
import threading
import asyncio
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

# Хранилища
active_battles = {}          # для временных битв
memory_players = {}          # резервное хранилище в памяти (когда БД нет)

# ---------- Шаблоны врагов ----------
ENEMY_TEMPLATES = [
    {
        'name': '🛡️ Дрон-охранник',
        'base_health': 50,
        'base_damage': 10,
        'exp_reward': 15,
        'credits_reward': 40,
        'type': 'machine'
    },
    {
        'name': '💻 Хакер',
        'base_health': 40,
        'base_damage': 12,
        'exp_reward': 20,
        'credits_reward': 50,
        'type': 'hacker'
    },
    {
        'name': '👾 Мутант',
        'base_health': 70,
        'base_damage': 15,
        'exp_reward': 25,
        'credits_reward': 70,
        'type': 'mutant'
    },
    {
        'name': '⚡ Элитный страж',
        'base_health': 100,
        'base_damage': 20,
        'exp_reward': 40,
        'credits_reward': 120,
        'type': 'elite'
    }
]

def generate_enemy(player_level):
    """Генерирует врага с уровнем, близким к уровню игрока"""
    template = random.choice(ENEMY_TEMPLATES)
    enemy_level = max(1, player_level + random.randint(-1, 2))
    multiplier = 1 + (enemy_level - 1) * 0.2  # +20% за уровень
    health = int(template['base_health'] * multiplier)
    damage = int(template['base_damage'] * multiplier)
    exp = int(template['exp_reward'] * (1 + (enemy_level - 1) * 0.1))
    credits = int(template['credits_reward'] * (1 + (enemy_level - 1) * 0.1))

    return {
        'name': f"{template['name']} (ур.{enemy_level})",
        'health': health,
        'damage': damage,
        'exp': exp,
        'credits': credits,
        'level': enemy_level,
        'type': template['type']
    }

# ---------- Работа с БД ----------
async def init_db():
    if not DATABASE_URL:
        print("⚠️ DATABASE_URL не задана – работа без сохранения данных")
        return
    try:
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
    except Exception as e:
        print(f"❌ Ошибка подключения к БД: {e}")

async def get_player_from_db(user_id):
    if not DATABASE_URL:
        return None
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        row = await conn.fetchrow('SELECT * FROM players WHERE user_id = $1', user_id)
        await conn.close()
        return row
    except:
        return None

async def create_player_in_db(user_id, username):
    if not DATABASE_URL:
        return
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute('''
            INSERT INTO players (user_id, username, last_daily) VALUES ($1, $2, NOW())
        ''', user_id, username)
        await conn.close()
    except:
        pass

async def update_player_in_db(user_id, **kwargs):
    if not DATABASE_URL:
        return
    try:
        set_clause = ', '.join(f"{k} = ${i+2}" for i, k in enumerate(kwargs))
        values = [user_id] + list(kwargs.values())
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute(f'UPDATE players SET {set_clause} WHERE user_id = $1', *values)
        await conn.close()
    except:
        pass

# ---------- Универсальные функции (БД + память) ----------
def get_default_player(username=None):
    return {
        'level': 1,
        'exp': 0,
        'credits': 1000,
        'health': 100,
        'max_health': 100,
        'energy': 100,
        'max_energy': 100,
        'monsters_killed': 0,
        'last_daily': None,
        'username': username
    }

async def get_player_safe(user_id, username=None):
    db_player = await get_player_from_db(user_id)
    if db_player:
        return dict(db_player)
    if user_id not in memory_players:
        memory_players[user_id] = get_default_player(username)
    return memory_players[user_id]

async def update_player_safe(user_id, **kwargs):
    if user_id in memory_players:
        memory_players[user_id].update(kwargs)
    await update_player_in_db(user_id, **kwargs)

# ---------- Команды бота ----------
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "NoName"
    player = await get_player_safe(user_id, username)
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
    player = await get_player_safe(user_id)
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
    player = await get_player_safe(user_id)
    if player['energy'] < 10:
        await message.reply("⚡ Недостаточно энергии! Используй /daily")
        return

    enemy = generate_enemy(player['level'])
    battle_id = f"{user_id}_{datetime.now().timestamp()}"
    active_battles[battle_id] = {
        'player_id': user_id,
        'enemy': enemy,
        'enemy_hp': enemy['health']
    }

    await update_player_safe(user_id, energy=player['energy'] - 10)

    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("⚔️ Атака", callback_data=f"attack_{battle_id}"),
        InlineKeyboardButton("🏃 Убежать", callback_data=f"run_{battle_id}")
    )
    await message.reply(
        f"⚔️ **БИТВА**\n\nВраг: {enemy['name']}\n"
        f"❤️ HP: {enemy['health']}\n"
        f"⚔️ Урон врага: {enemy['damage']}\n"
        f"🏆 Награда: +{enemy['exp']}✨ +{enemy['credits']}💰",
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
        player = await get_player_safe(user_id)
        enemy = battle['enemy']
        new_exp = player['exp'] + enemy['exp']
        new_credits = player['credits'] + enemy['credits']
        new_kills = player['monsters_killed'] + 1
        updates = {
            'exp': new_exp,
            'credits': new_credits,
            'monsters_killed': new_kills
        }
        level_up = ""
        if new_exp >= 100:
            new_level = player['level'] + 1
            updates['level'] = new_level
            updates['exp'] = new_exp - 100
            updates['max_health'] = player['max_health'] + 10
            updates['health'] = updates['max_health']
            level_up = "\n📈 **УРОВЕНЬ ПОВЫШЕН!**"
        await update_player_safe(user_id, **updates)
        del active_battles[battle_id]
        await callback.message.edit_text(
            f"🎉 **ПОБЕДА!** +{enemy['exp']}✨ +{enemy['credits']}💰{level_up}"
        )
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
    player = await get_player_safe(user_id)
    now = datetime.now()
    last = player['last_daily']
    if last and (now - last) < timedelta(days=1):
        left = timedelta(days=1) - (now - last)
        hours = left.seconds // 3600
        await message.reply(f"⏳ Бонус через {hours}ч")
    else:
        bonus = 100 + player['level'] * 10
        await update_player_safe(user_id,
            credits=player['credits'] + bonus,
            energy=player['max_energy'],
            health=player['max_health'],
            last_daily=now
        )
        await message.reply(f"🎁 Получено {bonus}💰 и полная энергия!")

@dp.message_handler(commands=['top'])
async def cmd_top(message: types.Message):
    if not DATABASE_URL:
        # Топ из памяти
        if not memory_players:
            await message.reply("Пока нет игроков")
            return
        sorted_players = sorted(memory_players.items(), key=lambda x: x[1]['level'], reverse=True)[:5]
        text = "🏆 **ТОП ИГРОКОВ (в памяти)**\n\n"
        for i, (uid, p) in enumerate(sorted_players, 1):
            name = p.get('username') or f"Игрок{uid}"
            text += f"{i}. {name} - Ур.{p['level']} (👾 {p['monsters_killed']})\n"
        await message.reply(text, parse_mode="Markdown")
        return

    try:
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
    except Exception as e:
        await message.reply("Ошибка получения топа")

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
    player = await get_player_safe(user_id)
    action = callback.data.split('_')[1]
    if action == "heal":
        if player['credits'] >= 50:
            new_health = min(player['max_health'], player['health'] + 50)
            await update_player_safe(user_id,
                credits=player['credits'] - 50,
                health=new_health
            )
            await callback.message.reply("❤️ Здоровье восстановлено!")
        else:
            await callback.message.reply("❌ Недостаточно кредов!")
    elif action == "energy":
        if player['credits'] >= 30:
            new_energy = min(player['max_energy'], player['energy'] + 30)
            await update_player_safe(user_id,
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
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init_db())

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print(f"🚀 Flask запущен в фоновом потоке на порту {PORT}")

    print("🚀 Запуск бота в режиме polling...")
    executor.start_polling(dp, skip_updates=True, loop=loop)