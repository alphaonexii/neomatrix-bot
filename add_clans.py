# add_clans.py - добавляем клановую систему

import asyncio
import asyncpg

DB_PASSWORD = "1234567890"  # ТВОЙ ПАРОЛЬ!

async def add_clans_tables():
    conn = await asyncpg.connect(
        user='postgres',
        password=DB_PASSWORD,
        database='postgres',
        host='localhost',
        port=5432
    )
    
    print("🏰 Добавляем клановую систему...")
    
    # Таблица кланов
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS clans (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            tag TEXT UNIQUE NOT NULL,
            owner_id INTEGER REFERENCES players(id),
            level INTEGER DEFAULT 1,
            exp INTEGER DEFAULT 0,
            members_count INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT NOW(),
            description TEXT,
            emblem TEXT
        )
    """)
    print("✅ Таблица clans создана")
    
    # Таблица участников клана
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS clan_members (
            id SERIAL PRIMARY KEY,
            clan_id INTEGER REFERENCES clans(id) ON DELETE CASCADE,
            player_id INTEGER REFERENCES players(id) UNIQUE,
            role TEXT DEFAULT 'member',  -- owner, admin, member
            joined_at TIMESTAMP DEFAULT NOW(),
            clan_score INTEGER DEFAULT 0,
            last_active TIMESTAMP DEFAULT NOW()
        )
    """)
    print("✅ Таблица clan_members создана")
    
    # Таблица клановых сообщений
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS clan_messages (
            id SERIAL PRIMARY KEY,
            clan_id INTEGER REFERENCES clans(id) ON DELETE CASCADE,
            player_id INTEGER REFERENCES players(id),
            message TEXT,
            sent_at TIMESTAMP DEFAULT NOW()
        )
    """)
    print("✅ Таблица clan_messages создана")
    
    # Таблица клановых боссов
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS clan_bosses (
            id SERIAL PRIMARY KEY,
            clan_id INTEGER REFERENCES clans(id) ON DELETE CASCADE,
            boss_name TEXT,
            boss_level INTEGER,
            boss_hp INTEGER,
            max_hp INTEGER,
            damage_dealt INTEGER DEFAULT 0,
            summoned_at TIMESTAMP DEFAULT NOW(),
            expires_at TIMESTAMP
        )
    """)
    print("✅ Таблица clan_bosses создана")
    
    await conn.close()
    print("\n✨ Клановая система готова!")
    print("Теперь можно добавлять кланы в игру!")

asyncio.run(add_clans_tables())
input("Нажми Enter для выхода...")