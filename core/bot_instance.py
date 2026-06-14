import discord
from discord.ext import commands
import os
import logging

import config

logger = logging.getLogger("MaO-Bot.core")

def _load_env_int(key: str, required: bool = False) -> int | None:
    val = os.getenv(key)
    if val is None:
        if required:
            raise RuntimeError(f"❌ Missing required environment variable: {key}")
        return None
    try:
        return int(val)
    except ValueError:
        raise RuntimeError(f"❌ Environment variable {key}='{val}' must be an integer")

class AntiSpamBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        
        super().__init__(command_prefix=config.COMMAND_PREFIX, intents=intents)
        self.log_channel_id = _load_env_int('LOG_CHANNEL_ID')
        self.owner_id = _load_env_int('OWNER_ID')

    async def setup_hook(self):
        """Called once when bot starts"""
        # Load Cogs
        cogs = ['cogs.antispam', 'cogs.admin_tools']
        for cog in cogs:
            try:
                await self.load_extension(cog)
                logger.info(f"Loaded cog: {cog}")
            except Exception as e:
                logger.error(f"Failed to load cog {cog}: {e}")

        # ⚡ ปิดการ Sync อัตโนมัติเพื่อป้องกัน Rate Limit 
        # ให้ใช้คำสั่ง !sync ใน Discord เมื่อมีการเพิ่มคำสั่งใหม่แทน
        # (เปิดชั่วคราวเพื่อให้คำสั่งเทสขึ้นไปก่อน)
        try:
            synced = await self.tree.sync()
            logger.info(f"Auto-synced {len(synced)} commands.")
        except Exception as e:
            logger.error(f"Failed to auto-sync commands: {e}")

    async def on_ready(self):
        logger.info("🛡️ Bot %s is online and monitoring!", self.user)

    async def on_disconnect(self):
        logger.warning("Bot disconnected from Discord, will attempt reconnect...")

    async def on_resumed(self):
        logger.info("Bot successfully resumed connection")
