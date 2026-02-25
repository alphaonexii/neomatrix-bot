@"
# game_quests.py - ПОЛНАЯ ВЕРСИЯ С КВЕСТАМИ

import asyncio
import logging
import random
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
pvp_battles = {}

# ========== ПОДКЛЮЧЕНИЕ К БАЗЕ ==========
async def get_db():
    return await asyncpg.connect(
        user='postgres',
        password=DB_PASSWORD,
        database='postgres',
        host='localhost',
        port=5432
    )

# ========== ФУНКЦИИ ДЛЯ КВЕСТОВ ==========

async def assign_daily_quests(player_id):
    """Назначает ежедневные квесты игроку"""
    conn = await get_db()
    
    # Удаляем старые квесты
    await conn.execute("""
        DELETE FROM player_quests 
        WHERE player_id = $1 AND (expires_at < NOW() OR claimed = TRUE)
    """, player_id)
    
    # Проверяем, есть ли уже активные квесты
    existing = await conn.fetchval("""
        SELECT COUNT(*) FROM player_quests 
        WHERE player_id = $1 AND completed = FALSE AND claimed = FALSE
    """, player_id)
    
    if existing == 0:
        # Выбираем 3 случайных квеста
        quests = await conn.fetch("""
            SELECT * FROM quest_templates 
            ORDER BY RANDOM() 
            LIMIT 3
        """)
        
        for quest in quests:
            await conn.execute("""
                INSERT INTO player_quests (player_id, quest_id)
                VALUES ($1, $2)
            """, player_id, quest['id'])
    
    await conn.close()

async def update_quest_progress(player_id, quest_type, amount=1):
    """Обновляет прогресс квеста"""
    conn = await get_db()
    
    # Получаем активные квесты этого типа
    quests = await conn.fetch("""
        SELECT pq.*, qt.* 
        FROM player_quests pq
        JOIN quest_templates qt ON pq.quest_id = qt.id
        WHERE pq.player_id = $1 
          AND pq.completed = FALSE 
          AND pq.claimed = FALSE
          AND qt.quest_type = $2
          AND pq.expires_at > NOW()
    """, player_id, quest_type)
    
    for quest in quests:
        new_progress = quest['progress'] + amount
        if new_progress >= quest['target']:
            # Квест выполнен
            await conn.execute("""
                UPDATE player_quests 
                SET progress = $1, completed = TRUE
                WHERE id = $2
            """, quest['target'], quest['id'])
        else:
            # Обновляем прогресс
            await conn.execute("""
                UPDATE player_quests 
                SET progress = $1
                WHERE id = $2
            """, new_progress, quest['id'])
    
    await conn.close()

async def claim_quest_reward(player_id, quest_id):
    """Получить награду за квест"""
    conn = await get_db()
    
    quest = await conn.fetchrow("""
        SELECT pq.*, qt.* 
        FROM player_quests pq
        JOIN quest_templates qt ON pq.quest_id = qt.id
        WHERE pq.id = $1 AND pq.player_id = $2
    """, quest_id, player_id)
    
    if not quest or not quest['completed'] or quest['claimed']:
        await conn.close()
        return None
    
    # Добавляем награду
    await conn.execute("""
        UPDATE players 
        SET experience = experience + $1,
            credits = credits + $2
        WHERE id = $3
    """, quest['reward_exp'], quest['reward_credits'], player_id)
    
    # Отмечаем квест как полученный
    await conn.execute("""
        UPDATE player_quests 
        SET claimed = TRUE
        WHERE id = $1
    """, quest_id)
    
    # Проверка на уровень
    player = await conn.fetchrow("SELECT * FROM players WHERE id = $1", player_id)
    await conn.close()
    
    return {
        'name': quest['name'],
        'exp': quest['reward_exp'],
        'credits': quest['reward_credits']
    }

