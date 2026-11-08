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

# Тимчасова історія в пам'яті
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

# --- ПОСИЛАННЯ НА СОЦМЕРЕЖІ ---
URL_SITE = "https://eliterp.pp.ua"                         
URL_FORUM = "http://eliterpforum.sytes.net/index.php"       
URL_TG_CHANNEL = "https://t.me/your_telegram_channel"       
URL_TG_CHAT = "https://t.me/your_telegram_chat"             
URL_TG_BOT = "🚧 В розробці"                                
URL_TIKTOK = "https://www.tiktok.com/@your_tiktok"          
URL_INSTAGRAM = "https://www.instagram.com/your_instagram"  

# --- ID РОЛЕЙ АКТИВНОСТІ ---
ROLE_ACTIVE_ID = 1405600607427100854      # Активний
ROLE_MASTER_ID = 1405600608576213002      # Майстер
ROLE_INCREDIBLE_ID = 1405600522010103949  # Неймовірний
ROLE_MOST_ACTIVE_ID = 1405600525826920568 # Найактивніший

# --- МАГАЗИН DISCORD-РОЛЕЙ З АДЕКВАТНИМИ ЦІНАМИ ---
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


# --- ФОНОВА ЗАДАЧА: ПІДРАХУНОК СЕКУНД ТА АВТОЗБЕРЕЖЕННЯ ---
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
    save_data()  # Автозбереження щохвилини у файл!

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
        msg_text = ""
        for idx, (uid, count) in enumerate(top_msg, 1):
            user_obj = bot.get_user(uid)
            name = user_obj.name if user_obj else f"ID: {uid}"
            msg_text += f"**{idx}.** {name} — **{count}** пов.\n"
        
        embed.add_field(name="💬 Топ за повідомленнями", value=msg_text if msg_text else "Поки немає даних", inline=False)

        top_voice = sorted(user_voice_seconds.items(), key=lambda x: x[1], reverse=True)[:5]
        voice_text = ""
        for idx, (uid, secs) in enumerate(top_voice, 1):
            user_obj = bot.get_user(uid)
            name = user_obj.name if user_obj else f"ID: {uid}"
            time_formatted = format_voice_time(secs)
            voice_text += f"**{idx}.** {name} — **{time_formatted}**\n"

        embed.add_field(name="🎙️ Топ за часом у войсі", value=voice_text if voice_text else "Поки немає даних", inline=False)
        embed.set_footer(text=f"Останнє оновлення (Польща): {poland_time.strftime('%H:%M:%S')}")

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
                description="Офіційні підсумки активності гравців за весь тиждень (неділя, 23:00). Статистика обнулена!",
                color=discord.Color.gold()
            )
            
            top_msg = sorted(user_messages.items(), key=lambda x: x[1], reverse=True)[:5]
            msg_text = "\n".join([f"**{i+1}.** <@{uid}> — **{cnt}** пов." for i, (uid, cnt) in enumerate(top_msg)])
            embed.add_field(name="💬 Найактивніші в чаті", value=msg_text if msg_text else "Немає даних", inline=False)

            top_voice = sorted(user_voice_seconds.items(), key=lambda x: x[1], reverse=True)[:5]
            voice_text = "\n".join([f"**{i+1}.** <@{uid}> — **{format_voice_time(secs)}**" for i, (uid, secs) in enumerate(top_voice)])
            embed.add_field(name="🎙️ Найактивніші у войсі", value=voice_text if voice_text else "Немає даних", inline=False)

            embed.set_footer(text="ELITE RP | Тижневий звіт")
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


# --- ВІТАЛЬНА СИСТЕМА ---
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
        await channel.send(embed=embed)

@bot.event
async def on_ready():
    print(f'Бот успішно увійшов в систему як {bot.user} і охороняє сервер!')
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
        print(f'Помилка синхронізації команд: {e}')

