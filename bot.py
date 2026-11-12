import os
import re
import json
import random
import asyncio
import threading
import collections
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler

import discord
from discord.ext import commands, tasks
from discord import app_commands
import yt_dlp
import imageio_ffmpeg

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

# --- НАЛАШТУВАННЯ МУЗИКИ (YT-DLP + FFMPEG) ---
FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)
music_queues = collections.defaultdict(collections.deque)

# --- ЗБЕРЕЖЕННЯ ТА ЗАВАНТАЖЕННЯ ДАНИХ (JSON) ---
DATA_FILE = "data.json"

user_messages = collections.defaultdict(int)
user_voice_seconds = collections.defaultdict(int)
user_coins = collections.defaultdict(int)
user_exp = collections.defaultdict(int)

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
            print("💾 Дані успішно завантажено з data.json!")
        except Exception as e:
            print(f"Помилка читання data.json: {e}")

def save_data():
    try:
        data = {
            "messages": {str(k): v for k, v in user_messages.items()},
            "voice": {str(k): v for k, v in user_voice_seconds.items()},
            "coins": {str(k): v for k, v in user_coins.items()},
            "exp": {str(k): v for k, v in user_exp.items()}
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


# --- 🎵 МУЗИЧНИЙ МОДУЛЬ ---

async def search_audio(query):
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, lambda: ytdl.extract_info(query, download=False))
    if 'entries' in data:
        if not data['entries']:
            return None
        data = data['entries'][0]
    return {
        'url': data['url'],
        'title': data.get('title', 'Невідомий трек'),
        'webpage_url': data.get('webpage_url', query)
    }

def play_next_in_queue(ctx):
    guild_id = ctx.guild.id
    if music_queues[guild_id]:
        next_track = music_queues[guild_id].popleft()
        voice_client = ctx.guild.voice_client
        if voice_client and voice_client.is_connected():
            source = discord.FFmpegPCMAudio(next_track['url'], executable=FFMPEG_PATH, **FFMPEG_OPTIONS)
            voice_client.play(source, after=lambda e: play_next_in_queue(ctx))
            asyncio.run_coroutine_threadsafe(
                ctx.send(f"🎶 Зараз грає: **[{next_track['title']}]({next_track['webpage_url']})**", delete_after=60),
                bot.loop
            )

@bot.command(name="play", aliases=["p", "грати", "музика"])
async def play_music(ctx, *, query: str = None):
    try:
        await ctx.message.delete()
    except Exception:
        pass

    if not query:
        await ctx.send("❌ Вкажіть посилання або назву пісні: `!play [посилання/назва]`", delete_after=6)
        return

    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("❌ Зайдіть у голосовий канал, щоб увімкнути музику!", delete_after=6)
        return

    voice_channel = ctx.author.voice.channel
    voice_client = ctx.guild.voice_client

    if not voice_client:
        voice_client = await voice_channel.connect()
    elif voice_client.channel != voice_channel:
        await voice_client.move_to(voice_channel)

    status_msg = await ctx.send(f"🔎 Шукаю: `{query}`...")

    try:
        track = await search_audio(query)
        if not track:
            await status_msg.edit(content="❌ Нічого не знайдено за вашим запитом!", delete_after=6)
            return

        if voice_client.is_playing() or voice_client.is_paused():
            music_queues[ctx.guild.id].append(track)
            await status_msg.edit(content=f"➕ Додано в чергу: **{track['title']}**", delete_after=30)
        else:
            source = discord.FFmpegPCMAudio(track['url'], executable=FFMPEG_PATH, **FFMPEG_OPTIONS)
            voice_client.play(source, after=lambda e: play_next_in_queue(ctx))
            await status_msg.edit(content=f"🎶 Зараз грає: **[{track['title']}]({track['webpage_url']})**", delete_after=60)
    except Exception as e:
        await status_msg.edit(content=f"❌ Помилка відтворення: майданчик заблокував доступ або посилання недійсне.", delete_after=8)
        print(f"Помилка музики: {e}")

