# game_dungeons.py - ПОЛНАЯ ВЕРСИЯ С ПОДЗЕМЕЛЬЯМИ

import asyncio
import logging
import random
import json
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import asyncpg

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = "8689690200:AAGkYm61FQntnn7yScMnzdHzMgxVKBeEndM"  # ЗАМЕНИ НА СВОЙ!
DB_PASSWORD = "1234567890"  # ТВОЙ ПАРОЛЬ!

logging.basicConfig(level=logging.INFO)

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# ========== ХРАНИЛИЩА ==========
active_battles = {}
pvp_queue = []
pvp_battles = []
dungeon_battles = {}

# ========== ПОДКЛЮЧЕНИЕ К БАЗЕ ==========
async def get_db():
    return await asyncpg.connect(
        user='postgres',
        password=DB_PASSWORD,
        database='postgres',
        host='localhost',
        port=5432
    )

# ========== ФУНКЦИИ ДЛЯ ПОДЗЕМЕЛИЙ ==========

async def start_dungeon(player_id, dungeon_id):
    """Начинает прохождение подземелья"""
    conn = await get_db()
    
    # Проверяем, есть ли уже прогресс
    progress = await conn.fetchrow("""
        SELECT * FROM dungeon_progress 
        WHERE player_id = $1 AND dungeon_id = $2 AND completed = FALSE
    """, player_id, dungeon_id)
    
    if not progress:
        # Создаем новый прогресс
        progress = await conn.fetchrow("""
            INSERT INTO dungeon_progress (player_id, dungeon_id, current_floor, max_floor)
            VALUES ($1, $2, 1, 1)
            RETURNING *
        """, player_id, dungeon_id)
    
    # Получаем информацию о текущем этаже
    floor = await conn.fetchrow("""
        SELECT * FROM dungeon_floors 
        WHERE dungeon_id = $1 AND floor_number = $2
    """, dungeon_id, progress['current_floor'])
    
    await conn.close()
    
    return progress, floor

async def next_dungeon_floor(player_id, dungeon_id):
    """Переход на следующий этаж"""
    conn = await get_db()
    
    # Получаем текущий прогресс
    progress = await conn.fetchrow("""
        SELECT * FROM dungeon_progress 
        WHERE player_id = $1 AND dungeon_id = $2
    """, player_id, dungeon_id)
    
    if not progress:
        await conn.close()
        return None
    
    new_floor = progress['current_floor'] + 1
    
    # Проверяем, есть ли такой этаж
    floor = await conn.fetchrow("""
        SELECT * FROM dungeon_floors 
        WHERE dungeon_id = $1 AND floor_number = $2
    """, dungeon_id, new_floor)
    
    if floor:
        # Обновляем прогресс
        new_max = max(progress['max_floor'], new_floor)
        await conn.execute("""
            UPDATE dungeon_progress 
            SET current_floor = $1, max_floor = $2
            WHERE id = $3
        """, new_floor, new_max, progress['id'])
        
        await conn.close()
        return floor
    else:
        # Подземелье пройдено
        await conn.execute("""
            UPDATE dungeon_progress 
            SET completed = TRUE
            WHERE id = $1
        """, progress['id'])
        await conn.close()
        return None

