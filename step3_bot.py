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

# ---------- Хранилища ----------
active_battles = {}          # обычные битвы с монстрами
pvp_queue = []                # очередь игроков на PvP
active_pvp_battles = {}       # активные PvP-битвы
memory_players = {}           # данные игроков в памяти (если нет БД)
memory_pvp_ratings = {}       # PvP-рейтинги в памяти

# ---------- Шаблоны врагов (из предыдущей версии) ----------
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
    template = random.choice(ENEMY_TEMPLATES)
    enemy_level = max(1, player_level + random.randint(-1, 2))
    multiplier = 1 + (enemy_level - 1) * 0.2
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

# ---------- Работа с БД (добавлена таблица pvp_rating) ----------
async def init_db():
    if not DATABASE_URL:
        print("⚠️ DATABASE_URL не задана – работа без сохранения данных")
        return
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        # Таблица игроков
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
        # Таблица PvP-рейтинга
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS pvp_rating (
                user_id BIGINT PRIMARY KEY REFERENCES players(user_id) ON DELETE CASCADE,
                rating INT DEFAULT 1000,
                wins INT DEFAULT 0,
                losses INT DEFAULT 0
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
        # При создании игрока автоматически создаём запись в pvp_rating
        await conn.execute('''
            INSERT INTO pvp_rating (user_id, rating, wins, losses) VALUES ($1, 1000, 0, 0)
            ON CONFLICT (user_id) DO NOTHING
        ''', user_id)
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

# ---------- Функции для PvP-рейтинга ----------
async def get_pvp_rating_from_db(user_id):
    if not DATABASE_URL:
        return None
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        row = await conn.fetchrow('SELECT rating, wins, losses FROM pvp_rating WHERE user_id = $1', user_id)
        await conn.close()
        return row
    except:
        return None

async def update_pvp_rating_in_db(user_id, **kwargs):
    if not DATABASE_URL:
        return
    try:
        set_clause = ', '.join(f"{k} = ${i+2}" for i, k in enumerate(kwargs))
        values = [user_id] + list(kwargs.values())
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute(f'UPDATE pvp_rating SET {set_clause} WHERE user_id = $1', *values)
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

async def get_pvp_rating_safe(user_id):
    # Из БД
    db_rating = await get_pvp_rating_from_db(user_id)
    if db_rating:
        return dict(db_rating)
    # Из памяти
    if user_id in memory_pvp_ratings:
        return memory_pvp_ratings[user_id]
    # Создаём по умолчанию
    default = {'rating': 1000, 'wins': 0, 'losses': 0}
    memory_pvp_ratings[user_id] = default
    return default

async def update_pvp_rating_safe(user_id, **kwargs):
    if user_id in memory_pvp_ratings:
        memory_pvp_ratings[user_id].update(kwargs)
    await update_pvp_rating_in_db(user_id, **kwargs)

# ---------- Команды бота (старые) ----------
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "NoName"
    player = await get_player_safe(user_id, username)
    await message.reply(
        f"🌟 Добро пожаловать, {message.from_user.first_name}!\n"
        f"Уровень: {player['level']} | Креды: {player['credits']}\n\n"
        f"⚔️ /battle - Битва с монстрами\n"
        f"🤺 /pvp - PvP-арена\n"
        f"📊 /profile - Профиль\n"
        f"🎁 /daily - Бонус\n"
        f"🏆 /top - Топ игроков\n"
        f"🏪 /shop - Магазин"
    )

@dp.message_handler(commands=['profile'])
async def cmd_profile(message: types.Message):
    user_id = message.from_user.id
    player = await get_player_safe(user_id)
    pvp = await get_pvp_rating_safe(user_id)
    await message.reply(
        f"📊 **ПРОФИЛЬ**\n\n"
        f"Уровень: {player['level']}\n"
        f"Опыт: {player['exp']}/100\n"
        f"❤️ HP: {player['health']}/{player['max_health']}\n"
        f"⚡ Энергия: {player['energy']}/{player['max_energy']}\n"
        f"💰 Креды: {player['credits']}\n"
        f"👾 Убито монстров: {player['monsters_killed']}\n\n"
        f"**PvP-рейтинг:** {pvp['rating']} (побед: {pvp['wins']}, поражений: {pvp['losses']})",
        parse_mode="Markdown"
    )

# ---------- Команды PvP ----------
@dp.message_handler(commands=['pvp'])
async def cmd_pvp(message: types.Message):
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("🔍 Найти противника", callback_data="pvp_find"),
        InlineKeyboardButton("📊 Мой рейтинг", callback_data="pvp_rating"),
        InlineKeyboardButton("🏆 Топ PvP", callback_data="pvp_top"),
        InlineKeyboardButton("❌ Выйти из очереди", callback_data="pvp_leave")
    )
    await message.reply(
        "🤺 **PvP-АРЕНА**\n\n"
        "Найди противника и сразись!\n"
        "Победа: +20 рейтинга\n"
        "Поражение: -10 рейтинга\n\n"
        "Выбери действие:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@dp.callback_query_handler(lambda c: c.data.startswith('pvp_'))
async def pvp_callback(callback: types.CallbackQuery):
    action = callback.data.split('_')[1]
    user_id = callback.from_user.id

    if action == 'find':
        # Добавляем в очередь, если ещё не там
        if user_id in pvp_queue:
            await callback.answer("Ты уже в очереди!")
            return
        pvp_queue.append(user_id)
        await callback.message.edit_text("🔍 **Поиск противника...**\nОжидай, как только найдётся соперник, битва начнётся.")
        # Проверяем, есть ли пара
        if len(pvp_queue) >= 2:
            player1 = pvp_queue.pop(0)
            player2 = pvp_queue.pop(0)
            await start_pvp_battle(player1, player2)
        await callback.answer()

    elif action == 'rating':
        pvp = await get_pvp_rating_safe(user_id)
        await callback.message.edit_text(
            f"📊 **Твой PvP-рейтинг**\n\n"
            f"Рейтинг: {pvp['rating']}\n"
            f"Побед: {pvp['wins']}\n"
            f"Поражений: {pvp['losses']}"
        )
        await callback.answer()

    elif action == 'top':
        # Топ из БД или памяти
        text = "🏆 **ТОП PvP**\n\n"
        if DATABASE_URL:
            try:
                conn = await asyncpg.connect(DATABASE_URL)
                rows = await conn.fetch('SELECT user_id, rating, wins FROM pvp_rating ORDER BY rating DESC LIMIT 10')
                await conn.close()
                for i, r in enumerate(rows, 1):
                    # Получаем username из players (или из памяти)
                    player = await get_player_safe(r['user_id'])
                    name = player.get('username') or f"Игрок{r['user_id']}"
                    text += f"{i}. {name} – {r['rating']} ⚔️ (побед: {r['wins']})\n"
            except:
                text += "Ошибка загрузки топа из БД"
        else:
            # Сортируем память
            sorted_ratings = sorted(memory_pvp_ratings.items(), key=lambda x: x[1]['rating'], reverse=True)[:10]
            for i, (uid, data) in enumerate(sorted_ratings, 1):
                player = await get_player_safe(uid)
                name = player.get('username') or f"Игрок{uid}"
                text += f"{i}. {name} – {data['rating']} ⚔️ (побед: {data['wins']})\n"
        await callback.message.edit_text(text)
        await callback.answer()

    elif action == 'leave':
        if user_id in pvp_queue:
            pvp_queue.remove(user_id)
            await callback.message.edit_text("❌ Ты вышел из очереди.")
        else:
            await callback.message.edit_text("Ты не в очереди.")
        await callback.answer()

async def start_pvp_battle(player1_id, player2_id):
    """Запускает PvP-битву между двумя игроками"""
    # Получаем имена
    p1 = await get_player_safe(player1_id)
    p2 = await get_player_safe(player2_id)
    name1 = p1.get('username') or f"Игрок{player1_id}"
    name2 = p2.get('username') or f"Игрок{player2_id}"

    battle_id = f"pvp_{player1_id}_{player2_id}_{datetime.now().timestamp()}"
    active_pvp_battles[battle_id] = {
        'player1': {'id': player1_id, 'name': name1, 'hp': 100, 'max_hp': 100, 'shield': 0},
        'player2': {'id': player2_id, 'name': name2, 'hp': 100, 'max_hp': 100, 'shield': 0},
        'turn': 1,
        'current_player': player1_id  # первый ходит тот, кто первый в очереди
    }

    # Создаём клавиатуру для битвы
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("⚔️ Атака", callback_data=f"pvp_attack_{battle_id}"),
        InlineKeyboardButton("🛡️ Защита", callback_data=f"pvp_defend_{battle_id}")
    )

    # Отправляем сообщения обоим
    await bot.send_message(
        player1_id,
        f"🤺 **PvP-битва началась!**\nПротивник: {name2}\n\nТвой ход!",
        reply_markup=keyboard
    )
    await bot.send_message(
        player2_id,
        f"🤺 **PvP-битва началась!**\nПротивник: {name1}\n\nОжидай хода противника..."
    )

