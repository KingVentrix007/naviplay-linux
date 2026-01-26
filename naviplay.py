import requests
from urllib.parse import urlencode
import hashlib, random
import json
import time
import os
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
        self._load_cache()
    def _auth_params(self):
        salt = str(random.randint(1000, 9999))
        token = hashlib.md5((self.password + salt).encode()).hexdigest()
        return salt, token
    def _call(self, endpoint, extra_params=None):
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
        r = requests.get(url, timeout=self.timeout)
        r.raise_for_status()

        data = r.json()["subsonic-response"]
        if data.get("status") != "ok":
            raise RuntimeError(data.get("error", {}).get("message", "Unknown error"))

        return data
    def _get_library_timestamp(self):
        resp = self._call("getIndexes")
        return resp["indexes"].get("lastModified")
    def _load_cache(self):
        if(self.cache_path == None):
            raise FileExistsError("Please Provide a cache path")
        with open(self.cache_path,"r") as cache_file:
            try:
                cache_data = json.load(cache_file)
            except json.JSONDecodeError:
                print("DC err")
                cache_data = {"lastUpdate":"-1","cachedSongs":{}}
            self.cache_data = cache_data
            cached_songs = self.cache_data["cachedSongs"]
            server_timestamp = self._get_library_timestamp()
            server_ts = int(self._get_library_timestamp())
            cache_ts  = int(self.cache_data["lastUpdate"])

            if abs(server_ts - cache_ts) < 2:
                for k in cached_songs.keys():
                    song = cached_songs.get(k,{})
                    self.songs.append(song)
            else:
                self._get_all_songs(False)
                self._cache()
    def _cache(self):
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
        self.cache_data["lastUpdate"] = self._get_library_timestamp()
        with open(self.cache_path,"w") as cache_file:
            json.dump(self.cache_data,cache_file)
    # def _load_cache(self):
    def _update_timesPlayed(self,song_id):
        tp = int(self.cache_data["cachedSongs"][song_id].get("timesPlayed"))
        tp+=1
        downLoaded =  self.cache_data["cachedSongs"][song_id].get("downloaded",False)
        if(tp > 5 and downLoaded == False):
            d_path = self._download_song(song_id)
            self.cache_data["cachedSongs"][song_id]["downloaded"] = True
            self.cache_data["cachedSongs"][song_id]["cache_path"] = d_path

            
        self.cache_data["cachedSongs"][song_id]["timesPlayed"] = tp
        

        with open(self.cache_path,"w") as cache_file:
            json.dump(self.cache_data,cache_file)
    def _get_song_name(self,song_id):
        for song in self.songs:
            # print(song.get("id",-1))
            if(song.get("id",-1) == song_id):
                return song.get("title")
        return None
    def _download_song_cover(self,song_id,cache=False):
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
            
        r = requests.get(url, params=server_params, stream=True)
        r.raise_for_status()
        with open(d_path, "wb") as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)
    def _get_song_cover(self,song_id):
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
            self._download_song_cover(song_id=song_id,cache=True)
            return  f"cache/{cover_id}.bin"
    def _download_song(self,song_id):
        print("Downloading")
        # song_name = self._get_song_name(song_id).replace(" ","_")
        stream_params = self._get_server_parmas()
        stream_params["id"] = song_id
        url = f"{self.base_url}/download.view"
        os.mkdir(f"downloads/{song_id}")
        d_path = f"downloads/{song_id}/{song_id}.bin"
        r = requests.get(url, params=stream_params, stream=True)
        r.raise_for_status()

        with open(d_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        self._download_song_cover(song_id)
        print("Download Done")
        return d_path
    def _get_server_parmas(self):
        # self._update_timesPlayed(song_id)
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
    
    
    def get_all_albums(self):
        albums = []
        offset = 0

        while True:
            resp = self._call(
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

    def get_album(self, album_id):
        resp = self._call("getAlbum", {"id": album_id})
        return resp["album"]

    def get_songs_for_album(self, album_id):
        album = self.get_album(album_id)
        return album.get("song", [])

    def _get_all_songs(self, progress=False):
        all_songs = []
        albums = self.get_all_albums()

        if progress:
            print(f"Found {len(albums)} albums")

        for i, album in enumerate(albums, 1):
            songs = self.get_songs_for_album(album["id"])
            all_songs.extend(songs)

            if progress:
                print(f"[{i}/{len(albums)}] {album['name']} → {len(songs)} songs")
        self.songs = all_songs
        return all_songs
    def get_all_songs(self):
        return self.songs
    def get_song_id(self,title):
        for song in self.songs:
            if(song.get("title","invalid") == title):
                return song.get("id",None)
    def get_bit_stream(self,song_name):
        song_id = self.get_song_id(song_name)
        print(song_id)
        if(song_id == None):
            return
        self._update_timesPlayed(song_id)
        isdown,file = self._is_downloaded(song_id)
        if(isdown == True):
            print("using download")
            with open(file, "rb") as f:
                while chunk := f.read(8192):
                    yield chunk
        else:
            stream_params = self._get_server_parmas()
            stream_params["id"] = song_id
            url = f"{self.base_url}/stream.view"
            r = requests.get(url, params=stream_params, stream=True)
            r.raise_for_status()

            for chunk in r.iter_content(8192):
                if chunk:
                    yield chunk
    def get_cover_art(self,song_id):
        ca_file_path = self._get_song_cover(song_id)
        if(ca_file_path == None):
            return None
        with open(ca_file_path,"rb") as file:
            return file.read()