# ========== КОМАНДА ПОДЗЕМЕЛИЙ ==========
@dp.message_handler(commands=['dungeon'])
async def cmd_dungeon(message: types.Message):
    user_id = message.from_user.id
    conn = await get_db()
    
    player = await conn.fetchrow(
        "SELECT * FROM players WHERE telegram_id = $1",
        user_id
    )
    
    # Получаем доступные подземелья
    dungeons = await conn.fetch("""
        SELECT * FROM dungeons 
        WHERE min_level <= $1
        ORDER BY min_level
    """, player['level'])
    
    await conn.close()
    
    text = "🏰 **ДОСТУПНЫЕ ПОДЗЕМЕЛЬЯ**\n\n"
    keyboard = InlineKeyboardMarkup(row_width=1)
    
    for d in dungeons:
        text += f"**{d['name']}**\n"
        text += f"_{d['description']}_\n"
        text += f"Этажей: {d['floors']} | Мин. уровень: {d['min_level']}\n\n"
        
        keyboard.add(
            InlineKeyboardButton(
                f"🚪 Войти в {d['name']}",
                callback_data=f"dungeon_enter_{d['id']}"
            )
        )
    
    await message.reply(text, reply_markup=keyboard, parse_mode="Markdown")

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('dungeon_enter_'))
async def dungeon_enter(callback_query: types.CallbackQuery):
    await callback_query.answer()
    
    dungeon_id = int(callback_query.data.split('_')[2])
    user_id = callback_query.from_user.id
    
    conn = await get_db()
    player = await conn.fetchrow(
        "SELECT * FROM players WHERE telegram_id = $1",
        user_id
    )
    
    # Начинаем подземелье
    progress, floor = await start_dungeon(player['id'], dungeon_id)
    
    dungeon = await conn.fetchrow(
        "SELECT * FROM dungeons WHERE id = $1",
        dungeon_id
    )
    
    await conn.close()
    
    # Создаем клавиатуру
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("⚔️ Сражаться", callback_data=f"dungeon_fight_{progress['id']}"),
        InlineKeyboardButton("🏃 Выйти", callback_data=f"dungeon_exit_{progress['id']}")
    )
    
    await callback_query.message.edit_text(
        f"🏰 **{dungeon['name']}**\n\n"
        f"Этаж: {progress['current_floor']}/{dungeon['floors']}\n"
        f"Противник: {floor['boss_name']}\n"
        f"❤️ HP: {floor['boss_hp']}\n"
        f"⚔️ Урон: {floor['boss_damage']}\n\n"
        f"Награда за этаж: +{floor['reward_exp']}✨ +{floor['reward_credits']}💰",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('dungeon_fight_'))
async def dungeon_fight(callback_query: types.CallbackQuery):
    await callback_query.answer()
    
    progress_id = int(callback_query.data.split('_')[2])
    user_id = callback_query.from_user.id
    
    conn = await get_db()
    
    # Получаем прогресс
    progress = await conn.fetchrow("""
        SELECT dp.*, d.name as dungeon_name, d.floors
        FROM dungeon_progress dp
        JOIN dungeons d ON dp.dungeon_id = d.id
        WHERE dp.id = $1
    """, progress_id)
    
    # Получаем этаж
    floor = await conn.fetchrow("""
        SELECT * FROM dungeon_floors 
        WHERE dungeon_id = $1 AND floor_number = $2
    """, progress['dungeon_id'], progress['current_floor'])
    
    # Проверяем энергию
    player = await conn.fetchrow(
        "SELECT * FROM players WHERE telegram_id = $1",
        user_id
    )
    
    if player['energy'] < 20:
        await callback_query.message.reply("⚡ Нужно 20 энергии для битвы в подземелье!")
        await conn.close()
        return
    
    # Тратим энергию
    await conn.execute("""
        UPDATE players SET energy = energy - 20 WHERE telegram_id = $1
    """, user_id)
    
    # Бой
    player_damage = random.randint(20, 40) + player['level'] * 2
    boss_damage = random.randint(10, 20) + floor['boss_damage']
    
    # Учитываем защиту (упрощенно)
    if player_damage > boss_damage:
        # Победа
        await conn.execute("""
            UPDATE players 
            SET experience = experience + $1,
                credits = credits + $2
            WHERE telegram_id = $3
        """, floor['reward_exp'], floor['reward_credits'], user_id)
        
        # Переход на следующий этаж
        next_floor = await next_dungeon_floor(player['id'], progress['dungeon_id'])
        
        if next_floor:
            # Есть следующий этаж
            result_text = f"🎉 **ПОБЕДА!**\n+{floor['reward_exp']}✨ +{floor['reward_credits']}💰\n\nПереход на этаж {progress['current_floor'] + 1}!"
            
            keyboard = InlineKeyboardMarkup(row_width=2)
            keyboard.add(
                InlineKeyboardButton("⚔️ Сражаться дальше", callback_data=f"dungeon_fight_{progress_id}"),
                InlineKeyboardButton("🏃 Выйти", callback_data=f"dungeon_exit_{progress_id}")
            )
            
            await callback_query.message.edit_text(
                f"{result_text}\n\n"
                f"Этаж: {progress['current_floor'] + 1}\n"
                f"Противник: {next_floor['boss_name']}\n"
                f"❤️ HP: {next_floor['boss_hp']}\n"
                f"⚔️ Урон: {next_floor['boss_damage']}",
                reply_markup=keyboard
            )
        else:
            # Подземелье пройдено полностью
            await callback_query.message.edit_text(
                f"🎉 **ПОДЗЕМЕЛЬЕ ПРОЙДЕНО!**\n\n"
                f"Ты покорил все {progress['floors']} этажей!"
            )
    else:
        # Поражение
        await callback_query.message.edit_text(
            f"💀 **ПОРАЖЕНИЕ...**\n\n"
            f"Ты не смог пройти этаж {progress['current_floor']}.\n"
            f"Попробуй еще раз, когда станешь сильнее!"
        )
    
    await conn.close()

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('dungeon_exit_'))
async def dungeon_exit(callback_query: types.CallbackQuery):
    await callback_query.answer()
    await callback_query.message.edit_text("🚪 Ты покинул подземелье. Возвращайся снова!")