@bot.event
async def on_message_delete(message):
    if message.author.bot or message.guild is None:
        return
    author_id = message.author.id
    if user_messages[author_id] > 0:
        user_messages[author_id] -= 1
        save_data()

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

    is_admin_or_mod = (
        perms.administrator or 
        perms.manage_messages or 
        perms.kick_members or 
        perms.ban_members
    )

    url_pattern = r'(https?://[^\s]+|www\.[^\s]+|discord\.gg/[^\s]+)'
    has_link = bool(re.search(url_pattern, message.content))

    if has_link:
        if not is_admin_or_mod:
            try:
                await message.delete()
                await message.channel.send(f'{message.author.mention}, посилання суворо заборонені на сервері!', delete_after=5)
                return
            except Exception:
                pass
        elif not is_owner:
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
                    await message.author.timeout(timedelta(minutes=10), reason="Автоматичний захист: Спам у чаті")
                    await message.channel.send(
                        f'🔇 {message.author.mention} отримав мут на 10 хвилин за спам! При повторній спробі спаму буде видано БАН.',
                        delete_after=8
                    )
                except Exception as e:
                    print(f"Не вдалося видати мут: {e}")
            else:
                try:
                    await message.guild.ban(message.author, reason="Автоматичний анти-спам: Повторний спам")
                    await message.channel.send(
                        f'🔨 {message.author.mention} був ЗАБАНЕНИЙ за повторний спам!',
                        delete_after=10
                    )
                except Exception as e:
                    print(f"Не вдалося забанити: {e}")


# --- 👑 КОМАНДА ВИДАЧІ ВАЛЮТИ ТІЛЬКИ ДЛЯ ВЛАСНИКА (!givecoins) ---
@bot.command(name="givecoins", aliases=["видати"])
async def give_coins(ctx, member: discord.Member = None, amount: int = 0):
    try:
        await ctx.message.delete()
    except Exception:
        pass

    if ctx.author.id != ctx.guild.owner_id:
        await ctx.send("❌ Ця команда доступна лише Власнику сервера!", delete_after=5)
        return

    if not member or amount <= 0:
        await ctx.send("❌ Використовуйте: `!givecoins @користувач кількість`", delete_after=6)
        return

    user_coins[member.id] += amount
    save_data()

    embed = discord.Embed(
        title="💳 Нарахування Elite Coins",
        description=f"👑 Власник сервера нарахував **+{amount}** EC для {member.mention}!\nПоточний баланс: **{user_coins[member.id]}** EC.",
        color=discord.Color.gold()
    )
    await ctx.send(embed=embed, delete_after=60)


# --- ТЕКСТОВА КОМАНДА !ранг ---
@bot.command(name="ранг")
async def text_rank(ctx):
    if ctx.channel.id != RANK_CHANNEL_ID:
        try:
            await ctx.message.delete()
        except Exception:
            pass
        await ctx.send("❌ Ця команда доступна лише у спеціальному каналі!", delete_after=4)
        return

    user_id = ctx.author.id
    m_count = user_messages[user_id]
    v_secs = user_voice_seconds[user_id]
    v_hours_float = v_secs / 3600.0
    coins = user_coins[user_id]

    msg_progress = min(int((m_count / REQ_MSG_MASTER) * 10), 10)
    msg_bar = "█" * msg_progress + "░" * (10 - msg_progress)

    voice_progress = min(int((v_hours_float / REQ_VOICE_ACTIVE) * 10), 10)
    voice_bar = "█" * voice_progress + "░" * (10 - voice_progress)

    current_timestamp = int(datetime.utcnow().timestamp())

    embed = discord.Embed(
        title=f"💳 Картка рангу — {ctx.author.name}",
        color=discord.Color.dark_theme()
    )
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    
    embed.add_field(name="💵 Баланс (Elite Coins)", value=f"**{coins}** EC", inline=False)
    embed.add_field(name="💬 Повідомлення в чаті", value=f"**{m_count}** / {REQ_MSG_MASTER} (Майстер)\n`{msg_bar}`", inline=False)
    embed.add_field(name="🎙️ Час у войсі", value=f"**{format_voice_time(v_secs)}** / {REQ_VOICE_ACTIVE} год. (Активний)\n`{voice_bar}`", inline=False)
    
    status_list = []
    if any(r.id == ROLE_MOST_ACTIVE_ID for r in ctx.author.roles):
        status_list.append("👑 Найактивніший")
    else:
        if any(r.id == ROLE_MASTER_ID for r in ctx.author.roles):
            status_list.append("✅ Майстер")
        if any(r.id == ROLE_ACTIVE_ID for r in ctx.author.roles):
            status_list.append("✅ Активний")
        if any(r.id == ROLE_INCREDIBLE_ID for r in ctx.author.roles):
            status_list.append("🔥 Неймовірний")

    embed.add_field(name="🏆 Поточні статуси", value=", ".join(status_list) if status_list else "Ще немає досягнень", inline=False)
    embed.set_footer(text=f"ELITE RP | Система активності")

    await ctx.send(content=f"🕒 Ваш час: <t:{current_timestamp}:T>", embed=embed)


