import discord
from discord.ext import commands
import logging
import time
import datetime
import io
from collections import defaultdict, deque

import config
from utils.scanner import analyze_text

logger = logging.getLogger("MaO-Bot.antispam")

# ==========================================
# 🛑 Mod Permission Check
# ==========================================
def has_mod_rights(member: discord.Member, default_permission_check) -> bool:
    allowed_roles = getattr(config, 'ALLOWED_MOD_ROLES', [])
    if allowed_roles:
        return any(role.id in allowed_roles for role in member.roles)
    return default_permission_check()

# ==========================================
# 🎛️ UI: Confirmation View
# ==========================================
class ConfirmActionView(discord.ui.View):
    def __init__(self, action_name, target_user, reason, execute_callback, original_view, original_message):
        super().__init__(timeout=getattr(config, 'CONFIRM_TIMEOUT', 15))
        self.action_name = action_name
        self.target_user = target_user
        self.reason = reason
        self.execute_callback = execute_callback
        self.original_view = original_view
        self.original_message = original_message
        self.message: discord.Message | None = None

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
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
# 🎛️ UI: Mod Panel View
# ==========================================
class ModPanelView(discord.ui.View):
    def __init__(self, target_user: discord.Member, reason: str):
        super().__init__(timeout=None)
        self.target_user = target_user
        self.reason = reason

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

        confirm_view = ConfirmActionView(
            action_name, self.target_user, self.reason,
            execute_callback, self, interaction.message
        )
        await interaction.response.send_message(embed=embed, view=confirm_view, ephemeral=True)
        confirm_view.message = await interaction.original_response()

    async def _check_mod(self, interaction: discord.Interaction, perm_check) -> bool:
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
                return await i.response.edit_message(content="❌ หาตัวผู้ใช้ไม่เจอ", embed=None, view=None)
            try:
                await member.timeout(None, reason=f"ปลดโดย {i.user.name}")
                await i.response.edit_message(content=f"✅ ปลด Timeout ให้ {self.target_user.mention} เรียบร้อย!", embed=None, view=None)
            except discord.Forbidden:
                await i.response.edit_message(content="❌ บอทไม่มีสิทธิ์ปลด Timeout ผู้ใช้คนนี้", embed=None, view=None)

        await self.prompt_confirm(interaction, "ปลด Timeout", execute)

    @discord.ui.button(label="แบนถาวร", style=discord.ButtonStyle.danger, emoji="🔨")
    async def ban_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_mod(interaction, lambda: interaction.user.guild_permissions.ban_members):
            return

        async def execute(i: discord.Interaction):
            try:
                await self.target_user.ban(reason=f"แบนด่วนโดย {i.user.name}")
                await i.response.edit_message(content=f"🔨 แบน {self.target_user.mention} เรียบร้อย!", embed=None, view=None)
            except discord.Forbidden:
                await i.response.edit_message(content="❌ บอทไม่มีสิทธิ์แบน (ตรวจสอบลำดับยศ)", embed=None, view=None)

        await self.prompt_confirm(interaction, "แบนถาวร (Ban)", execute)

    @discord.ui.button(label="เตะออก", style=discord.ButtonStyle.primary, emoji="🧹")
    async def kick_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_mod(interaction, lambda: interaction.user.guild_permissions.kick_members):
            return

        async def execute(i: discord.Interaction):
            try:
                await self.target_user.kick(reason=f"เตะด่วนโดย {i.user.name}")
                await i.response.edit_message(content=f"🧹 เตะ {self.target_user.mention} ออกแล้ว!", embed=None, view=None)
            except discord.Forbidden:
                await i.response.edit_message(content="❌ บอทไม่มีสิทธิ์เตะ (ตรวจสอบลำดับยศ)", embed=None, view=None)

        await self.prompt_confirm(interaction, "เตะออก (Kick)", execute)

