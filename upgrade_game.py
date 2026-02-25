# upgrade_game.py - добавляем новые функции в игру

import asyncio
import asyncpg

DB_PASSWORD = "1234567890"  # ТВОЙ ПАРОЛЬ!

async def upgrade_database():
    conn = await asyncpg.connect(
        user='postgres',
        password=DB_PASSWORD,
        database='postgres',
        host='localhost',
        port=5432
    )
    
    print("🔄 Улучшаем базу данных...")
    
    # Добавляем новые колонки в таблицу players
    try:
        await conn.execute("""
            ALTER TABLE players 
            ADD COLUMN IF NOT EXISTS last_daily TIMESTAMP,
            ADD COLUMN IF NOT EXISTS total_damage INTEGER DEFAULT 0,
            ADD COLUMN IF NOT EXISTS monsters_killed INTEGER DEFAULT 0,
            ADD COLUMN IF NOT EXISTS achievements TEXT[] DEFAULT '{}'
        """)
        print("✅ Добавлены новые колонки в players")
    except Exception as e:
        print(f"⚠️ Ошибка: {e}")
    
    # Создаем таблицу shop_items
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS shop_items (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            price INTEGER,
            type TEXT,
            value INTEGER
        )
    """)
    
    # Очищаем старые предметы и добавляем новые
    await conn.execute("DELETE FROM shop_items")
    
    await conn.execute("""
        INSERT INTO shop_items (name, description, price, type, value) VALUES
            ('🔥 Зелье силы', '+10 к урону на 3 битвы', 150, 'buff', 10),
            ('✨ Зелье опыта', '+50 опыта', 200, 'exp', 50),
            ('💎 Кристалл щита', 'Постоянный +5 к защите', 300, 'perm_shield', 5),
            ('⚡ Эликсир энергии', '+50 энергии', 100, 'energy', 50),
            ('🏆 Билет в топ', 'Попадание в топ на день', 500, 'top', 0),
            ('❤️ Большое зелье', '+100 здоровья', 180, 'heal', 100),
            ('⚔️ Меч героя', '+15 к урону навсегда', 400, 'perm_damage', 15)
    """)
    print("✅ Добавлены новые предметы в магазин")
    
    # Создаем таблицу достижений
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS achievements (
            id SERIAL PRIMARY KEY,
            player_id INTEGER REFERENCES players(id),
            achievement_name TEXT,
            achieved_at TIMESTAMP DEFAULT NOW()
        )
    """)
    print("✅ Создана таблица достижений")
    
    # Проверяем что добавилось
    items = await conn.fetch("SELECT * FROM shop_items")
    print(f"\n📋 Новые предметы в магазине ({len(items)}):")
    for item in items:
        print(f"   • {item['name']} - {item['price']}💰 - {item['description']}")
    
    await conn.close()
    print("\n✨ База данных улучшена!")

# Запускаем
asyncio.run(upgrade_database())
input("\nНажми Enter для выхода...")