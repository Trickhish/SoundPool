import os
import deezer as dz
import requests
from io import BytesIO

from configuration import config


def _init_session(arl: str):
    dz.init_deezer_session({"deezer": {"cookie_arl": arl}})


def search(q: str, arl: str):
    _init_session(arl)
    return dz.deezer_search(q, "track")


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



def get_deezer_playlists(arl: str):
    _init_session(arl)
    resp = dz.session.get('https://api.deezer.com/user/me/playlists?limit=100')
    data = resp.json()
    result = []
    for p in data.get('data', []):
        result.append({
            'id': p['id'],
            'title': p['title'],
            'nb_tracks': p.get('nb_tracks', 0),
            'picture': p.get('picture_medium', ''),
        })
    return result


def getDownloadData(song, arl: str):
    _init_session(arl)
    song_quality = 3 if song.get("FILESIZE_MP3_320") and song.get("FILESIZE_MP3_320") != '0' else \
                   5 if song.get("FILESIZE_MP3_256") and song.get("FILESIZE_MP3_256") != '0' else \
                   1

    song, url, extension = dz.get_song_url(song, song_quality)
    if "mp3" not in extension:
        raise Exception(f"Extension isn't mp3 but {extension}")

    key = dz.calcbfkey(song["SNG_ID"])
    return song, url, extension, key



def downloadSong(song, url, key, output_file="out.mp3"):
    try:
        with requests.get(url, stream=True) as response:
            response.raise_for_status()
            with open(output_file, "w+b") as fo:
                dz.writeid3v2(fo, song)
                dz.decryptfile(response, key, fo)
                dz.writeid3v1_1(fo, song)
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Download failed: {e}")
    else:
        print("Dowload finished: {}".format(output_file))




def getSong(song, url, key):
    fh = requests.get(url, stream=True)

    out = BytesIO()

    dz.writeid3v2(out, song)
    dz.decryptfile(fh, key, out)
    dz.writeid3v1_1(out, song)

    out.seek(0)

    return out.getvalue()