class AntiSpam(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Anti-Raid Tracker (user_id -> deque of timestamps)
        self.raid_tracker: defaultdict[int, deque] = defaultdict(deque)

    async def punish_user(self, message: discord.Message, target_user: discord.Member, reason: str, trigger_type: str):
        # 1. Download evidence image before deleting message if present
        evidence_file_dm = None
        evidence_file_log = None
        if message.attachments:
            try:
                for att in message.attachments:
                    if att.content_type and att.content_type.startswith('image/'):
                        img_data = await att.read()
                        evidence_file_dm = discord.File(io.BytesIO(img_data), filename="evidence.png")
                        evidence_file_log = discord.File(io.BytesIO(img_data), filename="evidence.png")
                        break
            except Exception as e:
                logger.warning(f"Failed to download evidence image: {e}")

        try:
            await message.delete()
        except discord.Forbidden:
            logger.warning("punish: No permission to delete message in #%s", message.channel.id)
        except discord.NotFound:
            pass
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

        # Public Warning
        public_warning_template = getattr(config, 'PUBLIC_WARNING_MSG', None)
        if public_warning_template:
            try:
                delete_delay = getattr(config, 'WARNING_DELETE_DELAY', 60)
                delete_time_text = f"ใน {delete_delay} วินาที"
                warning_text = public_warning_template.format(
                    user_mention=target_user.mention,
                    owner_id=getattr(self.bot, 'owner_id', ""),
                    delete_time=delete_time_text,
                )
                await message.channel.send(warning_text, delete_after=delete_delay)
            except Exception as e:
                logger.error("punish: Failed to send public warning: %s", e)

        # DM Warning with Evidence
        dm_warning_template = getattr(config, 'DM_WARNING_MSG', None)
        if dm_warning_template:
            try:
                dm_text = dm_warning_template.format(
                    server_name=message.guild.name if message.guild else "เซิร์ฟเวอร์",
                    timeout_days=config.TIMEOUT_DAYS,
                    owner_id=getattr(self.bot, 'owner_id', ""),
                )
                
                embed = discord.Embed(
                    title="🧾 หลักฐานการกระทำผิด (Evidence)",
                    description=f"**สาเหตุที่ถูกลงโทษ:**\n`{reason}`",
                    color=discord.Color.red(),
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )
                if message.content:
                    content_str = message.content[:1000] + "..." if len(message.content) > 1000 else message.content
                    embed.add_field(name="ข้อความที่คุณส่ง:", value=f"```\n{content_str}\n```", inline=False)
                
                if evidence_file_dm:
                    embed.set_image(url="attachment://evidence.png")

                kwargs = {"content": dm_text, "embed": embed}
                if evidence_file_dm:
                    kwargs["file"] = evidence_file_dm
                    
                await target_user.send(**kwargs)
            except discord.Forbidden:
                logger.info("punish: User %s has DMs disabled", target_user.id)
            except Exception as e:
                logger.error("punish: Failed to send DM warning: %s", e)

        # Log Channel with Evidence
        log_channel_id = getattr(self.bot, 'log_channel_id', None)
        if log_channel_id:
            log_channel = self.bot.get_channel(log_channel_id)
            if log_channel:
                embed = discord.Embed(
                    title="🚨 น้อง MaO ทำลายสแปม!",
                    color=discord.Color.red(),
                    timestamp=datetime.datetime.now(datetime.timezone.utc),
                )
                embed.add_field(name="คนร้าย", value=target_user.mention, inline=True)
                embed.add_field(name="ระบบที่จับได้", value=trigger_type, inline=True)
                embed.add_field(name="สาเหตุ", value=f"`{reason}`", inline=False)
                
                if message.content:
                    content_str = message.content[:1000] + "..." if len(message.content) > 1000 else message.content
                    embed.add_field(name="ข้อความที่ส่ง", value=f"```\n{content_str}\n```", inline=False)

                if evidence_file_log:
                    embed.set_image(url="attachment://evidence.png")
                
                view = ModPanelView(target_user, reason)
                kwargs = {"embed": embed, "view": view}
                if evidence_file_log:
                    kwargs["file"] = evidence_file_log
                    
                await log_channel.send(**kwargs)

    def check_raid(self, user_id: int) -> bool:
        """
        Check if user sent > 5 messages in 3 seconds across any channels.
        Returns True if spam detected.
        """
        if not getattr(config, 'ANTI_RAID_ENABLED', False):
            return False

        now = time.monotonic()
        # Custom rule: 5 messages in 3 seconds
        window = 3
        threshold = 5

        history = self.raid_tracker[user_id]

        # Remove expired timestamps
        while history and now - history[0] > window:
            history.popleft()

        history.append(now)

        if len(history) > threshold:
            # Clear history after trigger to avoid spamming the logs
            del self.raid_tracker[user_id]
            logger.warning("🚨 Cross-channel Spam detected: user_id=%s sent > %d messages in %ds", user_id, threshold, window)
            return True

        return False

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not getattr(config, 'AUTO_MOD_ENABLED', True):
            return
        if not message.guild:
            return
            
        ignore_channels = getattr(config, 'IGNORE_CHANNELS', [])
        if message.channel.id in ignore_channels:
            return

        exempt_roles = getattr(config, 'EXEMPT_ROLES', [])
        if exempt_roles and isinstance(message.author, discord.Member):
            if any(role.id in exempt_roles for role in message.author.roles):
                return

        # 1. Check Rate Limit (Cross-channel Spam)
        if self.check_raid(message.author.id):
            await self.punish_user(message, message.author, "ส่งข้อความเร็วเกินไป (> 5 ข้อความใน 3 วิ)", "Anti-Raid (Cross-Channel)")
            return

        # 2. Check attachments vs text
        # If it has attachments but NO text content, completely ignore it.
        if message.attachments and not message.content.strip():
            return
            
        # 3. Check text content
        if message.content:
            min_length = getattr(config, 'IGNORE_SHORT_MESSAGES', 3)
            if len(message.content) > min_length:
                is_text_spam, text_reason = analyze_text(message.content)
                if is_text_spam:
                    await self.punish_user(message, message.author, text_reason, "Auto-Mod (ข้อความ)")
                    return

async def setup(bot):
    await bot.add_cog(AntiSpam(bot))
