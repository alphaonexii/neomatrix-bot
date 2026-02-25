# add_dungeons.py - добавляем систему подземелий

import asyncio
import asyncpg

DB_PASSWORD = "1234567890"  # ТВОЙ ПАРОЛЬ!

async def add_dungeons_tables():
    conn = await asyncpg.connect(
        user='postgres',
        password=DB_PASSWORD,
        database='postgres',
        host='localhost',
        port=5432
    )
    
    print("🏰 Добавляем систему подземелий...")
    
    # Таблица подземелий
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS dungeons (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            min_level INTEGER DEFAULT 1,
            max_level INTEGER DEFAULT 100,
            floors INTEGER DEFAULT 10,
            image TEXT
        )
    """)
    print("✅ Таблица dungeons создана")
    
    # Таблица этажей подземелий
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS dungeon_floors (
            id SERIAL PRIMARY KEY,
            dungeon_id INTEGER REFERENCES dungeons(id),
            floor_number INTEGER NOT NULL,
            enemies TEXT,  -- JSON с врагами
            boss_name TEXT,
            boss_hp INTEGER,
            boss_damage INTEGER,
            reward_exp INTEGER DEFAULT 100,
            reward_credits INTEGER DEFAULT 200
        )
    """)
    print("✅ Таблица dungeon_floors создана")
    
    # Таблица прогресса игроков в подземельях
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS dungeon_progress (
            id SERIAL PRIMARY KEY,
            player_id INTEGER REFERENCES players(id),
            dungeon_id INTEGER REFERENCES dungeons(id),
            current_floor INTEGER DEFAULT 1,
            max_floor INTEGER DEFAULT 1,
            attempts INTEGER DEFAULT 0,
            completed BOOLEAN DEFAULT FALSE,
            started_at TIMESTAMP DEFAULT NOW()
        )
    """)
    print("✅ Таблица dungeon_progress создана")
    
    # Добавляем подземелья
    await conn.execute("""
        INSERT INTO dungeons (name, description, min_level, floors)
        VALUES 
            ('🏚️ Заброшенная фабрика', 'Старая фабрика машин, полная опасностей', 1, 5),
            ('🏭 Кибер-завод', 'Действующий завод по производству машин', 5, 10),
            ('🏛️ Храм Матрицы', 'Древнее святилище, где обитают могущественные программы', 10, 15),
            ('🔥 Цифровая бездна', 'Самое опасное место в Матрице', 15, 20)
        ON CONFLICT DO NOTHING
    """)
    print("✅ Подземелья добавлены")
    
    # Добавляем этажи для первого подземелья
    await conn.execute("""
        INSERT INTO dungeon_floors (dungeon_id, floor_number, boss_name, boss_hp, boss_damage, reward_exp, reward_credits)
        VALUES 
            (1, 1, '🛡️ Дрон-стражник', 100, 10, 50, 100),
            (1, 2, '⚔️ Хакер-охранник', 150, 15, 75, 150),
            (1, 3, '🤖 Тяжелый дрон', 200, 20, 100, 200),
            (1, 4, '👾 Командир машин', 300, 25, 150, 300),
            (1, 5, '💀 Гига-дрон', 500, 30, 200, 500)
        ON CONFLICT DO NOTHING
    """)
    print("✅ Этажи добавлены")
    
    await conn.close()
    print("\n✨ Система подземелий готова!")

asyncio.run(add_dungeons_tables())
input("Нажми Enter для выхода...")