import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import datetime
import gc
import os
import time
from dotenv import load_dotenv

import config
from scanner import analyze_image, analyze_text
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

# กล่องความจำสำหรับระบบ Anti-Raid
user_raid_history = {}

@bot.event
async def on_ready():
    global bot_session
    bot_session = aiohttp.ClientSession()
    
    # ลงทะเบียนคำสั่งคลิกขวากับ Discord
    try:
        synced = await bot.tree.sync()
        print(f"🔄 [System] ลงทะเบียนคำสั่งกับ Discord สำเร็จ {len(synced)} คำสั่ง")
    except Exception as e:
        print(f"❌ [Error] ลงทะเบียนคำสั่งไม่สำเร็จ: {e}")

    print(f'🛡️ Bot {bot.user} is ready!')
    print(f'⚙️ Auto-Mod (Text & Image): {"✅ ON" if config.AUTO_MOD_ENABLED else "❌ OFF"}')
    print(f'⚙️ Anti-Raid (Cross-Channel): {"✅ ON" if getattr(config, "ANTI_RAID_ENABLED", False) else "❌ OFF"}')
    print(f'⚙️ Manual-Mod (Apps Menu): {"✅ ON" if config.MANUAL_MOD_ENABLED else "❌ OFF"}')

async def punish_user(message_to_delete, target_user, reason, trigger_type):
    # 1. ลบข้อความสแปม
    try: await message_to_delete.delete()
    except discord.Forbidden: pass
    
    # 2. แจ้งเตือนหน้าห้อง พร้อมระบบเวลานับถอยหลังลบตัวเอง
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
    
    # 3. ทักเตือนเข้า DM
    try: 
        dm_msg = config.DM_WARNING_MSG.format(
            server_name=message_to_delete.guild.name,
            timeout_days=config.TIMEOUT_DAYS,
            owner_id=OWNER_ID
        )
        await target_user.send(dm_msg)
    except: 
        pass
    
    # 4. ลงดาบ Timeout
    try: 
        await target_user.timeout(datetime.timedelta(days=config.TIMEOUT_DAYS), reason=f"{trigger_type}: {reason}")
        print(f"✅ [Action] Timeout {target_user.name} ไป {config.TIMEOUT_DAYS} วัน สำเร็จ!")
    except discord.Forbidden:
        print(f"❌ [Timeout Error] บอทไม่มีสิทธิ์! (ยศบอทต่ำกว่าเป้าหมาย หรือเป้าหมายเป็นแอดมิน)")
    except Exception as e: 
        print(f"❌ [Timeout Error] เกิดข้อผิดพลาดอื่น: {e}")
    
    # 5. ส่งบันทึก Log เข้าห้องแอดมิน
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
    if message.author.bot: 
        return
    if not config.AUTO_MOD_ENABLED:
        return

    # ==========================================
    # 0. 🛡️ ด่านศูนย์: ระบบ Anti-Raid (กวาดล้างสแปมข้ามห้อง)
    # ==========================================
    if getattr(config, 'ANTI_RAID_ENABLED', False) and message.content:
        current_time = time.time()
        user_id = message.author.id
        content = message.content.strip()
        channel_id = message.channel.id

        if user_id not in user_raid_history:
            user_raid_history[user_id] = []

        # ล้างความจำเก่า
        user_raid_history[user_id] = [
            m for m in user_raid_history[user_id] 
            if current_time - m['time'] <= getattr(config, 'RAID_TIME_WINDOW', 15)
        ]

        # บันทึกข้อมูลข้อความล่าสุด
        user_raid_history[user_id].append({
            'time': current_time,
            'content': content,
            'channel_id': channel_id,
            'msg_obj': message
        })

        # เช็คจำนวนห้องที่เหมือนกัน
        same_content_logs = [m for m in user_raid_history[user_id] if m['content'] == content]
        distinct_channels = set(m['channel_id'] for m in same_content_logs)

        # ลงดาบถ้ายอดห้องถึงลิมิต
        if len(distinct_channels) >= getattr(config, 'RAID_CHANNEL_THRESHOLD', 3):
            print(f"🚨 [Anti-Raid] {message.author.name} ส่งข้อความเดิมไป {len(distinct_channels)} ห้องในเวลาอันสั้น!")
            
            # ย้อนกลับไปลบทุกข้อความในทุกห้อง
            for log in same_content_logs:
                try: await log['msg_obj'].delete()
                except: pass
                
            reason = f"พฤติกรรม Raid: ส่งข้อความเดิมซ้ำกันหลายห้อง ({len(distinct_channels)} ห้อง)"
            await punish_user(message, message.author, reason, "Anti-Raid (Cross-Channel)")
            user_raid_history[user_id].clear()
            return

    # ==========================================
    # 1. 📝 ด่านแรก: สแกนข้อความแชท
    # ==========================================
if message.content:
        print(f"👀 [Debug] บอทได้รับข้อความ: '{message.content}' จาก {message.author.name}")
        is_text_spam, text_reason = analyze_text(message.content)
        if is_text_spam:
            print(f"🚨 [Auto-Mod Text] ตรวจพบข้อความสแปมจาก {message.author.name}!")
            await punish_user(message, message.author, text_reason, "Auto-Mod (ข้อความ)")
            return 

    # ==========================================
    # 2. 🖼️ ด่านสอง: สแกนรูปภาพ
    # ==========================================
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
                        print(f"🚨 [Auto-Mod Image] สกัดรูปสแปมสำเร็จที่ภาพที่ {i+1}!")
                        await punish_user(message, message.author, reason, "Auto-Mod (รูปภาพ)")
                        break 
        except Exception as e:
            print(f"❌ [Error] ระบบสแกนภาพขัดข้อง: {e}")

# ==========================================
# 🌟 ระบบ Manual-Mod แบบใหม่ (คลิกขวา -> Apps)
# ==========================================
@bot.tree.context_menu(name="🚨 สแกนสแปม (MaO)")
async def despam_context_menu(interaction: discord.Interaction, message: discord.Message):
    # ephemeral=True ทำให้ข้อความแจ้งเตือนเห็นแค่คนที่กดสั่ง
    if not config.MANUAL_MOD_ENABLED:
        await interaction.response.send_message(config.MSG_DESPAM_DISABLED, ephemeral=True)
        return

    image_attachments = [att for att in message.attachments if att.content_type and att.content_type.startswith('image/')]

    if not image_attachments:
        await interaction.response.send_message(config.MSG_NO_IMAGE, ephemeral=True)
        return

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
