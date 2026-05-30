import discord
from discord.ext import commands
import aiohttp
import asyncio
import datetime
import os
import io
import logging
import time
from collections import defaultdict, deque
from dotenv import load_dotenv

import config
from scanner import analyze_image, analyze_text
from keep_alive import keep_alive

# ==========================================
# ✅ ใช้ logging แทน print() — ได้ timestamp + log level
#    เปลี่ยน level เป็น WARNING บน production เพื่อลด noise
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("MaO-Bot")

load_dotenv()


# ==========================================
# ✅ Validate env vars ตั้งแต่ต้น — ระเบิดตอน boot ดีกว่าระเบิดตอนใช้งาน
# ==========================================
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


TOKEN = os.getenv('DISCORD_TOKEN')
if not TOKEN:
    raise RuntimeError("❌ DISCORD_TOKEN is not set — bot cannot start")

LOG_CHANNEL_ID: int | None = _load_env_int('LOG_CHANNEL_ID')
OWNER_ID: int | None = _load_env_int('OWNER_ID')

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# ==========================================
# ✅ Anti-Raid Tracker (in-memory sliding window)
#    user_id -> deque of (timestamp, channel_id)
# ==========================================
raid_tracker: defaultdict[int, deque] = defaultdict(deque)


# ==========================================
# ✅ Subclass Bot เพื่อ lifecycle ที่ถูกต้อง
#    - setup_hook: เรียกครั้งเดียวก่อน login
#    - close(): cleanup resources เมื่อ shutdown
# ==========================================
class AntiSpamBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=config.COMMAND_PREFIX, intents=intents)
        self.http_session: aiohttp.ClientSession | None = None

    async def setup_hook(self):
        """เรียกครั้งเดียวตอน Bot เริ่ม — สร้าง aiohttp session ที่นี่เท่านั้น"""
        # ✅ Connector พร้อม limit ป้องกัน connection flood บน server เล็ก
        connector = aiohttp.TCPConnector(limit=10, ttl_dns_cache=300)
        self.http_session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=30),
        )
        try:
            await self.tree.sync()
            logger.info("Slash commands synced successfully")
        except Exception as e:
            logger.error("Failed to sync slash commands: %s", e)

    async def close(self):
        """✅ Cleanup — ปิด HTTP session ก่อน close bot เสมอ"""
        if self.http_session and not self.http_session.closed:
            await self.http_session.close()
            logger.info("HTTP session closed cleanly")
        await super().close()

    async def on_ready(self):
        logger.info("🛡️ Bot %s is online and monitoring!", self.user)

    async def on_disconnect(self):
        logger.warning("Bot disconnected from Discord, will attempt reconnect...")

    async def on_resumed(self):
        logger.info("Bot successfully resumed connection")


bot = AntiSpamBot()


# ==========================================
# 🛑 ระบบเช็คสิทธิ์
# ==========================================
def has_mod_rights(member: discord.Member, default_permission_check) -> bool:
    allowed_roles = getattr(config, 'ALLOWED_MOD_ROLES', [])
    if allowed_roles:
        return any(role.id in allowed_roles for role in member.roles)
    return default_permission_check()


# ==========================================
# 🛡️ ระบบ Anti-Raid (sliding window cross-channel detection)
# ==========================================
def check_raid(user_id: int, channel_id: int) -> bool:
    """
    ตรวจสอบว่า user ส่งข้อความในหลายห้องพร้อมกันเกิน threshold ไหม
    Returns True ถ้าตรวจพบ Raid pattern
    """
    if not getattr(config, 'ANTI_RAID_ENABLED', False):
        return False

    now = time.monotonic()
    window = getattr(config, 'RAID_TIME_WINDOW', 10)
    threshold = getattr(config, 'RAID_CHANNEL_THRESHOLD', 5)

    history = raid_tracker[user_id]

    # ลบ entry ที่หมดอายุออก (sliding window)
    while history and now - history[0][0] > window:
        history.popleft()

    history.append((now, channel_id))
    unique_channels = len({ch for _, ch in history})

    if unique_channels >= threshold:
        # เคลียร์ประวัติหลังตรวจพบ — ป้องกัน false positive ซ้ำ
        del raid_tracker[user_id]
        logger.warning("🚨 Raid detected: user_id=%s sent in %d channels within %ds", user_id, unique_channels, window)
        return True

    return False


