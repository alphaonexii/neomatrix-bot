# update_db.py - добавляем новые таблицы для боевой системы

import asyncio
import asyncpg

DB_PASSWORD = "1234567890"  # ТВОЙ ПАРОЛЬ!

async def update_database():
    conn = await asyncpg.connect(
        user='postgres',
        password=DB_PASSWORD,
        database='postgres',
        host='localhost',
        port=5432
    )
    
    print("🔄 Обновляем базу данных...")
    
    # Добавляем таблицу для врагов
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS enemies (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            enemy_type TEXT NOT NULL,
            level INTEGER DEFAULT 1,
            health INTEGER DEFAULT 50,
            max_health INTEGER DEFAULT 50,
            damage INTEGER DEFAULT 10,
            shield INTEGER DEFAULT 0,
            experience_reward INTEGER DEFAULT 10,
            credits_reward INTEGER DEFAULT 50,
            image TEXT
        )
    """)
    print("✅ Таблица enemies создана")
    
    # Добавляем начальных врагов
    await conn.execute("""
        INSERT INTO enemies (name, enemy_type, level, health, max_health, damage, shield, experience_reward, credits_reward)
        VALUES 
            ('🛡️ Патрульный дрон', 'machine', 1, 50, 50, 8, 5, 15, 40),
            ('💻 Хакер-одиночка', 'hacker', 1, 40, 40, 12, 0, 20, 60),
            ('🤖 Страж периметра', 'machine', 2, 70, 70, 10, 10, 25, 80),
            ('👤 Потерянная душа', 'wanderer', 2, 60, 60, 15, 5, 30, 100)
        ON CONFLICT DO NOTHING
    """)
    print("✅ Начальные враги добавлены")
    
    # Проверяем что добавилось
    enemies = await conn.fetch("SELECT * FROM enemies")
    print(f"\n📋 Доступные враги ({len(enemies)}):")
    for e in enemies:
        print(f"   • {e['name']} (Ур.{e['level']}) - ❤️ {e['health']} ⚔️ {e['damage']}")
    
    await conn.close()
    print("\n✨ База данных обновлена!")

# Запускаем функцию
asyncio.run(update_database())

# Ждем нажатия Enter перед закрытием
input("Нажми Enter для выхода...")