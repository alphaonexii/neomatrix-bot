import asyncio
import logging
from aiogram import Bot, Dispatcher, types

BOT_TOKEN = "8689690200:AAH7rUhbaqh1RjBz-dqmJCyGE0wcDj3uGmw"
logging.basicConfig(level=logging.INFO)

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.reply("Минимальный бот работает!")

if __name__ == '__main__':
    from aiogram import executor
    print("Запуск минимального бота...")
    executor.start_polling(dp, skip_updates=True, loop=loop)