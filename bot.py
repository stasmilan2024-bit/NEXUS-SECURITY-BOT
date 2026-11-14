import os
import re
import json
import random
import asyncio
import threading
import collections
from datetime import datetime, timedelta, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler

import discord
from discord.ext import commands, tasks
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

threading.Thread(target=run_server, daemon=True).start()

# --- ІНІЦІАЛІЗАЦІЯ БОТА ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.moderation = True
intents.voice_states = True
intents.webhooks = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --- ЗБЕРЕЖЕННЯ ТА ЗАВАНТАЖЕННЯ ДАНИХ (JSON) ---
DATA_FILE = "data.json"

user_messages = collections.defaultdict(int)
user_voice_seconds = collections.defaultdict(int)
user_coins = collections.defaultdict(int)
user_exp = collections.defaultdict(int)
user_levels = collections.defaultdict(lambda: 1)

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in data.get("messages", {}).items():
                    user_messages[int(k)] = v
                for k, v in data.get("voice", {}).items():
                    user_voice_seconds[int(k)] = v
                for k, v in data.get("coins", {}).items():
                    user_coins[int(k)] = v
                for k, v in data.get("exp", {}).items():
                    user_exp[int(k)] = v
                for k, v in data.get("levels", {}).items():
                    user_levels[int(k)] = v
            print("💾 Дані успішно завантажено з data.json!")
        except Exception as e:
            print(f"Помилка читання data.json: {e}")

def save_data():
    try:
        data = {
            "messages": {str(k): v for k, v in user_messages.items()},
            "voice": {str(k): v for k, v in user_voice_seconds.items()},
            "coins": {str(k): v for k, v in user_coins.items()},
            "exp": {str(k): v for k, v in user_exp.items()},
            "levels": {str(k): v for k, v in user_levels.items()}
        }
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Помилка збереження у data.json: {e}")

load_data()

message_history = collections.defaultdict(list)
ban_history = collections.defaultdict(list)
channel_delete_history = collections.defaultdict(list)
role_delete_history = collections.defaultdict(list)
last_user_messages = collections.defaultdict(list)
admin_spam_warnings = collections.defaultdict(int)
last_daily_claim = {}

# --- НАЛАШТУВАННЯ БЕЗПЕКИ (ANTI-TWINK) ---
MIN_ACCOUNT_AGE_DAYS = 7          # Мінімальний вік акаунта в днях (фільтр твінків)

# --- ID КАНАЛІВ ТА НАЛАШТУВАННЯ ---
WELCOME_CHANNEL_ID = 1566880572029018203
STATS_CHANNEL_ID = 1568373943138787349  
RANK_CHANNEL_ID = 1405600879587098644      
LOG_CHANNEL_ID = 1569067419740278936      
ADMIN_QUESTIONS_CHANNEL_ID = 1570510766186958858  
TICKET_PANEL_CHANNEL_ID = 1570511794190028960    

CREATE_VOICE_CHANNEL_ID = 1405601386674130965
PRIVATE_ROOMS_CATEGORY_ID = 1405600664704254103

active_private_channels = {}

# --- ПОСИЛАННЯ НА СОЦМЕРЕЖІ ---
URL_SITE = "https://elite-rp.qniks.me"                     
URL_FORUM = "http://eliterpforum.sytes.net/index.php"       
URL_TG_CHANNEL = "🚧 В розробці"                            
URL_TG_CHAT = "🚧 В розробці"                               
URL_TG_BOT = "🚧 В розробці"                                
URL_TIKTOK = "https://www.tiktok.com/@your_tiktok"          
URL_INSTAGRAM = "https://www.instagram.com/your_instagram"  

# --- ID РОЛЕЙ АКТИВНОСТІ ---
ROLE_ACTIVE_ID = 1405600607427100854      
ROLE_MASTER_ID = 1405600608576213002      
ROLE_INCREDIBLE_ID = 1405600522010103949  
ROLE_MOST_ACTIVE_ID = 1405600525826920568 

SHOP_ITEMS = {
    "1": {"name": "🎖️ Роль 'Активний'", "price": 150, "role_id": ROLE_ACTIVE_ID},
    "2": {"name": "💬 Роль 'Майстер'", "price": 300, "role_id": ROLE_MASTER_ID},
    "3": {"name": "🔥 Роль 'Неймовірний'", "price": 500, "role_id": ROLE_INCREDIBLE_ID},
    "4": {"name": "👑 Роль 'Найактивніший'", "price": 1000, "role_id": ROLE_MOST_ACTIVE_ID}
}

stats_message_id = None


def format_voice_time(total_seconds):
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    if hours > 0:
        return f"{hours} год. {minutes} хв. {seconds} сек."
    elif minutes > 0:
        return f"{minutes} хв. {seconds} сек."
    else:
        return f"{seconds} сек."


def get_level_and_exp(exp_total):
    level = 1
    while level < 500:
        exp_needed = level * 150
        if exp_total >= exp_needed:
            exp_total -= exp_needed
            level += 1
        else:
            break
    
    if level >= 500:
        level = 500
        exp_needed = 500 * 150
        exp_total = exp_needed

    current_level_exp_max = level * 150
    return level, exp_total, current_level_exp_max


