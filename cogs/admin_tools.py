import discord
from discord import app_commands
from discord.ext import commands
import logging

from core import database
import config

logger = logging.getLogger("MaO-Bot.admin_tools")

# Helper to check mod rights
def is_mod():
    def predicate(interaction: discord.Interaction) -> bool:
        allowed_roles = getattr(config, 'ALLOWED_MOD_ROLES', [])
        if allowed_roles:
            if isinstance(interaction.user, discord.Member):
                return any(role.id in allowed_roles for role in interaction.user.roles)
            return False
        return interaction.user.guild_permissions.administrator
    return app_commands.check(predicate)

class AdminTools(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="addword", description="เพิ่มคำ/ลิงก์เข้า Blacklist (เฉพาะ Mod)")
    @app_commands.describe(word="คำหรือลิงก์ที่ต้องการแบน", category="ประเภท (domain หรือ phrase)")
    @app_commands.choices(category=[
        app_commands.Choice(name="โดเมน/ลิงก์", value="domain"),
        app_commands.Choice(name="วลี/ประโยค", value="phrase"),
    ])
    @is_mod()
    async def add_word(self, interaction: discord.Interaction, word: str, category: str):
        if category == "domain":
            if word not in database.BLACK_LISTED_DOMAINS:
                database.BLACK_LISTED_DOMAINS.append(word)
                database.save_blacklist()
                await interaction.response.send_message(f"✅ เพิ่มโดเมน `{word}` ลงใน Blacklist เรียบร้อย", ephemeral=True)
            else:
                await interaction.response.send_message(f"⚠️ โดเมน `{word}` มีอยู่ใน Blacklist แล้ว", ephemeral=True)
        else:
            if word not in database.BLACK_LISTED_SPAM_PHRASES:
                database.BLACK_LISTED_SPAM_PHRASES.append(word)
                database.save_blacklist()
                await interaction.response.send_message(f"✅ เพิ่มวลี `{word}` ลงใน Blacklist เรียบร้อย", ephemeral=True)
            else:
                await interaction.response.send_message(f"⚠️ วลี `{word}` มีอยู่ใน Blacklist แล้ว", ephemeral=True)

    @app_commands.command(name="removeword", description="ลบคำ/ลิงก์ออกจาก Blacklist (เฉพาะ Mod)")
    @app_commands.describe(word="คำหรือลิงก์ที่ต้องการลบ", category="ประเภท (domain หรือ phrase)")
    @app_commands.choices(category=[
        app_commands.Choice(name="โดเมน/ลิงก์", value="domain"),
        app_commands.Choice(name="วลี/ประโยค", value="phrase"),
    ])
    @is_mod()
    async def remove_word(self, interaction: discord.Interaction, word: str, category: str):
        if category == "domain":
            if word in database.BLACK_LISTED_DOMAINS:
                database.BLACK_LISTED_DOMAINS.remove(word)
                database.save_blacklist()
                await interaction.response.send_message(f"✅ ลบโดเมน `{word}` ออกจาก Blacklist เรียบร้อย", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ ไม่พบโดเมน `{word}` ใน Blacklist", ephemeral=True)
        else:
            if word in database.BLACK_LISTED_SPAM_PHRASES:
                database.BLACK_LISTED_SPAM_PHRASES.remove(word)
                database.save_blacklist()
                await interaction.response.send_message(f"✅ ลบวลี `{word}` ออกจาก Blacklist เรียบร้อย", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ ไม่พบวลี `{word}` ใน Blacklist", ephemeral=True)

    @commands.command(name="sync")
    async def sync_commands(self, ctx: commands.Context):
        """ซิงค์ Slash Commands (เฉพาะคนที่มีสิทธิ์แอดมินบอท) พิมพ์ !sync"""
        # ให้เช็คว่าคนพิมพ์มีสิทธิ์ตั้งค่าเซิร์ฟเวอร์ไหม ป้องกันคนนอกกดมั่ว
        if not ctx.author.guild_permissions.administrator:
            return await ctx.send("❌ เฉพาะแอดมินเท่านั้นที่สามารถซิงค์คำสั่งได้")
            
        msg = await ctx.send("⏳ กำลังซิงค์คำสั่ง กรุณารอสักครู่...")
        try:
            synced = await self.bot.tree.sync()
            await msg.edit(content=f"✅ ซิงค์ Slash Commands สำเร็จจำนวน {len(synced)} คำสั่ง!")
            logger.info(f"Synced {len(synced)} commands.")
        except Exception as e:
            await msg.edit(content=f"❌ เกิดข้อผิดพลาด: {e}")
            logger.error(f"Failed to sync commands: {e}")

    @app_commands.command(name="test_spam_punish", description="[Test] ทดลองลงโทษฐานพิมพ์สแปม (เฉพาะ Mod)")
    @app_commands.describe(user="บัญชีเป้าหมายที่จะทดสอบ (เช่น รหัสรอง)")
    @is_mod()
    async def test_spam_punish(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.send_message(f"เริ่มการทดสอบลงโทษสแปมกับ {user.mention}...", ephemeral=True)
        # ส่งข้อความจำลองเข้าไปในห้องเพื่อส่งให้ punish_user ทำการลบ
        mock_msg = await interaction.channel.send(f"[Test Message] ข้อความจำลองจากระบบทดสอบ (ส่งโดยแอดมินเพื่อทดสอบการลงโทษ {user.mention})")
        
        antispam_cog = self.bot.get_cog("AntiSpam")
        if antispam_cog:
            await antispam_cog.punish_user(mock_msg, user, "ข้อความทดสอบจากคำสั่ง /test_spam_punish", "Auto-Mod (การทดสอบ)")
        else:
            await interaction.followup.send("❌ ไม่พบระบบ AntiSpam ในบอท", ephemeral=True)

    @app_commands.command(name="test_raid_punish", description="[Test] ทดลองลงโทษฐานฟลัดห้อง (เฉพาะ Mod)")
    @app_commands.describe(user="บัญชีเป้าหมายที่จะทดสอบ (เช่น รหัสรอง)")
    @is_mod()
    async def test_raid_punish(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.send_message(f"เริ่มการทดสอบลงโทษ Anti-Raid กับ {user.mention}...", ephemeral=True)
        mock_msg = await interaction.channel.send(f"[Test Message] ข้อความจำลองจากระบบทดสอบ (ส่งโดยแอดมินเพื่อทดสอบการลงโทษ {user.mention})")
        
        antispam_cog = self.bot.get_cog("AntiSpam")
        if antispam_cog:
            await antispam_cog.punish_user(mock_msg, user, "ฟลัดข้อความข้ามห้อง (ส่งสแปมกระจายหลายห้อง)", "Anti-Raid (การทดสอบ)")
        else:
            await interaction.followup.send("❌ ไม่พบระบบ AntiSpam ในบอท", ephemeral=True)

    @app_commands.command(name="test_text", description="[Test] ทดสอบเช็คข้อความว่าติดสแกนไหม โดยไม่แบนใคร (เฉพาะ Mod)")
    @app_commands.describe(text="ข้อความที่ต้องการทดสอบ")
    @is_mod()
    async def test_text(self, interaction: discord.Interaction, text: str):
        from utils.scanner import analyze_text
        is_spam, reason = analyze_text(text)
        if is_spam:
            await interaction.response.send_message(f"🚨 **ตรวจพบสแปม!** (คำสั่งทดสอบ)\n**สาเหตุ:** `{reason}`\n**ข้อความ:** {text}", ephemeral=True)
        else:
            await interaction.response.send_message(f"✅ **ปลอดภัย!** ข้อความนี้ไม่ติดเงื่อนไขสแปม\n**ข้อความ:** {text}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(AdminTools(bot))

