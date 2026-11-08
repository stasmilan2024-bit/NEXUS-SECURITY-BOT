import os
import re
import json
import random
import threading
import collections
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler

import discord
from discord.ext import commands, tasks

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

bot = commands.Bot(command_prefix="!", intents=intents)

# --- ЗБЕРЕЖЕННЯ ТА ЗАТАВАННЯ ДАНИХ (JSON) ---
DATA_FILE = "data.json"

user_messages = collections.defaultdict(int)
user_voice_seconds = collections.defaultdict(int)
user_coins = collections.defaultdict(int)

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
            print("💾 Дані успішно завантажено з data.json!")
        except Exception as e:
            print(f"Помилка читання data.json: {e}")

def save_data():
    try:
        data = {
            "messages": {str(k): v for k, v in user_messages.items()},
            "voice": {str(k): v for k, v in user_voice_seconds.items()},
            "coins": {str(k): v for k, v in user_coins.items()}
        }
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Помилка збереження у data.json: {e}")

load_data()

message_history = collections.defaultdict(list)
link_history = collections.defaultdict(list)
ban_history = collections.defaultdict(list)
channel_delete_history = collections.defaultdict(list)
last_user_messages = collections.defaultdict(list)
admin_spam_warnings = collections.defaultdict(int)
last_daily_claim = {}

# --- ID КАНАЛІВ ТА НАЛАШТУВАННЯ ---
WELCOME_CHANNEL_ID = 1566880572029018203
STATS_CHANNEL_ID = 1568373943138787349  
RANK_CHANNEL_ID = 1405600879587098644    
LOG_CHANNEL_ID = 1569067419740278936    

# ID для приватних войсів
CREATE_VOICE_CHANNEL_ID = 1405601386674130965
PRIVATE_ROOMS_CATEGORY_ID = 1405600664704254103

active_private_channels = {}

# --- ПОСИЛАННЯ НА СОЦМЕРЕЖІ ---
URL_SITE = "https://eliterp.pp.ua"                         
URL_FORUM = "http://eliterpforum.sytes.net/index.php"       
URL_TG_CHANNEL = "https://t.me/your_telegram_channel"       
URL_TG_CHAT = "https://t.me/your_telegram_chat"             
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

REQ_MSG_MASTER = 5000
REQ_VOICE_ACTIVE = 50  
REQ_MSG_MOST = 6000
REQ_VOICE_MOST = 90    

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


async def send_log(guild, title, description, color=discord.Color.blue()):
    if not guild:
        return
    channel = guild.get_channel(LOG_CHANNEL_ID)
    if channel:
        embed = discord.Embed(title=f"🛡️ ЛОГ ДІЙ | {title}", description=description, color=color, timestamp=datetime.utcnow())
        try:
            await channel.send(embed=embed)
        except Exception as e:
            print(f"Помилка відправки логу: {e}")


# --- МОДАЛЬНЕ ВІКНО НАЛАШТУВАННЯ КІМНАТИ ---
class RoomSettingsModal(discord.ui.Modal, title="Налаштування приватної кімнати"):
    room_name = discord.ui.TextInput(
        label="Назва вашої кімнати",
        placeholder="Наприклад: Chill Zone",
        max_length=50,
        required=True
    )
    user_limit = discord.ui.TextInput(
        label="Ліміт людей (0 - без обмежень)",
        placeholder="0",
        default="0",
        max_length=2,
        required=True
    )

    def __init__(self, member: discord.Member):
        super().__init__()
        self.member = member

    async def on_submit(self, interaction: discord.Interaction):
        # 1. Одразу робимо defer, щоб Discord не видавав помилку часу очікування
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ Помилка: не вдалося визначити сервер.", ephemeral=True)
            return

        category = guild.get_channel(PRIVATE_ROOMS_CATEGORY_ID)
        cat_obj = category if isinstance(category, discord.CategoryChannel) else None
        
        try:
            limit = int(self.user_limit.value)
            if limit < 0 or limit > 99:
                limit = 0
        except ValueError:
            limit = 0

        final_name = f"🔊 | {self.room_name.value}"

        try:
            # 2. Створюємо голосовий канал у потрібній категорії
            new_channel = await guild.create_voice_channel(
                name=final_name,
                user_limit=limit,
                category=cat_obj
            )
            
            # 3. Даємо власнику повні права керувати кімнатою
            await new_channel.set_permissions(self.member, manage_channels=True, move_members=True)
            
            # 4. Переносимо гравця у створену кімнату
            await self.member.move_to(new_channel)
            active_private_channels[new_channel.id] = self.member.id

            await send_log(guild, "Створення кімнати", f"Користувач {self.member.mention} створив приватний войс: **{final_name}** (ліміт: {limit})", discord.Color.green())
            await interaction.followup.send(f"✅ Кімнату **«{final_name}»** успішно створено!", ephemeral=True)
        except Exception as e:
            print(f"Помилка створення каналу: {e}")
            await interaction.followup.send(f"❌ Помилка створення каналу: {e}", ephemeral=True)


