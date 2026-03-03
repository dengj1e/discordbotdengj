import discord
from discord import app_commands
import logging
import asyncio
import yt_dlp
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

music_queues: dict[int, list[dict]] = {} # each key entry is a server id with its own queue
now_playing: dict[int, dict] = {} # hold the current song
chat_histories: dict[int, list[dict]] = {} # each user has their own chat history


YDL_OPTIONS = {
    "format": "bestaudio/best",    
    "noplaylist": True,           
    "quiet": True,                
    "no_warnings": True,
    "default_search": "ytsearch",
}

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


def get_queue(guild_id: int) -> list[dict]:
    """Get or create a queue for a server."""
    if guild_id not in music_queues:
        music_queues[guild_id] = []
    return music_queues[guild_id]


async def search_song(query: str) -> dict | None:
    """Search YouTube and return song info."""
    loop = asyncio.get_event_loop()
    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
        try:
            # Run in a thread so it doesn't block the bot
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(query, download=False))
            # grab the first search result
            if "entries" in info:
                info = info["entries"][0]
            return {"title": info["title"], "url": info["url"], "webpage_url": info["webpage_url"]}
        except Exception as e:
            logger.error(f"yt-dlp error: {e}")
            return None


def play_next(client: discord.Client, guild_id: int, voice_client: discord.VoiceClient):
    """Play the next song in the queue."""
    queue = get_queue(guild_id)
    if queue:
        song = queue.pop(0)
        now_playing[guild_id] = song 
        source = discord.FFmpegPCMAudio(song["url"], **FFMPEG_OPTIONS)
        voice_client.play(source, after=lambda e: play_next(client, guild_id, voice_client))
    elif voice_client.is_connected():
        # Queue is empty, disconnect after a short delay
        asyncio.run_coroutine_threadsafe(voice_client.disconnect(), client.loop)
        music_queues.pop(guild_id, None)