async def check_and_update_level(member, guild):
    user_id = member.id
    total_exp = user_exp[user_id]
    new_level, _, _ = get_level_and_exp(total_exp)
    
    if user_levels[user_id] < new_level:
        user_levels[user_id] = new_level
        save_data()

        rank_channel = guild.get_channel(RANK_CHANNEL_ID)
        if rank_channel:
            embed = discord.Embed(
                title="🎉 Підвищення рівня!",
                description=f"Вітаємо, {member.mention}! Ви досягли **{new_level} рівня** на сервері! 🌟",
                color=discord.Color.gold()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            await rank_channel.send(embed=embed, delete_after=120)

        await send_log(guild, "Підвищення рівня", f"Користувач {member.mention} підвищив рівень до **{new_level}**.", discord.Color.gold())


async def send_log(guild, title, description, color=discord.Color.blue(), ping_owner=False):
    if not guild:
        return
    channel = guild.get_channel(LOG_CHANNEL_ID)
    if channel:
        embed = discord.Embed(title=f"🛡️ ЛОГ ДІЙ | {title}", description=description, color=color, timestamp=datetime.now(timezone.utc))
        content = guild.owner.mention if (ping_owner and guild.owner) else None
        try:
            await channel.send(content=content, embed=embed)
        except Exception as e:
            print(f"Помилка відправки логу: {e}")


async def punish_rogue_admin(guild, executor, reason):
    if not executor or executor.bot or executor.id == guild.owner_id:
        return
    try:
        member = guild.get_member(executor.id)
        if member:
            roles_to_remove = [r for r in member.roles if r != guild.default_role and r.is_assignable()]
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason=reason)
        await guild.ban(executor, reason=reason)
        await send_log(
            guild,
            "🚨 CRITICAL SECURITY | Блокування адміністратора",
            f"**Порушник:** `{executor}` (`{executor.id}`)\n**Причина:** {reason}\n**Дія:** Усі ролі знято, акаунт заблоковано.",
            discord.Color.dark_red(),
            ping_owner=True
        )
    except Exception as e:
        print(f"Помилка нейтралізації порушника: {e}")


# --- 🎫 СИСТЕМА ЗВЕРНЕНЬ ТА ПІДТРИМКИ ---

class AdminReplyModal(discord.ui.Modal, title="Відповідь адміністрації"):
    reply_text = discord.ui.TextInput(
        label="Ваша відповідь гравцю",
        style=discord.TextStyle.paragraph,
        placeholder="Напишіть детальну відповідь на запитання...",
        required=True,
        max_length=1000
    )

    def __init__(self, target_user_id: int, question_text: str):
        super().__init__()
        self.target_user_id = target_user_id
        self.question_text = question_text

    async def on_submit(self, interaction: discord.Interaction):
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.add_field(
            name=f"✅ Відповідь від {interaction.user.display_name}:",
            value=self.reply_text.value,
            inline=False
        )
        embed.set_footer(text="Статус: Відповідь надано")

        await interaction.message.edit(embed=embed, view=None)
        await interaction.response.send_message("✅ Відповідь опубліковано!", ephemeral=True)

        target_member = interaction.guild.get_member(self.target_user_id)
        if target_member:
            try:
                dm_embed = discord.Embed(
                    title="📩 Відповідь на ваше звернення | ELITE RP",
                    description=f"**Ваше питання:**\n{self.question_text}\n\n**Відповідь адміністратора ({interaction.user.display_name}):**\n{self.reply_text.value}",
                    color=discord.Color.green()
                )
                await target_member.send(embed=dm_embed)
            except Exception:
                pass

        await send_log(interaction.guild, "Відповідь на тікет", f"Адміністратор {interaction.user.mention} відповів на звернення гравця <@{self.target_user_id}>.", discord.Color.green())


class AdminReplyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="💬 Відповісти (Для Адміністрації)", style=discord.ButtonStyle.primary, custom_id="admin_reply_ticket_btn")
    async def reply_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        perms = interaction.user.guild_permissions
        if not (perms.administrator or perms.manage_messages or perms.kick_members):
            await interaction.response.send_message("❌ Відповідати на звернення може лише адміністрація!", ephemeral=True)
            return

        embed = interaction.message.embeds[0]
        footer_text = embed.footer.text or ""
        user_id = 0
        if "ID:" in footer_text:
            try:
                user_id = int(footer_text.split("ID:")[1].strip())
            except Exception:
                pass
        
        question_text = embed.description or ""
        await interaction.response.send_modal(AdminReplyModal(user_id, question_text))


class AskQuestionModal(discord.ui.Modal, title="Нове питання до адміністрації"):
    question = discord.ui.TextInput(
        label="Опишіть ваше питання або проблему",
        style=discord.TextStyle.paragraph,
        placeholder="Напишіть тут ваше звернення...",
        required=True,
        max_length=1000
    )

    async def on_submit(self, interaction: discord.Interaction):
        admin_channel = interaction.guild.get_channel(ADMIN_QUESTIONS_CHANNEL_ID)
        if not admin_channel:
            await interaction.response.send_message("❌ Канал для адміністраторів не знайдено.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"🎫 Звернення від {interaction.user.display_name}",
            description=f"**Питання:**\n{self.question.value}",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.add_field(name="👤 Автор", value=interaction.user.mention, inline=True)
        embed.set_footer(text=f"Очікує відповіді | ID: {interaction.user.id}")

        await admin_channel.send(embed=embed, view=AdminReplyView())
        await interaction.response.send_message("✅ Ваше питання успішно надіслано адміністрації!", ephemeral=True)
        await send_log(interaction.guild, "Нове звернення", f"Користувач {interaction.user.mention} залишив питання для адміністрації.", discord.Color.orange())


class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎟️ Задати питання", style=discord.ButtonStyle.success, custom_id="ask_ticket_btn")
    async def ask_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AskQuestionModal())