# --- 🎁 ЩОДЕННИЙ БОНУС (!бонус / !daily) — Видалення через 60 секунд ---
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
            await ctx.send(f"⏳ {ctx.author.mention}, ви вже забирали щоденний бонус! Наступний через **{hours} год. {minutes} хв.**", delete_after=60)
            return

    reward = random.randint(50, 150)
    user_coins[user_id] += reward
    last_daily_claim[user_id] = now
    save_data()
    
    embed = discord.Embed(
        title="🎁 Щоденний бонус отримано!",
        description=f"{ctx.author.mention}, вам зараховано **+{reward}** Elite Coins!\nПоточний баланс: **{user_coins[user_id]}** EC.",
        color=discord.Color.gold()
    )
    await ctx.send(embed=embed, delete_after=60)


# --- 🎲 ДУЕЛЬ НА ВАЛЮТУ (!дуель @гравець ставка) — Видалення через 60 секунд ---
@bot.command(name="дуель")
async def duel_coins(ctx, opponent: discord.Member = None, bet: int = 0):
    try:
        await ctx.message.delete()
    except Exception:
        pass

    if not opponent or opponent.bot or opponent == ctx.author:
        await ctx.send("❌ Вкажіть коректного гравця для дуелі! Наприклад: `!дуель @User 50`", delete_after=60)
        return
    
    if bet <= 0:
        await ctx.send("❌ Ставка повинна бути більше 0 EC!", delete_after=60)
        return

    if user_coins[ctx.author.id] < bet:
        await ctx.send(f"❌ У вас недостатньо валюти! Ваш баланс: **{user_coins[ctx.author.id]}** EC.", delete_after=60)
        return

    if user_coins[opponent.id] < bet:
        await ctx.send(f"❌ У {opponent.mention} недостатньо валюти для цієї ставки!", delete_after=60)
        return

    winner = random.choice([ctx.author, opponent])
    loser = opponent if winner == ctx.author else ctx.author

    user_coins[winner.id] += bet
    user_coins[loser.id] -= bet
    save_data()

    embed = discord.Embed(
        title="🎲 Результат дуелі!",
        description=f"⚔️ **{ctx.author.name}** зійшовся у дуелі з **{opponent.name}** на **{bet}** EC!\n\n🏆 Переможець: {winner.mention} і забирає **+{bet}** EC!",
        color=discord.Color.purple()
    )
    await ctx.send(embed=embed, delete_after=60)


# --- 🛒 МАГАЗИН DISCORD-РОЛЕЙ (!магазин / !shop) — Видалення через 60 секунд ---
@bot.command(name="магазин", aliases=["shop"])
async def view_shop(ctx):
    try:
        await ctx.message.delete()
    except Exception:
        pass

    embed = discord.Embed(
        title="🛒 Магазин Ролей Discord | ELITE RP",
        description="Купуйте унікальні статусні ролі Discord за накопичені **Elite Coins (EC)**!\nЩоб купити роль, напишіть: `!купити [номер]` (наприклад: `!купити 1`)\n",
        color=discord.Color.green()
    )
    
    for item_id, info in SHOP_ITEMS.items():
        embed.add_field(name=f"Товар #{item_id}: {info['name']}", value=f"💵 Ціна: **{info['price']}** EC", inline=False)
        
    embed.set_footer(text=f"Ваш баланс: {user_coins[ctx.author.id]} EC | Заробляйте EC у чаті та войсі! (Повідомлення зникне через 1 хв)")
    await ctx.send(embed=embed, delete_after=60)


