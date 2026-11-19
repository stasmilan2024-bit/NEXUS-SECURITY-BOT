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



# --- 🎮 МОНІТОРИНГ ОНЛАЙНУ MTA SERVER (51.75.44.12:22003) ---
MTA_SERVER_IP = "51.75.44.12"
MTA_SERVER_PORT = 22003
MTA_QUERY_PORT = 22126  # Стандартний ASE порт MTA:SA (game_port + 123)
MTA_HTTP_PORT = 22005   # Стандартний HTTP-порт MTA:SA (game_port + 2)
mta_last_online_str = "0/100"


def _query_mta_ase_sync(host: str, query_port: int, timeout: float = 1.2):
    """Запитує статус сервера MTA:SA через протокол ASE (UDP)."""
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(b"s", (host, query_port))
        data, _ = sock.recvfrom(8192)
        if not data or len(data) < 5:
            return None

        idx = 4 if data.startswith(b"EYE1") else 0
        payload = data[idx:]

        def read_str(buf, pos):
            if pos >= len(buf):
                return "", pos
            length = buf[pos]
            pos += 1
            if length <= 0:
                return "", pos
            end = min(len(buf), pos + length - 1)
            val = buf[pos:end].decode("latin-1", errors="ignore")
            return val, pos + length

        _, pos = read_str(payload, 0)       # game
        _, pos = read_str(payload, pos)      # port
        _, pos = read_str(payload, pos)      # name
        _, pos = read_str(payload, pos)      # gamemode
        _, pos = read_str(payload, pos)      # map
        _, pos = read_str(payload, pos)      # version
        _, pos = read_str(payload, pos)      # passworded

        if pos + 2 > len(payload):
            return None

        players = payload[pos]
        max_players = payload[pos + 1]
        if max_players <= 0 or max_players > 4096:
            return None
        return int(players), int(max_players)
    except Exception:
        return None
    finally:
        sock.close()


def _query_mta_http_sync(host: str, http_port: int, game_port: int, timeout: float = 1.5):
    """Запасний запит онлайну MTA через HTTP-порт сервера (якщо UDP заблокований хостингом)."""
    import urllib.request
    import xml.etree.ElementTree as ET

    urls = [
        f"http://{host}:{http_port}/",
        f"http://{host}:{http_port}/status/",
        f"http://{host}:{game_port}/",
    ]
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", errors="ignore")
                if not body:
                    continue
                # Спроба розпарсити XML або текстові поля MTA server info
                try:
                    root = ET.fromstring(body)
                    p_el = root.find(".//players") or root.find(".//online")
                    m_el = root.find(".//maxplayers") or root.find(".//max_players")
                    if p_el is not None and p_el.text and p_el.text.strip().isdigit():
                        players = int(p_el.text.strip())
                        max_players = int(m_el.text.strip()) if (m_el is not None and m_el.text and m_el.text.strip().isdigit()) else 100
                        return players, max_players
                except Exception:
                    pass

                m = re.search(r'(?:players|online)["\s:=<>/]+(\d+)\s*(?:/|of|out of)\s*(\d+)', body, re.IGNORECASE)
                if m:
                    return int(m.group(1)), int(m.group(2))
        except Exception:
            continue
    return None


async def get_mta_online_text() -> str:
    global mta_last_online_str
    loop = asyncio.get_running_loop()
    res = await loop.run_in_executor(None, _query_mta_ase_sync, MTA_SERVER_IP, MTA_QUERY_PORT, 1.2)
    if res is None:
        res = await loop.run_in_executor(None, _query_mta_ase_sync, MTA_SERVER_IP, MTA_SERVER_PORT, 1.2)
    if res is None:
        res = await loop.run_in_executor(None, _query_mta_http_sync, MTA_SERVER_IP, MTA_HTTP_PORT, MTA_SERVER_PORT, 1.5)
    if res is not None:
        players, max_players = res
        mta_last_online_str = f"{players}/{max_players}"
    return mta_last_online_str


