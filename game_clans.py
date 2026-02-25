# game_clans.py - ПОЛНАЯ ВЕРСИЯ С КЛАНАМИ И ЭКИПИРОВКОЙ

import asyncio
import logging
import random
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import asyncpg

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = "8689690200:AAGkYm61FQntnn7yScMnzdHzMgxVKBeEndM"  # ЗАМЕНИ НА СВОЙ ТОКЕН!
DB_PASSWORD = "1234567890"  # ТВОЙ ПАРОЛЬ ОТ БАЗЫ ДАННЫХ!

logging.basicConfig(level=logging.INFO)

# Создаем цикл событий для Python 3.14
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# Создаем бота и диспетчер
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

# ========== СИСТЕМА ЭКИПИРОВКИ ==========

@dp.message_handler(commands=['inventory'])
async def cmd_inventory(message: types.Message):
    user_id = message.from_user.id
    conn = await get_db()
    
    player = await conn.fetchrow(
        "SELECT id FROM players WHERE telegram_id = $1",
        user_id
    )
    
    # Получаем все предметы игрока
    items = await conn.fetch("""
        SELECT pi.*, i.name, i.type, i.rarity, i.damage_bonus, 
               i.health_bonus, i.defense_bonus, i.description
        FROM player_items pi
        JOIN items i ON pi.item_id = i.id
        WHERE pi.player_id = $1
        ORDER BY pi.equipped DESC, i.rarity DESC
    """, player['id'])
    
    # Получаем надетую экипировку
    equip = await conn.fetchrow(
        "SELECT * FROM equipment WHERE player_id = $1",
        player['id']
    )
    await conn.close()
    
    if not items:
        await message.reply("📦 **Инвентарь пуст**\n\nКупи предметы в магазине /shop")
        return
    
    text = "📦 **ТВОЙ ИНВЕНТАРЬ**\n\n"
    keyboard = InlineKeyboardMarkup(row_width=1)
    
    for item in items:
        rarity_emoji = {
            'common': '⚪',
            'rare': '🔵',
            'epic': '🟣',
            'legendary': '🟡'
        }.get(item['rarity'], '⚪')
        
        equipped = "✅ " if item['equipped'] else ""
        text += f"{equipped}{rarity_emoji} **{item['name']}**\n"
        text += f"   Прочность: {item['durability']}%\n"
        
        keyboard.add(
            InlineKeyboardButton(
                f"{'✅ Надето' if item['equipped'] else '📌 Надеть'} {item['name']}",
                callback_data=f"equip_{item['id']}"
            )
        )
    
    await message.reply(text, reply_markup=keyboard, parse_mode="Markdown")

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('equip_'))
async def equip_item(callback_query: types.CallbackQuery):
    await callback_query.answer()
    
    item_id = int(callback_query.data.split('_')[1])
    user_id = callback_query.from_user.id
    
    conn = await get_db()
    player = await conn.fetchrow(
        "SELECT id FROM players WHERE telegram_id = $1",
        user_id
    )
    
    # Получаем предмет
    item = await conn.fetchrow("""
        SELECT pi.*, i.type, i.name
        FROM player_items pi
        JOIN items i ON pi.item_id = i.id
        WHERE pi.id = $1 AND pi.player_id = $2
    """, item_id, player['id'])
    
    if not item:
        await callback_query.message.reply("❌ Предмет не найден")
        await conn.close()
        return
    
    # Снимаем все предметы этого типа
    await conn.execute("""
        UPDATE player_items 
        SET equipped = FALSE 
        WHERE player_id = $1 AND item_id IN (
            SELECT id FROM items WHERE type = $2
        )
    """, player['id'], item['type'])
    
    # Надеваем новый предмет
    await conn.execute("""
        UPDATE player_items 
        SET equipped = TRUE 
        WHERE id = $1
    """, item_id)
    
    # Обновляем таблицу equipment
    column_name = f"{item['type']}_id"
    await conn.execute(f"""
        INSERT INTO equipment (player_id, {column_name})
        VALUES ($1, $2)
        ON CONFLICT (player_id) 
        DO UPDATE SET {column_name} = $2
    """, player['id'], item_id)
    
    await conn.close()
    
    await callback_query.message.edit_text(f"✅ **Надето:** {item['name']}")

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
            f"🏰 /clan - Создать или найти клан\n"
            f"🎁 /daily - Бонус"
        )
    await conn.close()