# --- 🛍️ КУПІВЛЯ РОЛІ У МАГАЗИНІ (!купити номер) — Видалення через 60 секунд ---
@bot.command(name="купити", aliases=["buy"])
async def buy_item(ctx, item_id: str = None):
    try:
        await ctx.message.delete()
    except Exception:
        pass

    if not item_id or item_id not in SHOP_ITEMS:
        await ctx.send("❌ Вкажіть правильний номер товару! Введіть `!магазин`, щоб переглянути товари.", delete_after=60)
        return

    item = SHOP_ITEMS[item_id]
    price = item["price"]
    user_id = ctx.author.id

    if user_coins[user_id] < price:
        await ctx.send(f"❌ У вас недостатньо валюти для купівлі **{item['name']}**! Потрібно **{price}** EC (у вас **{user_coins[user_id]}** EC).", delete_after=60)
        return

    role = ctx.guild.get_role(item["role_id"])
    if not role:
        await ctx.send("❌ Не вдалося знайти роль на сервері. Зверніться до адміністратора.", delete_after=60)
        return

    if role in ctx.author.roles:
        await ctx.send(f"❌ У вас вже є роль **{role.name}**!", delete_after=60)
        return

    try:
        user_coins[user_id] -= price
        await ctx.author.add_roles(role)
        save_data()

        embed = discord.Embed(
            title="🛍️ Успішна покупка ролі!",
            description=f"🎉 {ctx.author.mention}, ви успішно придбали **{item['name']}** за **{price}** EC!\n\n✅ **Роль успішно видано!**",
            color=discord.Color.blue()
        )
        embed.set_footer(text="ELITE RP | Автоматичний магазин ролей (Повідомлення зникне через 1 хв)")
        await ctx.send(embed=embed, delete_after=60)
    except Exception as e:
        await ctx.send(f"❌ Помилка при видачі ролі: {e}", delete_after=60)


# --- ТЕКСТОВА КОМАНДА !сервер ---
@bot.command(name="сервер")
async def text_server(ctx):
    guild = ctx.guild
    embed = discord.Embed(
        title=f"📌 Інформація про сервер: {guild.name}",
        color=discord.Color.gold()
    )
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
        
    created_at = guild.created_at.strftime("%d.%m.%Y о %H:%M")
    
    embed.add_field(name="👑 Власник сервера", value=guild.owner.mention if guild.owner else "Невідомо", inline=True)
    embed.add_field(name="👥 Учасників", value=f"**{guild.member_count}**", inline=True)
    embed.add_field(name="📅 Дата створення", value=created_at, inline=False)
    embed.add_field(name="💬 Текстові канали", value=str(len(guild.text_channels)), inline=True)
    embed.add_field(name="🔊 Голосові канали", value=str(len(guild.voice_channels)), inline=True)
    embed.add_field(name="🛡️ Ролей на сервері", value=str(len(guild.roles)), inline=True)
    embed.add_field(name="🚀 Рівень бусту", value=f"Рівень {guild.premium_tier} (Бустів: {guild.premium_subscription_count})", inline=False)
    
    embed.set_footer(text="ELITE RP | Офіційна інформаційна система")
    await ctx.send(embed=embed)


# --- КОМАНДИ ДЛЯ СОЦМЕРЕЖ (/links, !посилання, !соцмережі) ---
async def send_social_links(target):
    description_text = (
        "🎮 **ELITE RP** — онлайн-гра про Україну! 🇺🇦\n"
        "Приєднуйся до нашої спільноти та створюй власну історію разом із нами!\n\n"
        f"🔷 **Сайт:** {URL_SITE}\n"
        f"🔷 **Форум:** {URL_FORUM}\n"
        f"📢 **Telegram-канал:** {URL_TG_CHANNEL}\n"
        f"💬 **Telegram-чат:** {URL_TG_CHAT}\n"
        f"🛡️ **Telegram-бот:** {URL_TG_BOT}\n"
        f"🎵 **TikTok:** {URL_TIKTOK}\n"
        f"📸 **Instagram:** {URL_INSTAGRAM}\n\n"
        "🔹 Підписуйся на наші соціальні мережі, спілкуйся з учасниками та дізнавайся першим про новини, оновлення й події проєкту!"
    )

    embed = discord.Embed(
        title="🌐 СОЦІАЛЬНІ МЕРЕЖІ | ELITE RP",
        description=description_text,
        color=discord.Color.blue()
    )
    embed.set_footer(text="ELITE RP | Офіційні посилання")

    if isinstance(target, discord.Interaction):
        await target.response.send_message(embed=embed)
    else:
        await target.send(embed=embed, delete_after=60)

@bot.tree.command(name="links", description="Показати всі офіційні посилання та соцмережі проєкту")
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

