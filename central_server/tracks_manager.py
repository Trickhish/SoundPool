import os
from configuration import load_config
import deezer as dz
import requests
from io import BytesIO

config=None

config=load_config("cs_config.ini")
dz.init_deezer_session(config)

dzhds={}

def setDzHds(config):
    global dzhds

    cookies = {'arl': config['deezer']['cookie_arl'], 'comeback': '1'}

    dzhds = {
        'Pragma': 'no-cache',
        'Origin': 'https://www.deezer.com',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept-Language': 'en-US,en;q=0.9',
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/68.0.3440.106 Safari/537.36',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Accept': '*/*',
        'Cache-Control': 'no-cache',
        'X-Requested-With': 'XMLHttpRequest',
        'Connection': 'keep-alive',
        'Referer': 'https://www.deezer.com/login',
        'DNT': '1',
        "Cookie": ("; ".join(f"{key}={value}" for key, value in cookies.items()))
    }



def search(q):
    r = dz.deezer_search(q, "track")
    return(r)


def download_song_and_get_absolute_filename(search_type, song, playlist_name=None):
    global conf

    if search_type == dz.TYPE_ALBUM:
        song_filename = "{:02d} - {} {}.mp3".format(int(song['TRACK_NUMBER']),
                                                    song['ART_NAME'],
                                                    song['SNG_TITLE'])
    else:
        song_filename = "{} - {}.mp3".format(song['ART_NAME'],
                                             song['SNG_TITLE'])
    song_filename = clean_filename(song_filename)

    if search_type == dz.TYPE_TRACK:
        absolute_filename = os.path.join(config["download_dirs"]["songs"], song_filename)
    elif search_type == dz.TYPE_ALBUM:
        album_name = "{} - {}".format(song['ART_NAME'], song['ALB_TITLE'])
        album_name = clean_filename(album_name)
        album_dir = os.path.join(config["download_dirs"]["albums"], album_name)
        if not os.path.exists(album_dir):
            os.mkdir(album_dir)
        absolute_filename = os.path.join(album_dir, song_filename)
    elif search_type == dz.TYPE_PLAYLIST:
        assert type(playlist_name) == str
        playlist_name = clean_filename(playlist_name)
        playlist_dir = os.path.join(config["download_dirs"]["playlists"], playlist_name)
        if not os.path.exists(playlist_dir):
            os.mkdir(playlist_dir)
        absolute_filename = os.path.join(playlist_dir, song_filename)

    if os.path.exists(absolute_filename):
        print("Skipping song '{}'. Already exists.".format(absolute_filename))
    else:
        print("Downloading '{}'".format(song_filename))
        dz.download_song(song, absolute_filename)
    return absolute_filename



def update_mpd_db(songs, add_to_playlist):
    global conf

    # songs: list of music files or just a string (file path)
    if not config["mpd"].getboolean("use_mpd"):
        return
    print("Updating mpd database")
    timeout_counter = 0
    mpd_client = mpd.MPDClient(use_unicode=True)
    try:
        mpd_client.connect(config["mpd"]["host"], config["mpd"].getint("port"))
    except ConnectionRefusedError as e:
        print("ERROR connecting to MPD ({}:{}): {}".format(config["mpd"]["host"], config["mpd"]["port"], e))
        return
    mpd_client.update()
    if add_to_playlist:
        songs = [songs] if type(songs) != list else songs
        songs = make_song_paths_relative_to_mpd_root(songs)
        while len(mpd_client.search("file", songs[0])) == 0:
            # c.update() does not block so wait for it
            if timeout_counter == 10:
                print("Tried it {} times. Give up now.".format(timeout_counter))
                return
            print("'{}' not found in the music db. Let's wait for it".format(songs[0]))
            timeout_counter += 1
            time.sleep(2)
        for song in songs:
            try:
                mpd_client.add(song)
                print("Added to mpd playlist: '{}'".format(song))
            except mpd.base.CommandError as mpd_error:
                print("ERROR adding '{}' to playlist: {}".format(song, mpd_error))



def clean_filename(path):
    path = path.replace("\t", " ")
    if False:#any(platform.win32_ver()):
        path.replace("\"", "'")
        array_of_special_characters = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
    else:
        array_of_special_characters = ['/', ':', '"', '?']

    return ''.join([c for c in path if c not in array_of_special_characters])



def make_song_paths_relative_to_mpd_root(songs, prefix=""):
    config["mpd"]["music_dir_root"] = os.path.join(config["mpd"]["music_dir_root"], '')
    songs_paths_relative_to_mpd_root = []
    for song in songs:
        songs_paths_relative_to_mpd_root.append(prefix + song[len(config["mpd"]["music_dir_root"]):])
    return songs_paths_relative_to_mpd_root


def download(id, type="track"):
    global conf

    desc = f"Downloading {id}"

    song = dz.get_song_infos_from_deezer_website(dz.TYPE_TRACK, id)
    print(song)
    fn = download_song_and_get_absolute_filename(dz.TYPE_TRACK, song)
    update_mpd_db(fn, False)
    return(make_song_paths_relative_to_mpd_root([fn]))



def getDownloadData(song):
    song_quality = 3 if song.get("FILESIZE_MP3_320") and song.get("FILESIZE_MP3_320") != '0' else \
                   5 if song.get("FILESIZE_MP3_256") and song.get("FILESIZE_MP3_256") != '0' else \
                   1

    urlkey = dz.genurlkey(song["SNG_ID"], song["MD5_ORIGIN"], song["MEDIA_VERSION"], song_quality)
    key = dz.calcbfkey(song["SNG_ID"])
    try:
        url = "https://e-cdns-proxy-%s.dzcdn.net/mobile/1/%s" % (song["MD5_ORIGIN"][0], urlkey.decode())

        return(url, key)

    except Exception as e:
        raise


def downloadSong(song, url, key, output_file="out.mp3"):
    global config
    global dzhds
    setDzHds(config)

    fh = requests.get(url, stream=True, headers=dzhds)

    sc = fh.status_code
    if (sc >= 300):
        print(fh.headers)
        print(fh.text)
        raise Exception(f"Failed to download song ({sc})")

    with open(output_file, "w+b") as fo:
        dz.writeid3v2(fo, song)
        dz.decryptfile(fh, key, fo)
        dz.writeid3v1_1(fo, song)

def getSong(song, url, key):
    fh = requests.get(url, stream=True)

    out = BytesIO()

    dz.writeid3v2(out, song)
    dz.decryptfile(fh, key, out)
    dz.writeid3v1_1(out, song)

    out.seek(0)

    return out.getvalue()

#print(config["deezer"]["cookie_arl"])

#r=search("emmenez moi")
#print(r[0])

#print(config["mpd"]["music_dir_root"])

#song = dz.get_song_infos_from_deezer_website(dz.TYPE_TRACK, r[0]["id"])

#url,key = getDownloadData(song)

#print(url, key)

#downloadSong(song, url, key)

#rt=download(r[0]["id"])
#print(rt)