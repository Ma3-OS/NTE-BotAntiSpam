import discord
from discord.ext import commands
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
# 🛑 ระบบเช็คสิทธิ์ (Permissions Check)
# ==========================================
def has_mod_rights(member: discord.Member, default_permission_check):
    """เช็คว่ายูสเซอร์มียศที่อนุญาตให้กดปุ่มไหม หรือมีสิทธิ์ Discord พื้นฐานหรือไม่"""
    allowed_roles = getattr(config, 'ALLOWED_MOD_ROLES', [])
    if allowed_roles:
        return any(role.id in allowed_roles for role in member.roles)
    return default_permission_check()

# ==========================================
# 🎛️ UI: หน้าต่างยืนยัน (Confirmation View)
# ==========================================
class ConfirmActionView(discord.ui.View):
    def __init__(self, action_name, target_user, reason, hash_id, execute_callback, original_view, original_message):
        super().__init__(timeout=getattr(config, 'CONFIRM_TIMEOUT', 15))
        self.action_name = action_name
        self.target_user = target_user
        self.execute_callback = execute_callback
        self.original_view = original_view
        self.original_message = original_message

    async def on_timeout(self):
        # ถ้าหมดเวลา ให้ลบปุ่มยืนยันทิ้ง
        for item in self.children: item.disabled = True
        try: await self.message.edit(content="⏳ หมดเวลายืนยันคำสั่ง", view=self, embed=None)
        except: pass

    @discord.ui.button(label="ยืนยันคำสั่ง", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.execute_callback(interaction) # ทำงานจริง
        
        # ถ้ายืนยันแล้ว ให้ล็อกปุ่มอันเก่า (Log) ด้วย
        if getattr(config, 'HIDE_PANEL_AFTER_ACTION', True) and self.original_message:
            for item in self.original_view.children: item.disabled = True
            try: await self.original_message.edit(view=self.original_view)
            except: pass

    @discord.ui.button(label="ยกเลิก", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ ยกเลิกคำสั่งเรียบร้อยแล้ว", embed=None, view=None)

# ==========================================
# 🎛️ UI: แผงควบคุมหลัก (Mod Panel View)
# ==========================================
class ModPanelView(discord.ui.View):
    def __init__(self, target_user: discord.Member, reason: str, img_hash: str = None):
        super().__init__(timeout=None)
        self.target_user = target_user
        self.reason = reason
        self.img_hash = img_hash

    async def prompt_confirm(self, interaction: discord.Interaction, action_name: str, execute_callback):
        if not getattr(config, 'REQUIRE_CONFIRMATION', True):
            return await execute_callback(interaction)

        embed = discord.Embed(title="⚠️ [ยืนยันคำสั่ง]", description=f"คุณกำลังสั่ง **{action_name}** โปรดตรวจสอบข้อมูลให้ชัวร์:", color=discord.Color.orange())
        embed.add_field(name="👤 เป้าหมาย", value=f"{self.target_user.mention} (ID: {self.target_user.id})", inline=False)
        embed.add_field(name="📝 ข้อหา", value=f"`{self.reason}`", inline=False)
        if self.img_hash: embed.add_field(name="🖼️ รหัสภาพ", value=f"`{self.img_hash}`", inline=False)
        
        confirm_view = ConfirmActionView(action_name, self.target_user, self.reason, self.img_hash, execute_callback, self, interaction.message)
        await interaction.response.send_message(embed=embed, view=confirm_view, ephemeral=True)
        confirm_view.message = await interaction.original_response()

    @discord.ui.button(label="ปลด Timeout", style=discord.ButtonStyle.success, emoji="🟢")
    async def untimeout_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_mod_rights(interaction.user, lambda: interaction.user.guild_permissions.moderate_members):
            return await interaction.response.send_message("❌ สิทธิ์ไม่พอ!", ephemeral=True)
            
    @discord.ui.button(label="เตะออก", style=discord.ButtonStyle.primary, emoji="🧹")
    async def kick_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_mod_rights(interaction.user, lambda: interaction.user.guild_permissions.kick_members):
            return await interaction.response.send_message("❌ สิทธิ์ไม่พอ!", ephemeral=True)
        
        async def execute(i):
            try:
                await self.target_user.kick(reason=f"เตะด่วนโดย {i.user.name}")
                await i.response.edit_message(content=f"🧹 เตะ {self.target_user.mention} ออกจากเซิร์ฟเวอร์แล้ว!", embed=None, view=None)
            except Exception as e: await i.response.edit_message(content=f"❌ Error: {e}", embed=None, view=None)
        await self.prompt_confirm(interaction, "เตะออก (Kick)", execute)
        
        async def execute(i):
            try:
                await self.target_user.timeout(None, reason=f"ปลดโดย {i.user.name}")
                await i.response.edit_message(content=f"✅ ปลด Timeout ให้ {self.target_user.mention} เรียบร้อย!", embed=None, view=None)
            except Exception as e: await i.response.edit_message(content=f"❌ Error: {e}", embed=None, view=None)
        await self.prompt_confirm(interaction, "ปลด Timeout", execute)

    @discord.ui.button(label="แบนถาวร", style=discord.ButtonStyle.danger, emoji="🔨")
    async def ban_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_mod_rights(interaction.user, lambda: interaction.user.guild_permissions.ban_members):
            return await interaction.response.send_message("❌ สิทธิ์ไม่พอ!", ephemeral=True)
        
        async def execute(i):
            try:
                await self.target_user.ban(reason=f"แบนด่วนโดย {i.user.name}")
                await i.response.edit_message(content=f"🔨 แบน {self.target_user.mention} เรียบร้อย!", embed=None, view=None)
            except Exception as e: await i.response.edit_message(content=f"❌ Error: {e}", embed=None, view=None)
        await self.prompt_confirm(interaction, "แบนถาวร (Ban)", execute)

    @discord.ui.button(label="ลืมภาพนี้", style=discord.ButtonStyle.secondary, emoji="🗑️")
    async def uncache_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_mod_rights(interaction.user, lambda: interaction.user.guild_permissions.manage_messages):
            return await interaction.response.send_message("❌ สิทธิ์ไม่พอ!", ephemeral=True)
        
        async def execute(i):
            from scanner import spam_hash_cache
            if self.img_hash and self.img_hash in spam_hash_cache:
                del spam_hash_cache[self.img_hash]
                await i.response.edit_message(content="✅ ลบภาพออกจากสมองบอทแล้ว!", embed=None, view=None)
            else:
                await i.response.edit_message(content="⚠️ ภาพนี้ไม่ได้ถูกจำไว้ตั้งแต่แรกครับ", embed=None, view=None)
        await self.prompt_confirm(interaction, "ล้างความจำภาพ (Un-cache)", execute)

# ==========================================
# ระบบลงโทษและส่ง Log
# ==========================================
async def punish_user(message_to_delete, target_user, reason, trigger_type, img_hash=None):
    try: await message_to_delete.delete()
    except: pass
    
    try: await target_user.timeout(datetime.timedelta(days=config.TIMEOUT_DAYS), reason=f"{trigger_type}: {reason}")
    except: pass
    
    if LOG_CHANNEL_ID:
        try:
            log_channel = bot.get_channel(int(LOG_CHANNEL_ID))
            if log_channel:
                embed = discord.Embed(title="🚨 แจ้งเตือนระบบจับสแปม", color=discord.Color.red(), timestamp=datetime.datetime.now())
                embed.add_field(name="คนร้าย", value=target_user.mention, inline=True)
                embed.add_field(name="ระบบที่จับได้", value=trigger_type, inline=True)
                embed.add_field(name="สาเหตุ", value=f"`{reason}`", inline=False)
                view = ModPanelView(target_user, reason, img_hash)
                await log_channel.send(embed=embed, view=view)
        except Exception as e: print(f"Log Error: {e}")

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

    # 🛑 เช็คห้องละเว้น
    if getattr(config, 'IGNORE_CHANNELS', []) and message.channel.id in config.IGNORE_CHANNELS:
        return
    
    # 🛑 เช็คยศละเว้น (VIP / Admin)
    if getattr(config, 'EXEMPT_ROLES', []) and isinstance(message.author, discord.Member):
        if any(role.id in config.EXEMPT_ROLES for role in message.author.roles):
            return

    # ด่าน 1: ข้อความแชท (ถ้าสั้นเกินจะข้าม แต่รูปภาพยังสแกนนะ)
    if message.content:
        min_length = getattr(config, 'IGNORE_SHORT_MESSAGES', 3)
        if len(message.content) > min_length:
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
                    is_spam, reason, img_hash = await analyze_image(img_data)
                    del img_data
                    gc.collect()

                    if is_spam:
                        await punish_user(message, message.author, reason, "Auto-Mod (รูปภาพ)", img_hash)
                        break 
        except: pass

@bot.tree.context_menu(name="🚨 สแกนสแปม (MaO)")
async def despam_context_menu(interaction: discord.Interaction, message: discord.Message):
    if not getattr(config, 'MANUAL_MOD_ENABLED', True): return await interaction.response.send_message(config.MSG_DESPAM_DISABLED, ephemeral=True)
    image_attachments = [att for att in message.attachments if att.content_type and att.content_type.startswith('image/')]
    if not image_attachments: return await interaction.response.send_message(config.MSG_NO_IMAGE, ephemeral=True)

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
    else: await interaction.edit_original_response(content=config.MSG_SAFE)

if TOKEN:
    keep_alive()
    bot.run(TOKEN)