# --- СЛЕШ-КОМАНДИ МОДЕРАЦІЇ ТА ЕКОНОМІКИ ---
@bot.tree.command(name="help", description="Показати список команд модерації та економіки")
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(title="📜 Меню команд модерації та економіки", color=discord.Color.blue())
    embed.add_field(name="`!givecoins [@гравець] [кількість]`", value="👑 Видати Elite Coins (тільки для Власника)", inline=False)
    embed.add_field(name="`!бонус` або `!daily`", value="Отримати щоденні безкоштовні EC", inline=False)
    embed.add_field(name="`!магазин` або `!shop`", value="Переглянути магазин Discord-ролей", inline=False)
    embed.add_field(name="`!купити [номер]`", value="Купити роль у магазині", inline=False)
    embed.add_field(name="`!дуель [@гравець] [ставка]`", value="Зіграти в дуель на EC з іншим гравцем", inline=False)
    embed.add_field(name="`!ранг`", value="Перевірити свій ранг, баланс EC та активність", inline=False)
    embed.add_field(name="`/links` або `!посилання`", value="Показати всі соціальні мережі проєкту", inline=False)
    embed.add_field(name="`!сервер`", value="Отримати всю інформацію про сервер", inline=False)
    embed.add_field(name="`/clear [кількість]`", value="Очистити чат від повідомлень", inline=False)
    embed.add_field(name="`/mute` / `/unmute` / `/kick` / `/ban`", value="Команди модерації", inline=False)
    embed.set_footer(text="ELITE RP | Економічна система")
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

@bot.tree.command(name="poll", description="Створити голосування для гравців")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(question="Питання для голосування")
async def slash_poll(interaction: discord.Interaction, question: str):
    embed = discord.Embed(
        title="📊 Офіційне голосування",
        description=question,
        color=discord.Color.gold()
    )
    embed.set_footer(text="ELITE RP | Опитування спільноти")

    await interaction.response.send_message("✅ Голосування створено!", ephemeral=True)
    message = await interaction.channel.send(embed=embed)
    await message.add_reaction("👍")
    await message.add_reaction("👎")

@bot.tree.command(name="roll", description="Кинути кубик (випадкове число)")
@app_commands.describe(max_num="Максимальне число (за замовчуванням 100)")
async def slash_roll(interaction: discord.Interaction, max_num: int = 100):
    if max_num < 1:
        await interaction.response.send_message("❌ Число повинно бути більше 0!", ephemeral=True)
        return

    result = random.randint(1, max_num)
    embed = discord.Embed(
        title="🎲 Кидок кубика",
        description=f"{interaction.user.mention} викинув число **{result}** (з {max_num})!",
        color=discord.Color.purple()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

# --- КОМАНДА ДЛЯ ПОСИЛАННЯ НА ФОРУМ ---
@bot.tree.command(name="форум", description="Отримати посилання на офіційний форум ELITE RP")
async def slash_forum(interaction: discord.Interaction):
    view = discord.ui.View()
    forum_button = discord.ui.Button(
        label="Перейти на форум", 
        url=URL_FORUM,
        style=discord.ButtonStyle.link
    )
    view.add_item(forum_button)

    embed = discord.Embed(
        title="🌐 Офіційний форум ELITE RP",
        description="Натисніть кнопку нижче, щоб перейти на наш форум!",
        color=discord.Color.blue()
    )
    embed.set_footer(text="ELITE RP | Інформаційна система")

    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@bot.command(name="форум")
async def text_forum(ctx):
    view = discord.ui.View()
    forum_button = discord.ui.Button(
        label="Перейти на форум", 
        url=URL_FORUM,
        style=discord.ButtonStyle.link
    )
    view.add_item(forum_button)

    embed = discord.Embed(
        title="🌐 Офіційний форум ELITE RP",
        description="Натисніть кнопку нижче, щоб перейти на наш форум!",
        color=discord.Color.blue()
    )
    embed.set_footer(text="ELITE RP | Інформаційна система")

    try:
        await ctx.message.delete()
    except Exception:
        pass

    await ctx.send(embed=embed, view=view, delete_after=60)

# --- ЗАПУСК БОТА ---
if __name__ == '__main__':
    TOKEN = os.getenv("DISCORD_TOKEN")
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("Помилка: Не знайдено змінну середовища DISCORD_TOKEN!")
