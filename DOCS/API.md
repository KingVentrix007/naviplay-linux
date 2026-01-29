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

This returns a list of **all song IDs** from your Navidrome server.

⚠️ **Warning**: This fetches *every album* and then *every song* within each album. On large libraries, this may take some time.

---

### Get a Song Name by ID

```python
name = await client.get_song_name_by_id(song_id)
```

Returns the human-readable song name for the given `song_id`.

---

## Playing Songs

To play one song

await client.get_song_stream(song_id,output)

### What This Does

* Starts streaming of the requested song to the current output

To play all songs:

```python
await client.get_songs_stream(song_id, output)
```

### What This Does

* Starts streaming of the requested song to the current output
* Automatically builds a queue from **all available songs**
* Preloads the *next* song in the queue
* Automatically streams the next song when the current one finishes

### Output Modes

The `output` parameter controls how audio data is handled:

```python
STREAM_OUTPUT  # Returns an async generator
CLI_OUTPUT     # Writes audio data to stdout
FILE_OUTPUT    # Writes to a file: temp/output.mp3
```

✅ **Recommended**: Always use these constants. Internal output handling may change in future versions.

**Note**: It is up to to the user to play the output. As these functions only provide the songs data

---

## Developer API

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

The optional `progress` flag can be used for future UI or CLI feedback during long fetch operations.
