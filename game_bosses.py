# game_bosses.py - ПОЛНАЯ ВЕРСИЯ С БОССАМИ И РЕЙДАМИ

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
pvp_battles = []
boss_battles = {}

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
    conn = await get_db()
    await conn.execute("""
        DELETE FROM player_quests 
        WHERE player_id = $1 AND (expires_at < NOW() OR claimed = TRUE)
    """, player_id)
    
    existing = await conn.fetchval("""
        SELECT COUNT(*) FROM player_quests 
        WHERE player_id = $1 AND completed = FALSE AND claimed = FALSE
    """, player_id)
    
    if existing == 0:
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
    conn = await get_db()
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
            await conn.execute("""
                UPDATE player_quests 
                SET progress = $1, completed = TRUE
                WHERE id = $2
            """, quest['target'], quest['id'])
        else:
            await conn.execute("""
                UPDATE player_quests 
                SET progress = $1
                WHERE id = $2
            """, new_progress, quest['id'])
    await conn.close()

async def claim_quest_reward(player_id, quest_id):
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
    
    await conn.execute("""
        UPDATE players 
        SET experience = experience + $1,
            credits = credits + $2
        WHERE id = $3
    """, quest['reward_exp'], quest['reward_credits'], player_id)
    
    await conn.execute("""
        UPDATE player_quests 
        SET claimed = TRUE
        WHERE id = $1
    """, quest_id)
    
    await conn.close()
    return {'name': quest['name'], 'exp': quest['reward_exp'], 'credits': quest['reward_credits']}

# ========== ФУНКЦИИ ДЛЯ БОССОВ ==========

async def spawn_clan_boss(clan_id):
    """Создает босса для клана"""
    conn = await get_db()
    
    # Проверяем, есть ли уже активный босс
    existing = await conn.fetchrow("""
        SELECT * FROM active_bosses 
        WHERE clan_id = $1 AND defeated = FALSE AND expires_at > NOW()
    """, clan_id)
    
    if existing:
        await conn.close()
        return existing
    
    # Выбираем случайного босса подходящего уровня
    boss = await conn.fetchrow("""
        SELECT * FROM boss_templates 
        ORDER BY RANDOM() 
        LIMIT 1
    """)
    
    # Создаем босса
    active = await conn.fetchrow("""
        INSERT INTO active_bosses (boss_id, current_health, clan_id)
        VALUES ($1, $2, $3)
        RETURNING *
    """, boss['id'], boss['health'], clan_id)
    
    await conn.close()
    return active

async def get_clan_boss(clan_id):
    """Получает активного босса клана"""
    conn = await get_db()
    boss = await conn.fetchrow("""
        SELECT ab.*, bt.* 
        FROM active_bosses ab
        JOIN boss_templates bt ON ab.boss_id = bt.id
        WHERE ab.clan_id = $1 AND ab.defeated = FALSE AND ab.expires_at > NOW()
    """, clan_id)
    await conn.close()
    return boss

async def deal_damage_to_boss(boss_instance_id, player_id, damage):
    """Наносит урон боссу"""
    conn = await get_db()
    
    # Обновляем здоровье босса
    boss = await conn.fetchrow("""
        UPDATE active_bosses 
        SET current_health = current_health - $1
        WHERE id = $2 AND current_health > 0
        RETURNING *
    """, damage, boss_instance_id)
    
    if boss:
        # Записываем урон игрока
        await conn.execute("""
            INSERT INTO boss_damage (boss_instance_id, player_id, damage)
            VALUES ($1, $2, $3)
        """, boss_instance_id, player_id, damage)
        
        # Проверяем, не убит ли босс
        if boss['current_health'] <= 0:
            await conn.execute("""
                UPDATE active_bosses 
                SET defeated = TRUE
                WHERE id = $1
            """, boss_instance_id)
            
            # Награждаем всех участников
            await reward_boss_participants(boss_instance_id, conn)
    
    await conn.close()
    return boss

async def reward_boss_participants(boss_instance_id, conn):
    """Награждает участников битвы с боссом"""
    # Получаем информацию о боссе
    boss = await conn.fetchrow("""
        SELECT ab.*, bt.* 
        FROM active_bosses ab
        JOIN boss_templates bt ON ab.boss_id = bt.id
        WHERE ab.id = $1
    """, boss_instance_id)
    
    # Получаем всех кто наносил урон
    participants = await conn.fetch("""
        SELECT player_id, damage 
        FROM boss_damage 
        WHERE boss_instance_id = $1
        ORDER BY damage DESC
    """, boss_instance_id)
    
    total_damage = sum(p['damage'] for p in participants)
    
    for p in participants:
        # Награда пропорционально урону
        share = p['damage'] / total_damage
        exp_reward = int(boss['reward_exp'] * share * 2)
        credit_reward = int(boss['reward_credits'] * share * 2)
        
        await conn.execute("""
            UPDATE players 
            SET experience = experience + $1,
                credits = credits + $2
            WHERE id = $3
        """, exp_reward, credit_reward, p['player_id'])

