import discord
from discord.ext import commands
import aiohttp
import datetime
import gc
import os
from dotenv import load_dotenv

import config
from scanner import analyze_image
from keep_alive import keep_alive
from messages import get_public_warning, get_dm_warning

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
LOG_CHANNEL_ID = os.getenv('LOG_CHANNEL_ID')

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=config.COMMAND_PREFIX, intents=intents)
bot_session = None

@bot.event
async def on_ready():
    global bot_session
    bot_session = aiohttp.ClientSession()
    print(f'🛡️ Bot {bot.user} is ready!')
    print(f'⚙️ Auto-Mod: {"✅ ON" if config.AUTO_MOD_ENABLED else "❌ OFF"}')
    print(f'⚙️ Manual-Mod: {"✅ ON" if config.MANUAL_MOD_ENABLED else "❌ OFF"}')
    print(f'⚙️ Image Hash Cache: {"✅ ON" if config.IMAGE_CACHE_ENABLED else "❌ OFF"}')

async def punish_user(message_to_delete, target_user, reason, trigger_type):
    try: await message_to_delete.delete()
    except discord.Forbidden: pass
    
    try: await message_to_delete.channel.send(get_public_warning(target_user.mention), delete_after=60)
    except: pass
    
    try: await target_user.send(get_dm_warning(message_to_delete.guild.name))
    except: pass
    
    try: await target_user.timeout(datetime.timedelta(days=1), reason=f"{trigger_type}: {reason}")
    except: pass
    
    if LOG_CHANNEL_ID:
        try:
            log_channel = bot.get_channel(int(LOG_CHANNEL_ID))
            if log_channel:
                embed = discord.Embed(title="🚨 น้อง MaO ทำลายสแปม!", color=discord.Color.red(), timestamp=datetime.datetime.now())
                embed.add_field(name="คนร้าย", value=target_user.mention, inline=True)
                embed.add_field(name="ระบบที่จับได้", value=trigger_type, inline=True)
                embed.add_field(name="สาเหตุ", value=f"`{reason}`", inline=False)
                await log_channel.send(embed=embed)
        except Exception as e:
            print(f"⚠️ Log Error: {e}")

@bot.event
async def on_message(message):
    await bot.process_commands(message)

    if message.author.bot or not message.attachments: 
        return

    if message.content.startswith(config.COMMAND_PREFIX):
        return

    if not config.AUTO_MOD_ENABLED:
        return

    target_image = next((att for att in message.attachments if att.content_type and att.content_type.startswith('image/')), None)
    
    if target_image:
        try:
            async with bot_session.get(target_image.url) as resp:
                if resp.status == 200:
                    img_data = await resp.read()
                    
                    is_spam, reason = await analyze_image(img_data)
                    del img_data
                    gc.collect()

                    if is_spam:
                        print(f"🚨 [Auto-Mod] สกัดรูปสแปมจาก {message.author.name}")
                        await punish_user(message, message.author, reason, "Auto-Mod (รูปภาพ)")
        except Exception as e:
            print(f"Auto-Mod Error: {e}")

@bot.command(name="despam")
async def despam_image(ctx):
    if not config.MANUAL_MOD_ENABLED:
        await ctx.reply(config.MSG_DESPAM_DISABLED)
        return

    if not ctx.message.reference:
        await ctx.reply(config.MSG_NEED_REPLY)
        return

    try:
        replied_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
    except discord.NotFound:
        await ctx.reply(config.MSG_MSG_NOT_FOUND)
        return

    target_image = next((att for att in replied_msg.attachments if att.content_type and att.content_type.startswith('image/')), None)

    if not target_image:
        await ctx.reply(config.MSG_NO_IMAGE)
        return

    status_msg = await ctx.reply(config.MSG_SCANNING)

    try:
        async with bot_session.get(target_image.url) as resp:
            if resp.status == 200:
                img_data = await resp.read()
                
                is_spam, reason = await analyze_image(img_data)
                del img_data
                gc.collect()

                if not is_spam:
                    await status_msg.edit(content=config.MSG_SAFE)
                else:
                    await status_msg.edit(content=config.MSG_SPAM_FOUND.format(reason=reason))
                    await punish_user(replied_msg, replied_msg.author, reason, f"Manual-Mod (สั่งโดย {ctx.author.name})")
    except Exception as e:
        await status_msg.edit(content=config.MSG_ERROR.format(error=e))

if TOKEN:
    keep_alive()
    bot.run(TOKEN)