# ==========================================
# 🎛️ UI: หน้าต่างยืนยัน (Confirmation View)
# ==========================================
class ConfirmActionView(discord.ui.View):
    def __init__(self, action_name, target_user, reason, hash_id, execute_callback, original_view, original_message):
        super().__init__(timeout=getattr(config, 'CONFIRM_TIMEOUT', 15))
        self.action_name = action_name
        self.target_user = target_user
        # ✅ Fix: เพิ่ม self.reason และ self.hash_id ที่หายไปจากเดิม
        self.reason = reason
        self.hash_id = hash_id
        self.execute_callback = execute_callback
        self.original_view = original_view
        self.original_message = original_message
        self.message: discord.Message | None = None  # ✅ ประกาศชัดเจน ป้องกัน AttributeError

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        # ✅ ตรวจสอบก่อนเข้าถึง self.message — ป้องกัน AttributeError
        if self.message:
            try:
                await self.message.edit(content="⏳ หมดเวลายืนยันคำสั่ง", view=self, embed=None)
            except discord.HTTPException as e:
                logger.warning("on_timeout: Failed to edit message: %s", e)

    @discord.ui.button(label="ยืนยันคำสั่ง", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.execute_callback(interaction)
        if getattr(config, 'HIDE_PANEL_AFTER_ACTION', True) and self.original_message:
            for item in self.original_view.children:
                item.disabled = True
            try:
                await self.original_message.edit(view=self.original_view)
            except discord.HTTPException as e:
                logger.warning("confirm_btn: Failed to disable original panel: %s", e)

    @discord.ui.button(label="ยกเลิก", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ ยกเลิกคำสั่งเรียบร้อยแล้ว", embed=None, view=None)


# ==========================================
# 🎛️ UI: แผงควบคุมหลัก (Mod Panel View)
# ==========================================
class ModPanelView(discord.ui.View):
    def __init__(self, target_user: discord.Member, reason: str, img_hash: str | None = None):
        super().__init__(timeout=None)
        self.target_user = target_user
        self.reason = reason
        self.img_hash = img_hash

    async def prompt_confirm(self, interaction: discord.Interaction, action_name: str, execute_callback):
        if not getattr(config, 'REQUIRE_CONFIRMATION', True):
            return await execute_callback(interaction)

        embed = discord.Embed(
            title="⚠️ [ยืนยันคำสั่ง]",
            description=f"คุณกำลังสั่ง **{action_name}** โปรดตรวจสอบข้อมูล:",
            color=discord.Color.orange()
        )
        embed.add_field(name="👤 เป้าหมาย", value=self.target_user.mention, inline=False)
        embed.add_field(name="📝 ข้อหา", value=f"`{self.reason}`", inline=False)
        if self.img_hash:
            embed.add_field(name="🖼️ รหัสภาพ", value=f"`{self.img_hash}`", inline=False)

        confirm_view = ConfirmActionView(
            action_name, self.target_user, self.reason, self.img_hash,
            execute_callback, self, interaction.message
        )
        await interaction.response.send_message(embed=embed, view=confirm_view, ephemeral=True)
        confirm_view.message = await interaction.original_response()

    async def _check_mod(self, interaction: discord.Interaction, perm_check) -> bool:
        """✅ Helper เช็คสิทธิ์และตอบกลับ — ลด code ซ้ำในทุกปุ่ม"""
        if not has_mod_rights(interaction.user, perm_check):
            await interaction.response.send_message("❌ สิทธิ์ไม่พอ!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="ปลด Timeout", style=discord.ButtonStyle.success, emoji="🟢")
    async def untimeout_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_mod(interaction, lambda: interaction.user.guild_permissions.moderate_members):
            return

        async def execute(i: discord.Interaction):
            member = i.guild.get_member(self.target_user.id)
            if not member:
                return await i.response.edit_message(
                    content="❌ หาตัวผู้ใช้ไม่เจอ (อาจจะออกจากเซิร์ฟเวอร์ไปแล้ว)",
                    embed=None, view=None
                )
            try:
                await member.timeout(None, reason=f"ปลดโดย {i.user.name}")
                await i.response.edit_message(
                    content=f"✅ ปลด Timeout ให้ {self.target_user.mention} เรียบร้อย!",
                    embed=None, view=None
                )
            except discord.Forbidden:
                await i.response.edit_message(content="❌ บอทไม่มีสิทธิ์ปลด Timeout ผู้ใช้คนนี้", embed=None, view=None)
            except discord.HTTPException as e:
                logger.error("untimeout: Failed for user %s: %s", self.target_user.id, e)
                await i.response.edit_message(content=f"❌ Error: {e}", embed=None, view=None)

        await self.prompt_confirm(interaction, "ปลด Timeout", execute)

    @discord.ui.button(label="แบนถาวร", style=discord.ButtonStyle.danger, emoji="🔨")
    async def ban_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_mod(interaction, lambda: interaction.user.guild_permissions.ban_members):
            return

        async def execute(i: discord.Interaction):
            try:
                await self.target_user.ban(reason=f"แบนด่วนโดย {i.user.name}")
                await i.response.edit_message(
                    content=f"🔨 แบน {self.target_user.mention} เรียบร้อย!",
                    embed=None, view=None
                )
            except discord.Forbidden:
                await i.response.edit_message(content="❌ บอทไม่มีสิทธิ์แบน (ตรวจสอบลำดับยศ)", embed=None, view=None)
            except discord.HTTPException as e:
                logger.error("ban: Failed for user %s: %s", self.target_user.id, e)
                await i.response.edit_message(content=f"❌ Error: {e}", embed=None, view=None)

        await self.prompt_confirm(interaction, "แบนถาวร (Ban)", execute)

    @discord.ui.button(label="เตะออก", style=discord.ButtonStyle.primary, emoji="🧹")
    async def kick_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_mod(interaction, lambda: interaction.user.guild_permissions.kick_members):
            return

        async def execute(i: discord.Interaction):
            try:
                await self.target_user.kick(reason=f"เตะด่วนโดย {i.user.name}")
                await i.response.edit_message(
                    content=f"🧹 เตะ {self.target_user.mention} ออกแล้ว!",
                    embed=None, view=None
                )
            except discord.Forbidden:
                await i.response.edit_message(content="❌ บอทไม่มีสิทธิ์เตะ (ตรวจสอบลำดับยศ)", embed=None, view=None)
            except discord.HTTPException as e:
                logger.error("kick: Failed for user %s: %s", self.target_user.id, e)
                await i.response.edit_message(content=f"❌ Error: {e}", embed=None, view=None)

        await self.prompt_confirm(interaction, "เตะออก (Kick)", execute)

    @discord.ui.button(label="ลืมภาพนี้", style=discord.ButtonStyle.secondary, emoji="🗑️")
    async def uncache_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_mod(interaction, lambda: interaction.user.guild_permissions.manage_messages):
            return

        async def execute(i: discord.Interaction):
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
async def punish_user(
    message_to_delete: discord.Message,
    target_user: discord.Member,
    reason: str,
    trigger_type: str,
    img_hash: str | None = None,
    img_data: bytes | None = None,
):
    # ✅ แยก exception type ให้ชัด — Forbidden ≠ HTTPException ≠ NetworkError
    try:
        await message_to_delete.delete()
    except discord.Forbidden:
        logger.warning("punish: No permission to delete message in #%s", message_to_delete.channel.id)
    except discord.NotFound:
        pass  # ข้อความถูกลบไปแล้ว — ไม่ใช่ error
    except discord.HTTPException as e:
        logger.error("punish: Failed to delete message: %s", e)

    try:
        await target_user.timeout(
            datetime.timedelta(days=config.TIMEOUT_DAYS),
            reason=f"{trigger_type}: {reason}"
        )
    except discord.Forbidden:
        logger.warning("punish: No permission to timeout user %s", target_user.id)
    except discord.HTTPException as e:
        logger.error("punish: Failed to timeout user %s: %s", target_user.id, e)

    # ==========================================
    # 📢 ส่งข้อความแจ้งเตือนหน้าแชท (Public Warning)
    # ✅ ใช้ delete_after เพื่อลบข้อความอัตโนมัติ — ไม่ต้องสร้าง task แยก
    # ==========================================
    public_warning_template = getattr(config, 'PUBLIC_WARNING_MSG', None)
    if public_warning_template:
        try:
            delete_delay = getattr(config, 'WARNING_DELETE_DELAY', 60)
            delete_time_text = f"ใน {delete_delay} วินาที"
            warning_text = public_warning_template.format(
                user_mention=target_user.mention,
                owner_id=OWNER_ID or "",
                delete_time=delete_time_text,
            )
            await message_to_delete.channel.send(
                warning_text,
                delete_after=delete_delay,
            )
        except discord.Forbidden:
            logger.warning("punish: No permission to send public warning in channel %s", message_to_delete.channel.id)
        except discord.HTTPException as e:
            logger.error("punish: Failed to send public warning: %s", e)

    # ==========================================
    # 📩 ส่ง DM แจ้งเตือนส่วนตัวไปหาคนโดน
    # ✅ ใช้ try/except แยก — บางคนปิด DM ซึ่งเป็น Forbidden error ปกติ
    # ==========================================
    dm_warning_template = getattr(config, 'DM_WARNING_MSG', None)
    if dm_warning_template:
        try:
            dm_text = dm_warning_template.format(
                server_name=message_to_delete.guild.name if message_to_delete.guild else "เซิร์ฟเวอร์",
                timeout_days=config.TIMEOUT_DAYS,
                owner_id=OWNER_ID or "",
            )
            await target_user.send(dm_text)
            logger.info("punish: DM warning sent to user %s", target_user.id)
        except discord.Forbidden:
            # ปกติมากถ้าผู้ใช้ปิด DM — ไม่ใช่ error ร้ายแรง
            logger.info("punish: User %s has DMs disabled, skipping DM warning", target_user.id)
        except discord.HTTPException as e:
            logger.error("punish: Failed to send DM warning to user %s: %s", target_user.id, e)

    if not LOG_CHANNEL_ID:
        return

    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if not log_channel:
        logger.warning("punish: Log channel %s not found — check LOG_CHANNEL_ID env var", LOG_CHANNEL_ID)
        return

    try:
        embed = discord.Embed(
            title="🚨 น้อง MaO ทำลายสแปม!",
            color=discord.Color.red(),
            # ✅ ใช้ timezone-aware datetime — naive datetime deprecated ใน discord.py
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.add_field(name="คนร้าย", value=target_user.mention, inline=True)
        embed.add_field(name="ระบบที่จับได้", value=trigger_type, inline=True)
        embed.add_field(name="สาเหตุ", value=f"`{reason}`", inline=False)

        view = ModPanelView(target_user, reason, img_hash)
        kwargs: dict = {"embed": embed, "view": view}

        if img_data:
            file = discord.File(io.BytesIO(img_data), filename="spam_evidence.png")
            embed.set_image(url="attachment://spam_evidence.png")
            kwargs["file"] = file

        await log_channel.send(**kwargs)
        logger.info("punish: Logged action for user %s (%s)", target_user.id, trigger_type)
    except discord.HTTPException as e:
        logger.error("punish: Failed to send log message: %s", e)


# ==========================================
# 📨 on_message — ระบบ Auto-Mod หลัก
# ==========================================
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if not config.AUTO_MOD_ENABLED:
        return

    # ✅ บอทไม่ทำงานใน DM (ไม่มี guild → ไม่มี timeout/ban/kick)
    if not message.guild:
        return

    if getattr(config, 'IGNORE_CHANNELS', []) and message.channel.id in config.IGNORE_CHANNELS:
        return

    if getattr(config, 'EXEMPT_ROLES', []) and isinstance(message.author, discord.Member):
        if any(role.id in config.EXEMPT_ROLES for role in message.author.roles):
            return

    # ✅ Anti-Raid check ก่อนสแกน content
    if check_raid(message.author.id, message.channel.id):
        await punish_user(message, message.author, "ส่งข้อความหลายห้องพร้อมกัน (Raid)", "Anti-Raid")
        return

    # --- Text spam detection ---
    if message.content:
        min_length = getattr(config, 'IGNORE_SHORT_MESSAGES', 3)
        if len(message.content) > min_length:
            is_text_spam, text_reason = analyze_text(message.content)
            if is_text_spam:
                await punish_user(message, message.author, text_reason, "Auto-Mod (ข้อความ)")
                return

    # --- Image spam detection ---
    image_attachments = [
        att for att in message.attachments
        if att.content_type and att.content_type.startswith('image/')
    ]
    if not image_attachments:
        return

    # ✅ Guard: session ต้องพร้อมก่อนใช้ — ป้องกัน crash ถ้าเรียกก่อน setup_hook เสร็จ
    if not bot.http_session or bot.http_session.closed:
        logger.error("on_message: HTTP session unavailable, skipping image scan")
        return

    # ✅ จำกัดขนาดรูปก่อน download — ป้องกัน OOM บน Render free tier (512MB RAM)
    MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8 MB

    for attachment in image_attachments:
        if attachment.size > MAX_IMAGE_BYTES:
            logger.info("Skipping oversized image (%s bytes) from user %s", attachment.size, message.author.id)
            continue
        try:
            async with bot.http_session.get(attachment.url) as resp:
                if resp.status != 200:
                    logger.warning("on_message: Failed to fetch image HTTP %s", resp.status)
                    continue
                img_data = await resp.read()

            # ✅ ไม่ต้อง gc.collect() — CPython จัดการ refcount เองได้ทันที
            is_spam, reason, img_hash = await analyze_image(img_data)
            if is_spam:
                await punish_user(message, message.author, reason, "Auto-Mod (รูปภาพ)", img_hash, img_data)
                break  # พบสแปมแล้ว ไม่ต้องสแกนรูปถัดไป

        except aiohttp.ClientError as e:
            logger.error("on_message: Network error fetching image: %s", e)
        except Exception as e:
            # ✅ Catch-all สุดท้าย — ยัง log ไว้ ไม่ silent fail
            logger.exception("on_message: Unexpected error during image scan: %s", e)


# ==========================================
# 🔍 Context Menu: สแกนสแปมแบบ Manual
# ==========================================
@bot.tree.context_menu(name="🚨 สแกนสแปม (MaO)")
async def despam_context_menu(interaction: discord.Interaction, message: discord.Message):
    if not getattr(config, 'MANUAL_MOD_ENABLED', True):
        return await interaction.response.send_message(config.MSG_DESPAM_DISABLED, ephemeral=True)

    image_attachments = [
        att for att in message.attachments
        if att.content_type and att.content_type.startswith('image/')
    ]
    if not image_attachments:
        return await interaction.response.send_message(config.MSG_NO_IMAGE, ephemeral=True)

    await interaction.response.send_message(config.MSG_SCANNING, ephemeral=True)

    if not bot.http_session or bot.http_session.closed:
        return await interaction.edit_original_response(content="❌ ระบบ HTTP ไม่พร้อม กรุณาลองใหม่อีกครั้ง")

    is_spam_found = False
    spam_reason = ""
    found_hash: str | None = None
    saved_img_data: bytes | None = None

    MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8 MB

    for attachment in image_attachments:
        if attachment.size > MAX_IMAGE_BYTES:
            continue
        try:
            async with bot.http_session.get(attachment.url) as resp:
                if resp.status != 200:
                    continue
                img_data = await resp.read()

            is_spam, reason, img_hash = await analyze_image(img_data)
            if is_spam:
                is_spam_found = True
                spam_reason = reason
                found_hash = img_hash
                saved_img_data = img_data
                break

        except aiohttp.ClientError as e:
            logger.error("context_menu: Network error: %s", e)
        except Exception as e:
            logger.exception("context_menu: Unexpected error: %s", e)

    if is_spam_found:
        await interaction.edit_original_response(
            content=config.MSG_SPAM_FOUND.format(reason=spam_reason)
        )
        await punish_user(
            message, message.author, spam_reason,
            f"Manual-Mod ({interaction.user.name})",
            found_hash, saved_img_data
        )
    else:
        await interaction.edit_original_response(content=config.MSG_SAFE)


# ==========================================
# 🚀 เริ่มบอท
# ==========================================
keep_alive()
# ✅ log_handler=None เพราะเราตั้ง logging เองแล้ว ป้องกัน duplicate logs
bot.run(TOKEN, log_handler=None)
