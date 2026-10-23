import os
import asyncio
from datetime import timedelta, datetime, timezone
from collections import defaultdict, deque

import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask, jsonify
from threading import Thread

==============================

AG BOT MAKER - CONFIGURATION

==============================

TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
GUILD_ID = os.getenv("GUILD_ID", "").strip()

BOT_NAME = "AG BOT MAKER"
WELCOME_CHANNEL_NAME = "welcome"
LOG_CHANNEL_NAME = "mod-logs"

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

Demo warning storage: resets when the bot restarts.

warnings_store = defaultdict(list)

Basic anti-spam tracking, held in memory.

message_history = defaultdict(deque)
SPAM_LIMIT = 6
SPAM_WINDOW = 8

==============================

HEALTH CHECK FOR RENDER

==============================

app = Flask(name)

@app.get("/")
def home():
return jsonify({
"service": BOT_NAME,
"status": "running"
})

@app.get("/health")
def health():
return jsonify({"status": "ok"})

def run_web_server():
port = int(os.environ.get("PORT", "10000"))
app.run(host="0.0.0.0", port=port, use_reloader=False)

==============================

HELPERS

==============================

async def get_text_channel(guild, channel_name):
channel = discord.utils.get(
guild.text_channels,
name=channel_name
)
return channel

async def send_mod_log(guild, message):
channel = await get_text_channel(guild, LOG_CHANNEL_NAME)
if channel:
try:
await channel.send(message)
except discord.HTTPException:
pass

def is_moderator():
async def predicate(interaction: discord.Interaction):
if not interaction.guild or not isinstance(interaction.user, discord.Member):
raise app_commands.CheckFailure(
"এই কমান্ড শুধু সার্ভারে ব্যবহার করা যাবে।"
)

    if not (
        interaction.user.guild_permissions.manage_messages
        or interaction.user.guild_permissions.moderate_members
        or interaction.user.guild_permissions.administrator
    ):
        raise app_commands.CheckFailure(
            "এই কমান্ড ব্যবহারের জন্য Moderator permission প্রয়োজন।"
        )

    return True

return app_commands.check(predicate)

async def respond(interaction, message, ephemeral=True):
if interaction.response.is_done():
await interaction.followup.send(message, ephemeral=ephemeral)
else:
await interaction.response.send_message(message, ephemeral=ephemeral)

==============================

BOT EVENTS

==============================

@bot.event
async def on_ready():
print(f"Logged in as {bot.user} (ID: {bot.user.id})")

try:
    if GUILD_ID.isdigit():
        guild = discord.Object(id=int(GUILD_ID))
        synced = await bot.tree.sync(guild=guild)
        print(f"Synced {len(synced)} commands to guild {GUILD_ID}")
    else:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} global commands")
except Exception as exc:
    print(f"Command sync failed: {exc}")

await bot.change_presence(
    activity=discord.Activity(
        type=discord.ActivityType.watching,
        name="AG ANIME UNIVERSE"
    )
)

@bot.event
async def on_member_join(member):
channel = await get_text_channel(
member.guild,
WELCOME_CHANNEL_NAME
)

