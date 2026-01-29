import os
import sys
from dotenv import load_dotenv
import asyncio
from naviplay import NavidromeClient,STREAM_OUTPUT
import subprocess
async def main():
    load_dotenv()  # loads .env into os.environ

    base_url = os.getenv("NAVIDROME_URL")
    username = os.getenv("NAVIDROME_USER")
    password = os.getenv("NAVIDROME_PASS")
    client_name = os.getenv("NAVIDROME_CLIENT", "myscript")

    if not all([base_url, username, password]):
        print("❌ Missing Navidrome configuration.")
        print("Please set NAVIDROME_URL, NAVIDROME_USER, NAVIDROME_PASS")
        # sys.exit(1)

    client = NavidromeClient(
        base_url=base_url,
        username=username,
        password=password,
        client=client_name,
        cache_path="./cache.json"
    )
    await client.quick_init()
    songs = await client.get_all_songs()

    playlists = await client._get_all_playlists()
    p0 = playlists[0]
    
    pod = await client.get_playlist_data(p0)
    # print(pod)
    play_songs = await client.get_songs_from_playlist(p0)
    # print(play_songs)
    play_song = play_songs[0]
    song_name = await client.get_song_name_by_id(play_song)
    print(f"main.py: Playing song: {song_name}")
    proc = await asyncio.create_subprocess_exec(
    "ffplay",
    "-nodisp",
    "-autoexit",
    "-i",
    "pipe:0",
    stdin=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.DEVNULL,
    stdout=asyncio.subprocess.DEVNULL,
)

    stream = client.stream_playlist(play_song,p0,STREAM_OUTPUT)

    async for chunk in stream:
        proc.stdin.write(chunk)
        await proc.stdin.drain()   # <-- critical

    proc.stdin.close()
    await proc.wait()

if __name__ == "__main__":
    asyncio.run(main())
