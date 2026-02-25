# my_test.py - простой тест с твоим паролем

import asyncio
import asyncpg

async def test():
    print("Пробую подключиться...")
    try:
        conn = await asyncpg.connect(
            user='postgres',
            password='1234567890',  # ТВОЙ ПАРОЛЬ
            database='postgres',
            host='localhost',
            port=5432
        )
        print("✅ ПОДКЛЮЧЕНИЕ УСПЕШНО!")
        await conn.close()
    except Exception as e:
        print(f"❌ ОШИБКА: {e}")

asyncio.run(test())
input("Нажми Enter для выхода...")