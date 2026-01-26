
# NaviPlay Linux

**NaviPlay Linux** is a third-party **Python client library** for interacting with a **Navidrome** music server via the Subsonic-compatible API.
It is designed as the backend/core for NaviPlay clients on **Linux** (and later Android).

> **Disclaimer:**
> Navidrome is a trademark of its respective owners.
> NaviPlay is **not affiliated with or endorsed by Navidrome**.

---

## Features

* ✅ Full Subsonic/Navidrome API authentication
* 🎵 Fetch all albums and songs from a Navidrome server
* 📀 Album & song metadata access
* ▶️ Stream songs in chunks (generator-based)
* ⬇️ Automatic local caching & downloading of frequently played songs
* 🖼 Download and cache cover art
* 🧠 Smart cache invalidation using server library timestamps
* 🐍 Simple, hackable Python API

---

## Project Scope

NaviPlay Linux is **not a full music player UI** by itself.
It is a **library** intended to be used by:

* GUI music players (PyQt / Tkinter / etc.)
* CLI tools
* Background services
* Future NaviPlay Android client

---

## Installation

Clone the repository and install dependencies:

```bash
git clone https://github.com/yourname/naviplay-linux.git
cd naviplay-linux
pip install -r requirements.txt
```

> Requires **Python 3.9+**

Dependencies:

* `requests`

---

## Basic Usage

```python
from naviplay import NavidromeClient

client = NavidromeClient(
    base_url="http://localhost:4533/rest",
    username="admin",
    password="yourpassword",
    cache_path="cache.json"
)

songs = client.get_all_songs()
print(f"Loaded {len(songs)} songs")
```

---

## Streaming Audio

Stream a song as raw bytes (perfect for piping to ffplay, PyAudio, etc.):

```python
for chunk in client.get_bit_stream("Song Title"):
    audio_player.write(chunk)
```

The client will:

* Track play counts
* Automatically download songs after multiple plays
* Use the local cached file when available

---

## Cover Art

Get cover art bytes for a song:

```python
cover_bytes = client.get_cover_art(song_id)
```

Cover art is cached automatically to disk.

---

## Caching Behavior

* Cache is stored in a JSON file (`cache_path`)
* Library changes are detected via Navidrome’s `lastModified` timestamp
* Songs are auto-downloaded after **5 plays**
* Cache tracks:

  * play count
  * download state
  * local file paths

---

## Directory Structure

```
.
├── cache.json
├── cache/
│   └── <cover_id>.bin
├── downloads/
│   └── <song_id>/
│       ├── <song_id>.bin
│       └── <cover_id>.bin
```

---

## API Overview

### Core Methods

* `get_all_songs()`
* `get_all_albums()`
* `get_album(album_id)`
* `get_songs_for_album(album_id)`
* `get_bit_stream(song_title)`
* `get_cover_art(song_id)`

---

## Known Limitations

* No playlist support (yet)
* No search API (planned)
* No transcoding controls
* Minimal error recovery

---

## Roadmap

* 🔍 Search support
* 📃 Playlist handling
* 📱 Android client
* 🎛 Better cache management
* ⚡ Async version (`aiohttp`)

---

## License

MIT License 