# ========== КВЕСТЫ ==========
@dp.message_handler(commands=['quests'])
async def cmd_quests(message: types.Message):
    await message.reply("📜 **Квесты**\n\nСкоро будут!")

# ========== БОССЫ ==========
@dp.message_handler(commands=['boss'])
async def cmd_boss(message: types.Message):
    await message.reply("👾 **Клановые боссы**\n\nСкоро будут!")

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
            f"👾 /boss - Клановые боссы\n"
            f"📜 /quests - Квесты\n"
            f"🏪 /shop - Магазин\n"
            f"📦 /inventory - Инвентарь\n"
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
            f"🏰 /dungeon - Подземелья\n"
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

# ========== PvP ==========
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

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('pvp_'))
async def process_pvp(callback_query: types.CallbackQuery):
    await callback_query.answer()
    action = callback_query.data.split('_')[1]
    user_id = callback_query.from_user.id
    
    if action == "find":
        if user_id not in pvp_queue:
            pvp_queue.append(user_id)
            await callback_query.message.edit_text("🔍 **Поиск противника...**")
            if len(pvp_queue) >= 2:
                player1 = pvp_queue.pop(0)
                player2 = pvp_queue.pop(0)
                await start_pvp_battle(player1, player2)
    
    elif action == "rating":
        conn = await get_db()
        player = await conn.fetchrow(
            "SELECT id FROM players WHERE telegram_id = $1",
            user_id
        )
        rating = await conn.fetchrow(
            "SELECT * FROM pvp_rating WHERE player_id = $1",
            player['id']
        ) or {'rating': 1000, 'wins': 0, 'losses': 0}
        await conn.close()
        
        await callback_query.message.edit_text(
            f"📊 **ТВОЙ PvP РЕЙТИНГ**\n\n"
            f"Рейтинг: {rating['rating']}\n"
            f"Побед: {rating['wins']}\n"
            f"Поражений: {rating['losses']}"
        )
    
    elif action == "top":
        conn = await get_db()
        top = await conn.fetch("""
            SELECT p.username, pr.rating 
            FROM pvp_rating pr
            JOIN players p ON pr.player_id = p.id
            ORDER BY pr.rating DESC
            LIMIT 10
        """)
        await conn.close()
        
        text = "🏆 **ТОП PvP ИГРОКОВ**\n\n"
        for i, p in enumerate(top, 1):
            name = p['username'] or f"Игрок{i}"
            text += f"{i}. {name} - {p['rating']} ⚔️\n"
        
        await callback_query.message.edit_text(text)

async def start_pvp_battle(player1_id, player2_id):
    battle_id = f"pvp_{player1_id}_{player2_id}"
    pvp_battles.append(battle_id)
    
    await bot.send_message(player1_id, "🤺 **Противник найден!** Битва начинается!")
    await bot.send_message(player2_id, "🤺 **Противник найден!** Битва начинается!")

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
    
    pvp = await conn.fetchrow(
        "SELECT * FROM pvp_rating WHERE player_id = $1",
        player['id']
    ) or {'rating': 1000, 'wins': 0, 'losses': 0}
    
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
⚔️ PvP Рейтинг: {pvp['rating']}
🤺 PvP Побед: {pvp['wins']}
💔 PvP Поражений: {pvp['losses']}
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

# ========== ИНВЕНТАРЬ ==========
@dp.message_handler(commands=['inventory'])
async def cmd_inventory(message: types.Message):
    await message.reply("📦 **Инвентарь**\n\nСкоро тут будут предметы из подземелий!")

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    from aiogram import executor
    print("🏰 NEOMATRIX - ФИНАЛЬНАЯ ВЕРСИЯ С ПОДЗЕМЕЛЬЯМИ!")
    print("Нажми Ctrl+C для остановки")
    executor.start_polling(dp, skip_updates=True, loop=loop)