@dp.callback_query_handler(lambda c: c.data.startswith('pvp_attack_') or c.data.startswith('pvp_defend_'))
async def pvp_battle_action(callback: types.CallbackQuery):
    parts = callback.data.split('_')
    action = parts[1]  # attack или defend
    battle_id = '_'.join(parts[2:])  # остальная часть

    if battle_id not in active_pvp_battles:
        await callback.message.reply("⚠️ Битва уже закончена")
        await callback.answer()
        return

    battle = active_pvp_battles[battle_id]
    user_id = callback.from_user.id

    # Проверяем, чей ход
    if battle['current_player'] != user_id:
        await callback.message.reply("⏳ Сейчас не твой ход!")
        await callback.answer()
        return

    # Определяем текущего игрока и противника
    if user_id == battle['player1']['id']:
        player = battle['player1']
        opponent = battle['player2']
    else:
        player = battle['player2']
        opponent = battle['player1']

    # Обработка действия
    if action == 'attack':
        damage = random.randint(15, 25)
        # Учитываем защиту противника (если он защищался в прошлом ходу)
        if opponent.get('shield', 0) > 0:
            damage = max(0, damage - opponent['shield'])
            opponent['shield'] = 0
        opponent['hp'] -= damage
        result_text = f"⚔️ Ты нанёс {damage} урона!"
    else:  # defend
        shield = random.randint(10, 20)
        player['shield'] = shield
        result_text = f"🛡️ Ты встал в защиту (блок {shield} урона в следующем ходу)."

    # Проверка на победу
    if opponent['hp'] <= 0:
        # Победа текущего игрока
        winner_id = user_id
        loser_id = opponent['id']

        # Обновляем рейтинги
        winner_rating = await get_pvp_rating_safe(winner_id)
        loser_rating = await get_pvp_rating_safe(loser_id)
        await update_pvp_rating_safe(winner_id, rating=winner_rating['rating'] + 20, wins=winner_rating['wins'] + 1)
        await update_pvp_rating_safe(loser_id, rating=loser_rating['rating'] - 10, losses=loser_rating['losses'] + 1)

        # Уведомляем
        await bot.send_message(winner_id, f"🎉 **Победа!** +20 рейтинга!")
        await bot.send_message(loser_id, f"💔 **Поражение...** -10 рейтинга.")

        del active_pvp_battles[battle_id]
        await callback.message.edit_text(result_text + "\n\n🎉 Битва завершена!")
        await callback.answer()
        return

    # Меняем ход
    battle['turn'] += 1
    battle['current_player'] = opponent['id']

    # Обновляем сообщение текущему игроку
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("⚔️ Атака", callback_data=f"pvp_attack_{battle_id}"),
        InlineKeyboardButton("🛡️ Защита", callback_data=f"pvp_defend_{battle_id}")
    )
    await callback.message.edit_text(
        f"🤺 **PvP-битва**\n\n"
        f"Твоё HP: {player['hp']}/{player['max_hp']}\n"
        f"HP противника: {opponent['hp']}/{opponent['max_hp']}\n\n"
        f"{result_text}\n\n"
        f"Ход {battle['turn']}. Твой ход!",
        reply_markup=keyboard
    )
    await callback.answer()

    # Уведомляем противника
    await bot.send_message(opponent['id'], f"⚔️ Противник сходил. Теперь твой ход!")

