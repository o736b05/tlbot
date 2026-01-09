import os
import subprocess
import time

print("🚀 Starting Telegram Bot...")

# Проверяем переменные окружения
token = os.getenv('TELEGRAM_BOT_TOKEN')
if not token:
    print("❌ ERROR: TELEGRAM_BOT_TOKEN not set!")
    print("💡 Add it in Railway → Variables")
    exit(1)

print(f"✅ Token found: {token[:10]}...")

# Запускаем бота
try:
    print("🤖 Launching bot process...")
    subprocess.run(["python", "bot.py"])
except KeyboardInterrupt:
    print("🛑 Bot stopped")
except Exception as e:
    print(f"💥 Error: {e}")
    time.sleep(5)  # Пауза перед перезапуском