async def setup_ticket_panel():
    panel_channel = bot.get_channel(TICKET_PANEL_CHANNEL_ID)
    if not panel_channel:
        return

    embed = discord.Embed(
        title="🎫 ПІДТРИМКА ТА ЗВЕРНЕННЯ | ELITE RP",
        description="Маєте запитання до адміністрації або потрібна допомога?\nНатисніть кнопку **«Задати питання»** нижче, заповніть форму, і ваше звернення надійде адміністраторам.",
        color=discord.Color.gold()
    )
    embed.set_footer(text="ELITE RP | Панель звернень")

    try:
        pins = await panel_channel.pins()
        for pin in pins:
            if pin.author == bot.user and pin.embeds and "ПІДТРИМКА ТА ЗВЕРНЕННЯ" in (pin.embeds[0].title or ""):
                await pin.edit(embed=embed, view=TicketPanelView())
                return
        
        msg = await panel_channel.send(embed=embed, view=TicketPanelView())
        await msg.pin()
    except Exception as e:
        print(f"Помилка закріплення панелі звернень: {e}")


# --- 🛡️ ЖОРСТКИЙ ANTI-BOT ТА ANTI-TWINK ЩИТ (ВХІД НА СЕРВЕР) ---

@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    now = datetime.now(timezone.utc)

    # 1. ЖОРСТКИЙ ANTI-BOT: Якщо додано стороннього бота (не Власником)
    if member.bot:
        is_owner_action = False
        try:
            async for entry in guild.audit_logs(limit=3, action=discord.AuditLogAction.bot_add):
                if entry.target and entry.target.id == member.id:
                    if entry.user.id != guild.owner_id:
                        # Миттєвий бан бота і того, хто його запросив
                        try:
                            await member.ban(reason="Anti-Bot: Сторонніх ботів заборонено!")
                        except Exception:
                            pass
                        
                        try:
                            rogue_admin = guild.get_member(entry.user.id)
                            if rogue_admin:
                                roles_to_remove = [r for r in rogue_admin.roles if r != guild.default_role and r.is_assignable()]
                                if roles_to_remove:
                                    await rogue_admin.remove_roles(*roles_to_remove, reason="Додав стороннього бота")
                                await guild.ban(rogue_admin, reason="Додав стороннього бота на сервер")
                        except Exception:
                            pass

                        await send_log(
                            guild,
                            "🚨 ANTI-BOT ЗАХИСТ",
                            f"**Чужий бот:** {member.mention} (`{member.id}`)\n**Кого задіяли:** <@{entry.user.id}>\n**Дія:** Обох миттєво заблоковано!",
                            discord.Color.dark_red(),
                            ping_owner=True
                        )
                        return
                    else:
                        is_owner_action = True
                        break
        except Exception as e:
            print(f"Помилка перевірки аудит-логів бота: {e}")

        if not is_owner_action:
            try:
                await member.ban(reason="Anti-Bot: Несанкціонований бот")
                return
            except Exception:
                pass

    # 2. ФІЛЬТР ВІКУ АКАУНТА (Анти-Твінк): Менше ніж 7 днів — кік
    account_age = now - member.created_at
    if account_age < timedelta(days=MIN_ACCOUNT_AGE_DAYS):
        days_old = account_age.days
        try:
            await member.send(
                f"🛡️ **Система безпеки ELITE RP:**\nВаш акаунт створено занадто недавно ({days_old} дн.). "
                f"Для захисту від твінків мінімальний вік акаунта становить **{MIN_ACCOUNT_AGE_DAYS} днів**."
            )
        except Exception:
            pass
        try:
            await member.kick(reason=f"Anti-Twink: Вік акаунта {days_old} дн. (мін. {MIN_ACCOUNT_AGE_DAYS} дн.)")
            await send_log(
                guild,
                "🕵️ Anti-Twink Блокування",
                f"Користувача `{member}` (`{member.id}`) не допущено на сервер.\n**Вік акаунта:** {days_old} дн. (поріг: {MIN_ACCOUNT_AGE_DAYS} дн.)",
                discord.Color.orange()
            )
        except Exception as e:
            print(f"Помилка Anti-Twink: {e}")
        return

    # Якщо перевірки пройдено успішно
    channel = guild.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        embed = discord.Embed(
            title=f"Вітаємо на ELITE RP, {member.name}! 👋",
            description=f"Привіт, {member.mention}!\n\n**Раді бачити тебе на нашому сервері!** 🎉",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await channel.send(embed=embed)
    await send_log(guild, "Новий учасник", f"Користувач {member.mention} (`{member.name}`) пройшов перевірку безпеки та приєднався.", discord.Color.green())


# --- 🧬 КОНТРОЛЬ ЦІЛІСНОСТІ ПРАВ, РОЛЕЙ ТА ВЕБХУКІВ ---

@bot.event
async def on_guild_role_update(before: discord.Role, after: discord.Role):
    guild = after.guild
    dangerous_perms = [
        after.permissions.administrator,
        after.permissions.manage_guild,
        after.permissions.manage_roles,
        after.permissions.ban_members,
        after.permissions.manage_webhooks,
        after.permissions.manage_channels
    ]
    before_dangerous = [
        before.permissions.administrator,
        before.permissions.manage_guild,
        before.permissions.manage_roles,
        before.permissions.ban_members,
        before.permissions.manage_webhooks,
        before.permissions.manage_channels
    ]

    if any(dangerous_perms) and not any(before_dangerous):
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.role_update):
            if entry.target.id == after.id and entry.user.id != guild.owner_id and not entry.user.bot:
                try:
                    await after.edit(permissions=before.permissions, reason="Anti-Privilege Escalation: Відкат небезпечних прав")
                except Exception:
                    pass
                await punish_rogue_admin(guild, entry.user, f"Спроба видати небезпечні права ролі `{after.name}`")


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    guild = after.guild

    if before.roles != after.roles:
        added_roles = [r for r in after.roles if r not in before.roles]
        removed_roles = [r for r in before.roles if r not in after.roles]

        for role in added_roles:
            if role.permissions.administrator or role.permissions.manage_guild:
                async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.member_role_update):
                    if entry.target.id == after.id and entry.user.id != guild.owner_id and not entry.user.bot:
                        try:
                            await after.remove_roles(role, reason="Anti-Admin Grant: Несанкціонована видача адмін-ролі")
                        except Exception:
                            pass
                        await punish_rogue_admin(guild, entry.user, f"Спроба видати адмін-роль `{role.name}` гравцю `{after}`")
                        return

            await send_log(guild, "Видача ролі", f"Користувачу {after.mention} видано роль **{role.name}**.", discord.Color.green())
        
        for role in removed_roles:
            await send_log(guild, "Зняття ролі", f"З користувача {after.mention} знято роль **{role.name}**.", discord.Color.red())

    if before.nick != after.nick:
        old_nick = before.nick or before.name
        new_nick = after.nick or after.name
        await send_log(guild, "Зміна нікнейма", f"Користувач {after.mention} змінив нікнейм:\nСтарий: `{old_nick}`\nНовий: `{new_nick}`", discord.Color.purple())


