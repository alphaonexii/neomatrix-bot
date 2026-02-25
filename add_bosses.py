# add_bosses.py - добавляем систему боссов

import asyncio
import asyncpg
from datetime import datetime, timedelta

DB_PASSWORD = "1234567890"  # ТВОЙ ПАРОЛЬ!

async def add_bosses_tables():
    conn = await asyncpg.connect(
        user='postgres',
        password=DB_PASSWORD,
        database='postgres',
        host='localhost',
        port=5432
    )
    
    print("👾 Добавляем систему боссов...")
    
    # Таблица шаблонов боссов
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS boss_templates (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            level INTEGER DEFAULT 1,
            health BIGINT DEFAULT 1000,
            damage INTEGER DEFAULT 50,
            image TEXT,
            reward_exp INTEGER DEFAULT 500,
            reward_credits INTEGER DEFAULT 1000,
            reward_item_id INTEGER REFERENCES items(id)
        )
    """)
    print("✅ Таблица boss_templates создана")
    
    # Таблица активных боссов
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS active_bosses (
            id SERIAL PRIMARY KEY,
            boss_id INTEGER REFERENCES boss_templates(id),
            current_health BIGINT,
            clan_id INTEGER REFERENCES clans(id),
            spawned_at TIMESTAMP DEFAULT NOW(),
            expires_at TIMESTAMP DEFAULT NOW() + INTERVAL '3 hours',
            defeated BOOLEAN DEFAULT FALSE
        )
    """)
    print("✅ Таблица active_bosses создана")
    
    # Таблица урона по боссу
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS boss_damage (
            id SERIAL PRIMARY KEY,
            boss_instance_id INTEGER REFERENCES active_bosses(id),
            player_id INTEGER REFERENCES players(id),
            damage INTEGER DEFAULT 0,
            joined_at TIMESTAMP DEFAULT NOW()
        )
    """)
    print("✅ Таблица boss_damage создана")
    
    # Добавляем шаблоны боссов
    await conn.execute("""
        INSERT INTO boss_templates (name, description, level, health, damage, reward_exp, reward_credits)
        VALUES 
            ('👾 Гигантский дрон', 'Огромный дрон-защитник', 5, 5000, 30, 300, 600),
            ('🤖 Терминатор-убийца', 'Машина смерти из будущего', 10, 10000, 50, 600, 1200),
            ('🐉 Цифровой дракон', 'Легендарное создание Матрицы', 15, 20000, 80, 1000, 2000),
            ('👁️ Архитектор', 'Создатель Матрицы', 20, 50000, 150, 2000, 5000),
            ('💀 Нейросеть-бог', 'Высший разряд Матрицы', 25, 100000, 300, 5000, 10000)
        ON CONFLICT DO NOTHING
    """)
    print("✅ Шаблоны боссов добавлены")
    
    # Проверяем боссов
    bosses = await conn.fetch("SELECT * FROM boss_templates")
    print(f"\n📋 Доступные боссы ({len(bosses)}):")
    for b in bosses:
        print(f"   • {b['name']} (Ур.{b['level']}) - ❤️ {b['health']} HP")
    
    await conn.close()
    print("\n✨ Система боссов готова!")

asyncio.run(add_bosses_tables())
input("Нажми Enter для выхода...")