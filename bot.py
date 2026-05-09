import discord
from discord.ext import commands
import aiohttp
import datetime
import gc
import os
from dotenv import load_dotenv

# นำเข้าไฟล์ตั้งค่าและฟังก์ชันอื่นๆ ในโปรเจกต์ของเรา
import config
from scanner import analyze_image
from keep_alive import keep_alive
from messages import get_public_warning, get_dm_warning

# โหลดค่าจากไฟล์ .env (สำหรับรันบน Local)
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
LOG_CHANNEL_ID = os.getenv('LOG_CHANNEL_ID')

# ตั้งค่า Intents ให้บอทมองเห็นข้อความและสมาชิกในเซิร์ฟเวอร์
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
    print(f'⚙️ Image Hash Cache: {"✅ ON" if config.IMAGE_CACHE_ENABLED else "❌ OFF"}')

async def punish_user(message_to_delete, target_user, reason, trigger_type):
    """ฟังก์ชันกลางสำหรับลงดาบคนทำผิด (แบน, ลบ, แจ้งเตือน)"""
    # 1. ลบข้อความต้นฉบับทิ้ง
    try: 
        await message_to_delete.delete()
    except discord.Forbidden: 
        pass
    
    # 2. แจ้งเตือนหน้าห้องแชท (ข้อความจะลบตัวเองใน 60 วินาที)
    try: 
        await message_to_delete.channel.send(get_public_warning(target_user.mention), delete_after=60)
    except: 
        pass
    
    # 3. ทัก DM ไปเตือนหลังบ้าน
    try: 
        await target_user.send(get_dm_warning(message_to_delete.guild.name))
    except: 
        pass
    
    # 4. ลงดาบ Timeout 1 วัน
    try: 
        await target_user.timeout(datetime.timedelta(days=1), reason=f"{trigger_type}: {reason}")
    except: 
        pass
    
    # 5. ส่ง Log เข้าห้องแอดมิน (ถ้าตั้งค่าไว้)
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

# ==========================================
# ระบบ Auto-Mod (สแกนรูปภาพอัตโนมัติ)
# ==========================================
@bot.event
async def on_message(message):
    # ⚠️ บรรทัดนี้สำคัญมาก เพื่อให้คำสั่ง (!despam) ทำงานได้ปกติ
    await bot.process_commands(message)

    # ไม่สแกนข้อความของบอทด้วยกันเอง
    if message.author.bot: 
        return

    # ตรวจสอบว่ามีไฟล์แนบมากับข้อความหรือไม่
    if message.attachments:
        print(f"📩 [Event] ได้รับข้อความพร้อมไฟล์แนบจาก: {message.author.name} (ในห้อง: {message.channel.name})")
        
        # ข้ามถ้าเป็นคำสั่ง (ป้องกันการทำงานซ้ำซ้อนกับระบบ Manual)
        if message.content.startswith(config.COMMAND_PREFIX):
            print(f"⏭️ [Event] ข้ามการสแกนอัตโนมัติ เพราะมีการใช้คำสั่ง: {message.content}")
            return

        # ข้ามถ้าระบบ Auto-Mod ถูกตั้งปิดไว้ใน config.py
        if not config.AUTO_MOD_ENABLED:
            print("💤 [Event] ข้ามการสแกน เพราะระบบ Auto-Mod ปิดอยู่")
            return

        # ค้นหาไฟล์ที่เป็นประเภทรูปภาพ (image)
        target_image = next((att for att in message.attachments if att.content_type and att.content_type.startswith('image/')), None)
        
        if target_image:
            print(f"🖼️ [Event] ตรวจพบรูปภาพ: {target_image.filename} กำลังส่งให้ AI สแกน...")
            try:
                async with bot_session.get(target_image.url) as resp:
                    if resp.status == 200:
                        img_data = await resp.read()
                        
                        # ส่งรูปไปให้ scanner.py ตรวจสอบ (ระบบ AI)
                        is_spam, reason = await analyze_image(img_data)
                        
                        # เคลียร์ข้อมูลรูปภาพออกจาก RAM ทันที
                        del img_data
                        gc.collect()

                        if is_spam:
                            print(f"🚨 [Auto-Mod] สกัดรูปสแปมจาก {message.author.name} สำเร็จ!")
                            await punish_user(message, message.author, reason, "Auto-Mod (รูปภาพ)")
                        else:
                            print(f"✅ [Auto-Mod] รูปภาพจาก {message.author.name} ปลอดภัย")
            except Exception as e:
                print(f"❌ [Error] ระบบ Auto-Mod ขัดข้อง: {e}")

# ==========================================
# ระบบ Manual-Mod (คำสั่ง !despam)
# ==========================================
@bot.command(name="despam")
async def despam_image(ctx):
    print(f"🛠️ [Event] แอดมิน {ctx.author.name} เรียกใช้คำสั่ง !despam")
    
    if not config.MANUAL_MOD_ENABLED:
        await ctx.reply(config.MSG_DESPAM_DISABLED)
        return

    # ตรวจสอบว่าแอดมินได้กด Reply ข้อความต้นทางหรือไม่
    if not ctx.message.reference:
        await ctx.reply(config.MSG_NEED_REPLY)
        return

    try:
        replied_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
    except discord.NotFound:
        await ctx.reply(config.MSG_MSG_NOT_FOUND)
        return

    # หางรูปภาพในข้อความที่ถูก Reply
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
                    print(f"✅ [Manual-Mod] ตรวจสอบแล้วไม่ใช่สแปม")
                else:
                    # อัปเดตข้อความพร้อมแนบสาเหตุการแบน
                    await status_msg.edit(content=config.MSG_SPAM_FOUND.format(reason=reason))
                    print(f"🚨 [Manual-Mod] เจอสแปม! สาเหตุ: {reason}")
                    await punish_user(replied_msg, replied_msg.author, reason, f"Manual-Mod (สั่งโดย {ctx.author.name})")
    except Exception as e:
        await status_msg.edit(content=config.MSG_ERROR.format(error=e))
        print(f"❌ [Error] ระบบ Manual-Mod ขัดข้อง: {e}")

# ==========================================
# เริ่มต้นการทำงานของบอท
# ==========================================
if TOKEN:
    # เปิด Web Server เล็กๆ ไว้กันบอทหลับ (สำหรับ Render/UptimeRobot)
    keep_alive()
    bot.run(TOKEN)
else:
    print("❌ [Fatal Error] ไม่พบ DISCORD_TOKEN ในระบบ! โปรดเช็คไฟล์ .env หรือ Environment Variables")