# ========== КОМАНДА КВЕСТОВ ==========
@dp.message_handler(commands=['quests'])
async def cmd_quests(message: types.Message):
    user_id = message.from_user.id
    conn = await get_db()
    
    player = await conn.fetchrow(
        "SELECT * FROM players WHERE telegram_id = $1",
        user_id
    )
    
    # Назначаем квесты если нужно
    await assign_daily_quests(player['id'])
    
    # Получаем активные квесты
    quests = await conn.fetch("""
        SELECT pq.*, qt.* 
        FROM player_quests pq
        JOIN quest_templates qt ON pq.quest_id = qt.id
        WHERE pq.player_id = $1 
          AND pq.claimed = FALSE
          AND pq.expires_at > NOW()
        ORDER BY pq.completed DESC, pq.progress DESC
    """, player['id'])
    
    await conn.close()
    
    if not quests:
        await message.reply("📜 **Нет активных квестов**\n\nЗагляни завтра!")
        return
    
    text = "📜 **ЕЖЕДНЕВНЫЕ КВЕСТЫ**\n\n"
    keyboard = InlineKeyboardMarkup(row_width=1)
    
    for q in quests:
        progress_bar = "█" * (q['progress'] * 10 // q['target']) + "░" * (10 - (q['progress'] * 10 // q['target']))
        status = "✅" if q['completed'] else "⏳"
        
        text += f"{status} **{q['name']}**\n"
        text += f"   {q['description']}\n"
        text += f"   Прогресс: {q['progress']}/{q['target']} {progress_bar}\n"
        text += f"   Награда: +{q['reward_exp']}✨ +{q['reward_credits']}💰\n\n"
        
        if q['completed'] and not q['claimed']:
            keyboard.add(
                InlineKeyboardButton(
                    f"🎁 Забрать награду: {q['name']}",
                    callback_data=f"claim_quest_{q['id']}"
                )
            )
    
    await message.reply(text, reply_markup=keyboard, parse_mode="Markdown")

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('claim_quest_'))
async def claim_quest(callback_query: types.CallbackQuery):
    await callback_query.answer()
    
    quest_id = int(callback_query.data.split('_')[2])
    user_id = callback_query.from_user.id
    
    conn = await get_db()
    player = await conn.fetchrow(
        "SELECT id FROM players WHERE telegram_id = $1",
        user_id
    )
    
    reward = await claim_quest_reward(player['id'], quest_id)
    await conn.close()
    
    if reward:
        await callback_query.message.edit_text(
            f"🎁 **Награда получена!**\n\n"
            f"Квест: {reward['name']}\n"
            f"+{reward['exp']}✨ опыта\n"
            f"+{reward['credits']}💰 кредитов"
        )
    else:
        await callback_query.message.edit_text("❌ Не удалось получить награду")

# ========== ОБНОВЛЕННАЯ КОМАНДА START ==========
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    user = message.from_user
    conn = await get_db()
    
    player = await conn.fetchrow(
        "SELECT * FROM players WHERE telegram_id = $1",
        user.id
    )
    
    if player:
        # Назначаем квесты
        await assign_daily_quests(player['id'])
        
        # Проверяем PvP рейтинг
        rating = await conn.fetchrow(
            "SELECT * FROM pvp_rating WHERE player_id = $1",
            player['id']
        )
        if not rating:
            await conn.execute(
                "INSERT INTO pvp_rating (player_id) VALUES ($1)",
                player['id']
            )
        
        # Проверяем, состоит ли в клане
        clan_member = await conn.fetchrow(
            "SELECT * FROM clan_members WHERE player_id = $1",
            player['id']
        )
        
        clan_text = ""
        if clan_member:
            clan = await conn.fetchrow(
                "SELECT * FROM clans WHERE id = $1",
                clan_member['clan_id']
            )
            clan_text = f"\n🏰 Клан: {clan['name']} [{clan['tag']}]"
        
        await message.reply(
            f"🌟 С возвращением, {user.first_name}!{clan_text}\n"
            f"Уровень: {player['level']} | Креды: {player['credits']}\n\n"
            f"⚔️ /battle - Битва с монстрами\n"
            f"🤺 /pvp - PvP арена\n"
            f"🏰 /clan - Кланы и гильдии\n"
            f"🏪 /shop - Магазин\n"
            f"📦 /inventory - Инвентарь\n"
            f"📜 /quests - Ежедневные квесты\n"
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
            f"🌟 Добро пожаловать в NEOMATRIX, {user.first_name}!\n"
            f"Ты зарегистрирован как новый игрок.\n"
            f"Получено 1000 стартовых кредов!\n\n"
            f"⚔️ /battle - Начать битву\n"
            f"🤺 /pvp - PvP арена\n"
            f"🏰 /clan - Кланы\n"
            f"📜 /quests - Квесты\n"
            f"🎁 /daily - Бонус"
        )
    await conn.close()

# ========== ОБНОВЛЕННАЯ БИТВА (с прогрессом квестов) ==========
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
        if conn:
            await conn.close()
        return
    
    # Простой враг
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
    
    # Обновляем прогресс квеста на трату энергии
    await update_quest_progress(player['id'], 'spend_energy', 10)
    
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
        player = await conn.fetchrow(
            "SELECT id FROM players WHERE telegram_id = $1",
            user_id
        )
        
        await conn.execute("""
            UPDATE players 
            SET experience = experience + $1, 
                credits = credits + $2,
                monsters_killed = monsters_killed + 1
            WHERE telegram_id = $3
        """, 15, 40, user_id)
        
        # Обновляем прогресс квестов
        await update_quest_progress(player['id'], 'kill_monsters')
        await update_quest_progress(player['id'], 'earn_credits', 40)
        
        await conn.close()
        await callback_query.message.edit_text("🎉 **ПОБЕДА!** +15✨ +40💰")
        del active_battles[battle_id]