@bot.event
async def on_webhooks_update(channel):
    guild = channel.guild
    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.webhook_create):
        if entry.user.id != guild.owner_id and not entry.user.bot:
            try:
                webhooks = await channel.webhooks()
                for wh in webhooks:
                    if wh.id == entry.target.id:
                        await wh.delete(reason="Anti-Webhook Trap: Заборонено створювати вебхуки")
            except Exception:
                pass
            await punish_rogue_admin(guild, entry.user, f"Спроба створити вебхук у каналі `#{channel.name}`")


# --- СИСТЕМА ЛОГУВАННЯ ТА ВОЙСІВ ---

@bot.event
async def on_message_delete(message):
    if message.author.bot or message.guild is None:
        return
    
    if message.content.startswith("!") or message.content.startswith("/"):
        return

    author_id = message.author.id
    if user_messages[author_id] > 0:
        user_messages[author_id] -= 1
        save_data()

    content = message.content if message.content else "*[Медіафайл / Вкладення]*"
    desc = f"**Автор:** {message.author.mention}\n**Канал:** {message.channel.mention}\n**Повідомлення:** {content}"
    await send_log(message.guild, "Видалення повідомлення", desc, discord.Color.orange())


@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return

    guild = member.guild

    if after.channel and after.channel.id == CREATE_VOICE_CHANNEL_ID:
        category = guild.get_channel(PRIVATE_ROOMS_CATEGORY_ID)
        cat_obj = category if isinstance(category, discord.CategoryChannel) else None
        
        room_name = f"🔊 | Кімната {member.name}"
        try:
            new_channel = await guild.create_voice_channel(name=room_name, category=cat_obj)
            await new_channel.set_permissions(member, manage_channels=True, move_members=True, connect=True)
            await member.move_to(new_channel)
            active_private_channels[new_channel.id] = member.id
            await send_log(guild, "Створення кімнати", f"Користувач {member.mention} створив приватний войс: **{room_name}**", discord.Color.green())
        except Exception as e:
            print(f"Помилка створення приватної кімнати: {e}")

    if before.channel != after.channel:
        if before.channel is None and after.channel is not None:
            await send_log(guild, "Вхід у войс", f"Користувач {member.mention} зайшов у голосовий канал **{after.channel.name}**.", discord.Color.blue())
        elif before.channel is not None and after.channel is None:
            await send_log(guild, "Вихід з войсу", f"Користувач {member.mention} вийшов із голосового каналу **{before.channel.name}**.", discord.Color.blue())
        elif before.channel is not None and after.channel is not None:
            await send_log(guild, "Переміщення у войсі", f"Користувач {member.mention} перейшов з **{before.channel.name}** у **{after.channel.name}**.", discord.Color.blue())

    if before.channel and before.channel.id in active_private_channels:
        if len(before.channel.members) == 0:
            try:
                ch_name = before.channel.name
                ch_id = before.channel.id
                await before.channel.delete()
                active_private_channels.pop(ch_id, None)
                await send_log(before.guild, "Видалення кімнати", f"Порожню приватну кімнату **{ch_name}** було автоматично видалено.", discord.Color.orange())
            except Exception as e:
                print(f"Помилка видалення приватної кімнати: {e}")


# --- 🔊 КОМАНДИ КЕРУВАННЯ ПРИВАТНИМИ КІМНАТАМИ ---

def is_room_owner():
    async def predicate(ctx):
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("❌ Ви повинні перебувати у своїй приватній кімнаті!", delete_after=5)
            return False
        channel_id = ctx.author.voice.channel.id
        if channel_id not in active_private_channels or active_private_channels[channel_id] != ctx.author.id:
            await ctx.send("❌ Ви не є власником цієї приватної кімнати!", delete_after=5)
            return False
        return True
    return commands.check(predicate)

@bot.command(name="lock", aliases=["закрити"])
@is_room_owner()
async def lock_room(ctx):
    try:
        await ctx.message.delete()
    except Exception:
        pass
    channel = ctx.author.voice.channel
    await channel.set_permissions(ctx.guild.default_role, connect=False)
    await ctx.send(f"🔒 {ctx.author.mention} закрив кімнату **{channel.name}** для входу!", delete_after=10)

@bot.command(name="unlock", aliases=["відкрити"])
@is_room_owner()
async def unlock_room(ctx):
    try:
        await ctx.message.delete()
    except Exception:
        pass
    channel = ctx.author.voice.channel
    await channel.set_permissions(ctx.guild.default_role, connect=None)
    await ctx.send(f"🔓 {ctx.author.mention} відкрив кімнату **{channel.name}**!", delete_after=10)

