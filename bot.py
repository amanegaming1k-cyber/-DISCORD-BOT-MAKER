
import os
import asyncio
from datetime import datetime, timedelta, timezone
from collections import defaultdict, deque
from threading import Thread

import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask, jsonify

# ==========================================
# AG BOT MAKER - CONFIGURATION
# ==========================================

TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
GUILD_ID = os.getenv("GUILD_ID", "").strip()

BOT_NAME = "AG BOT MAKER"
BOT_VERSION = "2.0.0"

# ==========================================
# RENDER HEALTH CHECK
# ==========================================

app = Flask(__name__)


@app.get("/")
def home():
    return jsonify({
        "service": BOT_NAME,
        "status": "running",
        "version": BOT_VERSION
    })


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


def run_web_server():
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port, use_reloader=False)


# ==========================================
# DISCORD BOT SETUP
# ==========================================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None
)

# In-memory warning storage
warnings_db = defaultdict(list)

# Anti-spam tracking
message_history = defaultdict(deque)
SPAM_LIMIT = 6
SPAM_WINDOW = 8


# ==========================================
# RESPONSE HELPER
# ==========================================

async def respond(
    interaction: discord.Interaction,
    message=None,
    ephemeral=True,
    **kwargs
):
    if interaction.response.is_done():
        await interaction.followup.send(
            content=message,
            ephemeral=ephemeral,
            **kwargs
        )
    else:
        await interaction.response.send_message(
            content=message,
            ephemeral=ephemeral,
            **kwargs
        )


def make_embed(title, description, color=discord.Color.blurple()):
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text=f"{BOT_NAME} • v{BOT_VERSION}")
    return embed


def bot_can_moderate(member: discord.Member, target: discord.Member):
    if target.id == member.guild.owner_id:
        return False

    if target.id == member.id:
        return False

    if target.top_role >= member.top_role:
        return False

    return True


# ==========================================
# BOT EVENTS
# ==========================================

@bot.event
async def on_ready():
    print("=" * 40)
    print(f"{BOT_NAME} is online!")
    print(f"Logged in as: {bot.user}")
    print(f"Bot ID: {bot.user.id}")
    print(f"Discord.py: {discord.__version__}")
    print("=" * 40)

    try:
        if GUILD_ID:
            guild_object = discord.Object(id=int(GUILD_ID))
            bot.tree.copy_global_to(guild=guild_object)
            synced = await bot.tree.sync(guild=guild_object)
            print(f"Guild commands synced: {len(synced)}")
        else:
            synced = await bot.tree.sync()
            print(f"Global commands synced: {len(synced)}")
    except Exception as error:
        print(f"Command sync error: {error}")

    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="AG ANIME UNIVERSE"
        )
    )


@bot.event
async def on_member_join(member: discord.Member):
    if member.bot:
        return

    channel = discord.utils.get(
        member.guild.text_channels,
        name="welcome"
    )

    if channel:
        embed = make_embed(
            "Welcome to the server!",
            f"Welcome {member.mention} to **{member.guild.name}**!\n"
            f"You are member **#{member.guild.member_count}**."
        )

        if member.guild.icon:
            embed.set_thumbnail(url=member.guild.icon.url)

        await channel.send(embed=embed)


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        await bot.process_commands(message)
        return

    # Basic anti-spam
    now = datetime.now(timezone.utc)
    history = message_history[message.author.id]

    while history and (now - history[0]).total_seconds() > SPAM_WINDOW:
        history.popleft()

    history.append(now)

    if len(history) >= SPAM_LIMIT:
        history.clear()

        try:
            await message.delete()
        except discord.HTTPException:
            pass

        if message.channel.permissions_for(
            message.guild.me
        ).manage_messages:
            try:
                await message.channel.send(
                    f"{message.author.mention}, please slow down.",
                    delete_after=5
                )
            except discord.HTTPException:
                pass

    await bot.process_commands(message)


@bot.event
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError
):
    if isinstance(error, app_commands.MissingPermissions):
        message = "You do not have permission to use this command."

    elif isinstance(error, app_commands.BotMissingPermissions):
        message = "I am missing the required permissions."

    elif isinstance(error, app_commands.CommandOnCooldown):
        message = f"Please wait {error.retry_after:.1f} seconds."

    else:
        original = getattr(error, "original", error)
        print(f"Slash command error: {original}")
        message = "An error occurred while running this command."

    try:
        await respond(interaction, message, ephemeral=True)
    except discord.HTTPException:
        pass


# ==========================================
# BASIC COMMANDS
# ==========================================

@bot.tree.command(name="ping", description="Check bot response time")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    embed = make_embed(
        "Pong!",
        f"**Latency:** {latency} ms\n"
        f"**Status:** Online",
        discord.Color.green()
    )
    await respond(interaction, embed=embed)


