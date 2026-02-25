# game_bot.py - первая версия игры

import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import asyncpg

# НАСТРОЙКИ
BOT_TOKEN = "8689690200:AAGkYm61FQntnn7yScMnzdHzMgxVKBeEndM"  # ТВОЙ ТОКЕН!
DB_PASSWORD = "1234567890"  # ТВОЙ ПАРОЛЬ!

# Подключаем логирование
logging.basicConfig(level=logging.INFO)

# Создаем бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Функция для получения соединения с базой
async def get_db():
    return await asyncpg.connect(
        user='postgres',
        password=DB_PASSWORD,
        database='postgres',
        host='localhost',
        port=5432
    )

# Команда /start - теперь запоминает игрока!
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user = message.from_user
    
    # Подключаемся к базе
    conn = await get_db()
    
    # Проверяем, есть ли уже такой игрок
    existing = await conn.fetchrow(
        "SELECT * FROM players WHERE telegram_id = $1",
        user.id
    )
    
    if existing:
        # Игрок уже есть - приветствуем
        await message.answer(
            f"🌟 С возвращением, {user.first_name}!\n"
            f"Твой уровень: {existing['level']}\n"
            f"Креды: {existing['credits']}"
        )
    else:
        # Новый игрок - сохраняем
        await conn.execute("""
            INSERT INTO players (telegram_id, username) 
            VALUES ($1, $2)
        """, user.id, user.username)
        
        await message.answer(
            f"🌟 Добро пожаловать в NEOMATRIX, {user.first_name}!\n"
            f"Ты зарегистрирован как новый игрок.\n"
            f"Получено 1000 стартовых кредов!\n\n"
            f"Используй /profile чтобы увидеть свой профиль"
        )
    
    await conn.close()

# Команда /profile - показывает профиль
@dp.message(Command("profile"))
async def cmd_profile(message: types.Message):
    user = message.from_user
    
    conn = await get_db()
    
    # Получаем данные игрока
    player = await conn.fetchrow(
        "SELECT * FROM players WHERE telegram_id = $1",
        user.id
    )
    
    if not player:
        await message.answer("Сначала введи /start")
        await conn.close()
        return
    
    # Считаем статистику битв
    battles = await conn.fetch(
        "SELECT COUNT(*) as total, SUM(CASE WHEN won THEN 1 ELSE 0 END) as wins FROM battles WHERE player_id = $1",
        player['id']
    )
    
    total_battles = battles[0]['total'] or 0
    wins = battles[0]['wins'] or 0
    
    # Формируем красивый ответ
    profile_text = f"""
🎮 **ПРОФИЛЬ ИГРОКА**
╔═══════════════════╗
║ 🆔 {user.first_name}
╠═══════════════════╣
║ 📊 Уровень: {player['level']}
║ ✨ Опыт: {player['experience']}/100
║ ❤️ HP: {player['health']}/{player['max_health']}
║ ⚡ Энергия: {player['energy']}/{player['max_energy']}
╠═══════════════════╣
║ 💰 Креды: {player['credits']}
╠═══════════════════╣
║ ⚔️ Битв: {total_battles}
║ 🏆 Побед: {wins}
║ 📈 Винрейт: {wins/total_battles*100 if total_battles > 0 else 0:.1f}%
╚═══════════════════╝
    """
    
    await message.answer(profile_text, parse_mode="Markdown")
    await conn.close()

# Команда /top - топ игроков
@dp.message(Command("top"))
async def cmd_top(message: types.Message):
    conn = await get_db()
    
    # Получаем топ-5 игроков по уровню
    top_players = await conn.fetch("""
        SELECT username, level, credits 
        FROM players 
        ORDER BY level DESC, credits DESC 
        LIMIT 5
    """)
    
    text = "🏆 **ТОП ИГРОКОВ**\n\n"
    for i, player in enumerate(top_players, 1):
        name = player['username'] or f"Игрок{i}"
        text += f"{i}. {name} | Ур. {player['level']} | 💰 {player['credits']}\n"
    
    await message.answer(text, parse_mode="Markdown")
    await conn.close()

# Запуск бота
async def main():
    print("🤖 Бот запущен! Нажми Ctrl+C для остановки")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())