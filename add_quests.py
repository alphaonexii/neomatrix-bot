# add_quests.py - добавляем систему квестов

import asyncio
import asyncpg
from datetime import datetime, timedelta

DB_PASSWORD = "1234567890"  # ТВОЙ ПАРОЛЬ!

async def add_quests_tables():
    conn = await asyncpg.connect(
        user='postgres',
        password=DB_PASSWORD,
        database='postgres',
        host='localhost',
        port=5432
    )
    
    print("📜 Добавляем систему квестов...")
    
    # Таблица шаблонов квестов
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS quest_templates (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            quest_type TEXT NOT NULL,  -- kill_monsters, win_pvp, spend_energy, etc
            target INTEGER NOT NULL,
            reward_exp INTEGER DEFAULT 50,
            reward_credits INTEGER DEFAULT 100,
            reward_item_id INTEGER REFERENCES items(id),
            min_level INTEGER DEFAULT 1,
            max_level INTEGER DEFAULT 100
        )
    """)
    print("✅ Таблица quest_templates создана")
    
    # Таблица активных квестов игроков
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS player_quests (
            id SERIAL PRIMARY KEY,
            player_id INTEGER REFERENCES players(id),
            quest_id INTEGER REFERENCES quest_templates(id),
            progress INTEGER DEFAULT 0,
            completed BOOLEAN DEFAULT FALSE,
            claimed BOOLEAN DEFAULT FALSE,
            assigned_at TIMESTAMP DEFAULT NOW(),
            expires_at TIMESTAMP DEFAULT NOW() + INTERVAL '1 day'
        )
    """)
    print("✅ Таблица player_quests создана")
    
    # Добавляем шаблоны квестов
    await conn.execute("""
        INSERT INTO quest_templates (name, description, quest_type, target, reward_exp, reward_credits, min_level)
        VALUES 
            ('👾 Охотник на дронов', 'Уничтожь 5 врагов', 'kill_monsters', 5, 50, 100, 1),
            ('👾 Истребитель машин', 'Уничтожь 10 врагов', 'kill_monsters', 10, 100, 200, 3),
            ('👾 Легендарный охотник', 'Уничтожь 20 врагов', 'kill_monsters', 20, 200, 400, 10),
            
            ('🤺 Новичок арены', 'Победи в 1 PvP битве', 'win_pvp', 1, 75, 150, 1),
            ('🤺 Воин арены', 'Победи в 3 PvP битвах', 'win_pvp', 3, 150, 300, 5),
            ('🤺 Чемпион арены', 'Победи в 5 PvP битвах', 'win_pvp', 5, 300, 600, 15),
            
            ('⚡ Энергичный', 'Потрать 50 энергии', 'spend_energy', 50, 40, 80, 1),
            ('⚡ Неутомимый', 'Потрать 100 энергии', 'spend_energy', 100, 80, 160, 3),
            
            ('💰 Кредитный магнат', 'Заработай 500 кредитов', 'earn_credits', 500, 100, 200, 1),
            ('💰 Миллионер', 'Заработай 1000 кредитов', 'earn_credits', 1000, 200, 400, 5)
        ON CONFLICT DO NOTHING
    """)
    print("✅ Шаблоны квестов добавлены")
    
    # Проверяем квесты
    quests = await conn.fetch("SELECT * FROM quest_templates")
    print(f"\n📋 Доступные квесты ({len(quests)}):")
    for q in quests:
        print(f"   • {q['name']} - {q['description']} (+{q['reward_exp']}✨, +{q['reward_credits']}💰)")
    
    await conn.close()
    print("\n✨ Система квестов готова!")

asyncio.run(add_quests_tables())
input("Нажми Enter для выхода...")