@bot.command(name="rename", aliases=["назва"])
@is_room_owner()
async def rename_room(ctx, *, new_name: str = None):
    try:
        await ctx.message.delete()
    except Exception:
        pass
    if not new_name:
        await ctx.send("❌ Вкажіть нову назву: `!rename Моя Кімната`", delete_after=5)
        return
    channel = ctx.author.voice.channel
    formatted_name = f"🔊 | {new_name}"
    await channel.edit(name=formatted_name)
    await ctx.send(f"✏️ Назву кімнати змінено на **{formatted_name}**!", delete_after=10)

@bot.command(name="limit", aliases=["ліміт"])
@is_room_owner()
async def limit_room(ctx, limit: int = None):
    try:
        await ctx.message.delete()
    except Exception:
        pass
    if limit is None or limit < 0 or limit > 99:
        await ctx.send("❌ Вкажіть ліміт від 0 до 99: `!limit 5`", delete_after=5)
        return
    channel = ctx.author.voice.channel
    await channel.edit(user_limit=limit)
    txt = f"без обмежень" if limit == 0 else f"{limit} осіб"
    await ctx.send(f"👥 Встановлено ліміт кімнати: **{txt}**!", delete_after=10)

@bot.command(name="vkick", aliases=["вкік"])
@is_room_owner()
async def vkick_room(ctx, member: discord.Member = None):
    try:
        await ctx.message.delete()
    except Exception:
        pass
    if not member:
        await ctx.send("❌ Вкажіть користувача: `!vkick @user`", delete_after=5)
        return
    channel = ctx.author.voice.channel
    if member.voice and member.voice.channel.id == channel.id:
        await member.move_to(None)
        await channel.set_permissions(member, connect=False)
        await ctx.send(f"🚫 {member.mention} вигнано з вашої кімнати!", delete_after=10)
    else:
        await ctx.send("❌ Цього гравця немає у вашій кімнаті!", delete_after=5)


# --- ФОНОВІ ЗАДАЧІ ---
@tasks.loop(seconds=1)
async def voice_counter_loop():
    for guild in bot.guilds:
        for member in guild.members:
            if member.voice and member.voice.channel and not member.bot:
                user_voice_seconds[member.id] += 1
                user_exp[member.id] += 1
                bot.loop.create_task(check_and_update_level(member, guild))
                if user_voice_seconds[member.id] % 300 == 0:
                    user_coins[member.id] += 5

@tasks.loop(minutes=1)
async def activity_loop():
    global stats_message_id
    save_data()
    poland_time = datetime.now(timezone.utc) + timedelta(hours=1)

    stats_channel = bot.get_channel(STATS_CHANNEL_ID)
    if stats_channel:
        embed = discord.Embed(
            title="📊 Статистика активності гравців ELITE RP",
            description="Це повідомлення автоматично оновлюється в реальному часі.",
            color=discord.Color.blue()
        )
        
        top_msg = sorted(user_messages.items(), key=lambda x: x[1], reverse=True)[:5]
        msg_text = "\n".join([f"**{idx}.** <@{uid}> — **{count}** пов." for idx, (uid, count) in enumerate(top_msg, 1)])
        embed.add_field(name="💬 Топ за повідомленнями", value=msg_text if msg_text else "Поки немає даних", inline=False)

        top_voice = sorted(user_voice_seconds.items(), key=lambda x: x[1], reverse=True)[:5]
        voice_text = "\n".join([f"**{idx}.** <@{uid}> — **{format_voice_time(secs)}**" for idx, (uid, secs) in enumerate(top_voice, 1)])
        embed.add_field(name="🎙️ Топ за часом у войсі", value=voice_text if voice_text else "Поки немає даних", inline=False)
        embed.set_footer(text=f"Останнє оновлення: {poland_time.strftime('%H:%M:%S')}")

        try:
            if stats_message_id:
                try:
                    msg = await stats_channel.fetch_message(stats_message_id)
                    await msg.edit(embed=embed)
                except Exception:
                    msg = await stats_channel.send(embed=embed)
                    stats_message_id = msg.id
            else:
                async for message in stats_channel.history(limit=5):
                    if message.author == bot.user:
                        stats_message_id = message.id
                        await message.edit(embed=embed)
                        break
                else:
                    msg = await stats_channel.send(embed=embed)
                    stats_message_id = msg.id
        except Exception as e:
            print(f"Помилка оновлення статистики: {e}")


@tasks.loop(minutes=1)
async def weekly_report_loop():
    poland_time = datetime.now(timezone.utc) + timedelta(hours=1)
    if poland_time.weekday() == 6 and poland_time.hour == 23 and poland_time.minute == 0:
        stats_channel = bot.get_channel(STATS_CHANNEL_ID)
        if stats_channel:
            embed = discord.Embed(
                title="🏆 ПІДСУМКОВИЙ ТИЖНЕВИЙ ЗВІТ АКТИВНОСТІ",
                description="Офіційні підсумки активності за тиждень.",
                color=discord.Color.gold()
            )
            await stats_channel.send(embed=embed)


@activity_loop.before_loop
async def before_activity_loop():
    await bot.wait_until_ready()

@voice_counter_loop.before_loop
async def before_voice_loop():
    await bot.wait_until_ready()

@weekly_report_loop.before_loop
async def before_weekly_loop():
    await bot.wait_until_ready()


@bot.event
async def on_ready():
    print(f'Бот увійшов як {bot.user} і працює успішно!')
    bot.add_view(TicketPanelView())
    bot.add_view(AdminReplyView())
    await setup_ticket_panel()

    if not voice_counter_loop.is_running():
        voice_counter_loop.start()
    if not activity_loop.is_running():
        activity_loop.start()
    if not weekly_report_loop.is_running():
        weekly_report_loop.start()
    try:
        synced = await bot.tree.sync()
        print(f'Синхронізовано слеш-команд: {len(synced)}')
    except Exception as e:
        print(f'Помилка синхронізації: {e}')


