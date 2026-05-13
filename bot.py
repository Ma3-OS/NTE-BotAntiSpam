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
user_raid_history = {}

# ==========================================
# 🎛️ สร้างแผงควบคุมปุ่มกด (Mod Panel View)
# ==========================================
class ModPanelView(discord.ui.View):
    def __init__(self, target_user: discord.Member, img_hash: str = None):
        super().__init__(timeout=None) # ปุ่มไม่หมดอายุ
        self.target_user = target_user
        self.img_hash = img_hash

    @discord.ui.button(label="ปลด Timeout", style=discord.ButtonStyle.success, emoji="🟢")
    async def untimeout_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.moderate_members:
            return await interaction.response.send_message("❌ คุณไม่มีสิทธิ์จัดการ Timeout!", ephemeral=True)
        try:
            await self.target_user.timeout(None, reason=f"ปลดโดย {interaction.user.name}")
            await interaction.response.send_message(f"✅ ปลด Timeout ให้ {self.target_user.mention} เรียบร้อย!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @discord.ui.button(label="แบนถาวร", style=discord.ButtonStyle.danger, emoji="🔨")
    async def ban_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.ban_members:
            return await interaction.response.send_message("❌ คุณไม่มีสิทธิ์แบน!", ephemeral=True)
        try:
            await self.target_user.ban(reason=f"แบนด่วนโดย {interaction.user.name}")
            await interaction.response.send_message(f"🔨 แบน {self.target_user.mention} เรียบร้อย!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @discord.ui.button(label="เตะออก", style=discord.ButtonStyle.primary, emoji="🧹")
    async def kick_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.kick_members:
            return await interaction.response.send_message("❌ คุณไม่มีสิทธิ์เตะ!", ephemeral=True)
        try:
            await self.target_user.kick(reason=f"เตะด่วนโดย {interaction.user.name}")
            await interaction.response.send_message(f"🧹 เตะ {self.target_user.mention} ออกจากเซิร์ฟเวอร์แล้ว!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @discord.ui.button(label="ลืมภาพนี้", style=discord.ButtonStyle.secondary, emoji="🗑️")
    async def uncache_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message("❌ คุณไม่มีสิทธิ์!", ephemeral=True)
        
        if not self.img_hash:
            return await interaction.response.send_message("❌ ข้อความนี้ไม่ใช่สแปมจากรูปภาพ หรือไม่มีข้อมูลให้ลบครับ", ephemeral=True)

        # เรียกใช้หน่วยความจำจาก scanner
        from scanner import spam_hash_cache
        if self.img_hash in spam_hash_cache:
            spam_hash_cache.remove(self.img_hash)
            await interaction.response.send_message("✅ ลบภาพออกจากสมองบอทแล้ว! (จะไม่มีการแบนภาพนี้อัตโนมัติอีก)", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ ภาพนี้ไม่ได้อยู่ในระบบความจำอยู่แล้วครับ", ephemeral=True)

# ==========================================
# ระบบลงโทษและส่ง Log
# ==========================================
async def punish_user(message_to_delete, target_user, reason, trigger_type, img_hash=None):
    try: await message_to_delete.delete()
    except: pass
    
    try: 
        future_time = int(time.time() + config.WARNING_DELETE_DELAY)
        public_msg = config.PUBLIC_WARNING_MSG.format(
            user_mention=target_user.mention, owner_id=OWNER_ID, delete_time=f"<t:{future_time}:R>"
        )
        await message_to_delete.channel.send(public_msg, delete_after=config.WARNING_DELETE_DELAY)
    except: pass
    
    try: 
        dm_msg = config.DM_WARNING_MSG.format(server_name=message_to_delete.guild.name, timeout_days=config.TIMEOUT_DAYS, owner_id=OWNER_ID)
        await target_user.send(dm_msg)
    except: pass
    
    try: 
        await target_user.timeout(datetime.timedelta(days=config.TIMEOUT_DAYS), reason=f"{trigger_type}: {reason}")
    except: pass
    
    # 🌟 แนบแผงปุ่มกด (View) ไปกับ Log ด้วย
    if LOG_CHANNEL_ID:
        try:
            log_channel = bot.get_channel(int(LOG_CHANNEL_ID))
            if log_channel:
                embed = discord.Embed(title="🚨 น้อง MaO ทำลายสแปม!", color=discord.Color.red(), timestamp=datetime.datetime.now())
                embed.add_field(name="คนร้าย", value=target_user.mention, inline=True)
                embed.add_field(name="ระบบที่จับได้", value=trigger_type, inline=True)
                embed.add_field(name="สาเหตุ", value=f"`{reason}`", inline=False)
                
                # เรียกใช้คลาสปุ่มกดที่เราสร้างไว้
                view = ModPanelView(target_user, img_hash)
                await log_channel.send(embed=embed, view=view)
        except Exception as e:
            print(f"Log Error: {e}")

@bot.event
async def on_ready():
    global bot_session
    bot_session = aiohttp.ClientSession()
    try: await bot.tree.sync()
    except: pass
    print(f'🛡️ Bot {bot.user} is ready!')

@bot.event
async def on_message(message):
    if message.author.bot: return
    if not config.AUTO_MOD_ENABLED: return

    # ด่าน 0: Anti-Raid
    if getattr(config, 'ANTI_RAID_ENABLED', False) and message.content:
        current_time = time.time()
        user_id = message.author.id
        content = message.content.strip()
        channel_id = message.channel.id

        if user_id not in user_raid_history: user_raid_history[user_id] = []
        user_raid_history[user_id] = [m for m in user_raid_history[user_id] if current_time - m['time'] <= getattr(config, 'RAID_TIME_WINDOW', 15)]
        user_raid_history[user_id].append({'time': current_time, 'content': content, 'channel_id': channel_id, 'msg_obj': message})

        same_content_logs = [m for m in user_raid_history[user_id] if m['content'] == content]
        distinct_channels = set(m['channel_id'] for m in same_content_logs)

        if len(distinct_channels) >= getattr(config, 'RAID_CHANNEL_THRESHOLD', 3):
            for log in same_content_logs:
                try: await log['msg_obj'].delete()
                except: pass
            reason = f"พฤติกรรม Raid ({len(distinct_channels)} ห้อง)"
            await punish_user(message, message.author, reason, "Anti-Raid")
            user_raid_history[user_id].clear()
            return

    # ด่าน 1: ข้อความแชท
    if message.content:
        is_text_spam, text_reason = analyze_text(message.content)
        if is_text_spam:
            await punish_user(message, message.author, text_reason, "Auto-Mod (ข้อความ)")
            return 

    # ด่าน 2: รูปภาพ
    image_attachments = [att for att in message.attachments if att.content_type and att.content_type.startswith('image/')]
    if not image_attachments: return

    for target_image in image_attachments:
        try:
            async with bot_session.get(target_image.url) as resp:
                if resp.status == 200:
                    img_data = await resp.read()
                    # 🌟 รับค่า img_hash เพิ่มมาด้วย
                    is_spam, reason, img_hash = await analyze_image(img_data)
                    del img_data
                    gc.collect()

                    if is_spam:
                        # 🌟 โยน img_hash เข้า punish_user
                        await punish_user(message, message.author, reason, "Auto-Mod (รูปภาพ)", img_hash)
                        break 
        except: pass

@bot.tree.context_menu(name="🚨 สแกนสแปม (MaO)")
async def despam_context_menu(interaction: discord.Interaction, message: discord.Message):
    if not config.MANUAL_MOD_ENABLED:
        return await interaction.response.send_message(config.MSG_DESPAM_DISABLED, ephemeral=True)
    image_attachments = [att for att in message.attachments if att.content_type and att.content_type.startswith('image/')]
    if not image_attachments:
        return await interaction.response.send_message(config.MSG_NO_IMAGE, ephemeral=True)

    await interaction.response.send_message(config.MSG_SCANNING, ephemeral=True)
    is_spam_found, spam_reason, found_hash = False, "", None

    for target_image in image_attachments:
        try:
            async with bot_session.get(target_image.url) as resp:
                if resp.status == 200:
                    img_data = await resp.read()
                    is_spam, reason, img_hash = await analyze_image(img_data)
                    del img_data
                    gc.collect()
                    if is_spam:
                        is_spam_found, spam_reason, found_hash = True, reason, img_hash
                        break 
        except: pass

    if is_spam_found:
        await interaction.edit_original_response(content=config.MSG_SPAM_FOUND.format(reason=spam_reason))
        await punish_user(message, message.author, spam_reason, f"Manual-Mod ({interaction.user.name})", found_hash)
    else:
        await interaction.edit_original_response(content=config.MSG_SAFE)

if TOKEN:
    keep_alive()
    bot.run(TOKEN)