def register_commands(client: discord.Client, tree: app_commands.CommandTree, gemini_api_key: str):

    gemini_client = genai.Client(api_key=gemini_api_key)
    
    # enable we search with gemini
    grounding_tool = types.Tool(
        google_search=types.GoogleSearch()
    )

    config = types.GenerateContentConfig(
        tools=[grounding_tool]
    )
    
    # General Commands
    @tree.command(name="ping", description="Check bot latency")
    async def ping(interaction: discord.Interaction):
        latency = round(client.latency * 1000)
        await interaction.response.send_message(f"latency {latency}ms")


    @tree.command(name="help", description="list of commands")
    async def hello(interaction: discord.Interaction):
        await interaction.response.send_message(
            f"general commands\n"
            f"/ping - get bot latency\n"
            f"/serverinfo - get number of members, channels, and when server was created\n"
            f"/avatar - get users avatar\n"
            "\n"
            f"music commands\n"
            f"/play - play a song from youtube, url or search\n"
            f"/skip - skip current song\n"
            f"/queue - view current queue\n"
            f"/pause - pause current song\n"
            f"/resume - resume current song\n"
            f"/stop - stop playing, clear queue and exit\n"
            f"/nowplaying - info about the current song\n"
            "\n"
            f"ai commands\n"
            f"/ask - ask gemini 2.5 flash something\n"
            f"/clearchat - clear user chat history\n")


    @tree.command(name="serverinfo", description="Get server info")
    async def serverinfo(interaction: discord.Interaction):
        guild = interaction.guild
        embed = discord.Embed(title=guild.name, color=discord.Color.blurple())
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="Members", value=guild.member_count, inline=True)
        embed.add_field(name="Channels", value=len(guild.channels), inline=True)
        embed.add_field(name="Created", value=guild.created_at.strftime("%b %d, %Y"), inline=True)
        await interaction.response.send_message(embed=embed)


    @tree.command(name="avatar", description="Get a user's avatar")
    @app_commands.describe(user="The user to get the avatar of")
    async def avatar(interaction: discord.Interaction, user: discord.Member = None):
        user = user or interaction.user
        embed = discord.Embed(title=f"{user.display_name}'s Avatar", color=discord.Color.blurple())
        embed.set_image(url=user.display_avatar.url)
        await interaction.response.send_message(embed=embed)


    # Music Commands
    @tree.command(name="play", description="Play a song from YouTube")
    @app_commands.describe(query="Song name or YouTube URL")
    async def play(interaction: discord.Interaction, query: str):
        # Check if user is in a voice channel
        if not interaction.user.voice:
            await interaction.response.send_message("Join a voice channel first", ephemeral=True)
            return

        await interaction.response.defer()  # Searching takes time

        # Search for the song
        song = await search_song(query)
        if not song:
            await interaction.followup.send("Couldn't find that song")
            return

        voice_channel = interaction.user.voice.channel

        # Connect to voice if not already
        voice_client = interaction.guild.voice_client
        if not voice_client:
            voice_client = await voice_channel.connect()
        elif voice_client.channel != voice_channel:
            await voice_client.move_to(voice_channel)

        # If something is already playing, add to queue
        if voice_client.is_playing():
            queue = get_queue(interaction.guild.id)
            queue.append(song)
            embed = discord.Embed(
                title="Added to Queue",
                description=f"[{song['title']}]({song['webpage_url']})",
                color=discord.Color.yellow()
            )
            embed.add_field(name="Position", value=f"#{len(queue)}")
            await interaction.followup.send(embed=embed)
        else:
            now_playing[interaction.guild.id] = song
            source = discord.FFmpegPCMAudio(song["url"], **FFMPEG_OPTIONS)
            
            # when the audio stops for any reason, run play_next()
            voice_client.play(source, after=lambda e: play_next(client, interaction.guild.id, voice_client))
            embed = discord.Embed(
                title="Now Playing",
                description=f"[{song['title']}]({song['webpage_url']})",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed)


    @tree.command(name="skip", description="Skip the current song")
    async def skip(interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if not voice_client or not voice_client.is_playing():
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return

        song = now_playing.get(interaction.guild.id)
        if song:
            embed = discord.Embed(
                title="Skipping",
                description=f"[{song['title']}]({song['webpage_url']})",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message("Skipped")

        voice_client.stop()


    @tree.command(name="queue", description="Show the music queue")
    async def queue(interaction: discord.Interaction):
        q = get_queue(interaction.guild.id)
        if not q:
            await interaction.response.send_message("Queue is empty.", ephemeral=True)
            return

        songs = "\n".join([f"**{i+1}.** {s['title']}" for i, s in enumerate(q[:10])])
        if len(q) > 10:
            songs += f"\n...and {len(q) - 10} more"

        embed = discord.Embed(title="Music Queue", description=songs, color=discord.Color.blue())
        await interaction.response.send_message(embed=embed)


    @tree.command(name="pause", description="Pause the current song")
    async def pause(interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_playing():
            voice_client.pause()
            await interaction.response.send_message("Paused")
        else:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)


    @tree.command(name="resume", description="Resume the paused song")
    async def resume(interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_paused():
            voice_client.resume()
            await interaction.response.send_message("Resumed")
        else:
            await interaction.response.send_message("Nothing is paused", ephemeral=True)


    @tree.command(name="stop", description="Stop music and clear the queue")
    async def stop(interaction: discord.Interaction):
        try:
            await interaction.response.defer()

            voice_client = interaction.guild.voice_client
            if not voice_client:
                await interaction.followup.send("Not in a voice channel.")
                return

            music_queues.pop(interaction.guild.id, None)
            now_playing.pop(interaction.guild.id, None)
            await interaction.followup.send("Stopped and disconnected.")
            if voice_client.is_playing() or voice_client.is_paused():
                voice_client.stop()
            await voice_client.disconnect()
        except Exception as e:
            logger.error(f"Stop command error: {e}")


    @tree.command(name="nowplaying", description="Show what's currently playing")
    async def nowplaying(interaction: discord.Interaction):
        song = now_playing.get(interaction.guild.id)
        if not song:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Currently Playing",
            description=f"[{song['title']}]({song['webpage_url']})",
            color=discord.Color.pink()
        )
        queue = get_queue(interaction.guild.id)
        if queue:
            embed.add_field(name="Up Next", value=queue[0]["title"], inline=False)
        await interaction.response.send_message(embed=embed)


    # ai gemini commands
    @tree.command(name="ask", description="Ask Gemini AI a question")
    @app_commands.describe(question="Your question")
    async def ask(interaction: discord.Interaction, question: str):
        await interaction.response.defer()

        user_id = interaction.user.id

        # if no history
        if user_id not in chat_histories:
            chat_histories[user_id] = []

        chat_histories[user_id].append({
            "role": "user",
            "parts": [{"text": question}]
        })

        # Send full history to Gemini so it remembers context
        response = await asyncio.to_thread(
            gemini_client.models.generate_content,
            model="gemini-2.5-flash",
            contents=chat_histories[user_id],
            config=config,
        )

        answer = response.text

        # Save the AI's response to history
        chat_histories[user_id].append({
            "role": "model",
            "parts": [{"text": answer}]
        })

        # Cap history at 20 messages to avoid token limits
        if len(chat_histories[user_id]) > 20:
            chat_histories[user_id] = chat_histories[user_id][-20:]

        # Discord has a 2000 character limit
        if len(answer) > 2000:
            answer = answer[:1997] + "..."

        await interaction.followup.send(answer)



    @tree.command(name="clearchat", description="Clear your AI chat history")
    async def clearchat(interaction: discord.Interaction):
        chat_histories.pop(interaction.user.id, None)
        await interaction.response.send_message("Chat history cleared", ephemeral=True)


    @tree.error
    async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("Missing Permissions error", ephemeral=True)
        elif isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(f"Command On Cooldown error {error.retry_after:.0f}s.", ephemeral=True)
        else:
            logger.error(f"Command error: {error}")
            if not interaction.response.is_done():
                await interaction.response.send_message("error", ephemeral=True)