# --- 🧠 ПОВЕДІНКОВИЙ СКАНЕР СПАМУ ТА ФІШИНГУ ---
@bot.event
async def on_message(message):
    if message.author.bot or message.guild is None:
        return

    author_id = message.author.id
    now = datetime.now()
    perms = message.author.guild_permissions
    is_owner = (message.author.id == message.guild.owner_id)
    is_admin_or_mod = perms.administrator or perms.manage_messages or perms.kick_members or perms.ban_members

    if not is_admin_or_mod:
        content_lower = message.content.lower()
        scam_keywords = ["free nitro", "steam gift", "airdrop", "discord.gift", "discrod", "dlscord", "@everyone", "@here"]
        has_scam = any(word in content_lower for word in scam_keywords)
        has_mass_mentions = len(message.mentions) >= 4

        if has_scam or has_mass_mentions:
            try:
                await message.delete()
                await message.author.timeout(timedelta(hours=24), reason="Anti-Scam / Масові згадки")
                await message.channel.purge(limit=20, check=lambda m: m.author.id == author_id)
                await send_log(
                    message.guild,
                    "🚨 Anti-Scam / Raid-Ping",
                    f"Користувач {message.author.mention} спробував надіслати фішинг або масовий тег.\n**Дія:** Повідомлення видалено, видано ізоляцію на **24 години**.",
                    discord.Color.dark_red(),
                    ping_owner=True
                )
            except Exception as e:
                print(f"Помилка Anti-Scam: {e}")
            return

        url_pattern = r'(https?://[^\s]+|www\.[^\s]+|discord\.gg/[^\s]+)'
        if re.search(url_pattern, message.content):
            try:
                await message.delete()
                await message.channel.send(f'{message.author.mention}, посилання заборонені!', delete_after=5)
                await send_log(message.guild, "Заборонене посилання", f"Користувач {message.author.mention} надіслав посилання в канал {message.channel.mention} (видалено).", discord.Color.orange())
            except Exception:
                pass
            return

    user_messages[author_id] += 1
    user_exp[author_id] += 15
    await check_and_update_level(message.author, message.guild)
    
    earned_ec = 1
    if message.attachments:
        earned_ec += 3

    user_coins[author_id] += earned_ec
    save_data()

    await bot.process_commands(message)

    if not is_owner:
        message_history[author_id].append(now)
        message_history[author_id] = [t for t in message_history[author_id] if now - t < timedelta(seconds=4)]

        last_user_messages[author_id].append(message.content.strip().lower())
        if len(last_user_messages[author_id]) > 5:
            last_user_messages[author_id].pop(0)

        is_fast_spam = len(message_history[author_id]) > 5
        is_duplicate_spam = False
        if len(last_user_messages[author_id]) >= 3:
            recent_msgs = last_user_messages[author_id][-3:]
            if len(set(recent_msgs)) == 1 and len(recent_msgs[0]) > 0:
                is_duplicate_spam = True

        if is_fast_spam or is_duplicate_spam:
            try:
                await message.delete()
            except Exception:
                pass

            if admin_spam_warnings[author_id] == 0:
                admin_spam_warnings[author_id] = 1
                try:
                    await message.author.timeout(timedelta(minutes=10), reason="Спам у чаті")
                    await message.channel.send(f'🔇 {message.author.mention} отримав мут на 10 хвилин за спам!', delete_after=8)
                    await send_log(message.guild, "Мут за спам", f"Користувач {message.author.mention} отримав мут на 10 хв за спам.", discord.Color.red())
                except Exception as e:
                    print(f"Помилка муту: {e}")
            else:
                try:
                    await message.guild.ban(message.author, reason="Повторний спам")
                    await message.channel.send(f'🔨 {message.author.mention} забанений за повторний спам!', delete_after=10)
                    await send_log(message.guild, "Бан за спам", f"Користувач {message.author.mention} забанений за повторний спам.", discord.Color.dark_red())
                except Exception as e:
                    print(f"Помилка бану: {e}")


# --- ОСНОВНІ КОМАНДИ ---
@bot.command(name="givecoins", aliases=["видати"])
async def give_coins(ctx, member: discord.Member = None, amount: int = 0):
    try:
        await ctx.message.delete()
    except Exception:
        pass

    if ctx.author.id != ctx.guild.owner_id:
        await ctx.send("❌ Тільки для Власника!", delete_after=5)
        return

    if not member or amount <= 0:
        await ctx.send("❌ Використовуйте: `!givecoins @користувач кількість`", delete_after=6)
        return

    user_coins[member.id] += amount
    save_data()
    embed = discord.Embed(title="💳 Нарахування EC", description=f"👑 Власник нарахував **+{amount}** EC для {member.mention}!", color=discord.Color.gold())
    await ctx.send(embed=embed, delete_after=60)
    await send_log(ctx.guild, "Видача валюти", f"Власник нарахував {amount} EC для {member.mention}.", discord.Color.gold())


