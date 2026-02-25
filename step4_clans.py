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
active_battles = {}
pvp_queue = []
active_pvp_battles = {}
memory_players = {}
memory_pvp_ratings = {}
memory_clans = {}           # id клана -> данные
memory_clan_members = {}    # user_id -> clan_id
memory_clan_messages = {}   # clan_id -> список сообщений

# ---------- Шаблоны врагов (из предыдущего шага) ----------
ENEMY_TEMPLATES = [
    {'name': '🛡️ Дрон-охранник', 'base_health': 50, 'base_damage': 10, 'exp_reward': 15, 'credits_reward': 40, 'type': 'machine'},
    {'name': '💻 Хакер', 'base_health': 40, 'base_damage': 12, 'exp_reward': 20, 'credits_reward': 50, 'type': 'hacker'},
    {'name': '👾 Мутант', 'base_health': 70, 'base_damage': 15, 'exp_reward': 25, 'credits_reward': 70, 'type': 'mutant'},
    {'name': '⚡ Элитный страж', 'base_health': 100, 'base_damage': 20, 'exp_reward': 40, 'credits_reward': 120, 'type': 'elite'},
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

# ---------- Работа с БД (обновлено с клановыми таблицами) ----------
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
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS pvp_rating (
                user_id BIGINT PRIMARY KEY REFERENCES players(user_id) ON DELETE CASCADE,
                rating INT DEFAULT 1000,
                wins INT DEFAULT 0,
                losses INT DEFAULT 0
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS clans (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                tag TEXT UNIQUE NOT NULL,
                owner_id BIGINT NOT NULL,
                level INT DEFAULT 1,
                exp INT DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                description TEXT DEFAULT ''
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS clan_members (
                user_id BIGINT PRIMARY KEY REFERENCES players(user_id) ON DELETE CASCADE,
                clan_id INT REFERENCES clans(id) ON DELETE CASCADE,
                role TEXT DEFAULT 'member',
                joined_at TIMESTAMP DEFAULT NOW()
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS clan_messages (
                id SERIAL PRIMARY KEY,
                clan_id INT REFERENCES clans(id) ON DELETE CASCADE,
                user_id BIGINT,
                username TEXT,
                message TEXT,
                sent_at TIMESTAMP DEFAULT NOW()
            )
        ''')
        # Таблица для клановых боссов (будет использоваться позже)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS clan_bosses (
                id SERIAL PRIMARY KEY,
                clan_id INT UNIQUE REFERENCES clans(id) ON DELETE CASCADE,
                boss_name TEXT,
                boss_hp INT,
                max_hp INT,
                summoned_at TIMESTAMP
            )
        ''')
        await conn.close()
        print("✅ Таблицы созданы/проверены")
    except Exception as e:
        print(f"❌ Ошибка подключения к БД: {e}")

# ---------- Функции для игроков (без изменений) ----------
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
        await conn.execute('''
            INSERT INTO pvp_rating (user_id) VALUES ($1) ON CONFLICT DO NOTHING
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

async def get_player_safe(user_id, username=None):
    db_player = await get_player_from_db(user_id)
    if db_player:
        return dict(db_player)
    if user_id not in memory_players:
        memory_players[user_id] = {
            'level': 1, 'exp': 0, 'credits': 1000, 'health': 100, 'max_health': 100,
            'energy': 100, 'max_energy': 100, 'monsters_killed': 0, 'last_daily': None,
            'username': username
        }
    return memory_players[user_id]

async def update_player_safe(user_id, **kwargs):
    if user_id in memory_players:
        memory_players[user_id].update(kwargs)
    await update_player_in_db(user_id, **kwargs)

# ---------- Функции для PvP ----------
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

async def get_pvp_rating_safe(user_id):
    db = await get_pvp_rating_from_db(user_id)
    if db:
        return dict(db)
    if user_id not in memory_pvp_ratings:
        memory_pvp_ratings[user_id] = {'rating': 1000, 'wins': 0, 'losses': 0}
    return memory_pvp_ratings[user_id]

async def update_pvp_rating_safe(user_id, **kwargs):
    if user_id in memory_pvp_ratings:
        memory_pvp_ratings[user_id].update(kwargs)
    await update_pvp_rating_in_db(user_id, **kwargs)

# ---------- Функции для кланов ----------
async def create_clan_in_db(name, tag, owner_id):
    if not DATABASE_URL:
        clan_id = len(memory_clans) + 1
        memory_clans[clan_id] = {
            'id': clan_id, 'name': name, 'tag': tag, 'owner_id': owner_id,
            'level': 1, 'exp': 0, 'description': '', 'created_at': datetime.now()
        }
        memory_clan_members[owner_id] = clan_id
        return clan_id
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        row = await conn.fetchrow(
            'INSERT INTO clans (name, tag, owner_id) VALUES ($1, $2, $3) RETURNING id',
            name, tag, owner_id
        )
        clan_id = row['id']
        await conn.execute(
            'INSERT INTO clan_members (user_id, clan_id, role) VALUES ($1, $2, $3)',
            owner_id, clan_id, 'owner'
        )
        await conn.close()
        return clan_id
    except Exception as e:
        print(f"Ошибка создания клана: {e}")
        return None

async def get_clan_by_user(user_id):
    if user_id in memory_clan_members:
        clan_id = memory_clan_members[user_id]
        return memory_clans.get(clan_id)
    if not DATABASE_URL:
        return None
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        row = await conn.fetchrow(
            'SELECT c.* FROM clans c JOIN clan_members cm ON c.id = cm.clan_id WHERE cm.user_id = $1',
            user_id
        )
        await conn.close()
        if row:
            clan = dict(row)
            memory_clans[clan['id']] = clan
            memory_clan_members[user_id] = clan['id']
            return clan
        return None
    except:
        return None

async def get_clan_by_id(clan_id):
    if clan_id in memory_clans:
        return memory_clans[clan_id]
    if not DATABASE_URL:
        return None
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        row = await conn.fetchrow('SELECT * FROM clans WHERE id = $1', clan_id)
        await conn.close()
        if row:
            clan = dict(row)
            memory_clans[clan_id] = clan
            return clan
        return None
    except:
        return None

async def get_clan_members(clan_id):
    if not DATABASE_URL:
        return [(uid, 'member') for uid, cid in memory_clan_members.items() if cid == clan_id]
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        rows = await conn.fetch('SELECT user_id, role FROM clan_members WHERE clan_id = $1', clan_id)
        await conn.close()
        return [(r['user_id'], r['role']) for r in rows]
    except:
        return []

async def add_clan_member(user_id, clan_id, role='member'):
    if not DATABASE_URL:
        memory_clan_members[user_id] = clan_id
        return True
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute(
            'INSERT INTO clan_members (user_id, clan_id, role) VALUES ($1, $2, $3)',
            user_id, clan_id, role
        )
        await conn.close()
        return True
    except:
        return False

async def remove_clan_member(user_id):
    if user_id in memory_clan_members:
        del memory_clan_members[user_id]
    if not DATABASE_URL:
        return True
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute('DELETE FROM clan_members WHERE user_id = $1', user_id)
        await conn.close()
        return True
    except:
        return False

async def add_clan_message(clan_id, user_id, username, text):
    if not DATABASE_URL:
        if clan_id not in memory_clan_messages:
            memory_clan_messages[clan_id] = []
        memory_clan_messages[clan_id].append({
            'username': username,
            'message': text,
            'sent_at': datetime.now()
        })
        # Ограничим размер истории
        if len(memory_clan_messages[clan_id]) > 50:
            memory_clan_messages[clan_id] = memory_clan_messages[clan_id][-50:]
        return True
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute(
            'INSERT INTO clan_messages (clan_id, user_id, username, message) VALUES ($1, $2, $3, $4)',
            clan_id, user_id, username, text
        )
        await conn.close()
        return True
    except:
        return False

async def get_clan_messages(clan_id, limit=20):
    if not DATABASE_URL:
        msgs = memory_clan_messages.get(clan_id, [])
        return msgs[-limit:]
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        rows = await conn.fetch(
            'SELECT username, message, sent_at FROM clan_messages WHERE clan_id = $1 ORDER BY sent_at DESC LIMIT $2',
            clan_id, limit
        )
        await conn.close()
        return rows
    except:
        return []

# ---------- Команды бота (старые) ----------
# Здесь вставь все предыдущие обработчики: start, profile, battle, attack, run, daily, pvp, pvp_callback, pvp_battle_action, shop, buy, top
# Они остаются без изменений. Чтобы не загромождать ответ, я их опускаю, но в реальном файле они должны быть.
# Для краткости я покажу только новые команды для кланов, но в итоговом файле нужно соединить всё.

# ---------- НОВЫЕ КОМАНДЫ ДЛЯ КЛАНОВ ----------

@dp.message_handler(commands=['clan'])
async def cmd_clan(message: types.Message):
    user_id = message.from_user.id
    clan = await get_clan_by_user(user_id)
    if clan:
        # Показываем информацию о клане
        members = await get_clan_members(clan['id'])
        text = (
            f"🏰 **Клан: {clan['name']}** [{clan['tag']}]\n"
            f"Уровень: {clan['level']} | Участников: {len(members)}\n"
            f"Описание: {clan['description']}\n\n"
            f"/clan_chat - чат клана\n"
            f"/clan_leave - покинуть клан\n"
            f"(скоро: клановый босс)"
        )
    else:
        text = (
            "🏰 **Кланы и гильдии**\n\n"
            "Ты ещё не в клане. Выбери действие:\n"
            "/clan_create <название> [тег] – создать клан (ур.5, 1000💰)\n"
            "/clan_list – список кланов\n"
            "/clan_join <ID> – вступить в клан"
        )
    await message.reply(text, parse_mode="Markdown")

@dp.message_handler(commands=['clan_create'])
async def cmd_clan_create(message: types.Message):
    user_id = message.from_user.id
    args = message.get_args().split()
    if len(args) < 2:
        await message.reply("❌ Формат: /clan_create Название [ТЕГ]\nПример: /clan_create Хранители [ХМ]")
        return
    name = args[0]
    tag = args[1].strip('[]')
    player = await get_player_safe(user_id)
    if player['level'] < 5:
        await message.reply("❌ Для создания клана нужен уровень 5")
        return
    if player['credits'] < 1000:
        await message.reply("❌ Для создания клана нужно 1000 кредитов")
        return

    clan_id = await create_clan_in_db(name, tag, user_id)
    if clan_id:
        await update_player_safe(user_id, credits=player['credits'] - 1000)
        await message.reply(f"✅ Клан '{name}' [{tag}] успешно создан!")
    else:
        await message.reply("❌ Ошибка создания клана. Возможно, название или тег уже заняты.")

@dp.message_handler(commands=['clan_list'])
async def cmd_clan_list(message: types.Message):
    if DATABASE_URL:
        try:
            conn = await asyncpg.connect(DATABASE_URL)
            rows = await conn.fetch('SELECT id, name, tag, level FROM clans ORDER BY level DESC LIMIT 10')
            await conn.close()
        except:
            await message.reply("❌ Ошибка загрузки списка")
            return
    else:
        rows = list(memory_clans.values())
        rows.sort(key=lambda x: x['level'], reverse=True)
        rows = rows[:10]
    if not rows:
        await message.reply("Пока нет кланов. Создай первый!")
        return
    text = "🏰 **Доступные кланы**\n\n"
    for r in rows:
        text += f"ID: {r['id']} | {r['name']} [{r['tag']}] – Ур.{r['level']}\n"
    text += "\nЧтобы вступить: /clan_join <ID>"
    await message.reply(text, parse_mode="Markdown")

@dp.message_handler(commands=['clan_join'])
async def cmd_clan_join(message: types.Message):
    user_id = message.from_user.id
    try:
        clan_id = int(message.get_args())
    except:
        await message.reply("❌ Укажи ID клана. Пример: /clan_join 5")
        return

    # Проверим, есть ли уже клан
    existing = await get_clan_by_user(user_id)
    if existing:
        await message.reply("❌ Ты уже состоишь в клане.")
        return

    # Получим данные клана
    clan = await get_clan_by_id(clan_id)
    if not clan:
        await message.reply("❌ Клан с таким ID не найден.")
        return

    # Добавляем участника
    if await add_clan_member(user_id, clan_id):
        await message.reply(f"✅ Ты вступил в клан {clan['name']} [{clan['tag']}]!")
    else:
        await message.reply("❌ Ошибка при вступлении.")

@dp.message_handler(commands=['clan_leave'])
async def cmd_clan_leave(message: types.Message):
    user_id = message.from_user.id
    clan = await get_clan_by_user(user_id)
    if not clan:
        await message.reply("❌ Ты не в клане.")
        return
    if clan['owner_id'] == user_id:
        await message.reply("❌ Владелец не может покинуть клан. Передай права или удали клан.")
        return

    if await remove_clan_member(user_id):
        await message.reply(f"✅ Ты покинул клан {clan['name']}.")
    else:
        await message.reply("❌ Ошибка.")

@dp.message_handler(commands=['clan_chat'])
async def cmd_clan_chat(message: types.Message):
    user_id = message.from_user.id
    clan = await get_clan_by_user(user_id)
    if not clan:
        await message.reply("❌ Ты не в клане.")
        return

    text = message.get_args()
    if text:
        # Отправка сообщения
        username = message.from_user.username or message.from_user.first_name
        if await add_clan_message(clan['id'], user_id, username, text):
            await message.reply("💬 Сообщение отправлено в чат клана.")
        else:
            await message.reply("❌ Ошибка отправки.")
    else:
        # Чтение последних сообщений
        msgs = await get_clan_messages(clan['id'])
        if not msgs:
            await message.reply("В чате пока нет сообщений.")
            return
        text_lines = ["📢 **Чат клана**:"]
        for m in msgs[-10:]:
            if isinstance(m, dict):
                time_str = m['sent_at'].strftime("%H:%M") if isinstance(m['sent_at'], datetime) else ""
                text_lines.append(f"{time_str} {m['username']}: {m['message']}")
            else:
                time_str = m['sent_at'].strftime("%H:%M")
                text_lines.append(f"{time_str} {m['username']}: {m['message']}")
        await message.reply("\n".join(text_lines), parse_mode="Markdown")

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