# --- СИСТЕМА ПРИВАТНИХ ВОЙСІВ ---
@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return

    # Коли заходить у канал створення
    if after.channel and after.channel.id == CREATE_VOICE_CHANNEL_ID:
        view = discord.ui.View(timeout=120)
        button = discord.ui.Button(label="⚙️ Налаштувати кімнату", style=discord.ButtonStyle.green)

        async def button_callback(interaction: discord.Interaction):
            if interaction.user.id != member.id:
                await interaction.response.send_message("❌ Це меню не для вас!", ephemeral=True)
                return
            await interaction.response.send_modal(RoomSettingsModal(member))

        button.callback = button_callback
        view.add_item(button)

        try:
            await member.send("⚙️ Налаштуйте свою приватну кімнату ELITE RP за допомогою кнопки нижче:", view=view)
        except Exception:
            # Якщо у гравця закриті ЛС — створюємо автоматично
            guild = member.guild
            category = guild.get_channel(PRIVATE_ROOMS_CATEGORY_ID)
            cat_obj = category if isinstance(category, discord.CategoryChannel) else None
            try:
                new_channel = await guild.create_voice_channel(
                    name=f"🔊 | Кімната {member.name}",
                    category=cat_obj
                )
                await new_channel.set_permissions(member, manage_channels=True, move_members=True)
                await member.move_to(new_channel)
                active_private_channels[new_channel.id] = member.id
                await send_log(guild, "Створення кімнати (Авто)", f"Користувач {member.mention} створив стандартну кімнату (ЛС закриті).", discord.Color.green())
            except Exception as ex:
                print(f"Помилка автостворення: {ex}")

    # Видалення порожніх приватних кімнат
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


@tasks.loop(seconds=1)
async def voice_counter_loop():
    for guild in bot.guilds:
        for member in guild.members:
            if member.voice and member.voice.channel and not member.bot:
                user_voice_seconds[member.id] += 1
                if user_voice_seconds[member.id] % 300 == 0:
                    user_coins[member.id] += 5

