# create_tables.py - создаем таблицы для игры

import asyncio
import asyncpg

# ТВОЙ ПАРОЛЬ (вставь свои цифры)
DB_PASSWORD = "1234567890"  # ЗДЕСЬ ТВОЙ ПАРОЛЬ!

async def create_tables():
    """Создание всех таблиц для игры"""
    
    # Подключаемся к базе
    conn = await asyncpg.connect(
        user='postgres',
        password=DB_PASSWORD,
        database='postgres',
        host='localhost',
        port=5432
    )
    
    print("✅ Подключились к базе")
    print("📦 Создаем таблицы...")
    
    # Таблица для игроков (самая главная!)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS players (
            id SERIAL PRIMARY KEY,                    -- Уникальный номер
            telegram_id BIGINT UNIQUE NOT NULL,       -- ID в телеграме
            username TEXT,                             -- Имя в телеграме
            level INTEGER DEFAULT 1,                   -- Уровень
            experience INTEGER DEFAULT 0,               -- Опыт
            health INTEGER DEFAULT 100,                 -- Здоровье
            max_health INTEGER DEFAULT 100,             -- Макс здоровье
            energy INTEGER DEFAULT 100,                 -- Энергия
            max_energy INTEGER DEFAULT 100,             -- Макс энергия
            credits INTEGER DEFAULT 1000,               -- Деньги
            created_at TIMESTAMP DEFAULT NOW()          -- Дата регистрации
        )
    """)
    print("   ✅ Таблица players создана")
    
    # Таблица для инвентаря (что есть у игрока)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id SERIAL PRIMARY KEY,
            player_id INTEGER REFERENCES players(id),
            item_name TEXT,
            item_count INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    print("   ✅ Таблица inventory создана")
    
    # Таблица для статистики битв
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS battles (
            id SERIAL PRIMARY KEY,
            player_id INTEGER REFERENCES players(id),
            won BOOLEAN,
            enemy_name TEXT,
            damage_dealt INTEGER,
            damage_taken INTEGER,
            fought_at TIMESTAMP DEFAULT NOW()
        )
    """)
    print("   ✅ Таблица battles создана")
    
    # Проверяем что создалось
    tables = await conn.fetch("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
    """)
    
    print("\n📋 Таблицы в базе:")
    for table in tables:
        print(f"   • {table['table_name']}")
    
    await conn.close()
    print("\n✨ База данных готова к работе!")

# Запускаем
asyncio.run(create_tables())
input("\nНажми Enter для выхода...")