@bot.tree.command(name="botinfo", description="Show bot information")
async def botinfo(interaction: discord.Interaction):
    embed = make_embed(
        "AG BOT MAKER",
        f"**Version:** {BOT_VERSION}\n"
        f"**Library:** discord.py\n"
        f"**Servers:** {len(bot.guilds)}\n"
        f"**Latency:** {round(bot.latency * 1000)} ms\n"
        f"**Status:** Online",
        discord.Color.blue()
    )

    if bot.user:
        embed.set_thumbnail(url=bot.user.display_avatar.url)

    await respond(interaction, embed=embed)


@bot.tree.command(name="serverinfo", description="Show server information")
@app_commands.guild_only()
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild

    embed = make_embed(
        f"{guild.name} - Server Info",
        f"**Members:** {guild.member_count}\n"
        f"**Text channels:** {len(guild.text_channels)}\n"
        f"**Voice channels:** {len(guild.voice_channels)}\n"
        f"**Roles:** {len(guild.roles)}\n"
        f"**Created:** <t:{int(guild.created_at.timestamp())}:D>",
        discord.Color.blue()
    )

    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    await respond(interaction, embed=embed)


@bot.tree.command(name="help", description="Show available commands")
async def help_command(interaction: discord.Interaction):
    embed = make_embed(
        "AG BOT MAKER - Commands",
        "**General**\n"
        "`/ping` — Check bot latency\n"
        "`/botinfo` — Bot information\n"
        "`/serverinfo` — Server information\n"
        "`/help` — Show this help\n\n"
        "**Setup**\n"
        "`/setup` — Create basic server channels\n\n"
        "**Moderation**\n"
        "`/warn` — Warn a member\n"
        "`/warnings` — View warnings\n"
        "`/clearwarnings` — Clear warnings\n"
        "`/timeout` — Timeout a member\n"
        "`/kick` — Kick a member\n"
        "`/ban` — Ban a member\n"
        "`/clear` — Delete messages",
        discord.Color.purple()
    )

    await respond(interaction, embed=embed)


# ==========================================
# SERVER SETUP COMMAND
# ==========================================

@bot.tree.command(
    name="setup",
    description="Create basic community channels and categories"
)
@app_commands.guild_only()
@app_commands.checks.has_permissions(manage_channels=True)
async def setup(interaction: discord.Interaction):
    guild = interaction.guild

    await respond(
        interaction,
        "Setting up the server. Please wait...",
        ephemeral=True
    )

    created = []

    # Public category
    public_category = discord.utils.get(
        guild.categories,
        name="COMMUNITY"
    )

    if public_category is None:
        public_category = await guild.create_category("COMMUNITY")
        created.append("COMMUNITY")

    public_channels = [
        ("welcome", "Welcome and member updates"),
        ("rules", "Community rules"),
        ("announcements", "Official announcements"),
        ("general-chat", "General community chat"),
        ("media", "Share images and videos")
    ]

    for channel_name, topic in public_channels:
        existing = discord.utils.get(
            guild.text_channels,
            name=channel_name
        )

        if existing is None:
            await guild.create_text_channel(
                channel_name,
                category=public_category,
                topic=topic
            )
            created.append(channel_name)

    # Private staff category
    staff_category = discord.utils.get(
        guild.categories,
        name="STAFF"
    )

    if staff_category is None:
        bot_member = guild.me

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False
            )
        }

        if bot_member:
            overwrites[bot_member] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True
            )

        staff_category = await guild.create_category(
            "STAFF",
            overwrites=overwrites
        )
        created.append("STAFF")

    staff_log = discord.utils.get(
        guild.text_channels,
        name="mod-logs"
    )

    if staff_log is None:
        await guild.create_text_channel(
            "mod-logs",
            category=staff_category,
            topic="Moderation logs"
        )
        created.append("mod-logs")

    result = (
        "Setup completed.\n\n"
        + (
            "**Created:** " + ", ".join(created)
            if created
            else "All requested channels already existed."
        )
        + "\n\n**Important:** Check STAFF category permissions "
          "and grant access only to trusted moderators."
    )

    await interaction.followup.send(result, ephemeral=True)


# ==========================================
# WARNING COMMANDS
# ==========================================

@bot.tree.command(name="warn", description="Warn a server member")
@app_commands.guild_only()
@app_commands.checks.has_permissions(moderate_members=True)
async def warn(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str
):
    if not bot_can_moderate(interaction.user, member):
        await respond(
            interaction,
            "You cannot warn this member because of their role or status."
        )
        return

    entry = {
        "reason": reason,
        "moderator": interaction.user.id,
        "time": datetime.now(timezone.utc).isoformat()
    }

    warnings_db[(interaction.guild.id, member.id)].append(entry)

    embed = make_embed(
        "Member Warned",
        f"**Member:** {member.mention}\n"
        f"**Moderator:** {interaction.user.mention}\n"
        f"**Reason:** {reason}\n"
        f"**Total warnings:** "
        f"{len(warnings_db[(interaction.guild.id, member.id)])}",
        discord.Color.orange()
    )

    await respond(interaction, embed=embed)


