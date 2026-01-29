# Naviplay Python API Guidelines

## Setting Up the API

```python
client = NavidromeClient(
    base_url="url",
    username="username",
    password="strongpassword",
    client="appName",
    cache_path="cache/file/path.json"
)
```

### Important

You **must** call:

```python
await client.quick_init()
```

This initializes the cache and other essential internal systems. Most API calls will not work correctly without this step.

---

## Getting Songs

### Get All Song IDs

```python
songs = await client.get_all_songs()
```

Returns a list of **all song IDs** from your Navidrome server.

⚠️ **Warning**: This fetches *every album* and then *every song* within each album. Large libraries may take a noticeable amount of time to load.

---

### Get a Song Name by ID

```python
name = await client.get_song_name_by_id(song_id)
```

Returns the human‑readable song name for the given `song_id`.

---

## Playing Songs

### Stream a Single Song

```python
await client.get_song_stream(song_id, output)
```

#### What This Does

* Starts streaming the requested song to the specified output

---

### Stream All Songs (Queued Playback)

```python
await client.get_songs_stream(song_id, output)
```

#### What This Does

* Starts streaming the requested song
* Automatically builds a queue from **all available songs**
* Preloads the *next* song in the queue
* Automatically streams the next song when the current one finishes

---

### Output Modes

The `output` parameter controls how audio data is handled:

```python
STREAM_OUTPUT  # Returns an async generator
CLI_OUTPUT     # Writes audio data to stdout
FILE_OUTPUT    # Writes audio data to temp/output.mp3
```

✅ **Recommended**: Always use these constants. Internal output handling may change in future versions.

📌 **Note**
Naviplay does **not** perform audio playback. These functions only provide raw audio data. It is the caller’s responsibility to decode and play the output.

---


## Working with Playlists

Naviplay provides helpers for listing playlists, inspecting their contents, and streaming them in order.

> ⚠️ **Important**
> Playlist APIs rely on cached data. Ensure you have called:
>
> ```python
> await client.quick_init()
> ```
>
> before using any playlist‑related methods.

---

### Get All Playlists

```python
playlists = await client.get_all_playlists()
```

#### What This Does

* Fetches **all playlists** available to the user
* Stores playlist metadata in the internal cache
* Returns raw playlist data as provided by Navidrome

---

### Get Playlist Data

```python
playlist = await client.get_playlist_data(playlist_id)
```

#### What This Does

* Fetches detailed information about a specific playlist
* Includes playlist name, song IDs, and metadata
* Updates the internal cache entry for that playlist

---

### Get Songs from a Playlist

```python
songs = await client.get_songs_from_playlist(playlist_id)
```

#### What This Does

* Returns a list of **song IDs** belonging to the playlist
* Uses cached playlist data when available
* Falls back to a server request if required

---

## Streaming Playlists

### Stream a Playlist Starting from a Specific Song

```python
async for chunk in client.stream_playlist(
    first_song_id,
    playlist_id,
    output=STREAM_OUTPUT
):
    ...
```

#### What This Does

* Streams **all songs in the playlist**
* Starts playback from `first_song_id`
* Continues streaming remaining songs in playlist order
* Supports all standard output modes

If `first_song_id` is **not** part of the playlist, Naviplay will:

* Emit a warning
* Ignore the starting position
* Stream the playlist from the beginning

---

### Output Modes (Playlists)

The `output` parameter behaves identically to single‑song streaming:

```python
STREAM_OUTPUT  # Async generator (recommended)
CLI_OUTPUT     # Writes audio data to stdout
FILE_OUTPUT    # Writes audio data to temp/output.mp3
```

📌 **Note**
When using `FILE_OUTPUT`, the output file is **reset** before streaming begins.

---

## Notes & Behavior Details

* Playlists are streamed **song‑by‑song**
* Audio data is yielded or written in real time
* Naviplay performs **no decoding or playback**
* The consumer is responsible for playback, decoding, or further processing

---

## Developer API (Incomplete)

This section is intended for contributors or developers modifying Naviplay internals.

### `_get_all_songs`

```python
async def _get_all_songs(self, progress: bool = False)
```

#### Description

* Returns a list of all songs **exactly as provided by the Navidrome server**
* Stores the result in the internal cache:

  ```python
  self.songs
  ```

#### How It Works

1. Fetches all albums from the server
2. Fetches all songs for each album
3. Aggregates them into a single list

The optional `progress` flag is reserved for future UI or CLI feedback during long‑running fetch operations.

