# game_mega.py - МЕГА-ВЕРСИЯ СО ВСЕМИ ФИЧАМИ

import asyncio
import logging
import random
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import asyncpg

# НАСТРОЙКИ
BOT_TOKEN = "8689690200:AAGkYm61FQntnn7yScMnzdHzMgxVKBeEndM"  # ЗАМЕНИ НА СВОЙ!
DB_PASSWORD = "1234567890"  # ТВОЙ ПАРОЛЬ!

logging.basicConfig(level=logging.INFO)

# Создаем цикл событий
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# Хранилища
active_battles = {}
pvp_queue = []  # Очередь на PvP
pvp_battles = {}  # Активные PvP битвы

async def get_db():
    return await asyncpg.connect(
        user='postgres',
        password=DB_PASSWORD,
        database='postgres',
        host='localhost',
        port=5432
    )

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    user = message.from_user
    conn = await get_db()
    
    player = await conn.fetchrow(
        "SELECT * FROM players WHERE telegram_id = $1",
        user.id
    )
    
    if player:
        # Проверяем, есть ли PvP рейтинг
        rating = await conn.fetchrow(
            "SELECT * FROM pvp_rating WHERE player_id = $1",
            player['id']
        )
        if not rating:
            await conn.execute(
                "INSERT INTO pvp_rating (player_id) VALUES ($1)",
                player['id']
            )
        
        await message.reply(
            f"🌟 С возвращением, {user.first_name}!\n"
            f"Уровень: {player['level']} | Креды: {player['credits']}\n\n"
            f"⚔️ /battle - Битва с монстрами\n"
            f"🤺 /pvp - PvP арена\n"
            f"🏪 /shop - Магазин\n"
            f"📊 /profile - Профиль\n"
            f"🎁 /daily - Бонус\n"
            f"🏆 /top - Топ игроков"
        )
    else:
        await conn.execute("""
            INSERT INTO players (telegram_id, username, last_daily) 
            VALUES ($1, $2, NOW())
        """, user.id, user.username)
        
        new_player = await conn.fetchrow(
            "SELECT id FROM players WHERE telegram_id = $1",
            user.id
        )
        await conn.execute(
            "INSERT INTO pvp_rating (player_id) VALUES ($1)",
            new_player['id']
        )
        
        await message.reply(
            f"🌟 Добро пожаловать в NEOMATRIX MEGA, {user.first_name}!\n"
            f"Ты зарегистрирован как новый игрок.\n"
            f"Получено 1000 стартовых кредов!\n\n"
            f"⚔️ /battle - Начать битву\n"
            f"🤺 /pvp - PvP арена\n"
            f"🎁 /daily - Бонус"
        )
    await conn.close()

