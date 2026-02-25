# database_test.py - упрощенная версия

import asyncio
import asyncpg

async def test_connection():
    print("🔌 Подключаюсь к базе данных...")
    
    # Пробуем разные варианты пароля
    passwords_to_try = [
        '1234567890',  # твой пароль (замени если другой)
        'postgres',        # стандартный пароль
        '',                # пустой пароль
        '12345',           # простой пароль
        'password'         # еще вариант
    ]
    
    for password in passwords_to_try:
        try:
            print(f"Пробую пароль: {password}")
            conn = await asyncpg.connect(
                user='postgres',
                password=password,
                database='postgres',
                host='localhost',
                port=5432
            )
            print(f"✅ УСПЕХ! Пароль работает: {password}")
            await conn.close()
            return True
        except Exception as e:
            print(f"❌ Не подошел: {str(e)[:50]}...")
    
    print("\n❌ Ни один пароль не подошел")
    print("💡 PostgreSQL возможно не запущен")
    return False

print("=" * 50)
print("🚀 ТЕСТ ПОДКЛЮЧЕНИЯ")
print("=" * 50)
asyncio.run(test_connection())

input("\nНажми Enter для выхода...")