@bot.command(name="skip", aliases=["s", "пропустити"])
async def skip_music(ctx):
    try:
        await ctx.message.delete()
    except Exception:
        pass

    voice_client = ctx.guild.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.stop()
        await ctx.send("⏭️ Трек пропущено!", delete_after=10)
    else:
        await ctx.send("❌ Зараз нічого не грає.", delete_after=5)

@bot.command(name="pause", aliases=["пауза"])
async def pause_music(ctx):
    try:
        await ctx.message.delete()
    except Exception:
        pass

    voice_client = ctx.guild.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.pause()
        await ctx.send("⏸️ Музику поставлено на паузу.", delete_after=10)

@bot.command(name="resume", aliases=["продовжити"])
async def resume_music(ctx):
    try:
        await ctx.message.delete()
    except Exception:
        pass

    voice_client = ctx.guild.voice_client
    if voice_client and voice_client.is_paused():
        voice_client.resume()
        await ctx.send("▶️ Відтворення продовжено!", delete_after=10)

@bot.command(name="stop", aliases=["leave", "стоп"])
async def stop_music(ctx):
    try:
        await ctx.message.delete()
    except Exception:
        pass

    music_queues[ctx.guild.id].clear()
    voice_client = ctx.guild.voice_client
    if voice_client:
        await voice_client.disconnect()
        await ctx.send("⏹️ Музику зупинено, бот вийшов із войсу.", delete_after=10)

@bot.command(name="queue", aliases=["q", "черга"])
async def show_queue(ctx):
    try:
        await ctx.message.delete()
    except Exception:
        pass

    queue = music_queues[ctx.guild.id]
    if not queue:
        await ctx.send("📭 Черга треків порожня.", delete_after=10)
        return

    desc = "\n".join([f"**{i}.** {t['title']}" for i, t in enumerate(list(queue)[:10], 1)])
    embed = discord.Embed(title="🎵 Черга відтворення", description=desc, color=discord.Color.blue())
    await ctx.send(embed=embed, delete_after=30)


# --- СИСТЕМА ЛОГУВАННЯ ---

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
async def on_member_update(before: discord.Member, after: discord.Member):
    guild = after.guild

    if before.roles != after.roles:
        added_roles = [r for r in after.roles if r not in before.roles]
        removed_roles = [r for r in before.roles if r not in after.roles]

        for role in added_roles:
            await send_log(guild, "Видача ролі", f"Користувачу {after.mention} видано роль **{role.name}**.", discord.Color.green())
        
        for role in removed_roles:
            await send_log(guild, "Зняття ролі", f"З користувача {after.mention} знято роль **{role.name}**.", discord.Color.red())

    if before.nick != after.nick:
        old_nick = before.nick or before.name
        new_nick = after.nick or after.name
        await send_log(guild, "Зміна нікнейма", f"Користувач {after.mention} змінив нікнейм:\nСтарий: `{old_nick}`\nНовий: `{new_nick}`", discord.Color.purple())


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
                if user_voice_seconds[member.id] % 300 == 0:
                    user_coins[member.id] += 5

@tasks.loop(minutes=1)
async def activity_loop():
    global stats_message_id
    save_data()
    poland_time = datetime.utcnow() + timedelta(hours=1)

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
    user_exp[author_id] += 15
    
    earned_ec = 1
    if message.attachments:
        earned_ec += 3

    user_coins[author_id] += earned_ec
    save_data()

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
    
    await ctx.send(content=f"🕒 <t:{int(datetime.utcnow().timestamp())}:T>", embed=embed, delete_after=60)


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
    embed.add_field(name="`!play [назва/посилання]`", value="Увімкнути музику у войсі", inline=False)
    embed.add_field(name="`!skip` / `!pause` / `!resume` / `!stop`", value="Керування плеєром", inline=False)
    embed.add_field(name="`!queue`", value="Переглянути чергу треків", inline=False)
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