@bot.command(name="ранг")
async def text_rank(ctx):
    try:
        await ctx.message.delete()
    except Exception:
        pass

    if ctx.channel.id != RANK_CHANNEL_ID:
        await ctx.send("❌ Команда лише у спеціальному каналі!", delete_after=4)
        return

    user_id = ctx.author.id
    total_exp = user_exp[user_id]
    level, current_exp, max_exp = get_level_and_exp(total_exp)

    progress_blocks = 10
    filled_blocks = int((current_exp / max_exp) * progress_blocks) if max_exp > 0 else 0
    if filled_blocks > progress_blocks:
        filled_blocks = progress_blocks
    bar = "█" * filled_blocks + "░" * (progress_blocks - filled_blocks)

    embed = discord.Embed(title=f"💳 Картка рангу — {ctx.author.name}", color=discord.Color.dark_theme())
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    embed.add_field(name="⭐ Рівень", value=f"**{level}** / 500", inline=True)
    embed.add_field(name="📈 Досвід (EXP)", value=f"**{current_exp}** / **{max_exp}**", inline=True)
    embed.add_field(name="📊 Шкала прогресу", value=f"`{bar}` ({int((current_exp/max_exp)*100)}%)", inline=False)
    embed.add_field(name="💵 Баланс балів", value=f"**{user_coins[user_id]}** EC", inline=False)
    embed.set_footer(text="ELITE RP | Система рівнів та активності")
    
    await ctx.send(content=f"🕒 <t:{int(datetime.now(timezone.utc).timestamp())}:T>", embed=embed, delete_after=60)


@bot.command(name="бонус", aliases=["daily"])
async def get_daily_bonus(ctx):
    try:
        await ctx.message.delete()
    except Exception:
        pass

    user_id = ctx.author.id
    now = datetime.now()

    if user_id in last_daily_claim:
        time_passed = now - last_daily_claim[user_id]
        if time_passed < timedelta(hours=24):
            time_left = timedelta(hours=24) - time_passed
            hours, remainder = divmod(int(time_left.total_seconds()), 3600)
            minutes, _ = divmod(remainder, 60)
            await ctx.send(f"⏳ Бонус вже забирали! Чекайте ще **{hours} год. {minutes} хв.**", delete_after=60)
            return

    reward = random.randint(50, 150)
    user_coins[user_id] += reward
    last_daily_claim[user_id] = now
    save_data()
    
    embed = discord.Embed(title="🎁 Щоденний бонус", description=f"{ctx.author.mention}, вам зараховано **+{reward}** EC!", color=discord.Color.gold())
    await ctx.send(embed=embed, delete_after=60)


@bot.command(name="дуель")
async def duel_coins(ctx, opponent: discord.Member = None, bet: int = 0):
    try:
        await ctx.message.delete()
    except Exception:
        pass

    if not opponent or opponent.bot or opponent == ctx.author or bet <= 0:
        await ctx.send("❌ Некоректні дані для дуелі!", delete_after=60)
        return

    if user_coins[ctx.author.id] < bet or user_coins[opponent.id] < bet:
        await ctx.send("❌ У когось недостатньо коїнів!", delete_after=60)
        return

    winner = random.choice([ctx.author, opponent])
    loser = opponent if winner == ctx.author else ctx.author

    user_coins[winner.id] += bet
    user_coins[loser.id] -= bet
    save_data()

    embed = discord.Embed(title="🎲 Дуель", description=f"🏆 Переможець дуелі: {winner.mention} і забирає **+{bet}** EC!", color=discord.Color.purple())
    await ctx.send(embed=embed, delete_after=60)


@bot.command(name="магазин", aliases=["shop"])
async def view_shop(ctx):
    try:
        await ctx.message.delete()
    except Exception:
        pass

    embed = discord.Embed(
        title="🛒 Магазин Ролей Discord | ELITE RP",
        description="Напишіть `!купити [номер]`, щоб отримати роль:",
        color=discord.Color.green()
    )
    for item_id, info in SHOP_ITEMS.items():
        embed.add_field(name=f"Товар #{item_id}: {info['name']}", value=f"💵 Ціна: **{info['price']}** EC", inline=False)
    
    embed.set_footer(text=f"Ваш баланс: {user_coins[ctx.author.id]} EC")
    await ctx.send(embed=embed, delete_after=60)


@bot.command(name="купити", aliases=["buy"])
async def buy_item(ctx, item_id: str = None):
    try:
        await ctx.message.delete()
    except Exception:
        pass

    if not item_id or item_id not in SHOP_ITEMS:
        await ctx.send("❌ Невірний номер товару!", delete_after=60)
        return

    item = SHOP_ITEMS[item_id]
    price = item["price"]
    user_id = ctx.author.id

    if user_coins[user_id] < price:
        await ctx.send(f"❌ Недостатньо коштів! Потрібно {price} EC.", delete_after=60)
        return

    role = ctx.guild.get_role(item["role_id"])
    if not role or role in ctx.author.roles:
        await ctx.send("❌ Роль вже є або не знайдена на сервері.", delete_after=60)
        return

    user_coins[user_id] -= price
    await ctx.author.add_roles(role)
    save_data()
    
    await ctx.send(f"🎉 {ctx.author.mention}, ви успішно купили роль **{item['name']}**!", delete_after=60)
    await send_log(ctx.guild, "Покупка в магазині", f"Користувач {ctx.author.mention} купив роль **{item['name']}**.", discord.Color.blue())


@bot.command(name="сервер")
async def text_server(ctx):
    try:
        await ctx.message.delete()
    except Exception:
        pass
    guild = ctx.guild
    embed = discord.Embed(title=f"📌 Сервер: {guild.name}", color=discord.Color.gold())
    embed.add_field(name="👑 Власник", value=guild.owner.mention if guild.owner else "Невідомо", inline=True)
    embed.add_field(name="👥 Учасників", value=f"**{guild.member_count}**", inline=True)
    await ctx.send(embed=embed, delete_after=60)


async def send_social_links(target):
    embed = discord.Embed(
        title="🌐 СОЦІАЛЬНІ МЕРЕЖІ | ELITE RP",
        description=f"🔷 **Сайт:** {URL_SITE}\n🔷 **Форум:** {URL_FORUM}\n📢 **Telegram:** {URL_TG_CHANNEL}",
        color=discord.Color.blue()
    )
    if isinstance(target, discord.Interaction):
        await target.response.send_message(embed=embed)
    else:
        await target.send(embed=embed, delete_after=60)

