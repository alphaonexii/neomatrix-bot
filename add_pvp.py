# add_pvp.py - добавляем PvP арену

import asyncio
import asyncpg

DB_PASSWORD = "1234567890"  # ТВОЙ ПАРОЛЬ!

async def add_pvp_tables():
    conn = await asyncpg.connect(
        user='postgres',
        password=DB_PASSWORD,
        database='postgres',
        host='localhost',
        port=5432
    )
    
    print("⚔️ Добавляем PvP систему...")
    
    # Таблица для PvP рейтинга
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS pvp_rating (
            id SERIAL PRIMARY KEY,
            player_id INTEGER REFERENCES players(id),
            rating INTEGER DEFAULT 1000,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            last_battle TIMESTAMP
        )
    """)
    print("✅ Таблица pvp_rating создана")
    
    # Добавляем всем игрокам начальный рейтинг
    await conn.execute("""
        INSERT INTO pvp_rating (player_id, rating, wins, losses)
        SELECT id, 1000, 0, 0 FROM players
        ON CONFLICT DO NOTHING
    """)
    print("✅ Начальный рейтинг добавлен")
    
    # Таблица для истории PvP битв
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS pvp_battles (
            id SERIAL PRIMARY KEY,
            player1_id INTEGER REFERENCES players(id),
            player2_id INTEGER REFERENCES players(id),
            winner_id INTEGER REFERENCES players(id),
            rating_change INTEGER,
            battle_date TIMESTAMP DEFAULT NOW()
        )
    """)
    print("✅ Таблица pvp_battles создана")
    
    await conn.close()
    print("\n✨ PvP система готова!")

asyncio.run(add_pvp_tables())
input("Нажми Enter для выхода...")