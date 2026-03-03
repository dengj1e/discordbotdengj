import discord
import os
import logging
from dotenv import load_dotenv
from commands import register_commands

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("Missing DISCORD_TOKEN in .env file.")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("Missing GEMINI_API_KEY in .env file.")

intents = discord.Intents.default()

client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(client)

# Register all slash commands from commands.py
register_commands(client, tree, GEMINI_API_KEY)

#Events
@client.event
async def on_ready():
    try:
        synced = await tree.sync()
        logger.info(f"Logged in as {client.user} (ID: {client.user.id})")
        logger.info(f"Synced {len(synced)} slash command(s)")
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}")


if __name__ == "__main__":
    client.run(TOKEN)