import os
from dotenv import load_dotenv

from utils.logger import setup_logger
from core.bot_instance import AntiSpamBot
from keep_alive import keep_alive

# Setup logging
logger = setup_logger()

load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
if not TOKEN:
    raise RuntimeError("❌ DISCORD_TOKEN is not set — bot cannot start")

if __name__ == "__main__":
    bot = AntiSpamBot()
    keep_alive()
    bot.run(TOKEN, log_handler=None)
