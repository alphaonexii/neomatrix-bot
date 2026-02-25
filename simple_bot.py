# simple_bot.py - исправленная версия для aiogram 3.x

import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# ВСТАВЬ СВОЙ ТОКЕН СЮДА
BOT_TOKEN = "8689690200:AAGkYm61FQntnn7yScMnzdHzMgxVKBeEndM"  # ЗАМЕНИ НА СВОЙ!

# Включаем логирование
logging.basicConfig(level=logging.INFO)

# Создаем бота и диспетчер
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Команда /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "🌟 Привет! Я - твой первый бот!\n\n"
        "Я пока ничего не умею, но скоро научусь!"
    )

# Команда /help
@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "📚 Доступные команды:\n"
        "/start - Начать\n"
        "/help - Эта справка\n"
        "/info - Информация о тебе"
    )

# Команда /info
@dp.message(Command("info"))
async def cmd_info(message: types.Message):
    user = message.from_user
    await message.answer(
        f"ℹ️ Твоя информация:\n"
        f"Имя: {user.first_name}\n"
        f"ID: {user.id}\n"
        f"Username: @{user.username}"
    )

# Запуск бота
async def main():
    print("Бот запущен! Нажми Ctrl+C для остановки.")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())