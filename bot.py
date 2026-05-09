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
    print(f'🛡️ Bot {bot.user} is ready! Type {config.COMMAND_PREFIX}despam to destroy spam.')
    print(f'⚙️ Auto-Mod: {"✅ ON" if config.AUTO_MOD_ENABLED else "❌ OFF"}')
    print(f'⚙️ Manual-Mod: {"✅ ON" if config.MANUAL_MOD_ENABLED else "❌ OFF"}')

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

    # 🌟 รวบรวมไฟล์แนบทั้งหมดที่เป็น "รูปภาพ" มาใส่ List
    image_attachments = [att for att in message.attachments if att.content_type and att.content_type.startswith('image/')]
    
    if not image_attachments:
        return

    print(f"📩 [Event] พบรูปภาพ {len(image_attachments)} ภาพ จาก {message.author.name}")

    # 🌟 ลูปสแกนทีละภาพ
    for i, target_image in enumerate(image_attachments):
        print(f"🖼️ [Auto-Mod] กำลังสแกนภาพที่ {i+1}/{len(image_attachments)}...")
        try:
            async with bot_session.get(target_image.url) as resp:
                if resp.status == 200:
                    img_data = await resp.read()
                    
                    is_spam, reason = await analyze_image(img_data)
                    del img_data
                    gc.collect()

                    if is_spam:
                        print(f"🚨 [Auto-Mod] สกัดรูปสแปมสำเร็จที่ภาพที่ {i+1}! หยุดการสแกนภาพที่เหลือ")
                        await punish_user(message, message.author, reason, "Auto-Mod (รูปภาพ)")
                        break # เบรก Loop ทันทีที่เจอสแปม (ประหยัด RAM)
        except Exception as e:
            print(f"❌ [Error] ระบบ Auto-Mod ขัดข้องที่ภาพ {i+1}: {e}")

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

    # 🌟 รวบรวมรูปทั้งหมดในข้อความที่ถูก Reply
    image_attachments = [att for att in replied_msg.attachments if att.content_type and att.content_type.startswith('image/')]

    if not image_attachments:
        await ctx.reply(config.MSG_NO_IMAGE)
        return

    status_msg = await ctx.reply(config.MSG_SCANNING)
    
    is_spam_found = False
    spam_reason = ""

    # 🌟 ลูปสแกนทีละภาพ
    for i, target_image in enumerate(image_attachments):
        await status_msg.edit(content=f"⏳ กำลังตรวจสอบรูปภาพที่ {i+1}/{len(image_attachments)}...")
        try:
            async with bot_session.get(target_image.url) as resp:
                if resp.status == 200:
                    img_data = await resp.read()
                    
                    is_spam, reason = await analyze_image(img_data)
                    del img_data
                    gc.collect()

                    if is_spam:
                        is_spam_found = True
                        spam_reason = reason
                        break # เบรก Loop ทันที
        except Exception as e:
            print(f"❌ [Error] ระบบ Manual-Mod ขัดข้องที่ภาพ {i+1}: {e}")

    # สรุปผลลัพธ์หลังจากสแกนจบ (หรือสแกนเจอสแปมกลางคัน)
    if is_spam_found:
        await status_msg.edit(content=config.MSG_SPAM_FOUND.format(reason=spam_reason))
        await punish_user(replied_msg, replied_msg.author, spam_reason, f"Manual-Mod (สั่งโดย {ctx.author.name})")
    else:
        await status_msg.edit(content=config.MSG_SAFE)

if TOKEN:
    keep_alive()
    bot.run(TOKEN)
