# battle_bot.py - полная версия игры с боевой системой

import asyncio
import logging
import random
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import asyncpg
from datetime import datetime
asyncio.set_event_loop(asyncio.new_event_loop())

# НАСТРОЙКИ
BOT_TOKEN = "8689690200:AAGkYm61FQntnn7yScMnzdHzMgxVKBeEndM"  # ТВОЙ ТОКЕН!
DB_PASSWORD = "1234567890"  # ТВОЙ ПАРОЛЬ!

logging.basicConfig(level=logging.INFO)

# Создаем бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# Хранилище активных битв
active_battles = {}

# Подключение к базе
async def get_db():
    return await asyncpg.connect(
        user='postgres',
        password=DB_PASSWORD,
        database='postgres',
        host='localhost',
        port=5432
    )

# КОМАНДА START
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
            f"⚔️ /battle - Найти врага\n"
            f"📊 /profile - Мой профиль\n"
            f"🏪 /shop - Магазин"
        )
    else:
        await conn.execute("""
            INSERT INTO players (telegram_id, username) 
            VALUES ($1, $2)
        """, user.id, user.username)
        
        await message.reply(
            f"🌟 Добро пожаловать в NEOMATRIX, {user.first_name}!\n"
            f"Ты зарегистрирован как новый игрок.\n"
            f"Получено 1000 стартовых кредов!\n\n"
            f"⚔️ /battle - Начать первую битву!"
        )
    await conn.close()

# КОМАНДА PROFILE
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
    
    total = battles[0]['total'] or 0
    wins = battles[0]['wins'] or 0
    winrate = (wins / total * 100) if total > 0 else 0
    
    profile_text = f"""
🎮 **ПРОФИЛЬ {user.first_name}**
═══════════════════
📊 Уровень: {player['level']}
✨ Опыт: {player['experience']}/100
❤️ HP: {player['health']}/{player['max_health']}
⚡ Энергия: {player['energy']}/{player['max_energy']}
═══════════════════
💰 Креды: {player['credits']}
═══════════════════
⚔️ Битв: {total}
🏆 Побед: {wins}
📈 Винрейт: {winrate:.1f}%
═══════════════════
    """
    await message.reply(profile_text, parse_mode="Markdown")
    await conn.close()

# КОМАНДА TOP
@dp.message_handler(commands=['top'])
async def cmd_top(message: types.Message):
    conn = await get_db()
    
    top = await conn.fetch("""
        SELECT username, level, credits 
        FROM players 
        ORDER BY level DESC, credits DESC 
        LIMIT 10
    """)
    
    text = "🏆 **ТОП ИГРОКОВ**\n\n"
    for i, p in enumerate(top, 1):
        name = p['username'] or f"Игрок{i}"
        text += f"{i}. {name} | Ур. {p['level']} | 💰 {p['credits']}\n"
    
    await message.reply(text, parse_mode="Markdown")
    await conn.close()

