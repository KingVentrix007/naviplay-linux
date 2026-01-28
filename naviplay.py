from urllib.parse import urlencode
import hashlib, random
import json
import asyncio
import httpx
import os
import aiofiles
import sys
import warnings
STREAM_OUTPUT = "007stream007"
CLI_OUTPUT = "007client007"
FILE_OUTPUT = "007file007"



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

    async def quick_init(self):
        self.cache_loaded = True
        await self._load_cache()
        

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
        async with httpx.AsyncClient() as client:
            r = await client.get(url)

        data = r.json()["subsonic-response"]
        if data.get("status") != "ok":
            raise RuntimeError(data.get("error", {}).get("message", "Unknown error"))

        return data
    async def _get_library_timestamp(self):
        resp = await self._call("getIndexes")
        return resp["indexes"].get("lastModified")
    
    async def _load_cache(self):
        # if(self.cache_loaded == True):
        #     return
        if(self.cache_path == None):
            raise FileExistsError("Please Provide a cache path")
        with open(self.cache_path,"r") as cache_file:
            try:
                cache_data = json.load(cache_file)
            except json.JSONDecodeError as je:
                print("json decode err",je)
                cache_data = {"lastUpdate":"-1","cachedSongs":{}}
        with open(self.cache_path,"w") as cache_file:
            json.dump(cache_data,cache_file)
        self.cache_data = cache_data
        cached_songs = self.cache_data["cachedSongs"]
        server_ts = int(await self._get_library_timestamp())
        cache_ts  = int(self.cache_data["lastUpdate"])

        if abs(server_ts - cache_ts) < 2:
            for k in cached_songs.keys():
                song = cached_songs.get(k,{})
                self.songs.append(song)
        else:
            await self._get_all_songs(False)
            await self._cache()
    async def _cache(self):
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
        self.cache_data["lastUpdate"] = await self._get_library_timestamp()
        with open(self.cache_path,"w") as cache_file:
            json.dump(self.cache_data,cache_file)
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
        

        with open(self.cache_path,"w") as cache_file:
            json.dump(self.cache_data,cache_file)
    def _get_song_name(self,song_id):
        for song in self.songs:
            # print(song.get("id",-1))
            if(song.get("id",-1) == song_id):
                return song.get("title")
        return None
    async def _download_song_cover(self,song_id,cache=False):
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
            
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", url, params=server_params) as r:
                r.raise_for_status()
                with open(d_path, "wb") as f:
                    async for chunk in r.aiter_bytes(8192):
                        f.write(chunk)

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
        print("Downloading")
        # song_name = self._get_song_name(song_id).replace(" ","_")
        stream_params = self._get_server_parmas()
        stream_params["id"] = song_id
        url = f"{self.base_url}/download.view"
        if(os.path.exists(f"downloads/{song_id}")):
            pass
        else:
            os.mkdir(f"downloads/{song_id}")
        d_path = f"downloads/{song_id}/{song_id}.bin"
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", url, params=stream_params) as r:
                r.raise_for_status()
                with open(d_path, "wb") as f:
                    async for chunk in r.aiter_bytes(8192):
                        f.write(chunk)

                await self._download_song_cover(song_id)
                print("Download Done")
        self.cache_data["cachedSongs"][song_id]["downloaded"] = True
        self.cache_data["cachedSongs"][song_id]["cache_path"] = d_path
        with open(self.cache_path,"w") as cache_file:
            json.dump(self.cache_data,cache_file)
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
        for song in self.songs:
            # print(song.get("id",-1))
            if(song.get("id",-1) == song_id):
                return song
        return None
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
        # if(self.cache_loaded == False):
        #     await self._load_cache()
        #     self.cache_loaded = True
        all_songs = []
        albums = await self.get_all_albums()

        if progress:
            print(f"Found {len(albums)} albums")

        for i, album in enumerate(albums, 1):
            songs = await self.get_songs_for_album(album["id"])
            all_songs.extend(songs)

            if progress:
                print(f"[{i}/{len(albums)}] {album['name']} → {len(songs)} songs")
        self.songs = all_songs
        return all_songs
    async def get_all_songs(self):
        return self.songs
    async def get_song_id(self,title):
        
        for song in self.songs:
            if(song.get("title","invalid") == title):
                return song.get("id",None)
    async def _get_bit_stream(self, song_id, is_pre_pull=False):
        print(song_id)

        isdown, file = self._is_downloaded(song_id)
        if isdown:
            print("using download")
            with open(file, "rb") as f:
                while chunk := f.read(8192):
                    yield chunk
            return

        stream_params = self._get_server_parmas()
        stream_params["id"] = song_id
        url = f"{self.base_url}/stream.view"

        if song_id in self.preloaded_songs and not is_pre_pull:
            print("Using preload song")
            queue = self.preloaded_songs[song_id]

            while True:
                chunk = await queue.get()
                if chunk is None:
                    break
                yield chunk

            print("Preload song complete")

            return

        async with httpx.AsyncClient() as client:
            async with client.stream("GET", url, params=stream_params) as r:
                r.raise_for_status()
                async for chunk in r.aiter_bytes(8192):
                    yield chunk
    async def get_cover_art(self,song_id):
        
        ca_file_path = self._get_song_cover(song_id)
        if(ca_file_path == None):
            return None
        with open(ca_file_path,"rb") as file:
            return file.read()
    def create_que(self,first_song_id):
        temp_q = [first_song_id]
        for s in self.songs:
            if(s.get("id",-1) == first_song_id):
                continue
            temp_q.append(s.get("id",-1))
        self.que_list = temp_q
    async def preload_next_song(self, song_id):
        # self.preloaded_song_id = song_id
        queue = asyncio.Queue()
        self.preloaded_songs[song_id] = queue
        self.preloaded_song_id = song_id
        print("preloading song:",song_id)
        try:
            stream = self._get_bit_stream(song_id,is_pre_pull=True)
            async for chunk in stream:
                await queue.put(chunk)
        finally:
            await queue.put(None) 

            print("preloaded song")
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
    async def get_songs_stream(self,song_name,output=STREAM_OUTPUT):
        #Returns a song bit stream and creates a que
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
        if(r_out == FILE_OUTPUT):
                await self._write_to_output_file(None,True)
        
        song_id = await self.get_song_id(song_name)
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
        for x in range(1,len(self.que_list)):
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

        print("song done")