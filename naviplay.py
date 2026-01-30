from urllib.parse import urlencode
import hashlib, random
import json
import asyncio
import httpx
import os
import aiofiles
import sys
import warnings
import logging
from typing import AsyncIterator

STREAM_OUTPUT = "007stream007"
CLI_OUTPUT = "007client007"
FILE_OUTPUT = "007file007"


# Create a dedicated logger for your app
logger = logging.getLogger("naviplay")
logger.setLevel(logging.DEBUG)  # or INFO

# Prevent it from propagating to the root logger
logger.propagate = False

# Create a file handler
fh = logging.FileHandler("naviplay.log", mode='w')
fh.setLevel(logging.DEBUG)

# Create a formatter and add it to the handler
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')
fh.setFormatter(formatter)

# Add the handler to your logger
logger.addHandler(fh)



class NavidromeClient:
    def __init__(
        self,
        base_url,
        username,
        password,
        client="myscript",
        version="1.16.1",
        page_size=500,
        timeout=10,
        cache_path=None
    ):
        self.base_url:str = base_url.rstrip("/")
        self.username:str = username
        self.password:str = password
        self.client:str = client
        self.version:str = version
        self.page_size:int = page_size
        self.timeout:int = timeout
        self.songs:list = []
        self.cache_path:str = cache_path
        self.cache_data:dict = {}
        self.cache_loaded:bool = False
        self.que_list:list = []
        self.preloaded_song_id:str = "-1"
        self.preloaded_songs: dict[str, asyncio.Queue] = {}
        self.httpx_client:httpx.AsyncClient = None
        self.setup_client()
        self.cache_write_lock:asyncio.Lock =  asyncio.Lock()
    async def quick_init(self):
        # Sets up the cache
        self.cache_loaded = True
        await self._load_cache()
    def setup_client(self):
        if(self.httpx_client == None):
            self.httpx_client = httpx.AsyncClient()
    async def _save_cache(self):
        async with self.cache_write_lock:
            with open(self.cache_path,"w") as cache_file:
                if(self.cache_data == None):
                    warnings.warn(f"self.cache_data is None. This should not happen. Refusing to overwrite file {self.cache_path}",stacklevel=2)
                json.dump(
    self.cache_data,
    cache_file,
    indent=4,
    sort_keys=True
)
        
    def _auth_params(self) -> tuple[str, str]:
        # _auth_params creates a salt and token for authenticating with the Navidrome server
        salt = str(random.randint(1000, 9999))
        token = hashlib.md5((self.password + salt).encode()).hexdigest()
        return salt, token
    async def _call(self, endpoint:str, extra_params:dict={}) -> dict:
        salt, token = self._auth_params() # Get salt and token

        #Default parameters
        params = {
            "u": self.username,
            "t": token,
            "s": salt,
            "v": self.version,
            "c": self.client,
            "f": "json",
        }
        if extra_params != {}:
            # Add user parameters
            params.update(extra_params)
        
        url = f"{self.base_url}/{endpoint}.view?{urlencode(params)}" # create url
        
        r = await self.httpx_client.get(url) # make request

        data = r.json()["subsonic-response"] #  extract useful data
        if data.get("status") != "ok": # Check status
            raise RuntimeError(data.get("error", {}).get("message", "Unknown error")) # Error
 
        return data # return data
    
    async def _get_library_timestamp(self):
        #Get the last time the library as changed in as time from epoch
        try:
            resp = await self._call("getIndexes") # Request time from server
            return resp["indexes"].get("lastModified") # Return time since last modification
        except httpx.ConnectTimeout: # Catch timeout error
            logger.warning(f"Fetching index time from '{self.base_url}' failed. Assuming up to date cache")
            return -1 # Return "impossible" time
    
    async def _load_cache(self):
        #Loads the cache into self.cache_data
        if(self.cache_path == None): # Safety checks
            raise FileExistsError("Please Provide a cache path") 
        with open(self.cache_path,"r") as cache_file: # Open cache file
            try:
                logger.debug(f"Getting cache from cache file: {self.cache_path}")
                cache_data = json.load(cache_file) # Try load cache data
            except json.JSONDecodeError as je:
                #If it fails to decode, we assume that the cache is empty or corrupted and we make a new cache
                logger.warning(f"Error decoding cache_file. Treating as empty: {je}",)
                cache_data = {"lastUpdate":"-1","cachedSongs":{}}
        
        self.cache_data = cache_data
        if(self.cache_data != None): # Sanity checks
            await self._save_cache()
        else:
            logger.warning("self.cache_data is somehow None,",stacklevel=2)
        server_ts = int(await self._get_library_timestamp()) # Get server timestamp
        cache_ts  = int(self.cache_data["lastUpdate"]) # Get the caches last updated time
        if(server_ts == -1): # If its -1, the timestamp failed to be fetched from the server.
            logger.warning("Server timestamp is -1. This means the code failed to fetch the true timestamp from the server")
            server_ts = cache_ts # Treat it as if it is up to date
        logger.debug("Checking if cache is up to date")
        if abs(server_ts - cache_ts) < 2: # Check if the cache is up to date
            logger.debug("Cache is up to date. Parsing songs")
        else: # If not
            logger.debug("Cache is outdated. Updating")
            await self._get_all_songs(False) # Fetch ALL the songs, without providing terminal output
            await self._cache() # setup new cache from songs
        
    async def _cache(self):
        #creates a cache from the list of songs
        logger.debug("Creating cache....")
        for song in self.songs: # Loop through the songs
            artists = [] # List of artists for the song
            for art in song.get("artists",[]): # Get each artist
                artists.append(art.get("name")) # Store there human readable name
            if(self.cache_data["cachedSongs"].get(song.get("id","-1"),None) == None): # Check if song already exists in cache
                #If not
                timesPlayed = 0 # Has never been played
                downLoaded = False # is not downloaded
                cache_path = None # is not stored anywhere on disk
            else:
                # IF it does exist
                timesPlayed =  self.cache_data["cachedSongs"][song.get("id","-1")].get("timesPlayed",0) # Save times played
                downLoaded =  self.cache_data["cachedSongs"][song.get("id","-1")].get("downloaded",False) # Save download state
                cache_path =  self.cache_data["cachedSongs"][song.get("id","-1")].get("cache_path",False) # Save path where file is downloaded(cached)
            

            #Create cache entry
            cache_entry = {"title":song.get("title"),"id":song.get("id"),"coverArt":song.get("coverArt"),"artists":artists,"timesPlayed":timesPlayed,"downloaded":downLoaded,"cache_path":cache_path,"playlist":"-1"}
            self.cache_data["cachedSongs"][song.get("id","-1")] = cache_entry # Store in cache
        logger.debug("Updating cache timestamp")
        self.cache_data["lastUpdate"] = await self._get_library_timestamp() # Update timestamp
        if(self.cache_data != None): # Sanity check
            await self._save_cache() # Save the cache to disk
        else:
            logger.warning("self.cache_data is somehow None,",stacklevel=2)
        logger.debug("Cache is created")
        

    async def _update_timesPlayed(self,song_id:str) -> None:
        tp = int(self.cache_data["cachedSongs"][song_id].get("timesPlayed",0)) # Get current time played
        tp+=1 # update by 1
        downLoaded =  self.cache_data["cachedSongs"][song_id].get("downloaded",False) # Get download state
        if(tp > 5 and downLoaded == False): # if it is freqently played and not downloaded
            asyncio.create_task(self._download_song(song_id)) # Spawn new task and download
           

            
        self.cache_data["cachedSongs"][song_id]["timesPlayed"] = tp # Update times played
        
        if(self.cache_data != None): # Sanity check
            await self._save_cache() # Save cache to disk
        else:
            warnings.warn("self.cache_data is somehow None,",stacklevel=2)

    async def _download_song_cover(self,song_id:str,cache:bool=False) -> str|None:
        logger.debug(f"Downloading cover for song: {song_id}")
        song = self._get_song_by_id(song_id) # Get the song data
        if(song == None): # Check if song is valid
            return None
        cover_id = song.get("coverArt",None) # extract cover data

        #TODO replace with self._call
        server_params = self._get_server_parmas() # get server parameters
        server_params["id"] = cover_id # add cover id to parameters
        url = f"{self.base_url}/getCoverArt.view" # set url
        if(cache == False): # check if this is for cache #TODO Actually Implement this part. Currently on disk caching is 100% permanent
            d_path = f"downloads/{song_id}/{cover_id}.bin" # Store as .bin
        else:
            d_path = f"cache/{cover_id}.bin" # Store as .bin
            
        # Fetch
        async with self.httpx_client.stream("GET", url, params=server_params) as r:
            r.raise_for_status()
            with open(d_path, "wb") as f:
                async for chunk in r.aiter_bytes(8192):
                    f.write(chunk)
        # END OF SECTION THAT WILL BE REMOVED
        logger.debug(f"Cover download for sing {song_id} complete")
        return d_path # return download path
    

    async def _get_song_cover(self,song_id):
        #Get songs cover art from the song id, only used by caching code
        song = self._get_song_by_id(song_id) # Get the song data
        if(song == None): # Sanity check
            return None
        cover_id = song.get("coverArt",None) # Get the cover ID
        #TODO Add check for if cover_id is None
        c_path = f"downloads/{song_id}/{cover_id}.bin" # Create oath
        if(os.path.exists(c_path)): # Check if path exists
            return c_path # Return path
        else:
            if(os.path.exists("cache") != True): # Check if is cache dir exits
                os.mkdir(f"cache") # create it if not
            await self._download_song_cover(song_id=song_id,cache=True) # Download cover song into cache dir
            #TODO Make it return the path from _download_song_cover
            return  f"cache/{cover_id}.bin" # Return path
        
    async def _download_song(self,song_id:str) -> None:
        #Download the song into the download der
        logger.debug(f"Downloading song: {song_id}")
        #TODO Replace with _call
        stream_params = self._get_server_parmas() # Get server parameters
        stream_params["id"] = song_id # add song ID
        url = f"{self.base_url}/download.view" # Create URL
        if(os.path.exists(f"downloads/{song_id}")): # Check if the folder already exits
            pass
        else:
            os.mkdir(f"downloads/{song_id}") # IF not, create it
        d_path = f"downloads/{song_id}/{song_id}.bin" # Set download path, store as .bin, maybe will add more file types
        
        async with self.httpx_client.stream("GET", url, params=stream_params) as r: # Stream data to download
            r.raise_for_status()
            with open(d_path, "wb") as f:
                async for chunk in r.aiter_bytes(8192):
                    f.write(chunk) # Write to disk

            await self._download_song_cover(song_id) # Download the cover to the same dir
            logger.debug(f"Download Done for song: {song_id}") 
        self.cache_data["cachedSongs"][song_id]["downloaded"] = True # Update download state
        self.cache_data["cachedSongs"][song_id]["cache_path"] = d_path # Update download location
        if(self.cache_data != None): # Sanity check
            await self._save_cache() # Write cache to disk
        else:
            warnings.warn("self.cache_data is somehow None,",stacklevel=2)

        # return d_path
    def _get_server_parmas(self) -> dict:
        # Returns a dict of the common server parameters
        salt, token = self._auth_params() # Get auth details
        #TODO replace v and c with globals/vars
        stream_params = {
        "u": self.username,
        "t": token,
        "s": salt,
        "v": "1.16.1",
        "c": "mini-player",
    }
        return  stream_params # return parameters
    
    def _get_song_by_id(self,song_id:str)->dict|None:
        #Returns song data from song_id
        return self.cache_data["cachedSongs"].get(song_id,None)
    def _get_song_name_by_id(self,song_id:str)->dict|None:
        #Returns song name from song_id
        return self.cache_data["cachedSongs"].get(song_id,{"title":None}).get("title",None)
    
    def _is_downloaded(self,song_id:str) -> tuple[bool,str]| tuple[bool,None]:
        song = self._get_song_by_id(song_id) # Get the songs data
        if(song == None): # Check song exits
            return False,None
        if(song.get("downloaded",False) == True): # Get download state
            return True,song.get("cache_path",None) # Return download path if is downloaded
        return False,None
    
    async def _get_all_songs(self, progress=False):
        #Get every song from the server
        #TODO Add some form of optimization
        logger.debug("Getting ALL songs. See doc section '_get_all_songs'")
        all_songs = [] 
        albums = await self.get_all_albums() # Get all the albums

        if progress:
            logger.debug(f"Found {len(albums)} albums")

        for i, album in enumerate(albums, 1): # Loop through  all the albums
            songs = await self.get_songs_for_album(album["id"]) # Get each song from each album
            all_songs.extend(songs) # add songs tolist

            if progress:
                logger.debug(f"[{i}/{len(albums)}] {album['name']} → {len(songs)} songs")
        self.songs = all_songs # Update global var
        return all_songs # Return all the song
    
    async def _get_bit_stream(self, song_id:str, is_pre_pull:bool=False) ->  AsyncIterator[bytes]:

        # Get the bit-stream for a specific song, pre-pull dictates wether or not we are preloading songs
        logger.debug(f"Getting bit stream for: {song_id}")
        isdown, file = self._is_downloaded(song_id) # Check if song is downloaded and get path
        if isdown: # If is downloaded
            logger.debug(f"Using downloaded file for: {song_id}")
            with open(file, "rb") as f:
                while chunk := f.read(8192): #Read file
                    yield chunk # Return data
            return
        # Song is not downloaded
        #TODO Replace with _call
        stream_params = self._get_server_parmas() # get server parameters
        stream_params["id"] = song_id # Add song id to server parameters
        url = f"{self.base_url}/stream.view" # Create url

        if song_id in self.preloaded_songs and not is_pre_pull: # Check if we can use a preloaded song 
            logger.debug(f"Using preloaded song for: {song_id}")
            queue = self.preloaded_songs[song_id] # Get the que for this song

            while True:
                chunk = await queue.get() # read the data from the que
                if chunk is None:
                    break
                yield chunk

            logger.debug(f"Done playing Preloaded song: {song_id}")

            return

        try:
            #Song is either not preloaded or we are preloading a song
            async with  self.httpx_client.stream("GET", url, params=stream_params) as r: # Request data from server
                r.raise_for_status()
                async for chunk in r.aiter_bytes(8192): 
                    yield chunk # Return data
        except httpx.ReadTimeout: # Catch timeout errors
            if(is_pre_pull == True): # Check if we where preloading
                logger.warning(f"Preloading song [{song_id}] failed with ReadTimeout error to url: {url}. retrying...",stacklevel=2)
                try:
                    async with  self.httpx_client.stream("GET", url, params=stream_params) as r: # If preloading, tray again
                        r.raise_for_status()
                        async for chunk in r.aiter_bytes(8192):
                            yield chunk
                except httpx.ReadTimeout: # Failed again
                     logger.error(f"Preloading  song [{song_id}] failed with ReadTimeout error to url: {url} again. Check that server is online",stacklevel=2)#Error
                
            else:
                logger.error(f"Getting bit stream for song [{song_id}] failed with ReadTimeout error to url: {url}",stacklevel=2) # Failed to pull live song, playback crashes so throw error
        return
    
    async def _write_to_output_file(self,data:str,first_write:bool=False) -> bool:
        #Write song data to the output file
        #TODO Make this use a global constant or a variable
        if(first_write == True): # Overwrite file
            with open("temp/output.mp3","wb") as f:
                if(data == None):
                    return False
                f.write(data) 
            return True
        else: # Add data to file
            with open("temp/output.mp3","ab") as f:
                f.write(data)
            return True
    
    def _match_output(self,string:str)->tuple[str,str]|tuple[None,None]:
        # Attempt to match users output spec to constants
        if string.lower() in CLI_OUTPUT.lower():
            return CLI_OUTPUT,"cli"
        elif string.lower() in FILE_OUTPUT.lower():
            return FILE_OUTPUT,"file"
        elif string.lower() in STREAM_OUTPUT.lower():
            return STREAM_OUTPUT,"stream"
        else:
            return None,None

    def _validate_output_type(self,output:str) -> str:
        r_out = output
        #TODO, make "007" a var
        if(output[:3] != "007"): # Check if chosen output is a constant
            warnings.warn("You have used a string to specify the output. This is not recommend as we may change the output types at a future date. To future proof your code, please use on of the constants we made", stacklevel=2)
            out,t = self._match_output(r_out) # Check if we can match it to a constant
            if(out == None):
                warnings.warn(f"We tried to match you input '{output}' to one of our formats but failed. We are defaulting to file output. And because you obviously didn't read the docs. That outout it temp/song.mp3",stacklevel=2)
                r_out = FILE_OUTPUT # Default output(Safest)
            else:
                warnings.warn(f"We tried to match you input '{output}' to one of our formats and succeeded. You song data will be sent to output {t}. Was it worth being diffrent and ignoring the perfectly good, and future proofed constants we gave you? If you said yes, come back to this when your code stops working after a version update ",stacklevel=2)
        
                r_out = out
        return r_out
    

    async def _get_all_playlists(self)->list:
        # Gets a list of all the users playlists
        data = await self._call("getPlaylists") # Call server API to get playlists
        playlists_all_data =  data.get("playlists", {}).get("playlist", []) # Extract playlist data

        playlists = [] # list to store list od playlist IDs
        for p in playlists_all_data:
            playlists.append(p.get("id",'-1')) # append IDs to list
        if(playlists != []):# Check if playlist is empty
            return playlists # Return playlist
        else:
            #TODO Add some sort of error message
            return [] # Return empty list
       

    async def _get_playlist_data(self, playlist_id:str)->dict:
        if(playlist_id == "-1"): # Check playlist not invalid
            return {} # Return empty dict
        data = await self._call( 
            "getPlaylist",
            extra_params={"id": playlist_id}
        )# Call server api to get specific playlist data
        play_list_data = data["playlist"] # extract info from request
        cached_playlist_entry = self.cache_data.get("CachedPlaylists",{}) # Get current playlist cache
        cached_playlist_entry[playlist_id] = [] # add new entry
        tmp = cached_playlist_entry.get(playlist_id,[]) # add new list of songs to new entry
        for song in play_list_data.get("entry"):  # Loop through playlists songs got from API
             tmp.append(song.get("id","-1")) # add song to playlist(or -1 if something goes wrong)
        
        cached_playlist_entry[playlist_id] = tmp # Update entry
        self.cache_data["CachedPlaylists"] = cached_playlist_entry # Add entry to cache
        await self._save_cache() # Save cache
        return play_list_data # Return playlist data

    async def _get_songs_from_playlist(self,playlist_id:str,re_call:bool=False)->[]|None:
        cached_playlist_entry = self.cache_data.get("CachedPlaylists",{}) # Get playlist cache entry
        if(playlist_id in cached_playlist_entry): # Check if playlist is in cache
            pass
        else:
            if(re_call == False):
                #TODO Should probably add some sort of time check to see if playlist changed since last fetch
                await self._get_playlist_data(playlist_id,re_call = True) # Populate the cache with data for this playlist if not already cached
            else:
                return None # Return None
        songs = cached_playlist_entry.get(playlist_id,[]) # Get songs from playlist
        return songs # Return a list of song IDs

    # ---------- High-level API ----------
    #These are the APIs the user calls
    #TODO add each one to API.md
    
    
    async def get_all_albums(self) -> list:
        #Get all the albums
        #TODO Optimize this function
        albums = [] # list holding the albums
        offset = 0 # Current fetch offset

        while True: # Got until break
            resp = await self._call( 
                "getAlbumList2",
                {
                    "type": "alphabeticalByName",
                    "size": self.page_size, #Max albums to fetch
                    "offset": offset, # Current offset
                },
            )#Make call to API

            batch = resp["albumList2"].get("album", []) # Get data
            if not batch: # If batch is empty break
                break

            albums.extend(batch) # Extend list of albums
            offset += self.page_size # update offset

        return albums # Return album

    async def get_album(self, album_id:str)->dict:
        # Get one specific albums data
        resp = await self._call("getAlbum", {"id": album_id}) # API call
        return resp["album"] # Return album data

    async def get_songs_for_album(self, album_id:str)->list:
        # Get all the sings in the album
        album = await self.get_album(album_id) # Get album data
        return album.get("song", []) # Return list of songs. Note this is raw song data, not just IDs

    
    async def get_all_songs(self)->list:
        #Get all the songs from cache
        cachedSongs = self.cache_data.get("cachedSongs",{})#Extract cache data for songs
        if(cachedSongs == {}): # Cache is empty
            logger.warning("Cache is empty")
        else:
            songs = cachedSongs.keys() # Keys are song IDs
            return list(songs) # convert to list

    async def get_song_id(self,title:str)->str|None:
        #Get a songs id from tile
        warnings.warn("The 'warn' method is deprecated, "
            "use 'warning' instead", DeprecationWarning, 2)
        for song in self.songs: # loop through songs
            if(song.get("title","invalid") == title): # Direct title match, inaccurate
                return song.get("id",None) # Return ID or None
        return None # Couldn't find song
    

    async def get_cover_art(self,song_id:str)->bytes|None:
        # get the actual bytes of a songs cover art
        ca_file_path = self._get_song_cover(song_id) # Get path of song cover
        if(ca_file_path == None): # Check is not NULL
            return None
        with open(ca_file_path,"rb") as file: # Open to read byte
            return file.read() # Read the whole file
    def create_que(self,first_song_id:str)->None:
        #Creates a song que from ALL the songs, with first_song_id as first song
        #TODO Move to internal API.
        #TODO Add warning about heavy function
        temp_q = [first_song_id]
        for s in self.cache_data["cachedSongs"]: # Loop through cached songs
            if(s == first_song_id): # Skip fist song id
                continue
            temp_q.append(s) # Create que
        self.que_list = temp_q # make que accessible to all functions
    
    async def preload_next_song(self, song_id:str)->None:
        #Creates a queue for this specific song ID
        queue = asyncio.Queue() # Create asyncio Queue
        self.preloaded_songs[song_id] = queue # Add to preloaded songs queue
        logger.debug(f"Preloading song {song_id}")
        try:
            stream = self._get_bit_stream(song_id,is_pre_pull=True) # Stream song bites
            async for chunk in stream:
                await queue.put(chunk) # Add to queue
        finally:
            await queue.put(None) # Add none to spec end of queue

            logger.debug(f"Completed Preloading song: {song_id}")
    

    async def get_songs_stream(
    self,
    song_id: str,
    output: str = STREAM_OUTPUT
) -> Generator | None:
        """
        Streams a song and then continues streaming queued songs.
        
        - Supports multiple output modes:
            STREAM_OUTPUT : yields chunks (for HTTP / async streaming)
            CLI_OUTPUT    : writes raw bytes to stdout
            FILE_OUTPUT   : writes bytes to temp/output.mp3
        - Automatically preloads the next song in the queue.
        """

        # Validate and normalize the output type
        r_out = self._validate_output_type(output)

        # If output is a file, ensure it starts empty
        if r_out == FILE_OUTPUT:
            with open("temp/output.mp3", "wb") as f:
                f.write(b"")

        logger.debug(
            f"Streaming song: {song_id} to output: {output.replace('007','')}"
        )

        # Safety check: do nothing if no song ID was provided
        if song_id is None:
            return

        # Update play count / analytics for this song
        await self._update_timesPlayed(song_id)

        # Get async generator yielding audio chunks
        song_bit_stream = self._get_bit_stream(song_id)

        # Add this song to the playback queue
        self.create_que(song_id)

        # If there is a next song queued, preload it asynchronously
        if len(self.que_list) > 1:
            asyncio.create_task(
                self.preload_next_song(self.que_list[1])
            )

        # Stream the first song
        async for chunk in song_bit_stream:
            if r_out == STREAM_OUTPUT:
                yield chunk
            elif r_out == CLI_OUTPUT:
                sys.stdout.buffer.write(chunk)
            elif r_out == FILE_OUTPUT:
                await self._write_to_output_file(chunk)

        logger.debug(f"Done streaming song: {song_id}")

        # Stream remaining songs in the queue sequentially
        for x in range(1, len(self.que_list)):
            logger.debug(
                f"Streaming song: {song_id} to output: {output.replace('007','')}"
            )

            current_song_id = self.que_list[x]

            # Determine which song to preload next (if any)
            if x + 1 <= len(self.que_list):
                next_song_id = self.que_list[x + 1]
            else:
                next_song_id = -1  # Sentinel value for "no next song"

            # Preload next song without blocking playback
            asyncio.create_task(
                self.preload_next_song(next_song_id)
            )

            # Get stream for current queued song
            song_bit_stream = self._get_bit_stream(current_song_id)

            # Stream queued song
            async for chunk in song_bit_stream:
                if r_out == STREAM_OUTPUT:
                    yield chunk
                elif r_out == CLI_OUTPUT:
                    sys.stdout.buffer.write(chunk)
                elif r_out == FILE_OUTPUT:
                    await self._write_to_output_file(chunk)

            logger.debug(f"Done streaming song: {song_id}")


    async def get_song_stream(
        self,
        song_id: str,
        output: str = STREAM_OUTPUT
    ):
        """
        Streams a single song only (no queue handling).
        """

        r_out = self._validate_output_type(output)

        # Clear output file if writing to disk
        if r_out == FILE_OUTPUT:
            with open("temp/output.mp3", "wb") as f:
                f.write(b"")

        logger.debug(
            f"Streaming singular song: {song_id} to output: {output.replace('007','')}"
        )

        # Update play statistics
        await self._update_timesPlayed(song_id)

        # Safety check
        if song_id is None:
            return

        # Get async chunk stream
        song_bit_stream = self._get_bit_stream(song_id)

        # Stream song
        async for chunk in song_bit_stream:
            if r_out == STREAM_OUTPUT:
                yield chunk
            elif r_out == CLI_OUTPUT:
                sys.stdout.buffer.write(chunk)
            elif r_out == FILE_OUTPUT:
                await self._write_to_output_file(chunk)

        logger.debug(f"Done streaming song: {song_id}")


    async def get_song_name_by_id(self, song_id):
        """Returns the display name of a song by ID."""
        return self._get_song_name_by_id(song_id)


    async def get_all_playlists(self):
        """Returns metadata for all playlists."""
        return await self._get_all_playlists()


    async def get_playlist_data(self, playlist_id):
        """Returns playlist metadata and song list."""
        return await self._get_playlist_data(playlist_id)


    async def stream_playlist(
        self,
        first_song_id,
        playlist_id,
        output=STREAM_OUTPUT
    ):
        """
        Streams an entire playlist, starting from a given song.
        """

        r_out = self._validate_output_type(output)

        # Reset output file if needed
        if r_out == FILE_OUTPUT:
            with open("temp/output.mp3", "wb") as f:
                f.write(b"")

        # Fetch cached playlist song IDs
        songs_to_play_t = self.cache_data.get(
            "CachedPlaylists", {}
        ).get(playlist_id, [])

        # Handle case where requested starting song is not in playlist
        if first_song_id not in songs_to_play_t:
            warnings.warn(
                f"Sooo, this is awkward, but the song "
                f"{await self.get_song_name_by_id(first_song_id)} "
                f"isn't actually in this playlist. "
                f"We will just play the playlist anyway tho",
                stacklevel=2
            )
            songs_to_play = songs_to_play_t
        else:
            # Reorder playlist so it starts from first_song_id
            songs_to_play = [first_song_id]
            songs_to_play.remove(first_song_id)
            songs_to_play.extend(songs_to_play_t)

        # Sanity check
        if songs_to_play[0] != first_song_id:
            print("ERROR")

        # Stream each song in playlist order
        for current_song_id in songs_to_play:
            logger.debug(
                f"Streaming singular song: {current_song_id} "
                f"from playlist: {playlist_id} "
                f"to output: {output.replace('007','')}"
            )

            song_bit_stream = self._get_bit_stream(current_song_id)

            async for chunk in song_bit_stream:
                if r_out == STREAM_OUTPUT:
                    yield chunk
                elif r_out == CLI_OUTPUT:
                    sys.stdout.buffer.write(chunk)
                elif r_out == FILE_OUTPUT:
                    await self._write_to_output_file(chunk)

            logger.debug(
                f"Done streaming song: {current_song_id} "
                f"from playlist {playlist_id}"
            )


    async def get_songs_from_playlist(self, playlist_id):
        """Returns a list of song IDs belonging to a playlist."""
        return await self._get_songs_from_playlist(playlist_id)