# КОМАНДА SHOP
@dp.message_handler(commands=['shop'])
async def cmd_shop(message: types.Message):
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("❤️ Лечение (50💰)", callback_data="buy_heal"),
        InlineKeyboardButton("⚡ Энергия (30💰)", callback_data="buy_energy"),
        InlineKeyboardButton("🛡️ Щит (100💰)", callback_data="buy_shield"),
        InlineKeyboardButton("⚔️ Урон (150💰)", callback_data="buy_damage")
    )
    
    await message.reply(
        "🏪 **МАГАЗИН**\n\n"
        "❤️ Лечение - восстановить 50 HP (50💰)\n"
        "⚡ Энергия - восстановить 30 энергии (30💰)\n"
        "🛡️ Щит - +10 к защите навсегда (100💰)\n"
        "⚔️ Урон - +5 к атаке навсегда (150💰)",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

# КОМАНДА BATTLE
@dp.message_handler(commands=['battle'])
async def cmd_battle(message: types.Message):
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
    
    if player['energy'] < 10:
        await message.reply("⚡ Недостаточно энергии! Отдохни немного.")
        await conn.close()
        return
    
    # Выбираем случайного врага
    enemy = await conn.fetchrow("""
        SELECT * FROM enemies 
        WHERE level <= $1 
        ORDER BY RANDOM() 
        LIMIT 1
    """, player['level'])
    
    if not enemy:
        await message.reply("😵 Враги закончились... Попробуй позже")
        await conn.close()
        return
    
    # Создаем битву
    battle_id = f"{user.id}_{datetime.now().timestamp()}"
    active_battles[battle_id] = {
        'player_id': user.id,
        'player_hp': player['health'],
        'player_max_hp': player['max_health'],
        'enemy': dict(enemy),
        'enemy_hp': enemy['health'],
        'enemy_max_hp': enemy['max_health'],
        'turn': 1,
        'player_shield': 0
    }
    
    # Тратим энергию
    await conn.execute(
        "UPDATE players SET energy = energy - 10 WHERE telegram_id = $1",
        user.id
    )
    await conn.close()
    
    # Клавиатура битвы
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("⚔️ Атаковать", callback_data=f"battle_attack_{battle_id}"),
        InlineKeyboardButton("🛡️ Защита", callback_data=f"battle_defend_{battle_id}"),
        InlineKeyboardButton("💻 Взлом", callback_data=f"battle_hack_{battle_id}"),
        InlineKeyboardButton("🏃 Сдаться", callback_data=f"battle_run_{battle_id}")
    )
    
    battle_text = f"""
⚔️ **БИТВА НАЧАЛАСЬ!** ⚔️

**{enemy['name']}** (Ур. {enemy['level']})
❤️ HP: {enemy['health']}
⚔️ Урон: {enemy['damage']}
🛡️ Щит: {enemy['shield']}

**Твои показатели:**
❤️ Твое HP: {player['health']}/{player['max_health']}
⚡ Энергия: {player['energy']-10}/{player['max_energy']}

Ход 1. Твой ход!
    """
    
    await message.reply(battle_text, reply_markup=keyboard, parse_mode="Markdown")