# ---------- Остальные команды (battle, daily, shop, top) ----------
# (они остаются почти без изменений, но в top добавим PvP-категорию)

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
        f"⚔️ **БИТВА**\n\nВраг: {enemy['name']}\n❤️ {enemy['health']} HP\n⚔️ Урон врага: {enemy['damage']}\n🏆 Награда: +{enemy['exp']}✨ +{enemy['credits']}💰",
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
            new_exp -= 100
            new_max_health = player['max_health'] + 10
            updates.update({
                'level': new_level,
                'exp': new_exp,
                'max_health': new_max_health,
                'health': new_max_health
            })
            level_up = "\n📈 **УРОВЕНЬ ПОВЫШЕН!**"

        await update_player_safe(user_id, **updates)
        del active_battles[battle_id]
        await callback.message.edit_text(f"🎉 **ПОБЕДА!** +{enemy['exp']}✨ +{enemy['credits']}💰{level_up}")
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
    # Топ по уровню (PvE)
    top_level_text = ""
    if DATABASE_URL:
        try:
            conn = await asyncpg.connect(DATABASE_URL)
            rows = await conn.fetch('SELECT username, level, monsters_killed FROM players ORDER BY level DESC, monsters_killed DESC LIMIT 5')
            await conn.close()
            for i, r in enumerate(rows, 1):
                name = r['username'] or f"Игрок{i}"
                top_level_text += f"{i}. {name} – Ур.{r['level']} (👾 {r['monsters_killed']})\n"
        except:
            top_level_text = "Ошибка загрузки"
    else:
        sorted_players = sorted(memory_players.items(), key=lambda x: x[1]['level'], reverse=True)[:5]
        for i, (uid, p) in enumerate(sorted_players, 1):
            name = p.get('username') or f"Игрок{uid}"
            top_level_text += f"{i}. {name} – Ур.{p['level']} (👾 {p['monsters_killed']})\n"

    # Топ по PvP
    top_pvp_text = ""
    if DATABASE_URL:
        try:
            conn = await asyncpg.connect(DATABASE_URL)
            rows = await conn.fetch('SELECT user_id, rating, wins FROM pvp_rating ORDER BY rating DESC LIMIT 5')
            await conn.close()
            for i, r in enumerate(rows, 1):
                player = await get_player_safe(r['user_id'])
                name = player.get('username') or f"Игрок{r['user_id']}"
                top_pvp_text += f"{i}. {name} – {r['rating']} ⚔️ (побед: {r['wins']})\n"
        except:
            top_pvp_text = "Ошибка загрузки"
    else:
        sorted_ratings = sorted(memory_pvp_ratings.items(), key=lambda x: x[1]['rating'], reverse=True)[:5]
        for i, (uid, data) in enumerate(sorted_ratings, 1):
            player = await get_player_safe(uid)
            name = player.get('username') or f"Игрок{uid}"
            top_pvp_text += f"{i}. {name} – {data['rating']} ⚔️ (побед: {data['wins']})\n"

    # Топ по богатству
    top_credits_text = ""
    if DATABASE_URL:
        try:
            conn = await asyncpg.connect(DATABASE_URL)
            rows = await conn.fetch('SELECT username, credits FROM players ORDER BY credits DESC LIMIT 5')
            await conn.close()
            for i, r in enumerate(rows, 1):
                name = r['username'] or f"Игрок{i}"
                top_credits_text += f"{i}. {name} – {r['credits']}💰\n"
        except:
            top_credits_text = "Ошибка загрузки"
    else:
        sorted_credits = sorted(memory_players.items(), key=lambda x: x[1]['credits'], reverse=True)[:5]
        for i, (uid, p) in enumerate(sorted_credits, 1):
            name = p.get('username') or f"Игрок{uid}"
            top_credits_text += f"{i}. {name} – {p['credits']}💰\n"

    result = f"🏆 **ТОП ИГРОКОВ**\n\n**⚔️ По уровню:**\n{top_level_text}\n**🤺 По PvP:**\n{top_pvp_text}\n**💰 По кредитам:**\n{top_credits_text}"
    await message.reply(result, parse_mode="Markdown")

