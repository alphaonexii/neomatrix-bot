# test_simple.py
print("Проверка импортов...")

try:
    import asyncpg
    print("✅ asyncpg работает")
except:
    print("❌ asyncpg не работает")

try:
    from aiogram import Bot, Dispatcher
    print("✅ aiogram работает")
except:
    print("❌ aiogram не работает")

input("Нажми Enter для выхода...")