@bot.tree.command(name="links", description="Показати соцмережі")
async def slash_links(interaction: discord.Interaction):
    await send_social_links(interaction)

@bot.command(name="посилання", aliases=["соцмережі", "links"])
async def text_links(ctx):
    try:
        await ctx.message.delete()
    except Exception:
        pass
    await send_social_links(ctx)


# --- ANTI-NUKE (МАСОВІ БАНИ, ВИДАЛЕННЯ КАНАЛІВ ТА РОЛЕЙ) ---

@bot.event
async def on_member_ban(guild, user):
    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
        executor = entry.user
        if executor.bot or executor.id == guild.owner_id:
            return

        now = datetime.now()
        ban_history[executor.id].append(now)
        ban_history[executor.id] = [t for t in ban_history[executor.id] if now - t < timedelta(seconds=10)]

        if len(ban_history[executor.id]) >= 2:
            await punish_rogue_admin(guild, executor, "Anti-Nuke: Масовий бан учасників")

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

        if len(channel_delete_history[executor.id]) >= 2:
            await punish_rogue_admin(guild, executor, "Anti-Nuke: Масове видалення каналів")

@bot.event
async def on_guild_role_delete(role):
    guild = role.guild
    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.role_delete):
        executor = entry.user
        if executor.bot or executor.id == guild.owner_id:
            return

        now = datetime.now()
        role_delete_history[executor.id].append(now)
        role_delete_history[executor.id] = [t for t in role_delete_history[executor.id] if now - t < timedelta(seconds=10)]

        if len(role_delete_history[executor.id]) >= 2:
            await punish_rogue_admin(guild, executor, "Anti-Nuke: Масове видалення ролей")


@bot.tree.command(name="help", description="Доступні команди")
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(title="📜 Меню команд", color=discord.Color.blue())
    embed.add_field(name="`!givecoins`", value="Видати коїни (тільки Власнику)", inline=False)
    embed.add_field(name="`!бонус` / `!daily`", value="Щоденний бонус", inline=False)
    embed.add_field(name="`!магазин` / `!купити`", value="Магазин ролей", inline=False)
    embed.add_field(name="`!дуель`", value="Дуель на коїни", inline=False)
    embed.add_field(name="`!ранг`", value="Перевірити рівень та прогрес", inline=False)
    embed.add_field(name="`!lock` / `!unlock` / `!rename` / `!limit` / `!vkick`", value="Керування приватним войсом", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="clear", description="Очистити чат")
@app_commands.checks.has_permissions(manage_messages=True)
async def slash_clear(interaction: discord.Interaction, amount: int = 5):
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"🧹 Видалено {len(deleted)} повідомлень!", ephemeral=True)
    await send_log(interaction.guild, "Очищення чату", f"Адміністратор {interaction.user.mention} видалив {len(deleted)} повідомлень у {interaction.channel.mention}.", discord.Color.orange())

@bot.tree.command(name="mute", description="Мут на 10 хвилин")
@app_commands.checks.has_permissions(moderate_members=True)
async def slash_mute(interaction: discord.Interaction, member: discord.Member, reason: str = "Порушення"):
    try:
        await member.timeout(timedelta(minutes=10), reason=reason)
        await interaction.response.send_message(f"🔇 {member.mention} в муті.", ephemeral=True)
        await send_log(interaction.guild, "Мут гравця", f"Модератор {interaction.user.mention} видав мут {member.mention}. Причина: {reason}", discord.Color.red())
    except Exception as e:
        await interaction.response.send_message(f"❌ Помилка: {e}", ephemeral=True)

@bot.tree.command(name="unmute", description="Зняти мут")
@app_commands.checks.has_permissions(moderate_members=True)
async def slash_unmute(interaction: discord.Interaction, member: discord.Member):
    try:
        await member.timeout(None)
        await interaction.response.send_message(f"🔊 З {member.mention} знято мут.", ephemeral=True)
        await send_log(interaction.guild, "Зняття муту", f"Модератор {interaction.user.mention} зняв мут з {member.mention}.", discord.Color.green())
    except Exception as e:
        await interaction.response.send_message(f"❌ Помилка: {e}", ephemeral=True)

@bot.tree.command(name="kick", description="Вигнати гравця")
@app_commands.checks.has_permissions(kick_members=True)
async def slash_kick(interaction: discord.Interaction, member: discord.Member, reason: str = "Не вказано"):
    try:
        await member.kick(reason=reason)
        await interaction.response.send_message(f"👢 {member.mention} вигнано.", ephemeral=True)
        await send_log(interaction.guild, "Кік гравця", f"Модератор {interaction.user.mention} вигнав {member.mention}. Причина: {reason}", discord.Color.orange())
    except Exception as e:
        await interaction.response.send_message(f"❌ Помилка: {e}", ephemeral=True)

@bot.tree.command(name="ban", description="Забанити гравця")
@app_commands.checks.has_permissions(ban_members=True)
async def slash_ban(interaction: discord.Interaction, member: discord.Member, reason: str = "Не вказано"):
    try:
        await member.ban(reason=reason)
        await interaction.response.send_message(f"🔨 {member.mention} забанений.", ephemeral=True)
        await send_log(interaction.guild, "Бан гравця", f"Адміністратор {interaction.user.mention} забанив {member.mention}. Причина: {reason}", discord.Color.dark_red())
    except Exception as e:
        await interaction.response.send_message(f"❌ Помилка: {e}", ephemeral=True)


if __name__ == '__main__':
    TOKEN = os.getenv("DISCORD_TOKEN")
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("Помилка: Не знайдено DISCORD_TOKEN!")