# ========== ОБНОВЛЕННЫЙ PvP (с прогрессом квестов) ==========
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
            await callback_query.message.edit_text(
                "🔍 **Поиск противника...**\nОжидайте..."
            )
            if len(pvp_queue) >= 2:
                player1 = pvp_queue.pop(0)
                player2 = pvp_queue.pop(0)
                await start_pvp_battle(player1, player2, callback_query.message)
    
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
    
    r1 = await conn.fetchrow(
        "SELECT * FROM pvp_rating WHERE player_id = $1",
        p1['id']
    )
    r2 = await conn.fetchrow(
        "SELECT * FROM pvp_rating WHERE player_id = $1",
        p2['id']
    )
    await conn.close()
    
    battle_id = f"pvp_{player1_id}_{player2_id}"
    
    pvp_battles[battle_id] = {
        'player1': {'id': player1_id, 'name': p1['username'] or "Игрок1", 'hp': 100, 'max_hp': 100},
        'player2': {'id': player2_id, 'name': p2['username'] or "Игрок2", 'hp': 100, 'max_hp': 100},
        'turn': 1,
        'current_player': player1_id
    }
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("⚔️ Атаковать", callback_data=f"pvp_attack_{battle_id}"),
        InlineKeyboardButton("🛡️ Защита", callback_data=f"pvp_defend_{battle_id}")
    )
    
    await bot.send_message(player1_id, 
        f"🤺 **PvP БИТВА**\n\nПротивник: {p2['username']}\nРейтинг соперника: {r2['rating']}\n\nТвой ход!",
        reply_markup=keyboard)
    await bot.send_message(player2_id, "🤺 Началась PvP битва! Ожидай своего хода...")

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('pvp_attack_'))
async def pvp_attack(callback_query: types.CallbackQuery):
    await callback_query.answer()
    
    battle_id = callback_query.data.replace('pvp_attack_', '')
    
    if battle_id not in pvp_battles:
        await callback_query.message.reply("⚠️ Битва закончена!")
        return
    
    battle = pvp_battles[battle_id]
    user_id = callback_query.from_user.id
    
    # Определяем, кто сейчас ходит
    if user_id == battle['player1']['id']:
        attacker = battle['player1']
        defender = battle['player2']
    else:
        attacker = battle['player2']
        defender = battle['player1']
    
    damage = random.randint(15, 25)
    defender['hp'] -= damage
    
    result_text = f"⚔️ Ты нанес {damage} урона!\n"
    
    if defender['hp'] <= 0:
        # Победа
        winner_id = attacker['id']
        loser_id = defender['id']
        
        conn = await get_db()
        
        winner = await conn.fetchrow(
            "SELECT id FROM players WHERE telegram_id = $1",
            winner_id
        )
        loser = await conn.fetchrow(
            "SELECT id FROM players WHERE telegram_id = $1",
            loser_id
        )
        
        # Обновляем рейтинг
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
        
        # Обновляем прогресс квеста для победителя
        await update_quest_progress(winner['id'], 'win_pvp')
        
        await conn.close()
        
        await bot.send_message(winner_id, f"🎉 **ПОБЕДА!** +20 рейтинга!")
        await bot.send_message(loser_id, f"💔 **Поражение!** -10 рейтинга")
        
        del pvp_battles[battle_id]
        return
    
    # Меняем ход
    battle['current_player'] = defender['id']
    battle['turn'] += 1
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("⚔️ Атаковать", callback_data=f"pvp_attack_{battle_id}"),
        InlineKeyboardButton("🛡️ Защита", callback_data=f"pvp_defend_{battle_id}")
    )
    
    await callback_query.message.edit_text(
        f"🤺 **PvP БИТВА**\n\n"
        f"{battle['player1']['name']}: ❤️ {battle['player1']['hp']}\n"
        f"{battle['player2']['name']}: ❤️ {battle['player2']['hp']}\n\n"
        f"{result_text}\n"
        f"Ход {battle['turn']}. Твой ход!",
        reply_markup=keyboard
    )
    
    await bot.send_message(defender['id'], "⚔️ Твой ход в PvP битве!")

# Остальные команды (inventory, shop, profile, daily, top, clan) остаются такими же как в game_clans.py

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    from aiogram import executor
    print("📜 NEOMATRIX - ПОЛНАЯ ВЕРСИЯ С КВЕСТАМИ!")
    print("Нажми Ctrl+C для остановки")
    executor.start_polling(dp, skip_updates=True, loop=loop)
"@ | Out-File -FilePath game_quests.py -Encoding UTF8