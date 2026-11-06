import os
import re
import threading
import collections
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler

import discord
from discord.ext import commands
from discord import app_commands

# --- ВЕБ-СЕРВЕР ДЛЯ RENDER ---
def run_server():
    class SimpleHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot is alive!")
    
    server = HTTPServer(('0.0.0.0', 10000), SimpleHandler)
    server.serve_forever()

# Запускаємо веб-сервер у окремому потоці, щоб Render бачив порт
threading.Thread(target=run_server, daemon=True).start()

# --- ІНІЦІАЛІЗАЦІЯ БОТА ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.moderation = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Збереження історії для Anti-Nuke, Anti-Spam та Ліміту посилань
message_history = collections.defaultdict(list)
link_history = collections.defaultdict(list)
ban_history = collections.defaultdict(list)
channel_delete_history = collections.defaultdict(list)

# --- ВІТАЛЬНА СИСТЕМА ---
WELCOME_CHANNEL_ID = 1566880572029018203

@bot.event
async def on_member_join(member: discord.Member):
    channel = member.guild.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        embed = discord.Embed(
            title=f"Вітаємо на ELITE RP, {member.name}! 👋",
            description=(
                f"Привіт, {member.mention}!\n\n"
                f"**Раді бачити тебе на нашому сервері!** 🎉\n"
                f"Будь ласка, обов'язково ознайомся з правилами сервера перед початком гри."
            ),
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="ELITE RP | Система безпеки")
        await channel.send(content=f"{member.mention}", embed=embed)

# --- ПОДІЇ БОТА ---
@bot.event
async def on_ready():
    print(f'Бот успішно увійшов в систему як {bot.user} і охороняє сервер!')
    try:
        synced = await bot.tree.sync()
        print(f'Синхронізовано слеш-команд: {len(synced)}')
    except Exception as e:
        print(f'Помилка синхронізації команд: {e}')

@bot.event
async def on_message(message):
    if message.author.bot or message.guild is None:
        return

    author_id = message.author.id
    now = datetime.now()
    perms = message.author.guild_permissions

    # Перевірка чи є в користувача адміністративні/модераторські права
    is_admin_or_mod = (
        perms.administrator or 
        perms.manage_messages or 
        perms.kick_members or 
        perms.ban_members
    )

    url_pattern = r'(https?://[^\s]+|www\.[^\s]+|discord\.gg/[^\s]+)'
    has_link = bool(re.search(url_pattern, message.content))

    # --- ОБРОБКА ПОСИЛАНЬ ---
    if has_link:
        if not is_admin_or_mod:
            # Звичайним користувачам заборонено будь-які посилання
            try:
                await message.delete()
                await message.channel.send(f'{message.author.mention}, посилання суворо заборонені на сервері!', delete_after=5)
                return
            except Exception:
                pass
        else:
            # Для адміністрації: ліміт 3 посилання на 1 хвилину (60 сек)
            link_history[author_id].append(now)
            link_history[author_id] = [t for t in link_history[author_id] if now - t < timedelta(seconds=60)]

            if len(link_history[author_id]) > 3:
                try:
                    await message.delete()
                    await message.channel.send(
                        f'⚠️ {message.author.mention}, ліміт посилань перевищено! (Максимум 3 посилання на 1 хвилину)',
                        delete_after=5
                    )
                    return
                except Exception:
                    pass

    # --- ЗАХИСТ ВІД СПАМУ (для звичайних користувачів) ---
    if not is_admin_or_mod:
        message_history[author_id].append(now)
        message_history[author_id] = [t for t in message_history[author_id] if now - t < timedelta(seconds=4)]

        if len(message_history[author_id]) > 5:
            try:
                await message.delete()
                await message.author.timeout(timedelta(minutes=5), reason="Автоматичний захист від спаму")
                await message.channel.send(f'⚠️ {message.author.mention} отримав мут на 5 хвилин за спам!', delete_after=5)
            except Exception:
                pass

@bot.event
async def on_member_ban(guild, user):
    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
        executor = entry.user
        if executor.bot or executor.id == guild.owner_id:
            return

        now = datetime.now()
        ban_history[executor.id].append(now)
        ban_history[executor.id] = [t for t in ban_history[executor.id] if now - t < timedelta(seconds=10)]

        if len(ban_history[executor.id]) > 3:
            try:
                await guild.ban(executor, reason="Anti-Nuke: Спроба масового бану учасників")
                owner = guild.owner
                if owner:
                    await owner.send(f"🚨 **УВАГА!** Користувач `{executor}` масово банив учасників і був заблокований ботом.")
            except Exception as e:
                print(f"Помилка захисту: {e}")

