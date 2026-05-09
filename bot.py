import discord
from discord.ext import commands
from discord import app_commands  # 🌟 เพิ่มตัวนี้สำหรับระบบ Slash/Context Menu
import aiohttp
import datetime
import gc
import os
import time
from dotenv import load_dotenv

import config
from scanner import analyze_image
from keep_alive import keep_alive

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
LOG_CHANNEL_ID = os.getenv('LOG_CHANNEL_ID')
OWNER_ID = os.getenv('OWNER_ID')

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=config.COMMAND_PREFIX, intents=intents)
bot_session = None

@bot.event
async def on_ready():
    global bot_session
    bot_session = aiohttp.ClientSession()
    
    # 🌟 จุดสำคัญ: สั่งให้บอทลงทะเบียนคำสั่งคลิกขวา/Slash ไปที่เซิร์ฟเวอร์ของ Discord
    try:
        synced = await bot.tree.sync()
        print(f"🔄 [System] ลงทะเบียนคำสั่งกับ Discord สำเร็จ {len(synced)} คำสั่ง")
    except Exception as e:
        print(f"❌ [Error] ลงทะเบียนคำสั่งไม่สำเร็จ: {e}")

    print(f'🛡️ Bot {bot.user} is ready!')
    print(f'⚙️ Auto-Mod: {"✅ ON" if config.AUTO_MOD_ENABLED else "❌ OFF"}')
    print(f'⚙️ Manual-Mod (Apps Menu): {"✅ ON" if config.MANUAL_MOD_ENABLED else "❌ OFF"}')

async def punish_user(message_to_delete, target_user, reason, trigger_type):
    try: await message_to_delete.delete()
    except discord.Forbidden: pass
    
    try: 
        future_time = int(time.time() + config.WARNING_DELETE_DELAY)
        countdown_tag = f"<t:{future_time}:R>" 

        public_msg = config.PUBLIC_WARNING_MSG.format(
            user_mention=target_user.mention,
            owner_id=OWNER_ID,
            delete_time=countdown_tag
        )
        await message_to_delete.channel.send(public_msg, delete_after=config.WARNING_DELETE_DELAY)
    except Exception as e: 
        print(f"⚠️ [Error] ส่งข้อความหน้าบ้านไม่ได้: {e}")
    
    try: 
        dm_msg = config.DM_WARNING_MSG.format(
            server_name=message_to_delete.guild.name,
            timeout_days=config.TIMEOUT_DAYS,
            owner_id=OWNER_ID
        )
        await target_user.send(dm_msg)
    except: 
        pass
    
    try: 
        await target_user.timeout(datetime.timedelta(days=config.TIMEOUT_DAYS), reason=f"{trigger_type}: {reason}")
        print(f"✅ [Action] Timeout {target_user.name} ไป {config.TIMEOUT_DAYS} วัน สำเร็จ!")
    except discord.Forbidden:
        print(f"❌ [Timeout Error] บอทไม่มีสิทธิ์! (ยศบอทต่ำกว่าเป้าหมาย หรือเป้าหมายเป็นแอดมิน)")
    except Exception as e: 
        print(f"❌ [Timeout Error] เกิดข้อผิดพลาดอื่น: {e}")
    
    if LOG_CHANNEL_ID:
        try:
            log_channel = bot.get_channel(int(LOG_CHANNEL_ID))
            if log_channel:
                embed = discord.Embed(title="🚨 น้อง MaO ทำลายสแปม!", color=discord.Color.red(), timestamp=datetime.datetime.now())
                embed.add_field(name="คนร้าย", value=target_user.mention, inline=True)
                embed.add_field(name="ระบบที่จับได้", value=trigger_type, inline=True)
                embed.add_field(name="สาเหตุ", value=f"`{reason}`", inline=False)
                await log_channel.send(embed=embed)
        except:
            pass

@bot.event
async def on_message(message):
    # คำสั่งเก่าเราไม่ใช้แล้ว แต่ยังคงฟังก์ชันดักจับ Auto-Mod ไว้
    if message.author.bot or not message.attachments: 
        return
    if not config.AUTO_MOD_ENABLED:
        return

    image_attachments = [att for att in message.attachments if att.content_type and att.content_type.startswith('image/')]
    if not image_attachments:
        return

    for i, target_image in enumerate(image_attachments):
        try:
            async with bot_session.get(target_image.url) as resp:
                if resp.status == 200:
                    img_data = await resp.read()
                    is_spam, reason = await analyze_image(img_data)
                    del img_data
                    gc.collect()

                    if is_spam:
                        await punish_user(message, message.author, reason, "Auto-Mod (รูปภาพ)")
                        break 
        except:
            pass

# ==========================================
# 🌟 ระบบ Manual-Mod แบบใหม่ (Context Menu)
# ==========================================
@bot.tree.context_menu(name="🚨 สแกนสแปม (MaO)")
async def despam_context_menu(interaction: discord.Interaction, message: discord.Message):
    # ephemeral=True คือเวทมนตร์ที่ทำให้ข้อความเห็นแค่คนที่กดสั่ง
    if not config.MANUAL_MOD_ENABLED:
        await interaction.response.send_message(config.MSG_DESPAM_DISABLED, ephemeral=True)
        return

    image_attachments = [att for att in message.attachments if att.content_type and att.content_type.startswith('image/')]

    if not image_attachments:
        await interaction.response.send_message(config.MSG_NO_IMAGE, ephemeral=True)
        return

    # ตอบกลับแบบส่วนตัวทันทีว่ากำลังสแกน
    await interaction.response.send_message(config.MSG_SCANNING, ephemeral=True)
    
    is_spam_found = False
    spam_reason = ""

    for target_image in image_attachments:
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
                        break 
        except Exception as e:
            print(f"❌ [Error] Manual-Mod ขัดข้อง: {e}")

    # อัปเดตข้อความส่วนตัวอันเดิม เพื่อแจ้งผลลัพธ์
    if is_spam_found:
        await interaction.edit_original_response(content=config.MSG_SPAM_FOUND.format(reason=spam_reason))
        await punish_user(message, message.author, spam_reason, f"Manual-Mod (สั่งโดย {interaction.user.name})")
    else:
        await interaction.edit_original_response(content=config.MSG_SAFE)

if TOKEN:
    keep_alive()
    bot.run(TOKEN)
