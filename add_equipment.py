# add_equipment.py - добавляем систему экипировки

import asyncio
import asyncpg

DB_PASSWORD = "1234567890"  # ТВОЙ ПАРОЛЬ!

async def add_equipment_tables():
    conn = await asyncpg.connect(
        user='postgres',
        password=DB_PASSWORD,
        database='postgres',
        host='localhost',
        port=5432
    )
    
    print("⚔️ Добавляем систему экипировки...")
    
    # Таблица предметов
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL,  -- helmet, armor, weapon, accessory
            rarity TEXT NOT NULL, -- common, rare, epic, legendary
            level INTEGER DEFAULT 1,
            damage_bonus INTEGER DEFAULT 0,
            health_bonus INTEGER DEFAULT 0,
            defense_bonus INTEGER DEFAULT 0,
            price INTEGER,
            description TEXT,
            image TEXT
        )
    """)
    print("✅ Таблица items создана")
    
    # Таблица инвентаря игроков
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS player_items (
            id SERIAL PRIMARY KEY,
            player_id INTEGER REFERENCES players(id),
            item_id INTEGER REFERENCES items(id),
            equipped BOOLEAN DEFAULT FALSE,
            durability INTEGER DEFAULT 100,
            obtained_at TIMESTAMP DEFAULT NOW()
        )
    """)
    print("✅ Таблица player_items создана")
    
    # Таблица экипировки (что надето)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS equipment (
            player_id INTEGER PRIMARY KEY REFERENCES players(id),
            helmet_id INTEGER REFERENCES player_items(id),
            armor_id INTEGER REFERENCES player_items(id),
            weapon_id INTEGER REFERENCES player_items(id),
            accessory_id INTEGER REFERENCES player_items(id)
        )
    """)
    print("✅ Таблица equipment создана")
    
    # Добавляем начальные предметы
    await conn.execute("""
        INSERT INTO items (name, type, rarity, level, damage_bonus, health_bonus, defense_bonus, price, description)
        VALUES 
            ('🪖 Кожаный шлем', 'helmet', 'common', 1, 0, 0, 2, 100, 'Простой шлем из кожи'),
            ('🛡️ Кожаная броня', 'armor', 'common', 1, 0, 10, 1, 150, 'Легкая броня'),
            ('⚔️ Деревянный меч', 'weapon', 'common', 1, 5, 0, 0, 120, 'Меч для начинающих'),
            ('💍 Кольцо силы', 'accessory', 'rare', 1, 3, 5, 1, 300, 'Увеличивает силу'),
            
            ('🪖 Стальной шлем', 'helmet', 'rare', 5, 0, 0, 5, 500, 'Надежный стальной шлем'),
            ('🛡️ Стальная броня', 'armor', 'rare', 5, 0, 30, 3, 600, 'Тяжелая броня'),
            ('⚔️ Меч героя', 'weapon', 'rare', 5, 12, 0, 0, 550, 'Острый меч'),
            ('📿 Амунет мудрости', 'accessory', 'epic', 10, 5, 20, 5, 1000, 'Древний амулет'),
            
            ('👑 Шлем командора', 'helmet', 'epic', 10, 0, 0, 10, 1200, 'Легендарный шлем'),
            ('🔥 Пылающая броня', 'armor', 'legendary', 15, 0, 100, 15, 2500, 'Броня с огненной аурой'),
            ('⚡ Громовой клинок', 'weapon', 'legendary', 15, 30, 0, 5, 3000, 'Меч с молниями')
        ON CONFLICT DO NOTHING
    """)
    print("✅ Начальные предметы добавлены")
    
    # Проверяем предметы
    items = await conn.fetch("SELECT * FROM items")
    print(f"\n📋 Доступные предметы ({len(items)}):")
    for item in items:
        print(f"   • {item['name']} ({item['rarity']}) - {item['price']}💰")
    
    await conn.close()
    print("\n✨ Система экипировки готова!")

asyncio.run(add_equipment_tables())
input("Нажми Enter для выхода...")