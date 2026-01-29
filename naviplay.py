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
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.client = client
        self.version = version
        self.page_size = page_size
        self.timeout = timeout
        self.songs = []
        self.cache_path = cache_path
        self.cache_data = None
        self.cache_loaded = False
        self.que_list = []
        self.preloaded_song_id = None
        self.curr_preload_buffer = 1
        self.preloaded_songs: dict[str, asyncio.Queue] = {}
        self.httpx_client:httpx.AsyncClient = None
        self.setup_client()
        self.cache_write_lock =  asyncio.Lock()
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
                json.dump(self.cache_data,cache_file)
        
    def _auth_params(self):
        salt = str(random.randint(1000, 9999))
        token = hashlib.md5((self.password + salt).encode()).hexdigest()
        return salt, token
    async def _call(self, endpoint, extra_params=None):
        salt, token = self._auth_params()
        params = {
            "u": self.username,
            "t": token,
            "s": salt,
            "v": self.version,
            "c": self.client,
            "f": "json",
        }
        if extra_params:
            params.update(extra_params)
        url = f"{self.base_url}/{endpoint}.view?{urlencode(params)}"
        
        r = await self.httpx_client.get(url)

        data = r.json()["subsonic-response"]
        if data.get("status") != "ok":
            raise RuntimeError(data.get("error", {}).get("message", "Unknown error"))

        return data
    async def _get_library_timestamp(self):
        try:
            resp = await self._call("getIndexes")
            return resp["indexes"].get("lastModified")
        except httpx.ConnectTimeout:
            logger.warning(f"Fetching index time from '{self.base_url}' failed. Assuming up to date cache")
            return -1
    async def _load_cache(self):
        if(self.cache_path == None):
            raise FileExistsError("Please Provide a cache path")
        with open(self.cache_path,"r") as cache_file:
            try:
                logger.debug(f"Getting cache from cache file: {self.cache_path}")
                cache_data = json.load(cache_file)
            except json.JSONDecodeError as je:
                
                logger.warning(f"Error decoding cache_file. Treating as empty: {je}",)
                cache_data = {"lastUpdate":"-1","cachedSongs":{}}
        
        self.cache_data = cache_data
        if(self.cache_data != None):
            await self._save_cache()
        else:
            logger.warning("self.cache_data is somehow None,",stacklevel=2)
        server_ts = int(await self._get_library_timestamp())
        cache_ts  = int(self.cache_data["lastUpdate"])
        if(server_ts == -1):
            logger.warning("Server timestamp is -1. This means the code failed to fetch the true timestamp from the server")
            server_ts = cache_ts
        logger.debug("Checking if cache is up to date")
        if abs(server_ts - cache_ts) < 2:
            logger.debug("Cache is up to date. Parsing songs")
        else:
            logger.debug("Cache is outdated. Updating")
            await self._get_all_songs(False)
            await self._cache()
    async def _cache(self):
        logger.debug("Creating cache....")
        for song in self.songs:
            artists = []
            for art in song.get("artists",[]):
                artists.append(art.get("name"))
            if(self.cache_data["cachedSongs"].get(song.get("id","-1"),None) == None):
                timesPlayed = 0
                downLoaded = False
                cache_path = None
            else:
                timesPlayed =  self.cache_data["cachedSongs"][song.get("id","-1")].get("timesPlayed",0)
                downLoaded =  self.cache_data["cachedSongs"][song.get("id","-1")].get("downloaded",False)
                cache_path =  self.cache_data["cachedSongs"][song.get("id","-1")].get("cache_path",False)

            if(timesPlayed > 5 and downLoaded == False):
                pass
            cache_entry = {"title":song.get("title"),"id":song.get("id"),"coverArt":song.get("coverArt"),"artists":artists,"timesPlayed":timesPlayed,"downloaded":downLoaded,"cache_path":cache_path}
            self.cache_data["cachedSongs"][song.get("id","-1")] = cache_entry
        logger.debug("Updating cache timestamp")
        self.cache_data["lastUpdate"] = await self._get_library_timestamp()
        if(self.cache_data != None):
            await self._save_cache()
        else:
            logger.warning("self.cache_data is somehow None,",stacklevel=2)
        logger.debug("Cache is created")
        
    # def _load_cache(self):
    async def _update_timesPlayed(self,song_id):
        tp = int(self.cache_data["cachedSongs"][song_id].get("timesPlayed"))
        tp+=1
        downLoaded =  self.cache_data["cachedSongs"][song_id].get("downloaded",False)
        if(tp > 5 and downLoaded == False):
            asyncio.create_task(self._download_song(song_id))
            # self.cache_data["cachedSongs"][song_id]["downloaded"] = True
            # self.cache_data["cachedSongs"][song_id]["cache_path"] = d_path

            
        self.cache_data["cachedSongs"][song_id]["timesPlayed"] = tp
        
        if(self.cache_data != None):
            await self._save_cache()
        else:
            warnings.warn("self.cache_data is somehow None,",stacklevel=2)

    async def _download_song_cover(self,song_id,cache=False):
        logger.debug(f"Downloading cover for song: {song_id}")
        song = self._get_song_by_id(song_id)
        if(song == None):
            return None
        cover_id = song.get("coverArt",None)
        server_params = self._get_server_parmas()
        server_params["id"] = cover_id
        url = f"{self.base_url}/getCoverArt.view"
        if(cache == False):
            d_path = f"downloads/{song_id}/{cover_id}.bin"
        else:
            d_path = f"cache/{cover_id}.bin"
            
        # async with httpx.AsyncClient() as client:
            async with self.httpx_client.stream("GET", url, params=server_params) as r:
                r.raise_for_status()
                with open(d_path, "wb") as f:
                    async for chunk in r.aiter_bytes(8192):
                        f.write(chunk)
        logger.debug(f"Cover download for sing {song_id} complete")
        return d_path
    async def _get_song_cover(self,song_id):
        song = self._get_song_by_id(song_id)
        if(song == None):
            return None
        cover_id = song.get("coverArt",None)
        c_path = f"downloads/{song_id}/{cover_id}.bin"
        if(os.path.exists(c_path)):
            return c_path
        else:
            if(os.path.exists("cache") != True):
                os.mkdir(f"cache")
            await self._download_song_cover(song_id=song_id,cache=True)
            return  f"cache/{cover_id}.bin"
    async def _download_song(self,song_id):
        logger.debug(f"Downloading song: {song_id}")
        stream_params = self._get_server_parmas()
        stream_params["id"] = song_id
        url = f"{self.base_url}/download.view"
        if(os.path.exists(f"downloads/{song_id}")):
            pass
        else:
            os.mkdir(f"downloads/{song_id}")
        d_path = f"downloads/{song_id}/{song_id}.bin"
        
        async with self.httpx_client.stream("GET", url, params=stream_params) as r:
            r.raise_for_status()
            with open(d_path, "wb") as f:
                async for chunk in r.aiter_bytes(8192):
                    f.write(chunk)

            await self._download_song_cover(song_id)
            logger.debug(f"Download Done for song: {song_id}")
        self.cache_data["cachedSongs"][song_id]["downloaded"] = True
        self.cache_data["cachedSongs"][song_id]["cache_path"] = d_path
        if(self.cache_data != None):
            await self._save_cache()
        else:
            warnings.warn("self.cache_data is somehow None,",stacklevel=2)

        # return d_path
    def _get_server_parmas(self):
        salt, token = self._auth_params()
        stream_params = {
        "u": self.username,
        "t": token,
        "s": salt,
        "v": "1.16.1",
        "c": "mini-player",
    }
        return  stream_params
    def _get_song_by_id(self,song_id):
        return self.cache_data["cachedSongs"].get(song_id,None)
    def _get_song_name_by_id(self,song_id):
        return self.cache_data["cachedSongs"].get(song_id,{"title":None}).get("title",None)
    def _is_downloaded(self,song_id):
        song = self._get_song_by_id(song_id)
        if(song == None):
            return False,None
        if(song.get("downloaded",False) == True):
            return True,song.get("cache_path",None)
        return False,None
    
    

    # ---------- High-level API ----------
    
    
    async def get_all_albums(self):
        
        albums = []
        offset = 0

        while True:
            resp = await self._call(
                "getAlbumList2",
                {
                    "type": "alphabeticalByName",
                    "size": self.page_size,
                    "offset": offset,
                },
            )

            batch = resp["albumList2"].get("album", [])
            if not batch:
                break

            albums.extend(batch)
            offset += self.page_size

        return albums

    async def get_album(self, album_id):
        
        resp = await self._call("getAlbum", {"id": album_id})
        return resp["album"]

    async def get_songs_for_album(self, album_id):
        
        album = await self.get_album(album_id)
        return album.get("song", [])

    async def _get_all_songs(self, progress=False):
        logger.debug("Getting ALL songs. See doc section '_get_all_songs'")
        all_songs = []
        albums = await self.get_all_albums()

        if progress:
            logger.debug(f"Found {len(albums)} albums")

        for i, album in enumerate(albums, 1):
            songs = await self.get_songs_for_album(album["id"])
            all_songs.extend(songs)

            if progress:
                logger.debug(f"[{i}/{len(albums)}] {album['name']} → {len(songs)} songs")
        self.songs = all_songs
        return all_songs
    async def get_all_songs(self):
        cachedSongs = self.cache_data.get("cachedSongs",{})
        if(cachedSongs == {}):
            logger.warning("Cache is empty")
        else:
            songs = cachedSongs.keys()
            return list(songs)
    async def get_song_id(self,title):
        
        for song in self.songs:
            if(song.get("title","invalid") == title):
                return song.get("id",None)
    async def _get_bit_stream(self, song_id, is_pre_pull=False):
        logger.debug(f"Getting bit stream for: {song_id}")
        isdown, file = self._is_downloaded(song_id)
        if isdown:
            logger.debug(f"Using downloaded file for: {song_id}")
            with open(file, "rb") as f:
                while chunk := f.read(8192):
                    yield chunk
            return

        stream_params = self._get_server_parmas()
        stream_params["id"] = song_id
        url = f"{self.base_url}/stream.view"

        if song_id in self.preloaded_songs and not is_pre_pull:
            logger.debug(f"Using preloaded song for: {song_id}")
            queue = self.preloaded_songs[song_id]

            while True:
                chunk = await queue.get()
                if chunk is None:
                    break
                yield chunk

            logger.debug(f"Done playing Preloaded song: {song_id}")

            return

        try:
            async with  self.httpx_client.stream("GET", url, params=stream_params) as r:
                r.raise_for_status()
                async for chunk in r.aiter_bytes(8192):
                    yield chunk
        except httpx.ReadTimeout:
            if(is_pre_pull == True):
                logger.warning(f"Preloading song [{song_id}] failed with ReadTimeout error to url: {url}. retrying...",stacklevel=2)
                try:
                    async with  self.httpx_client.stream("GET", url, params=stream_params) as r:
                        r.raise_for_status()
                        async for chunk in r.aiter_bytes(8192):
                            yield chunk
                except httpx.ReadTimeout:
                     logger.error(f"Preloading  song [{song_id}] failed with ReadTimeout error to url: {url} again. Check that server is online",stacklevel=2)
                
            else:
                logger.error(f"Getting bit stream for song [{song_id}] failed with ReadTimeout error to url: {url}",stacklevel=2)
    async def get_cover_art(self,song_id):
        
        ca_file_path = self._get_song_cover(song_id)
        if(ca_file_path == None):
            return None
        with open(ca_file_path,"rb") as file:
            return file.read()
    def create_que(self,first_song_id):
        temp_q = [first_song_id]
        for s in self.cache_data["cachedSongs"]:
            if(s == first_song_id):
                continue
            temp_q.append(s)
        self.que_list = temp_q
    async def preload_next_song(self, song_id):
        queue = asyncio.Queue()
        self.preloaded_songs[song_id] = queue
        self.preloaded_song_id = song_id
        logger.debug(f"Preloading song {song_id}")
        try:
            stream = self._get_bit_stream(song_id,is_pre_pull=True)
            async for chunk in stream:
                await queue.put(chunk)
        finally:
            await queue.put(None) 

            logger.debug(f"Completed Preloading song: {song_id}")
    async def _write_to_output_file(self,data,first_write=False):
        if(first_write == True):
            with open("temp/output.mp3","wb") as f:
                if(data == None):
                    return
                f.write(data)
        else:
             with open("temp/output.mp3","ab") as f:
                f.write(data)
    def _match_output(self,string):
        if string.lower() in CLI_OUTPUT.lower():
            return CLI_OUTPUT,"cli"
        elif string.lower() in FILE_OUTPUT.lower():
            return FILE_OUTPUT,"file"
        elif string.lower() in STREAM_OUTPUT.lower():
            return STREAM_OUTPUT,"stream"
        else:
            return None,None
    def _validate_output_type(self,output):
        r_out = output
        if(output[:3] != "007"):
            warnings.warn("You have used a string to specify the output. This is not recommened as we may change the output types at a future date. To future proof your code, please use on of the constants we made", stacklevel=2)
            out,t = self._match_output(r_out)
            if(out == None):
                warnings.warn(f"We tried to match you input '{output}' to one of our formats but failed. We are defaulting to file output. And because you obviously didn't read the docs. That outout it temp/song.mp3",stacklevel=2)
                r_out = FILE_OUTPUT
            else:
                warnings.warn(f"We tried to match you input '{output}' to one of our formats and succeeded. You song data will be sent to output {t}. Was it worth being diffrent and ignoring the perfectly good, and future proofed constants we gave you? If you said yes, come back to this when your code stops working after a version update ",stacklevel=2)
        
                r_out = out
        return r_out
    async def get_songs_stream(self,song_id:str,output:str=STREAM_OUTPUT):
        #Returns a song bit stream and creates a que
        
        r_out = self._validate_output_type(output)
        if(r_out == FILE_OUTPUT):
            with open("temp/output.mp3","wb") as f:
                f.write(b"")
        logger.debug(f"Streaming song: {song_id} to output: {output.replace("007","")}")
        await self._update_timesPlayed(song_id)
        if(song_id == None):
            return
        song_bit_stream = self._get_bit_stream(song_id)
        self.create_que(song_id)
        if len(self.que_list) > 1:
            asyncio.create_task(
                self.preload_next_song(self.que_list[1])
            )
        async for chunk in song_bit_stream:
            if(r_out == STREAM_OUTPUT):
                yield chunk
            elif(r_out == CLI_OUTPUT):
                sys.stdout.buffer.write(chunk)
            elif(r_out == FILE_OUTPUT):
                await self._write_to_output_file(chunk)
        logger.debug(f"Done streaming song: {song_id} ")
        
        for x in range(1,len(self.que_list)):
            logger.debug(f"Streaming song: {song_id} to output: {output.replace("007","")}")

            current_song_id = self.que_list[x]
            if(x+1 <=len(self.que_list)):
                next_song_id = self.que_list[x+1]
            else:
                next_song_id = -1
            asyncio.create_task(self.preload_next_song(next_song_id))
            song_bit_stream = self._get_bit_stream(current_song_id)
            async for chunk in song_bit_stream:
                if(r_out == STREAM_OUTPUT):
                    yield chunk
                elif(r_out == CLI_OUTPUT):
                    sys.stdout.buffer.write(chunk)
                elif(r_out == FILE_OUTPUT):
                    await self._write_to_output_file(chunk)

            logger.debug(f"Done streaming song: {song_id} ")
    async def get_song_stream(self,song_id:str,output:str=STREAM_OUTPUT):
        r_out = self._validate_output_type(output)
        if(r_out == FILE_OUTPUT):
            with open("temp/output.mp3","wb") as f:
                f.write(b"")
        logger.debug(f"Streaming singular song: {song_id} to output: {output.replace("007","")}")
        await self._update_timesPlayed(song_id)
        if(song_id == None):
            return
        song_bit_stream = self._get_bit_stream(song_id)
        async for chunk in song_bit_stream:
            if(r_out == STREAM_OUTPUT):
                yield chunk
            elif(r_out == CLI_OUTPUT):
                sys.stdout.buffer.write(chunk)
            elif(r_out == FILE_OUTPUT):
                await self._write_to_output_file(chunk)
        logger.debug(f"Done streaming song: {song_id} ")
    async def get_song_name_by_id(self,song_id):
        return self._get_song_name_by_id(song_id)