# ========== КЛАНЫ ==========
@dp.message_handler(commands=['clan'])
async def cmd_clan(message: types.Message):
    user_id = message.from_user.id
    conn = await get_db()
    
    player = await conn.fetchrow(
        "SELECT id FROM players WHERE telegram_id = $1",
        user_id
    )
    
    # Проверяем, состоит ли в клане
    member = await conn.fetchrow(
        "SELECT * FROM clan_members WHERE player_id = $1",
        player['id']
    )
    await conn.close()
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    if member:
        # Уже в клане
        keyboard.add(
            InlineKeyboardButton("🏰 Мой клан", callback_data="clan_my"),
            InlineKeyboardButton("📊 Рейтинг кланов", callback_data="clan_top"),
            InlineKeyboardButton("🚪 Покинуть клан", callback_data="clan_leave")
        )
        text = "🏰 **КЛАНОВОЕ МЕНЮ**\n\nТы уже в клане! Выбери действие:"
    else:
        # Не в клане
        keyboard.add(
            InlineKeyboardButton("🔍 Найти клан", callback_data="clan_search"),
            InlineKeyboardButton("✨ Создать клан", callback_data="clan_create"),
            InlineKeyboardButton("📊 Рейтинг кланов", callback_data="clan_top")
        )
        text = "🏰 **КЛАНЫ И ГИЛЬДИИ**\n\nТы еще не в клане. Создай свой или вступи в существующий!"
    
    await message.reply(text, reply_markup=keyboard, parse_mode="Markdown")

@dp.callback_query_handler(lambda c: c.data == "clan_create")
async def clan_create(callback_query: types.CallbackQuery):
    await callback_query.answer()
    await callback_query.message.edit_text(
        "✨ **СОЗДАНИЕ КЛАНА**\n\n"
        "Отправь мне название и тег клана в формате:\n"
        "`Название [ТЕГ]`\n\n"
        "Например: `Хранители Матрицы [ХМ]`\n\n"
        "Требования:\n"
        "• Уровень 5+\n"
        "• 1000 кредов\n\n"
        "Для отмены напиши /cancel",
        parse_mode="Markdown"
    )

@dp.callback_query_handler(lambda c: c.data == "clan_search")
async def clan_search(callback_query: types.CallbackQuery):
    await callback_query.answer()
    
    conn = await get_db()
    clans = await conn.fetch("""
        SELECT c.*, COUNT(cm.id) as members 
        FROM clans c
        LEFT JOIN clan_members cm ON c.id = cm.clan_id
        GROUP BY c.id
        ORDER BY c.level DESC
        LIMIT 10
    """)
    await conn.close()
    
    text = "🔍 **ДОСТУПНЫЕ КЛАНЫ**\n\n"
    keyboard = InlineKeyboardMarkup(row_width=1)
    
    for clan in clans:
        text += f"**{clan['name']}** [{clan['tag']}]\n"
        text += f"Уровень: {clan['level']} | Участников: {clan['members']}\n\n"
        
        keyboard.add(
            InlineKeyboardButton(
                f"📝 Вступить в {clan['name']}",
                callback_data=f"clan_join_{clan['id']}"
            )
        )
    
    await callback_query.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")

@dp.callback_query_handler(lambda c: c.data.startswith("clan_join_"))
async def clan_join(callback_query: types.CallbackQuery):
    await callback_query.answer()
    
    clan_id = int(callback_query.data.split('_')[2])
    user_id = callback_query.from_user.id
    
    conn = await get_db()
    player = await conn.fetchrow(
        "SELECT id FROM players WHERE telegram_id = $1",
        user_id
    )
    
    # Проверяем, не в клане ли уже
    existing = await conn.fetchrow(
        "SELECT * FROM clan_members WHERE player_id = $1",
        player['id']
    )
    if existing:
        await callback_query.message.edit_text("❌ Ты уже в клане!")
        await conn.close()
        return
    
    clan = await conn.fetchrow("SELECT * FROM clans WHERE id = $1", clan_id)
    
    # Добавляем в клан
    await conn.execute("""
        INSERT INTO clan_members (clan_id, player_id, role)
        VALUES ($1, $2, 'member')
    """, clan_id, player['id'])
    
    # Обновляем счетчик участников
    await conn.execute("""
        UPDATE clans SET members_count = members_count + 1 WHERE id = $1
    """, clan_id)
    
    await conn.close()
    
    await callback_query.message.edit_text(
        f"✅ **Ты вступил в клан!**\n\n"
        f"Клан: {clan['name']} [{clan['tag']}]"
    )