@tasks.loop(minutes=1)
async def activity_loop():
    global stats_message_id
    save_data()
    poland_time = datetime.utcnow() + timedelta(hours=1)

    for guild in bot.guilds:
        for member in guild.members:
            if member.bot:
                continue
            
            m_count = user_messages[member.id]
            v_hours = user_voice_seconds[member.id] / 3600.0

            r_active = guild.get_role(ROLE_ACTIVE_ID)
            r_master = guild.get_role(ROLE_MASTER_ID)
            r_incredible = guild.get_role(ROLE_INCREDIBLE_ID)
            r_most_active = guild.get_role(ROLE_MOST_ACTIVE_ID)

            if m_count >= REQ_MSG_MOST and v_hours >= REQ_VOICE_MOST:
                if r_most_active and r_most_active not in member.roles:
                    try:
                        roles_to_remove = [r for r in [r_active, r_master, r_incredible] if r in member.roles]
                        if roles_to_remove:
                            await member.remove_roles(*roles_to_remove)
                        await member.add_roles(r_most_active)
                    except Exception:
                        pass
                continue

            if m_count >= REQ_MSG_MASTER and r_master and r_master not in member.roles:
                try:
                    await member.add_roles(r_master)
                except Exception:
                    pass

            if v_hours >= REQ_VOICE_ACTIVE and r_active and r_active not in member.roles:
                try:
                    await member.add_roles(r_active)
                except Exception:
                    pass

            has_master = r_master in member.roles if r_master else False
            has_active = r_active in member.roles if r_active else False

            if has_master and has_active and r_incredible and r_incredible not in member.roles:
                try:
                    await member.add_roles(r_incredible)
                except Exception:
                    pass

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
    poland_time = datetime.utcnow() + timedelta(hours=1)
    if poland_time.weekday() == 6 and poland_time.hour == 23 and poland_time.minute == 0:
        stats_channel = bot.get_channel(STATS_CHANNEL_ID)
        if stats_channel:
            embed = discord.Embed(
                title="🏆 ПІДСУМКОВИЙ ТИЖНЕВИЙ ЗВІТ АКТИВНОСТІ",
                description="Офіційні підсумки активності за тиждень. Статистика обнулена!",
                color=discord.Color.gold()
            )
            await stats_channel.send(embed=embed)
            user_messages.clear()
            user_voice_seconds.clear()
            save_data()


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
async def on_member_join(member: discord.Member):
    channel = member.guild.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        embed = discord.Embed(
            title=f"Вітаємо на ELITE RP, {member.name}! 👋",
            description=f"Привіт, {member.mention}!\n\n**Раді бачити тебе на нашому сервері!** 🎉",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await channel.send(embed=embed)
    await send_log(member.guild, "Новий учасник", f"Користувач {member.mention} (`{member.name}`) приєднався до сервера.", discord.Color.green())

@bot.event
async def on_ready():
    print(f'Бот увійшов як {bot.user} і працює успішно!')
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

@bot.event
async def on_message_delete(message):
    if message.author.bot or message.guild is None:
        return
    author_id = message.author.id
    if user_messages[author_id] > 0:
        user_messages[author_id] -= 1
        save_data()


# --- АКТИВНІСТЬ ТА АНТИСПАМ ---
@bot.event
async def on_message(message):
    if message.author.bot or message.guild is None:
        return

    author_id = message.author.id
    now = datetime.now()
    perms = message.author.guild_permissions
    is_owner = (message.author.id == message.guild.owner_id)

    user_messages[author_id] += 1
    
    earned_ec = 1
    if message.attachments:
        earned_ec += 3

    user_coins[author_id] += earned_ec

    is_admin_or_mod = perms.administrator or perms.manage_messages or perms.kick_members or perms.ban_members

    url_pattern = r'(https?://[^\s]+|www\.[^\s]+|discord\.gg/[^\s]+)'
    has_link = bool(re.search(url_pattern, message.content))

    if has_link:
        if not is_admin_or_mod:
            try:
                await message.delete()
                await message.channel.send(f'{message.author.mention}, посилання заборонені!', delete_after=5)
                await send_log(message.guild, "Заборонене посилання", f"Користувач {message.author.mention} надіслав посилання в канал {message.channel.mention} (видалено).", discord.Color.orange())
                return
            except Exception:
                pass
        elif not is_owner:
            link_history[author_id].append(now)
            link_history[author_id] = [t for t in link_history[author_id] if now - t < timedelta(seconds=60)]

            if len(link_history[author_id]) > 3:
                try:
                    await message.delete()
                    await message.channel.send(f'⚠️ {message.author.mention}, ліміт посилань перевищено!', delete_after=5)
                    return
                except Exception:
                    pass

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


# --- КОМАНДИ ---
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
    if ctx.channel.id != RANK_CHANNEL_ID:
        try:
            await ctx.message.delete()
        except Exception:
            pass
        await ctx.send("❌ Команда лише у спеціальному каналі!", delete_after=4)
        return

    user_id = ctx.author.id
    m_count = user_messages[user_id]
    v_secs = user_voice_seconds[user_id]
    coins = user_coins[user_id]

    embed = discord.Embed(title=f"💳 Картка рангу — {ctx.author.name}", color=discord.Color.dark_theme())
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    embed.add_field(name="💵 Баланс", value=f"**{coins}** EC", inline=False)
    embed.add_field(name="💬 Повідомлення", value=f"**{m_count}**", inline=False)
    embed.add_field(name="🎙️ Войс", value=f"**{format_voice_time(v_secs)}**", inline=False)
    await ctx.send(content=f"🕒 <t:{int(datetime.utcnow().timestamp())}:T>", embed=embed)


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

    embed = discord.Embed(title="🛒 Магазин Ролей Discord", description="Напишіть `!купити [номер]`, щоб отримати роль:", color=discord.Color.green())
    for item_id, info in SHOP_ITEMS.items():
        embed.add_field(name=f"Товар #{item_id}: {info['name']}", value=f"💵 Ціна: **{info['price']}** EC", inline=False)
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
    guild = ctx.guild
    embed = discord.Embed(title=f"📌 Сервер: {guild.name}", color=discord.Color.gold())
    embed.add_field(name="👑 Власник", value=guild.owner.mention if guild.owner else "Невідомо", inline=True)
    embed.add_field(name="👥 Учасників", value=f"**{guild.member_count}**", inline=True)
    await ctx.send(embed=embed)


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
                await guild.ban(executor, reason="Anti-Nuke: Масовий бан")
                await send_log(guild, "🚨 Anti-Nuke BAN", f"Користувач `{executor}` спробував масово забанити учасників і був заблокований!", discord.Color.dark_red())
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
                await send_log(guild, "🚨 Anti-Nuke CHANNEL DELETE", f"Користувач `{executor}` видаляв канали і був заблокований!", discord.Color.dark_red())
            except Exception as e:
                print(f"Помилка захисту каналів: {e}")


@bot.tree.command(name="help", description="Доступні команди")
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(title="📜 Меню команд", color=discord.Color.blue())
    embed.add_field(name="`!givecoins`", value="Видати коїни (тільки Власнику)", inline=False)
    embed.add_field(name="`!бонус` / `!daily`", value="Щоденний бонус", inline=False)
    embed.add_field(name="`!магазин`", value="Магазин ролей", inline=False)
    embed.add_field(name="`!купити [номер]`", value="Купити роль", inline=False)
    embed.add_field(name="`!дуель`", value="Дуель на коїни", inline=False)
    embed.add_field(name="`!ранг`", value="Перевірити профіль", inline=False)
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