async def update_bot_bio_online():
    """Оновлює статус/біо бота з поточним онлайном MTA та синхронізує Application Bio (якщо доступно)."""
    online_str = await get_mta_online_text()
    status_text = f"MTA: {online_str} гравців"
    try:
        activity = discord.Activity(type=discord.ActivityType.watching, name=status_text)
        await bot.change_presence(status=discord.Status.online, activity=activity)
    except Exception as e:
        print(f"Помилка оновлення статусу бота: {e}")

    # Спроба оновити опис (Bio) застосунку бота через Discord API, якщо підтримується
    try:
        app_info = await bot.application_info()
        bio_text = f"ELITE RP | Онлайн MTA ({MTA_SERVER_IP}:{MTA_SERVER_PORT}): {online_str}"
        await bot.http.request(
            discord.http.Route("PATCH", "/applications/{application_id}", application_id=app_info.id),
            json={"description": bio_text}
        )
    except Exception:
        pass

# --- ФОНОВІ ЗАДАЧІ ---
@tasks.loop(seconds=5)
async def mta_online_24_7_loop():
    await update_bot_bio_online()


@mta_online_24_7_loop.before_loop
async def before_mta_loop():
    await bot.wait_until_ready()


@tasks.loop(seconds=1)
async def voice_counter_loop():
    if not data_restored:
        return
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
    if not data_restored:
        return
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
        embed.set_footer(text=f"MTA ({MTA_SERVER_IP}:{MTA_SERVER_PORT}) онлайн: {mta_last_online_str} • Оновлено: {poland_time.strftime('%H:%M:%S')}")

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


@tasks.loop(minutes=5)
async def cloud_backup_loop():
    await sync_cloud_backup()


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

@cloud_backup_loop.before_loop
async def before_backup_loop():
    await bot.wait_until_ready()

@weekly_report_loop.before_loop
async def before_weekly_loop():
    await bot.wait_until_ready()


@bot.event
async def on_ready():
    print(f'Бот увійшов як {bot.user} і працює успішно!')
    await restore_data_from_discord()
    await update_bot_bio_online()
    bot.add_view(TicketPanelView())
    bot.add_view(AdminReplyView())
    await setup_ticket_panel()

    if not mta_online_24_7_loop.is_running():
        mta_online_24_7_loop.start()
    if not voice_counter_loop.is_running():
        voice_counter_loop.start()
    if not activity_loop.is_running():
        activity_loop.start()
    if not cloud_backup_loop.is_running():
        cloud_backup_loop.start()
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
    is_trusted = is_trusted_role_manager(message.guild, message.author)
    is_admin_or_mod = is_trusted or perms.administrator or perms.manage_messages or perms.kick_members or perms.ban_members

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

    if not is_trusted:
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

    if not is_trusted_role_manager(ctx.guild, ctx.author):
        await ctx.send("❌ Тільки для Власника або Заступника Власника!", delete_after=5)
        return

    if not member or amount <= 0:
        await ctx.send("❌ Використовуйте: `!givecoins @користувач кількість`", delete_after=6)
        return

    user_coins[member.id] += amount
    save_data()
    await sync_cloud_backup()
    embed = discord.Embed(title="💳 Нарахування EC", description=f"👑 {ctx.author.mention} нарахував **+{amount}** EC для {member.mention}!", color=discord.Color.gold())
    await ctx.send(embed=embed, delete_after=60)
    await send_log(ctx.guild, "Видача валюти", f"{ctx.author.mention} нарахував {amount} EC для {member.mention}.", discord.Color.gold())


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
    min_required_exp = exp_for_level(user_levels[user_id])
    if user_exp[user_id] < min_required_exp:
        user_exp[user_id] = min_required_exp
    total_exp = user_exp[user_id]
    calc_level, current_exp, max_exp = get_level_and_exp(total_exp)
    if calc_level > user_levels[user_id]:
        user_levels[user_id] = calc_level
    level = user_levels[user_id]

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
    await sync_cloud_backup()
    
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
        if executor.bot or is_trusted_role_manager(guild, executor):
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
        if executor.bot or is_trusted_role_manager(guild, executor):
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
        if executor.bot or is_trusted_role_manager(guild, executor):
            return

        now = datetime.now()
        role_delete_history[executor.id].append(now)
        role_delete_history[executor.id] = [t for t in role_delete_history[executor.id] if now - t < timedelta(seconds=10)]

        if len(role_delete_history[executor.id]) >= 2:
            await punish_rogue_admin(guild, executor, "Anti-Nuke: Масове видалення ролей")


@bot.tree.command(name="help", description="Доступні команди")
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(title="📜 Меню команд", color=discord.Color.blue())
    embed.add_field(name="`!givecoins`", value="Видати коїни (Власнику / Заступнику)", inline=False)
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