@dp.callback_query_handler(lambda c: c.data == "clan_my")
async def clan_my(callback_query: types.CallbackQuery):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    
    conn = await get_db()
    player = await conn.fetchrow(
        "SELECT id FROM players WHERE telegram_id = $1",
        user_id
    )
    
    member = await conn.fetchrow(
        "SELECT * FROM clan_members WHERE player_id = $1",
        player['id']
    )
    
    if not member:
        await callback_query.message.edit_text("❌ Ты не в клане!")
        await conn.close()
        return
    
    clan = await conn.fetchrow("SELECT * FROM clans WHERE id = $1", member['clan_id'])
    members = await conn.fetch("""
        SELECT p.username, cm.role, cm.clan_score
        FROM clan_members cm
        JOIN players p ON cm.player_id = p.id
        WHERE cm.clan_id = $1
        ORDER BY cm.role DESC, cm.clan_score DESC
    """, clan['id'])
    await conn.close()
    
    text = f"""
🏰 **КЛАН: {clan['name']}** [{clan['tag']}]
═══════════════════
📊 Уровень: {clan['level']}
👥 Участников: {len(members)}
═══════════════════
**УЧАСТНИКИ:**
    """
    
    for m in members:
        role_emoji = "👑" if m['role'] == 'owner' else "⚔️"
        name = m['username'] or "Игрок"
        text += f"\n{role_emoji} {name}"
    
    await callback_query.message.edit_text(text, parse_mode="Markdown")