# ---------- Магазин (без изменений) ----------
SHOP_ITEMS = {
    'heal': {'name': '❤️ Лечение', 'price': 50, 'effect': 'health+50'},
    'energy': {'name': '⚡ Энергия', 'price': 30, 'effect': 'energy+30'},
    'exp_potion': {'name': '✨ Зелье опыта', 'price': 100, 'effect': 'exp+25'},
    'shield_crystal': {'name': '🛡️ Кристалл щита', 'price': 200, 'effect': 'max_health+10'},
    'sword': {'name': '⚔️ Меч силы', 'price': 300, 'effect': 'damage_bonus+5'}
}

@dp.message_handler(commands=['shop'])
async def cmd_shop(message: types.Message):
    keyboard = InlineKeyboardMarkup(row_width=2)
    for item_id, item in SHOP_ITEMS.items():
        keyboard.insert(
            InlineKeyboardButton(f"{item['name']} ({item['price']}💰)", callback_data=f"buy_{item_id}")
        )
    shop_text = "🏪 **МАГАЗИН**\n\n"
    for item in SHOP_ITEMS.values():
        shop_text += f"{item['name']} – {item['price']}💰\n"
    await message.reply(shop_text, reply_markup=keyboard, parse_mode="Markdown")

@dp.callback_query_handler(lambda c: c.data.startswith('buy_'))
async def buy(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    item_id = callback.data.split('_')[1]
    if item_id not in SHOP_ITEMS:
        await callback.answer("Товар не найден")
        return

    player = await get_player_safe(user_id)
    item = SHOP_ITEMS[item_id]
    price = item['price']

    if player['credits'] < price:
        await callback.message.reply("❌ Недостаточно кредов!")
        await callback.answer()
        return

    updates = {'credits': player['credits'] - price}
    if item_id == 'heal':
        new_health = min(player['max_health'], player['health'] + 50)
        updates['health'] = new_health
        reply_text = "❤️ Здоровье восстановлено!"
    elif item_id == 'energy':
        new_energy = min(player['max_energy'], player['energy'] + 30)
        updates['energy'] = new_energy
        reply_text = "⚡ Энергия восстановлена!"
    elif item_id == 'exp_potion':
        new_exp = player['exp'] + 25
        level_up = ""
        if new_exp >= 100:
            new_exp -= 100
            updates['level'] = player['level'] + 1
            updates['max_health'] = player['max_health'] + 10
            updates['health'] = updates['max_health']
            level_up = " 📈 Уровень повышен!"
        updates['exp'] = new_exp
        reply_text = f"✨ Получено 25 опыта!{level_up}"
    elif item_id == 'shield_crystal':
        updates['max_health'] = player['max_health'] + 10
        updates['health'] = player['health'] + 10
        reply_text = "🛡️ Максимальное здоровье увеличено на 10!"
    elif item_id == 'sword':
        reply_text = "⚔️ Меч силы куплен! (эффект будет добавлен позже)"
    else:
        reply_text = "✅ Покупка совершена!"

    await update_player_safe(user_id, **updates)
    await callback.message.reply(reply_text)
    await callback.answer()

# ---------- Flask ----------
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