if channel:
    embed = discord.Embed(
        title="Welcome to AG ANIME UNIVERSE!",
        description=(
            f"Hello {member.mention}!\n"
            "Welcome to our anime community. Please read the rules."
        ),
        color=discord.Color.blurple(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=BOT_NAME)

    try:
        await channel.send(embed=embed)
    except discord.HTTPException:
        pass

@bot.event
async def on_message(message):
if message.author.bot or not message.guild:
return

# Basic anti-spam: deletes repeated rapid messages.
now = asyncio.get_running_loop().time()
history = message_history[message.author.id]

while history and now - history[0] > SPAM_WINDOW:
    history.popleft()

history.append(now)

if len(history) >= SPAM_LIMIT:
    try:
        await message.delete()
    except discord.HTTPException:
        pass

    if isinstance(message.author, discord.Member):
        if message.author.guild_permissions.manage_messages:
            return

        try:
            await message.author.timeout(
                timedelta(seconds=60),
                reason="Automatic anti-spam"
            )
            await send_mod_log(
                message.guild,
                f"Anti-spam: timed out {message.author.mention} for 60 seconds."
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

    history.clear()
    return

await bot.process_commands(message)

==============================

BASIC COMMANDS

==============================

@bot.tree.command(name="ping", description="Check bot response time")
async def ping(interaction: discord.Interaction):
latency = round(bot.latency * 1000)
await respond(interaction, f"Pong! 🏓 {latency} ms")

@bot.tree.command(name="botinfo", description="Show bot information")
async def botinfo(interaction: discord.Interaction):
embed = discord.Embed(
title=BOT_NAME,
description="Community management bot",
color=discord.Color.blurple()
)
embed.add_field(name="Servers", value=str(len(bot.guilds)))
embed.add_field(name="Latency", value=f"{round(bot.latency * 1000)} ms")
embed.set_footer(text="AG BOT MAKER")

await respond(interaction, embed=embed)

@bot.tree.command(name="serverinfo", description="Show this server's information")
async def serverinfo(interaction: discord.Interaction):
guild = interaction.guild

if not guild:
    await respond(interaction, "এই কমান্ড সার্ভারে ব্যবহার করুন।")
    return

embed = discord.Embed(
    title=guild.name,
    color=discord.Color.blurple()
)
embed.add_field(name="Members", value=str(guild.member_count or "Unknown"))
embed.add_field(name="Text channels", value=str(len(guild.text_channels)))
embed.add_field(name="Roles", value=str(len(guild.roles)))
embed.set_thumbnail(url=guild.icon.url if guild.icon else discord.Embed.Empty)

await respond(interaction, embed=embed)

==============================

AUTOMATIC SERVER SETUP

==============================

@bot.tree.command(name="setup", description="Create basic community channels and roles")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.guild_only()
async def setup(interaction: discord.Interaction):
await interaction.response.defer(ephemeral=True, thinking=True)

guild = interaction.guild
created = []

# Roles
role_specs = [
    ("Admin", discord.Color.red()),
    ("Moderator", discord.Color.orange()),
    ("Anime Fan", discord.Color.blurple()),
    ("Member", discord.Color.green()),
]

for role_name, color in role_specs:
    if not discord.utils.get(guild.roles, name=role_name):
        try:
            await guild.create_role(
                name=role_name,
                color=color,
                reason=f"{BOT_NAME} setup"
            )
            created.append(f"Role: {role_name}")
        except discord.Forbidden:
            created.append(f"Could not create role: {role_name}")

# Categories and channels
category_specs = {
    "INFORMATION": [
        "welcome",
        "rules",
        "announcements"
    ],
    "COMMUNITY": [
        "general-chat",
        "anime-discussion",
        "bot-commands"
    ],
    "STAFF": [
        "mod-logs"
    ]
}

for category_name, channel_names in category_specs.items():
    category = discord.utils.get(
        guild.categories,
        name=category_name
    )

    if not category:
        try:
            category = await guild.create_category(
                category_name,
                reason=f"{BOT_NAME} setup"
            )
            created.append(f"Category: {category_name}")
        except discord.Forbidden:
            created.append(f"Could not create category: {category_name}")
            continue

    for channel_name in channel_names:
        if discord.utils.get(guild.text_channels, name=channel_name):
            continue

        try:
            await guild.create_text_channel(
                channel_name,
                category=category,
                reason=f"{BOT_NAME} setup"
            )
            created.append(f"Channel: #{channel_name}")
        except discord.Forbidden:
            created.append(f"Could not create channel: #{channel_name}")

result = "\n".join(created[:35]) if created else "সব প্রয়োজনীয় channel ও role আগে থেকেই আছে।"

await interaction.followup.send(
    f"**Setup complete**\n{result}\n\n"
    "নোট: STAFF category-র permissions হাতে পরীক্ষা করে নিন।",
    ephemeral=True
)

==============================

MODERATION COMMANDS

==============================

@bot.tree.command(name="warn", description="Warn a member")
@app_commands.describe(member="Member to warn", reason="Reason for warning")
@app_commands.checks.has_permissions(moderate_members=True)
@app_commands.guild_only()
async def warn(
interaction: discord.Interaction,
member: discord.Member,
reason: str
):
if member.bot or member.id == interaction.user.id:
await respond(interaction, "এই সদস্যকে warn করা যাবে না।")
return

warnings_store[(interaction.guild_id, member.id)].append({
    "reason": reason,
    "moderator": interaction.user.id,
    "time": datetime.now(timezone.utc).isoformat()
})

await respond(
    interaction,
    f"{member.mention}-কে warn করা হয়েছে। কারণ: {reason}"
)

await send_mod_log(
    interaction.guild,
    f"⚠️ {member.mention} warned by {interaction.user.mention}. Reason: {reason}"
)

@bot.tree.command(name="warnings", description="View a member's warnings")
@app_commands.describe(member="Member to check")
@app_commands.checks.has_permissions(moderate_members=True)
@app_commands.guild_only()
async def warnings(
interaction: discord.Interaction,
member: discord.Member
):
records = warnings_store[(interaction.guild_id, member.id)]

if not records:
    await respond(interaction, f"{member.display_name}-এর কোনো সংরক্ষিত warning নেই।")
    return

lines = [
    f"{index}. {record['reason']}"
    for index, record in enumerate(records, start=1)
]

await respond(
    interaction,
    f"**{member.display_name}-এর Warnings**\n" + "\n".join(lines[:20])
)

@bot.tree.command(name="clearwarnings", description="Clear a member's warnings")
@app_commands.describe(member="Member whose warnings should be cleared")
@app_commands.checks.has_permissions(moderate_members=True)
@app_commands.guild_only()
async def clearwarnings(
interaction: discord.Interaction,
member: discord.Member
):
warnings_store.pop((interaction.guild_id, member.id), None)
await respond(interaction, f"{member.mention}-এর warning তালিকা পরিষ্কার করা হয়েছে।")

@bot.tree.command(name="timeout", description="Temporarily timeout a member")
@app_commands.describe(
member="Member to timeout",
minutes="Duration in minutes",
reason="Reason for timeout"
)
@app_commands.checks.has_permissions(moderate_members=True)
@app_commands.guild_only()
async def timeout_member(
interaction: discord.Interaction,
member: discord.Member,
minutes: app_commands.Range[int, 1, 10080],
reason: str
):
if member.bot or member.id == interaction.user.id:
await respond(interaction, "এই সদস্যকে timeout করা যাবে না।")
return

try:
    await member.timeout(
        timedelta(minutes=minutes),
        reason=reason
    )
    await respond(
        interaction,
        f"{member.mention}-কে {minutes} মিনিট timeout করা হয়েছে।"
    )
    await send_mod_log(
        interaction.guild,
        f"⏱️ {member.mention} timed out by {interaction.user.mention}. Reason: {reason}"
    )
except discord.Forbidden:
    await respond(interaction, "Permission নেই। Bot-এর role hierarchy ও permissions পরীক্ষা করুন।")
except discord.HTTPException:
    await respond(interaction, "Timeout করা যায়নি। আবার চেষ্টা করুন।")

@bot.tree.command(name="kick", description="Kick a member from the server")
@app_commands.describe(member="Member to kick", reason="Reason")
@app_commands.checks.has_permissions(kick_members=True)
@app_commands.guild_only()
async def kick_member(
interaction: discord.Interaction,
member: discord.Member,
reason: str
):
if member.bot or member.id == interaction.user.id:
await respond(interaction, "এই সদস্যকে kick করা যাবে না।")
return

try:
    await member.kick(reason=reason)
    await respond(interaction, f"{member.display_name}-কে সার্ভার থেকে kick করা হয়েছে।")
    await send_mod_log(
        interaction.guild,
        f"👢 {member} kicked by {interaction.user.mention}. Reason: {reason}"
    )
except discord.Forbidden:
    await respond(interaction, "Permission নেই। Bot-এর role hierarchy পরীক্ষা করুন।")
except discord.HTTPException:
    await respond(interaction, "Kick করা যায়নি।")

@bot.tree.command(name="ban", description="Ban a member from the server")
@app_commands.describe(member="Member to ban", reason="Reason")
@app_commands.checks.has_permissions(ban_members=True)
@app_commands.guild_only()
async def ban_member(
interaction: discord.Interaction,
member: discord.Member,
reason: str
):
if member.bot or member.id == interaction.user.id:
await respond(interaction, "এই সদস্যকে ban করা যাবে না।")
return

try:
    await member.ban(reason=reason)
    await respond(interaction, f"{member.display_name}-কে ban করা হয়েছে।")
    await send_mod_log(
        interaction.guild,
        f"🔨 {member} banned by {interaction.user.mention}. Reason: {reason}"
    )
except discord.Forbidden:
    await respond(interaction, "Permission নেই। Bot-এর role hierarchy পরীক্ষা করুন।")
except discord.HTTPException:
    await respond(interaction, "Ban করা যায়নি।")

@bot.tree.command(name="clear", description="Delete recent messages in this channel")
@app_commands.describe(amount="Number of messages to delete, 1–100")
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.guild_only()
async def clear(
interaction: discord.Interaction,
amount: app_commands.Range[int, 1, 100]
):
channel = interaction.channel

if not isinstance(channel, discord.TextChannel):
    await respond(interaction, "এই কমান্ড শুধু text channel-এ ব্যবহার করুন।")
    return

await interaction.response.defer(ephemeral=True, thinking=True)

try:
    deleted = await channel.purge(limit=amount)
    await interaction.followup.send(
        f"{len(deleted)}টি message মুছে ফেলা হয়েছে।",
        ephemeral=True
    )
except discord.Forbidden:
    await interaction.followup.send(
        "Message মুছতে permission নেই।",
        ephemeral=True
    )

==============================

COMMAND ERROR HANDLING

==============================

@bot.tree.error
async def on_app_command_error(
interaction: discord.Interaction,
error: app_commands.AppCommandError
):
if isinstance(error, app_commands.MissingPermissions):
message = "এই কমান্ড ব্যবহারের permission আপনার নেই।"
elif isinstance(error, app_commands.CheckFailure):
message = str(error) or "এই কমান্ড ব্যবহার করার অনুমতি নেই।"
else:
print(f"Command error: {error}")
message = "কমান্ড চালাতে সমস্যা হয়েছে। Bot logs পরীক্ষা করুন।"

try:
    await respond(interaction, message)
except discord.HTTPException:
    pass

==============================

START

==============================

if name == "main":
if not TOKEN:
raise RuntimeError(
"DISCORD_TOKEN সেট করা নেই। Render Environment Variables-এ সেট করুন।"
)

Thread(target=run_web_server, daemon=True).start()
bot.run(TOKEN)