@bot.tree.command(name="warnings", description="View a member's warnings")
@app_commands.guild_only()
@app_commands.checks.has_permissions(moderate_members=True)
async def warnings(
    interaction: discord.Interaction,
    member: discord.Member
):
    entries = warnings_db.get(
        (interaction.guild.id, member.id),
        []
    )

    if not entries:
        await respond(interaction, f"{member.mention} has no recorded warnings.")
        return

    lines = []

    for number, entry in enumerate(entries[-10:], start=1):
        lines.append(
            f"**{number}.** {entry['reason']}\n"
            f"Moderator ID: `{entry['moderator']}`"
        )

    embed = make_embed(
        f"Warnings: {member}",
        "\n\n".join(lines),
        discord.Color.orange()
    )

    await respond(interaction, embed=embed)


@bot.tree.command(
    name="clearwarnings",
    description="Clear a member's recorded warnings"
)
@app_commands.guild_only()
@app_commands.checks.has_permissions(moderate_members=True)
async def clearwarnings(
    interaction: discord.Interaction,
    member: discord.Member
):
    key = (interaction.guild.id, member.id)
    previous = len(warnings_db.get(key, []))
    warnings_db.pop(key, None)

    await respond(
        interaction,
        f"Cleared {previous} warning(s) for {member.mention}."
    )


# ==========================================
# TIMEOUT COMMAND
# ==========================================

@bot.tree.command(name="timeout", description="Timeout a member")
@app_commands.guild_only()
@app_commands.checks.has_permissions(moderate_members=True)
async def timeout(
    interaction: discord.Interaction,
    member: discord.Member,
    minutes: app_commands.Range[int, 1, 40320],
    reason: str = "No reason provided"
):
    if not bot_can_moderate(interaction.user, member):
        await respond(interaction, "You cannot timeout this member.")
        return

    if not interaction.guild.me.guild_permissions.moderate_members:
        await respond(interaction, "I need the Moderate Members permission.")
        return

    try:
        await member.timeout(
            timedelta(minutes=minutes),
            reason=f"{reason} | Moderator: {interaction.user}"
        )
        await respond(
            interaction,
            f"{member.mention} was timed out for {minutes} minute(s).\n"
            f"Reason: {reason}"
        )
    except discord.HTTPException as error:
        print(f"Timeout error: {error}")
        await respond(interaction, "Could not timeout that member.")


# ==========================================
# KICK COMMAND
# ==========================================

@bot.tree.command(name="kick", description="Kick a server member")
@app_commands.guild_only()
@app_commands.checks.has_permissions(kick_members=True)
async def kick(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str = "No reason provided"
):
    if not bot_can_moderate(interaction.user, member):
        await respond(interaction, "You cannot kick this member.")
        return

    if not interaction.guild.me.guild_permissions.kick_members:
        await respond(interaction, "I need the Kick Members permission.")
        return

    try:
        await member.kick(
            reason=f"{reason} | Moderator: {interaction.user}"
        )
        await respond(
            interaction,
            f"**{member}** was kicked.\nReason: {reason}"
        )
    except discord.HTTPException as error:
        print(f"Kick error: {error}")
        await respond(interaction, "Could not kick that member.")


# ==========================================
# BAN COMMAND
# ==========================================

@bot.tree.command(name="ban", description="Ban a server member")
@app_commands.guild_only()
@app_commands.checks.has_permissions(ban_members=True)
async def ban(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str = "No reason provided"
):
    if not bot_can_moderate(interaction.user, member):
        await respond(interaction, "You cannot ban this member.")
        return

    if not interaction.guild.me.guild_permissions.ban_members:
        await respond(interaction, "I need the Ban Members permission.")
        return

    try:
        await member.ban(
            reason=f"{reason} | Moderator: {interaction.user}"
        )
        await respond(
            interaction,
            f"**{member}** was banned.\nReason: {reason}"
        )
    except discord.HTTPException as error:
        print(f"Ban error: {error}")
        await respond(interaction, "Could not ban that member.")


# ==========================================
# CLEAR MESSAGES COMMAND
# ==========================================

@bot.tree.command(
    name="clear",
    description="Delete recent messages from this channel"
)
@app_commands.guild_only()
@app_commands.checks.has_permissions(manage_messages=True)
async def clear(
    interaction: discord.Interaction,
    amount: app_commands.Range[int, 1, 100]
):
    channel = interaction.channel

    if not isinstance(channel, discord.TextChannel):
        await respond(interaction, "Use this command in a text channel.")
        return

    if not interaction.guild.me.guild_permissions.manage_messages:
        await respond(interaction, "I need the Manage Messages permission.")
        return

    await respond(
        interaction,
        f"Deleting up to {amount} messages...",
        ephemeral=True
    )

    try:
        deleted = await channel.purge(limit=amount)
        await interaction.followup.send(
            f"Deleted {len(deleted)} message(s).",
            ephemeral=True
        )
    except discord.HTTPException as error:
        print(f"Clear error: {error}")
        await interaction.followup.send(
            "Could not delete messages.",
            ephemeral=True
        )


# ==========================================
# START BOT
# ==========================================

if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError(
            "DISCORD_TOKEN is missing. Set it in Render Environment Variables."
        )

    Thread(
        target=run_web_server,
        daemon=True
    ).start()

    bot.run(TOKEN, log_handler=None)