@dp.message_handler(commands=['pvp'])
async def cmd_pvp(message: types.Message):
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("🔍 Найти противника", callback_data="pvp_find"),
        InlineKeyboardButton("📊 Мой рейтинг", callback_data="pvp_rating"),
        InlineKeyboardButton("🏆 Топ PvP", callback_data="pvp_top"),
        InlineKeyboardButton("❌ Отмена", callback_data="pvp_cancel")
    )
    
    await message.reply(
        "🤺 **PvP АРЕНА**\n\n"
        "Здесь ты можешь сразиться с другими игроками!\n"
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
        # Добавляем в очередь
        if user_id not in pvp_queue:
            pvp_queue.append(user_id)
            await callback_query.message.edit_text(
                "🔍 **Поиск противника...**\n"
                "Ожидайте, как только найдется игрок - битва начнется!\n\n"
                "Для отмены нажми /pvp_cancel"
            )
            
            # Проверяем, есть ли второй игрок
            if len(pvp_queue) >= 2:
                player1 = pvp_queue.pop(0)
                player2 = pvp_queue.pop(0)
                await start_pvp_battle(player1, player2, callback_query.message)
        else:
            await callback_query.message.edit_text("Ты уже в очереди!")
    
    elif action == "rating":
        conn = await get_db()
        player = await conn.fetchrow(
            "SELECT id FROM players WHERE telegram_id = $1",
            user_id
        )
        rating = await conn.fetchrow(
            "SELECT * FROM pvp_rating WHERE player_id = $1",
            player['id']
        )
        await conn.close()
        
        await callback_query.message.edit_text(
            f"📊 **ТВОЙ PvP РЕЙТИНГ**\n\n"
            f"Рейтинг: {rating['rating']}\n"
            f"Побед: {rating['wins']}\n"
            f"Поражений: {rating['losses']}\n"
            f"Всего битв: {rating['wins'] + rating['losses']}"
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

@dp.message_handler(commands=['pvp_cancel'])
async def cmd_pvp_cancel(message: types.Message):
    if message.from_user.id in pvp_queue:
        pvp_queue.remove(message.from_user.id)
        await message.reply("❌ Ты удален из очереди PvP")
    else:
        await message.reply("Ты не в очереди")

async def start_pvp_battle(player1_id, player2_id, message):
    conn = await get_db()
    
    p1 = await conn.fetchrow(
        "SELECT * FROM players WHERE telegram_id = $1",
        player1_id
    )
    p2 = await conn.fetchrow(
        "SELECT * FROM players WHERE telegram_id = $1",
        player2_id
    )
    
    # Получаем рейтинги
    r1 = await conn.fetchrow(
        "SELECT * FROM pvp_rating WHERE player_id = $1",
        p1['id']
    )
    r2 = await conn.fetchrow(
        "SELECT * FROM pvp_rating WHERE player_id = $1",
        p2['id']
    )
    await conn.close()
    
    battle_id = f"pvp_{player1_id}_{player2_id}_{datetime.now().timestamp()}"
    
    pvp_battles[battle_id] = {
        'player1': {
            'id': player1_id,
            'name': p1['username'] or f"Игрок",
            'hp': 100,
            'max_hp': 100,
            'damage': 15,
            'rating': r1['rating']
        },
        'player2': {
            'id': player2_id,
            'name': p2['username'] or f"Игрок",
            'hp': 100,
            'max_hp': 100,
            'damage': 15,
            'rating': r2['rating']
        },
        'turn': 1,
        'current_player': player1_id
    }
    
    # Отправляем сообщение обоим игрокам
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("⚔️ Атаковать", callback_data=f"pvp_attack_{battle_id}"),
        InlineKeyboardButton("🛡️ Защита", callback_data=f"pvp_defend_{battle_id}")
    )
    
    battle_text = f"""
🤺 **PvP БИТВА НАЧАЛАСЬ!** 🤺

**{pvp_battles[battle_id]['player1']['name']}** VS **{pvp_battles[battle_id]['player2']['name']}**

Рейтинги: {r1['rating']} ⚔️ {r2['rating']}

❤️ HP игроков: 100/100

Ход 1. Сейчас ходит первый игрок!
    """
    
    await bot.send_message(player1_id, battle_text, reply_markup=keyboard)
    await bot.send_message(player2_id, "🤺 Началась PvP битва! Ожидай своего хода...")

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('pvp_'))
async def process_pvp_battle(callback_query: types.CallbackQuery):
    await callback_query.answer()
    
    data = callback_query.data.split('_')
    action = data[1]
    battle_id = data[2]
    
    if battle_id not in pvp_battles:
        await callback_query.message.reply("⚠️ Битва уже закончена!")
        return
    
    battle = pvp_battles[battle_id]
    user_id = callback_query.from_user.id
    
    # Проверяем, чей ход
    if battle['current_player'] != user_id:
        await callback_query.message.reply("⏳ Сейчас не твой ход!")
        return
    
    # Определяем противника
    if user_id == battle['player1']['id']:
        player = battle['player1']
        opponent = battle['player2']
    else:
        player = battle['player2']
        opponent = battle['player1']
    
    result_text = ""
    damage = 0
    
    if action == "attack":
        damage = random.randint(10, 20)
        opponent['hp'] -= damage
        result_text += f"⚔️ Ты нанес {damage} урона!\n"
    
    elif action == "defend":
        shield = random.randint(5, 15)
        result_text += f"🛡️ Ты защищаешься (блок {shield})\n"
        battle[f'shield_{user_id}'] = shield
    
    # Проверка на победу
    if opponent['hp'] <= 0:
        # Игрок победил
        winner_id = user_id
        loser_id = opponent['id']
        
        # Обновляем рейтинги
        conn = await get_db()
        
        winner = await conn.fetchrow(
            "SELECT id FROM players WHERE telegram_id = $1",
            winner_id
        )
        loser = await conn.fetchrow(
            "SELECT id FROM players WHERE telegram_id = $1",
            loser_id
        )
        
        await conn.execute("""
            UPDATE pvp_rating 
            SET rating = rating + 20, wins = wins + 1 
            WHERE player_id = $1
        """, winner['id'])
        
        await conn.execute("""
            UPDATE pvp_rating 
            SET rating = rating - 10, losses = losses + 1 
            WHERE player_id = $1
        """, loser['id'])
        
        await conn.execute("""
            INSERT INTO pvp_battles (player1_id, player2_id, winner_id, rating_change)
            VALUES ($1, $2, $3, 20)
        """, winner['id'], loser['id'], winner['id'])
        
        await conn.close()
        
        result_text += f"\n🎉 **ТЫ ПОБЕДИЛ!** +20 рейтинга!"
        
        await bot.send_message(
            opponent['id'],
            f"💔 Ты проиграл PvP битву... -10 рейтинга"
        )
        
        del pvp_battles[battle_id]
        
        await callback_query.message.edit_text(result_text)
        return
    
    # Меняем ход
    battle['turn'] += 1
    battle['current_player'] = opponent['id']
    
    # Отправляем обновление текущему игроку
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("⚔️ Атаковать", callback_data=f"pvp_attack_{battle_id}"),
        InlineKeyboardButton("🛡️ Защита", callback_data=f"pvp_defend_{battle_id}")
    )
    
    battle_text = f"""
🤺 **PvP БИТВА** 🤺

**{battle['player1']['name']}** VS **{battle['player2']['name']}**

❤️ {battle['player1']['name']}: {battle['player1']['hp']}/{battle['player1']['max_hp']}
❤️ {battle['player2']['name']}: {battle['player2']['hp']}/{battle['player2']['max_hp']}

{result_text}

Ход {battle['turn']}. Твой ход!
    """
    
    await callback_query.message.edit_text(battle_text, reply_markup=keyboard)
    
    # Уведомляем противника
    await bot.send_message(
        opponent['id'],
        f"⚔️ Противник сходил! Теперь твой ход!"
    )
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
    
    # PvP статистика
    pvp = await conn.fetchrow(
        "SELECT * FROM pvp_rating WHERE player_id = $1",
        player['id']
    )
    
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
⚔️ Битв с монстрами: {total}
🏆 Побед: {wins}
📈 Винрейт: {winrate:.1f}%
═══════════════════
    """
    await message.reply(profile_text, parse_mode="Markdown")
    await conn.close()
@dp.message_handler(commands=['top'])
async def cmd_top(message: types.Message):
    conn = await get_db()
    
    top_pve = await conn.fetch("""
        SELECT username, level, monsters_killed 
        FROM players 
        ORDER BY level DESC, monsters_killed DESC 
        LIMIT 5
    """)
    
    top_pvp = await conn.fetch("""
        SELECT p.username, pr.rating 
        FROM pvp_rating pr
        JOIN players p ON pr.player_id = p.id
        ORDER BY pr.rating DESC 
        LIMIT 5
    """)
    
    top_rich = await conn.fetch("""
        SELECT username, credits 
        FROM players 
        ORDER BY credits DESC 
        LIMIT 5
    """)
    
    text = "🏆 **ЗАЛ СЛАВЫ NEOMATRIX MEGA**\n\n"
    
    text += "**⚔️ ТОП ПО УРОВНЮ (PvE):**\n"
    for i, p in enumerate(top_pve, 1):
        name = p['username'] or f"Игрок{i}"
        text += f"{i}. {name} - Ур.{p['level']} (👾 {p['monsters_killed']})\n"
    
    text += "\n**🤺 ТОП PvP РЕЙТИНГА:**\n"
    for i, p in enumerate(top_pvp, 1):
        name = p['username'] or f"Игрок{i}"
        text += f"{i}. {name} - {p['rating']} ⚔️\n"
    
    text += "\n**💰 ТОП ПО КРЕДАМ:**\n"
    for i, p in enumerate(top_rich, 1):
        name = p['username'] or f"Игрок{i}"
        text += f"{i}. {name} - {p['credits']}💰\n"
    
    await message.reply(text, parse_mode="Markdown")
    await conn.close()
# ========== БИТВА С МОНСТРАМИ ==========
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
        await message.reply("⚡ Недостаточно энергии! Используй /daily")
        await conn.close()
        return
    
    # Генерация врага
    enemy_level = max(1, player['level'] + random.randint(-1, 2))
    enemy_types = [
        {"name": "🛡️ Дрон-охранник", "damage": 8, "health": 50, "exp": 15, "credits": 40},
        {"name": "💻 Хакер", "damage": 12, "health": 40, "exp": 20, "credits": 60},
        {"name": "🤖 Терминатор", "damage": 15, "health": 70, "exp": 25, "credits": 80}
    ]
    
    enemy = random.choice(enemy_types)
    enemy['level'] = enemy_level
    enemy['health'] = int(enemy['health'] * (1 + enemy_level * 0.2))
    
    battle_id = f"{user.id}_{datetime.now().timestamp()}"
    active_battles[battle_id] = {
        'player_id': user.id,
        'player_hp': player['health'],
        'player_max_hp': player['max_health'],
        'enemy': enemy,
        'enemy_hp': enemy['health'],
        'turn': 1,
        'player_shield': 0
    }
    
    await conn.execute(
        "UPDATE players SET energy = energy - 10 WHERE telegram_id = $1",
        user.id
    )
    await conn.close()
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("⚔️ Атаковать", callback_data=f"monster_attack_{battle_id}"),
        InlineKeyboardButton("🛡️ Защита", callback_data=f"monster_defend_{battle_id}")
    )
    
    await message.reply(
        f"⚔️ **БИТВА С {enemy['name']}**\n\n"
        f"❤️ HP врага: {enemy['health']}\n"
        f"⚔️ Урон врага: {enemy['damage']}\n\n"
        f"❤️ Твое HP: {player['health']}/{player['max_health']}\n\n"
        f"Ход 1. Твой ход!",
        reply_markup=keyboard
    )

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('monster_'))
async def process_monster_battle(callback_query: types.CallbackQuery):
    await callback_query.answer()
    
    data = callback_query.data.split('_')
    action = data[1]
    battle_id = data[2]
    
    if battle_id not in active_battles:
        await callback_query.message.reply("⚠️ Битва уже закончена!")
        return
    
    battle = active_battles[battle_id]
    
    result_text = ""
    player_damage = random.randint(15, 25)
    enemy_damage = random.randint(5, 15) + battle['enemy']['damage']
    
    if action == "attack":
        battle['enemy_hp'] -= player_damage
        result_text += f"⚔️ Ты нанес {player_damage} урона!\n"
    elif action == "defend":
        shield = random.randint(10, 20)
        battle['player_shield'] = shield
        result_text += f"🛡️ Ты защищаешься (блок {shield})\n"
    
    if battle['enemy_hp'] > 0:
        if battle.get('player_shield', 0) > 0:
            enemy_damage = max(0, enemy_damage - battle['player_shield'])
            battle['player_shield'] = 0
        battle['player_hp'] -= enemy_damage
        result_text += f"🤖 Враг нанес {enemy_damage} урона!\n"
    
    if battle['player_hp'] <= 0:
        await callback_query.message.edit_text("💀 Ты проиграл...")
        del active_battles[battle_id]
        return
    elif battle['enemy_hp'] <= 0:
        conn = await get_db()
        player = await conn.fetchrow(
            "SELECT * FROM players WHERE telegram_id = $1",
            battle['player_id']
        )
        
        new_exp = player['experience'] + battle['enemy']['exp']
        new_level = player['level']
        if new_exp >= 100:
            new_level += 1
            new_exp = new_exp - 100
        
        await conn.execute("""
            UPDATE players 
            SET experience = $1, level = $2, 
                credits = credits + $3,
                monsters_killed = monsters_killed + 1
            WHERE telegram_id = $4
        """, new_exp, new_level, battle['enemy']['credits'], battle['player_id'])
        await conn.close()
        
        await callback_query.message.edit_text(
            f"🎉 **ПОБЕДА!**\n\n"
            f"+{battle['enemy']['exp']} опыта\n"
            f"+{battle['enemy']['credits']} кредов"
        )
        del active_battles[battle_id]
        return
    
    battle['turn'] += 1
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("⚔️ Атаковать", callback_data=f"monster_attack_{battle_id}"),
        InlineKeyboardButton("🛡️ Защита", callback_data=f"monster_defend_{battle_id}")
    )
    
    await callback_query.message.edit_text(
        f"⚔️ **БИТВА ПРОДОЛЖАЕТСЯ**\n\n"
        f"❤️ HP врага: {battle['enemy_hp']}\n"
        f"❤️ Твое HP: {battle['player_hp']}\n\n"
        f"{result_text}\n"
        f"Ход {battle['turn']}. Твой ход!",
        reply_markup=keyboard
    )

# ========== МАГАЗИН ==========
@dp.message_handler(commands=['shop'])
async def cmd_shop(message: types.Message):
    conn = await get_db()
    items = await conn.fetch("SELECT * FROM shop_items")
    await conn.close()
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    for item in items:
        keyboard.insert(
            InlineKeyboardButton(
                f"{item['name']} ({item['price']}💰)", 
                callback_data=f"buy_{item['id']}"
            )
        )
    
    await message.reply("🏪 **МАГАЗИН**", reply_markup=keyboard)

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
        await conn.close()
        await message.reply(f"🎁 Получено {bonus}💰 и полная энергия!")

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    from aiogram import executor
    print("⚔️ NEOMATRIX MEGA - СО ВСЕМИ ФИЧАМИ!")
    print("Нажми Ctrl+C для остановки")
    executor.start_polling(dp, skip_updates=True, loop=loop)
