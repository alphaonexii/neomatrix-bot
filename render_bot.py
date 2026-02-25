# render_bot.py - ИСПРАВЛЕННАЯ ВЕРСИЯ С FLASK

import asyncio
import logging
import random
import os
import threading
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask, jsonify

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8689690200:AAH7rUhbaqh1RjBz-dqmJCyGE0wcDj3uGmw')
logging.basicConfig(level=logging.INFO)

# Создаём цикл событий
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# Временное хранилище (пока без базы)
players = {}
active_battles = {}

# ========== КОМАНДЫ БОТА ==========
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    if user_id not in players:
        players[user_id] = {
            'level': 1,
            'exp': 0,
            'credits': 1000,
            'health': 100,
            'max_health': 100,
            'energy': 100,
            'max_energy': 100,
            'last_daily': None,
            'monsters_killed': 0
        }
    p = players[user_id]
    await message.reply(
        f"🌟 С возвращением, {message.from_user.first_name}!\n"
        f"Уровень: {p['level']} | Креды: {p['credits']}\n\n"
        f"⚔️ /battle - Битва с монстрами\n"
        f"🤺 /pvp - PvP арена\n"
        f"🏰 /dungeon - Подземелья\n"
        f"🏪 /shop - Магазин\n"
        f"🎁 /daily - Бонус\n"
        f"📊 /profile - Профиль\n"
        f"🏆 /top - Топ игроков"
    )

@dp.message_handler(commands=['profile'])
async def cmd_profile(message: types.Message):
    user_id = message.from_user.id
    if user_id not in players:
        await message.reply("Сначала введи /start")
        return
    p = players[user_id]
    await message.reply(
        f"📊 **ПРОФИЛЬ {message.from_user.first_name}**\n\n"
        f"Уровень: {p['level']}\n"
        f"❤️ HP: {p['health']}/{p['max_health']}\n"
        f"⚡ Энергия: {p['energy']}/{p['max_energy']}\n"
        f"💰 Креды: {p['credits']}\n"
        f"👾 Убито монстров: {p['monsters_killed']}",
        parse_mode="Markdown"
    )

@dp.message_handler(commands=['battle'])
async def cmd_battle(message: types.Message):
    user_id = message.from_user.id
    if user_id not in players:
        await message.reply("Сначала введи /start")
        return
    if players[user_id]['energy'] < 10:
        await message.reply("⚡ Недостаточно энергии! Используй /daily")
        return

    enemy = {"name": "🛡️ Дрон-охранник", "health": 50, "damage": 10, "exp": 15, "credits": 40}
    battle_id = f"{user_id}_{datetime.now().timestamp()}"
    active_battles[battle_id] = {
        'player_id': user_id,
        'enemy': enemy,
        'enemy_hp': enemy['health']
    }

    players[user_id]['energy'] -= 10

    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("⚔️ Атака", callback_data=f"attack_{battle_id}"),
        InlineKeyboardButton("🏃 Убежать", callback_data=f"run_{battle_id}")
    )
    await message.reply(
        f"⚔️ **БИТВА**\n\nВраг: {enemy['name']}\n❤️ {enemy['health']}",
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
        # Победа
        p = players[user_id]
        p['exp'] += 15
        p['credits'] += 40
        p['monsters_killed'] += 1
        if p['exp'] >= 100:
            p['level'] += 1
            p['exp'] -= 100
            p['max_health'] += 10
            p['health'] = p['max_health']
            level_up = "\n📈 **УРОВЕНЬ ПОВЫШЕН!**"
        else:
            level_up = ""
        del active_battles[battle_id]
        await callback.message.edit_text(f"🎉 **ПОБЕДА!** +15✨ +40💰{level_up}")
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
    if user_id not in players:
        await message.reply("Сначала введи /start")
        return
    p = players[user_id]
    now = datetime.now()
    if p['last_daily'] and (now - p['last_daily']) < timedelta(days=1):
        left = timedelta(days=1) - (now - p['last_daily'])
        hours = left.seconds // 3600
        await message.reply(f"⏳ Бонус через {hours}ч")
    else:
        bonus = 100 + p['level'] * 10
        p['credits'] += bonus
        p['energy'] = p['max_energy']
        p['health'] = p['max_health']
        p['last_daily'] = now
        await message.reply(f"🎁 Получено {bonus}💰 и полная энергия!")

@dp.message_handler(commands=['top'])
async def cmd_top(message: types.Message):
    if not players:
        await message.reply("Пока нет игроков")
        return
    top = sorted(players.items(), key=lambda x: x[1]['level'], reverse=True)[:5]
    text = "🏆 **ТОП ИГРОКОВ**\n\n"
    for i, (uid, p) in enumerate(top, 1):
        name = f"Игрок{uid}"
        text += f"{i}. {name} - Ур.{p['level']} (👾 {p['monsters_killed']})\n"
    await message.reply(text, parse_mode="Markdown")

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
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@dp.callback_query_handler(lambda c: c.data.startswith('buy_'))
async def buy(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in players:
        await callback.message.reply("Сначала введи /start")
        await callback.answer()
        return
    p = players[user_id]
    action = callback.data.split('_')[1]

    if action == "heal":
        if p['credits'] >= 50:
            p['credits'] -= 50
            p['health'] = min(p['max_health'], p['health'] + 50)
            await callback.message.reply("❤️ Здоровье восстановлено!")
        else:
            await callback.message.reply("❌ Недостаточно кредов!")
    elif action == "energy":
        if p['credits'] >= 30:
            p['credits'] -= 30
            p['energy'] = min(p['max_energy'], p['energy'] + 30)
            await callback.message.reply("⚡ Энергия восстановлена!")
        else:
            await callback.message.reply("❌ Недостаточно кредов!")
    await callback.answer()

@dp.message_handler(commands=['pvp', 'dungeon'])
async def cmd_not_ready(message: types.Message):
    await message.reply("🚧 Эта функция в разработке. Скоро появится!")

# ========== FLASK ДЛЯ HEALTH CHECK ==========
app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({"status": "Bot is running!", "time": datetime.now().isoformat()})

@app.route('/health')
def health():
    return jsonify({"status": "healthy"}), 200

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print("🚀 Flask запущен в фоновом потоке")

    # Запускаем бота в основном потоке
    print("🚀 Запуск бота...")
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True, loop=loop)