@dp.callback_query_handler(lambda c: c.data == "clan_top")
async def clan_top(callback_query: types.CallbackQuery):
    await callback_query.answer()
    
    conn = await get_db()
    top_clans = await conn.fetch("""
        SELECT name, level, members_count 
        FROM clans 
        ORDER BY level DESC, members_count DESC 
        LIMIT 10
    """)
    await conn.close()
    
    text = "🏆 **ТОП КЛАНОВ**\n\n"
    for i, c in enumerate(top_clans, 1):
        text += f"{i}. {c['name']} - Ур.{c['level']} (👥 {c['members_count']})\n"
    
    await callback_query.message.edit_text(text, parse_mode="Markdown")

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
        'player1': {'id': player1_id, 'name': p1['username'] or "Игрок", 'hp': 100, 'max_hp': 100},
        'player2': {'id': player2_id, 'name': p2['username'] or "Игрок", 'hp': 100, 'max_hp': 100},
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
    
    # Получаем бонусы от экипировки
    equip = await conn.fetchrow(
        "SELECT * FROM equipment WHERE player_id = $1",
        player['id']
    )
    
    total_damage_bonus = 0
    total_health_bonus = 0
    total_defense_bonus = 0
    
    if equip:
        # Собираем все надетые предметы
        for slot in ['helmet_id', 'armor_id', 'weapon_id', 'accessory_id']:
            if equip[slot]:
                item = await conn.fetchrow("""
                    SELECT i.* FROM player_items pi
                    JOIN items i ON pi.item_id = i.id
                    WHERE pi.id = $1
                """, equip[slot])
                if item:
                    total_damage_bonus += item['damage_bonus']
                    total_health_bonus += item['health_bonus']
                    total_defense_bonus += item['defense_bonus']
    
    pvp = await conn.fetchrow(
        "SELECT * FROM pvp_rating WHERE player_id = $1",
        player['id']
    )
    
    # Информация о клане
    clan_member = await conn.fetchrow(
        "SELECT * FROM clan_members WHERE player_id = $1",
        player['id']
    )
    
    clan_text = "Нет клана"
    if clan_member:
        clan = await conn.fetchrow(
            "SELECT * FROM clans WHERE id = $1",
            clan_member['clan_id']
        )
        clan_text = f"{clan['name']} [{clan['tag']}]"
    
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
🏰 Клан: {clan_text}
📊 Уровень: {player['level']}
❤️ HP: {player['health']}/{player['max_health']} +{total_health_bonus}
⚡ Энергия: {player['energy']}/{player['max_energy']}
⚔️ Доп. урон: +{total_damage_bonus}
🛡️ Доп. защита: +{total_defense_bonus}
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
📦 /inventory - Инвентарь
    """
    await message.reply(profile_text, parse_mode="Markdown")

# ========== МАГАЗИН ==========
@dp.message_handler(commands=['shop'])
async def cmd_shop(message: types.Message):
    conn = await get_db()
    
    items = await conn.fetch("""
        SELECT * FROM items 
        ORDER BY price
    """)
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    for item in items:
        rarity_emoji = {
            'common': '⚪',
            'rare': '🔵',
            'epic': '🟣',
            'legendary': '🟡'
        }.get(item['rarity'], '⚪')
        
        keyboard.insert(
            InlineKeyboardButton(
                f"{rarity_emoji} {item['name']} ({item['price']}💰)",
                callback_data=f"buy_item_{item['id']}"
            )
        )
    await conn.close()
    
    await message.reply(
        "🏪 **МАГАЗИН ЭКИПИРОВКИ**\n\n"
        "Покупай предметы и надевай их через /inventory",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('buy_item_'))
async def buy_item(callback_query: types.CallbackQuery):
    await callback_query.answer()
    
    item_id = int(callback_query.data.split('_')[2])
    user_id = callback_query.from_user.id
    
    conn = await get_db()
    player = await conn.fetchrow(
        "SELECT * FROM players WHERE telegram_id = $1",
        user_id
    )
    
    item = await conn.fetchrow(
        "SELECT * FROM items WHERE id = $1",
        item_id
    )
    
    if player['credits'] < item['price']:
        await callback_query.message.reply("❌ Недостаточно кредов!")
        await conn.close()
        return
    
    # Добавляем предмет игроку
    await conn.execute("""
        INSERT INTO player_items (player_id, item_id, durability)
        VALUES ($1, $2, 100)
    """, player['id'], item_id)
    
    # Списываем кредиты
    await conn.execute("""
        UPDATE players SET credits = credits - $1 WHERE id = $2
    """, item['price'], player['id'])
    
    await conn.close()
    
    await callback_query.message.reply(
        f"✅ **Куплено:** {item['name']}!\n"
        f"Посмотри в /inventory и надень его!"
    )

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
    
    if action == "attack":
        damage = random.randint(15, 25)
        battle['enemy_hp'] -= damage
        await callback_query.message.edit_text(f"⚔️ Ты нанес {damage} урона!\n❤️ Враг: {battle['enemy_hp']}")
    
    if battle['enemy_hp'] <= 0:
        conn = await get_db()
        await conn.execute("""
            UPDATE players 
            SET experience = experience + $1, credits = credits + $2,
                monsters_killed = monsters_killed + 1
            WHERE telegram_id = $3
        """, 15, 40, battle['player_id'])
        await conn.close()
        await callback_query.message.edit_text("🎉 **ПОБЕДА!** +15 опыта, +40💰")
        del active_battles[battle_id]

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
    
    top_clans = await conn.fetch("""
        SELECT name, level, members_count 
        FROM clans 
        ORDER BY level DESC, members_count DESC 
        LIMIT 5
    """)
    await conn.close()
    
    text = "🏆 **ЗАЛ СЛАВЫ**\n\n"
    
    text += "**⚔️ ТОП ПО УРОВНЮ:**\n"
    for i, p in enumerate(top_pve, 1):
        name = p['username'] or f"Игрок{i}"
        text += f"{i}. {name} - Ур.{p['level']} (👾 {p['monsters_killed']})\n"
    
    text += "\n**🤺 ТОП PvP:**\n"
    for i, p in enumerate(top_pvp, 1):
        name = p['username'] or f"Игрок{i}"
        text += f"{i}. {name} - {p['rating']} ⚔️\n"
    
    text += "\n**🏰 ТОП КЛАНОВ:**\n"
    for i, c in enumerate(top_clans, 1):
        text += f"{i}. {c['name']} - Ур.{c['level']} (👥 {c['members_count']})\n"
    
    await message.reply(text, parse_mode="Markdown")

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    from aiogram import executor
    print("🏰 NEOMATRIX - ПОЛНАЯ ВЕРСИЯ С КЛАНАМИ И ЭКИПИРОВКОЙ!")
    print("Нажми Ctrl+C для остановки")
    executor.start_polling(dp, skip_updates=True, loop=loop)