# ========== КОМАНДА БОССОВ ==========
@dp.message_handler(commands=['boss'])
async def cmd_boss(message: types.Message):
    user_id = message.from_user.id
    conn = await get_db()
    
    player = await conn.fetchrow(
        "SELECT * FROM players WHERE telegram_id = $1",
        user_id
    )
    
    # Проверяем, состоит ли в клане
    member = await conn.fetchrow(
        "SELECT * FROM clan_members WHERE player_id = $1",
        player['id']
    )
    
    if not member:
        await message.reply("❌ Ты должен состоять в клане, чтобы сражаться с боссами!")
        await conn.close()
        return
    
    # Получаем или создаем босса клана
    boss = await get_clan_boss(member['clan_id'])
    
    if not boss:
        # Создаем нового босса
        boss = await spawn_clan_boss(member['clan_id'])
        await message.reply("👾 **Появился новый клановый босс!**")
    
    # Получаем топ урона
    top_damage = await conn.fetch("""
        SELECT p.username, bd.damage 
        FROM boss_damage bd
        JOIN players p ON bd.player_id = p.id
        WHERE bd.boss_instance_id = $1
        ORDER BY bd.damage DESC
        LIMIT 5
    """, boss['id'])
    
    await conn.close()
    
    # Создаем клавиатуру
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("⚔️ Атаковать босса", callback_data=f"boss_attack_{boss['id']}")
    )
    
    # Формируем текст
    text = f"""
👾 **КЛАНОВЫЙ БОСС**
═══════════════════
**{boss['name']}** (Ур.{boss['level']})
❤️ HP: {boss['current_health']}/{boss['health']}
⚔️ Урон босса: {boss['damage']}

**Топ урона по боссу:**
"""
    for i, t in enumerate(top_damage, 1):
        name = t['username'] or f"Игрок{i}"
        text += f"{i}. {name} - {t['damage']}⚔️\n"
    
    text += f"\nОсталось времени: 3 часа"
    
    await message.reply(text, reply_markup=keyboard, parse_mode="Markdown")

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('boss_attack_'))
async def boss_attack(callback_query: types.CallbackQuery):
    await callback_query.answer()
    
    boss_id = int(callback_query.data.split('_')[2])
    user_id = callback_query.from_user.id
    
    conn = await get_db()
    player = await conn.fetchrow(
        "SELECT * FROM players WHERE telegram_id = $1",
        user_id
    )
    
    # Проверяем энергию
    if player['energy'] < 20:
        await callback_query.message.reply("⚡ Нужно 20 энергии для атаки босса!")
        await conn.close()
        return
    
    # Получаем босса
    boss = await conn.fetchrow("""
        SELECT ab.*, bt.* 
        FROM active_bosses ab
        JOIN boss_templates bt ON ab.boss_id = bt.id
        WHERE ab.id = $1 AND ab.defeated = FALSE
    """, boss_id)
    
    if not boss:
        await callback_query.message.reply("❌ Босс уже побежден или исчез!")
        await conn.close()
        return
    
    # Рассчитываем урон
    damage = random.randint(30, 50) + player['level'] * 5
    
    # Тратим энергию
    await conn.execute("""
        UPDATE players SET energy = energy - 20 WHERE id = $1
    """, player['id'])
    
    # Наносим урон
    updated = await deal_damage_to_boss(boss_id, player['id'], damage)
    
    if updated and updated['current_health'] <= 0:
        await callback_query.message.reply(
            f"🎉 **БОСС ПОБЕЖДЕН!**\n\n"
            f"Ты нанес {damage} урона!\n"
            f"Награда будет распределена между всеми участниками!"
        )
    else:
        await callback_query.message.reply(
            f"⚔️ Ты нанес {damage} урона боссу!\n"
            f"❤️ Осталось HP: {updated['current_health'] if updated else 0}"
        )
    
    await conn.close()

# ========== КВЕСТЫ ==========
@dp.message_handler(commands=['quests'])
async def cmd_quests(message: types.Message):
    user_id = message.from_user.id
    conn = await get_db()
    
    player = await conn.fetchrow(
        "SELECT * FROM players WHERE telegram_id = $1",
        user_id
    )
    
    await assign_daily_quests(player['id'])
    
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
        await assign_daily_quests(player['id'])
        
        await message.reply(
            f"🌟 С возвращением, {user.first_name}!\n"
            f"Уровень: {player['level']} | Креды: {player['credits']}\n\n"
            f"⚔️ /battle - Битва с монстрами\n"
            f"🤺 /pvp - PvP арена\n"
            f"👾 /boss - Клановые боссы\n"
            f"📜 /quests - Ежедневные квесты\n"
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
            f"👾 /boss - Клановые боссы\n"
            f"📜 /quests - Квесты\n"
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
        
        await update_quest_progress(player['id'], 'kill_monsters')
        await update_quest_progress(player['id'], 'earn_credits', 40)
        
        await conn.close()
        await callback_query.message.edit_text("🎉 **ПОБЕДА!** +15✨ +40💰")
        del active_battles[battle_id]

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
    await message.reply("📦 **Инвентарь**\n\nСкоро тут будут предметы от боссов!")

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    from aiogram import executor
    print("👾 NEOMATRIX - ПОЛНАЯ ВЕРСИЯ С БОССАМИ!")
    print("Нажми Ctrl+C для остановки")
    executor.start_polling(dp, skip_updates=True, loop=loop)