@bot.event
async def on_guild_channel_delete(channel):
    guild = channel.guild
    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
        executor = entry.user
        if executor.bot or executor.id == guild.owner_id:
            return

        now = datetime.now()
        channel_delete_history[executor.id].append(now)
        channel_delete_history[executor.id] = [t for t in channel_delete_history[executor.id] if now - t < timedelta(seconds=10)]

        if len(channel_delete_history[executor.id]) > 2:
            try:
                await guild.ban(executor, reason="Anti-Nuke: Масове видалення каналів")
                owner = guild.owner
                if owner:
                    await owner.send(f"🚨 **УВАГА!** Користувач `{executor}` намагався видалити канали та був заблокований!")
            except Exception as e:
                print(f"Помилка захисту каналів: {e}")

# --- СЛЕШ-КОМАНДИ МОДЕРАЦІЇ ТА ОГОЛОШЕНЬ ---
@bot.tree.command(name="help", description="Показати список команд модерації та безпеки")
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(title="📜 Меню команд модерації та безпеки", color=discord.Color.blue())
    embed.add_field(name="`/clear [кількість]`", value="Очистити чат від повідомлень", inline=False)
    embed.add_field(name="`/mute [@користувач]`", value="Дати мут користувачу на 10 хвилин", inline=False)
    embed.add_field(name="`/unmute [@користувач]`", value="Зняти мут з користувача", inline=False)
    embed.add_field(name="`/kick [@користувач]`", value="Вигнати користувача з сервера", inline=False)
    embed.add_field(name="`/ban [@користувач]`", value="Забанити користувача на сервері", inline=False)
    embed.add_field(name="`/say [канал] [заголовок] [текст]`", value="Надіслати красиве оголошення від імені бота", inline=False)
    embed.set_footer(text="ELITE RP | Система безпеки")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="clear", description="Очистити чат від повідомлень")
@app_commands.checks.has_permissions(manage_messages=True)
async def slash_clear(interaction: discord.Interaction, amount: int = 5):
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"🧹 Успішно видалено {len(deleted)} повідомлень!", ephemeral=True)

@bot.tree.command(name="mute", description="Видати мут користувачу на 10 хвилин")
@app_commands.checks.has_permissions(moderate_members=True)
async def slash_mute(interaction: discord.Interaction, member: discord.Member, reason: str = "Порушення правил"):
    try:
        await member.timeout(timedelta(minutes=10), reason=reason)
        await interaction.response.send_message(f"🔇 Користувач {member.mention} отримав мут на 10 хвилин.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Не вдалося видати мут: {e}", ephemeral=True)

@bot.tree.command(name="unmute", description="Зняти мут з користувача")
@app_commands.checks.has_permissions(moderate_members=True)
async def slash_unmute(interaction: discord.Interaction, member: discord.Member):
    try:
        await member.timeout(None)
        await interaction.response.send_message(f"🔊 З {member.mention} знято мут.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Помилка: {e}", ephemeral=True)

@bot.tree.command(name="kick", description="Вигнати користувача з сервера")
@app_commands.checks.has_permissions(kick_members=True)
async def slash_kick(interaction: discord.Interaction, member: discord.Member, reason: str = "Не вказано"):
    try:
        await member.kick(reason=reason)
        await interaction.response.send_message(f"👢 Користувача {member.mention} вигнано з сервера.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Помилка: {e}", ephemeral=True)

@bot.tree.command(name="ban", description="Забанити користувача на сервері")
@app_commands.checks.has_permissions(ban_members=True)
async def slash_ban(interaction: discord.Interaction, member: discord.Member, reason: str = "Не вказано"):
    try:
        await member.ban(reason=reason)
        await interaction.response.send_message(f"🔨 Користувача {member.mention} забанено на сервері.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Помилка: {e}", ephemeral=True)

@bot.tree.command(name="say", description="Надіслати оголошення від імені бота")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    channel="Канал для відправки",
    title="Заголовок оголошення",
    text="Основний текст оголошення",
    ping_everyone="Чи потрібно згадувати @everyone? (True/False)",
    image_url="Посилання на картинку (необов'язково)"
)
async def slash_say(
    interaction: discord.Interaction, 
    channel: discord.TextChannel, 
    title: str, 
    text: str,
    ping_everyone: bool = False,
    image_url: str = None
):
    embed = discord.Embed(
        title=title,
        description=text,
        color=discord.Color.blue()
    )
    embed.set_footer(text="ELITE RP | Офіційне повідомлення")
    
    if image_url:
        embed.set_image(url=image_url)
    
    content_text = "@everyone" if ping_everyone else None
    
    try:
        await channel.send(content=content_text, embed=embed)
        await interaction.response.send_message("✅ Оголошення успішно надіслано!", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Помилка при відправці: {e}", ephemeral=True)

# --- ЗАПУСК БОТА ---
if __name__ == '__main__':
    TOKEN = os.getenv("DISCORD_TOKEN")
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("Помилка: Не знайдено змінну середовища DISCORD_TOKEN!")