# ОБРАБОТКА БОЕВЫХ ДЕЙСТВИЙ
@dp.callback_query_handler(lambda c: c.data and c.data.startswith('battle_'))
async def process_battle(callback_query: types.CallbackQuery):
    await callback_query.answer()
    
    data = callback_query.data.split('_')
    action = data[1]
    battle_id = data[2]
    
    if battle_id not in active_battles:
        await callback_query.message.reply("⚠️ Битва уже закончена!")
        return
    
    battle = active_battles[battle_id]
    user_id = callback_query.from_user.id
    
    if battle['player_id'] != user_id:
        await callback_query.message.reply("Это не твоя битва!")
        return
    
    result_text = ""
    player_damage = 0
    enemy_damage = 0
    
    # ДЕЙСТВИЕ ИГРОКА
    if action == "attack":
        player_damage = random.randint(10, 20) + battle['enemy']['level'] * 2
        battle['enemy_hp'] -= player_damage
        result_text += f"⚔️ Ты нанес {player_damage} урона!\n"
    
    elif action == "defend":
        shield = random.randint(5, 15)
        battle['player_shield'] = shield
        result_text += f"🛡️ Ты приготовился к защите (блок {shield} урона)\n"
    
    elif action == "hack":
        if random.random() < 0.3:  # 30% шанс успеха
            hack_damage = random.randint(15, 25)
            battle['enemy_hp'] -= hack_damage
            result_text += f"💻 Удачный взлом! {hack_damage} урона!\n"
        else:
            result_text += f"💻 Взлом не удался...\n"
    
    elif action == "run":
        if random.random() < 0.5:  # 50% шанс сбежать
            del active_battles[battle_id]
            await callback_query.message.edit_text("🏃 Ты сбежал с поля боя!")
            return
        else:
            result_text += "🏃 Не удалось сбежать!\n"
    
    # ДЕЙСТВИЕ ВРАГА (если враг еще жив)
    if battle['enemy_hp'] > 0:
        # Враг атакует
        enemy_damage = random.randint(5, 15) + battle['enemy']['damage']
        
        # Учитываем защиту
        if battle.get('player_shield', 0) > 0:
            enemy_damage = max(0, enemy_damage - battle['player_shield'])
            result_text += f"🛡️ Щит заблокировал часть урона!\n"
            battle['player_shield'] = 0
        
        battle['player_hp'] -= enemy_damage
        result_text += f"🤖 Враг атакует и наносит {enemy_damage} урона!\n"
    
    # ПРОВЕРКА НА ПОБЕДУ/ПОРАЖЕНИЕ
    battle_ended = False
    victory = False
    
    if battle['player_hp'] <= 0:
        battle_ended = True
        victory = False
        result_text += "\n💀 Ты проиграл..."
    elif battle['enemy_hp'] <= 0:
        battle_ended = True
        victory = True
        result_text += "\n🎉 ТЫ ПОБЕДИЛ!"
        
        # Награда
        exp_reward = battle['enemy']['experience_reward']
        credit_reward = battle['enemy']['credits_reward']
        
        conn = await get_db()
        player = await conn.fetchrow(
            "SELECT * FROM players WHERE telegram_id = $1",
            user_id
        )
        
        # Добавляем опыт и кредиты
        new_exp = player['experience'] + exp_reward
        new_level = player['level']
        new_credits = player['credits'] + credit_reward
        
        # Проверка на повышение уровня
        if new_exp >= 100:
            new_level += 1
            new_exp = new_exp - 100
            result_text += f"\n📈 УРОВЕНЬ ПОВЫШЕН! Теперь уровень {new_level}!"
        
        await conn.execute("""
            UPDATE players 
            SET experience = $1, level = $2, credits = $3,
                health = max_health
            WHERE telegram_id = $4
        """, new_exp, new_level, new_credits, user_id)
        
        # Записываем битву в историю
        await conn.execute("""
            INSERT INTO battles (player_id, won, enemy_name, damage_dealt, damage_taken)
            VALUES ($1, $2, $3, $4, $5)
        """, player['id'], True, battle['enemy']['name'], player_damage, enemy_damage)
        
        await conn.close()
        
        result_text += f"\n\n💰 Награда: +{exp_reward} опыта, +{credit_reward} кредов!"
    
    # Если битва не закончена - показываем следующий ход
    if not battle_ended:
        battle['turn'] += 1
        
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("⚔️ Атаковать", callback_data=f"battle_attack_{battle_id}"),
            InlineKeyboardButton("🛡️ Защита", callback_data=f"battle_defend_{battle_id}"),
            InlineKeyboardButton("💻 Взлом", callback_data=f"battle_hack_{battle_id}"),
            InlineKeyboardButton("🏃 Сдаться", callback_data=f"battle_run_{battle_id}")
        )
        
        battle_text = f"""
⚔️ **БИТВА ПРОДОЛЖАЕТСЯ** ⚔️

**{battle['enemy']['name']}**
❤️ HP: {max(0, battle['enemy_hp'])}/{battle['enemy_max_hp']}

**Твои показатели:**
❤️ Твое HP: {max(0, battle['player_hp'])}/{battle['player_max_hp']}

{result_text}

Ход {battle['turn']}. Твой ход!
        """
        
        await callback_query.message.edit_text(battle_text, reply_markup=keyboard, parse_mode="Markdown")
    
    else:
        # Битва закончена
        del active_battles[battle_id]
        
        if not victory:
            # Восстанавливаем HP после поражения (половина)
            conn = await get_db()
            await conn.execute("""
                UPDATE players 
                SET health = max_health / 2 
                WHERE telegram_id = $1
            """, user_id)
            await conn.close()
        
        await callback_query.message.edit_text(result_text, parse_mode="Markdown")

# ПОКУПКИ В МАГАЗИНЕ
@dp.callback_query_handler(lambda c: c.data and c.data.startswith('buy_'))
async def process_buy(callback_query: types.CallbackQuery):
    await callback_query.answer()
    
    item = callback_query.data.split('_')[1]
    user_id = callback_query.from_user.id
    
    conn = await get_db()
    player = await conn.fetchrow(
        "SELECT * FROM players WHERE telegram_id = $1",
        user_id
    )
    
    if not player:
        await callback_query.message.reply("Сначала введи /start")
        await conn.close()
        return
    
    if item == "heal":
        if player['credits'] >= 50:
            await conn.execute("""
                UPDATE players 
                SET credits = credits - 50,
                    health = LEAST(max_health, health + 50)
                WHERE telegram_id = $1
            """, user_id)
            await callback_query.message.reply("❤️ Здоровье восстановлено!")
        else:
            await callback_query.message.reply("❌ Недостаточно кредов!")
    
    elif item == "energy":
        if player['credits'] >= 30:
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

# ЗАПУСК БОТА
if __name__ == '__main__':
    from aiogram import executor
    print("⚔️ БОТ С БОЕВОЙ СИСТЕМОЙ ЗАПУЩЕН!")
    print("Нажми Ctrl+C для остановки")
    executor.start_polling(dp, skip_updates=True)