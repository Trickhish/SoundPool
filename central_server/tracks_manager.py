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


def chart(arl: str, limit: int = 40):
    _init_session(arl)
    return dz.deezer_chart(limit)


def track_radio(arl: str, sng_id: str, limit: int = 40):
    _init_session(arl)
    return dz.deezer_track_radio(sng_id, limit)


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



def get_song_gw_data(song_id: str, arl: str) -> dict:
    """Fetch full GW track data (includes TRACK_TOKEN) for a given Deezer song ID."""
    _init_session(arl)
    dz.session.cookies.set('arl', arl, domain='.deezer.com')
    gw = 'https://www.deezer.com/ajax/gw-light.php'
    resp = dz.session.post(gw, params={
        'method': 'deezer.getUserData', 'input': '3', 'api_version': '1.0', 'api_token': '',
    }, json={})
    csrf = resp.json()['results']['checkForm']
    resp = dz.session.post(gw, params={
        'method': 'song.getData', 'input': '3', 'api_version': '1.0', 'api_token': csrf,
    }, json={'sng_id': str(song_id)})
    return resp.json()['results']


def get_song_lyrics(song_id: str, arl: str) -> dict:
    """Fetch a track's lyrics from Deezer. Returns
    {"synced": [{"ms": int, "line": str}, ...], "plain": str}. `synced` is empty
    when the track only has unsynced (or no) lyrics."""
    _init_session(arl)
    dz.session.cookies.set('arl', arl, domain='.deezer.com')
    gw = 'https://www.deezer.com/ajax/gw-light.php'
    resp = dz.session.post(gw, params={
        'method': 'deezer.getUserData', 'input': '3', 'api_version': '1.0', 'api_token': '',
    }, json={})
    csrf = resp.json()['results']['checkForm']
    resp = dz.session.post(gw, params={
        'method': 'song.getLyrics', 'input': '3', 'api_version': '1.0', 'api_token': csrf,
    }, json={'sng_id': str(song_id)})
    res = (resp.json() or {}).get('results') or {}
    synced = []
    for row in (res.get('LYRICS_SYNC_JSON') or []):
        ms = row.get('milliseconds')
        line = row.get('line', '')
        if ms is None:
            continue
        try:
            entry = {"ms": int(ms), "line": line}
        except (TypeError, ValueError):
            continue
        # How long the line is actually sung. Needed to tell a genuine
        # instrumental break from a slow song whose lines simply take a while —
        # the gap between line STARTS can't distinguish the two.
        try:
            if row.get('duration') is not None:
                entry["dur"] = int(row["duration"])
        except (TypeError, ValueError):
            pass
        synced.append(entry)
    return {"synced": synced, "plain": res.get('LYRICS_TEXT') or ''}


import re as _re

_LRC_TAG = _re.compile(r'\[(\d+):(\d+)(?:\.(\d+))?\]')


def _parse_lrc(lrc: str) -> list:
    """Parse an LRC string into [{"ms": int, "line": str}] sorted by time.
    Handles multiple timestamps per line and 2- or 3-digit fractions."""
    out = []
    for raw in (lrc or '').splitlines():
        tags = _LRC_TAG.findall(raw)
        if not tags:
            continue
        text = _LRC_TAG.sub('', raw).strip()
        for mnt, sec, frac in tags:
            ms = int(mnt) * 60000 + int(sec) * 1000
            if frac:
                ms += int(frac.ljust(3, '0')[:3])   # ".34" -> 340ms, ".5" -> 500ms
            out.append({"ms": ms, "line": text})
    out.sort(key=lambda x: x["ms"])
    return out


LRCLIB_GET = "https://lrclib.net/api/get"


def _lrclib_exact(title: str, artist: str, duration_sec: float, album: str = None) -> dict:
    """Ask LRCLIB for THIS recording, not just this song title.

    Its /api/get takes a duration and only answers when it has a track within a
    couple of seconds of it. That matters more than it sounds: LRCLIB lists ten
    different "Lowlife" by YUNGBLUD (211s, 212s, 233s, 234s, a live cut...), and
    a title+artist search picks one arbitrarily. Matching on duration pins the
    version actually playing.

    Returns None when it has nothing at that length, so the caller can fall
    back to the fuzzy providers.
    """
    params = {"artist_name": artist, "track_name": title,
              "duration": int(round(duration_sec))}
    if album:
        params["album_name"] = album
    try:
        r = requests.get(LRCLIB_GET, params=params, timeout=10,
                         headers={"User-Agent": "SoundPool (https://soundpool.dury.dev)"})
        if r.status_code != 200:
            return None
        d = r.json() or {}
    except Exception as e:
        print(f"[lyrics] lrclib exact lookup failed for {artist} - {title}: {e}")
        return None
    if d.get("instrumental"):
        return {"synced": [], "plain": ""}
    lrc = d.get("syncedLyrics")
    if lrc:
        synced = _parse_lrc(lrc)
        if synced:
            return {"synced": synced, "plain": "\n".join(l["line"] for l in synced)}
    plain = (d.get("plainLyrics") or "").strip()
    return {"synced": [], "plain": plain} if plain else None


def get_fallback_lyrics(title: str, artist: str, duration_sec=None, album=None) -> dict:
    """Fallback lyrics via syncedlyrics, which aggregates several free providers
    — LRCLIB (community), Musixmatch (what Spotify uses) and NetEase — and
    returns synced LRC when any of them has it. Returns
    {"synced": [...], "plain": str}."""
    if not title or not artist:
        return {"synced": [], "plain": ""}

    # Duration-matched lookup first: it identifies the recording, where the
    # aggregate search below only knows the title and artist and will happily
    # hand back another version's timings.
    if duration_sec:
        exact = _lrclib_exact(title, artist, duration_sec, album)
        if exact and exact["synced"]:
            return exact

    try:
        import syncedlyrics
        lrc = syncedlyrics.search(f"{title} {artist}",
                                  providers=["Lrclib", "Musixmatch", "NetEase"])
    except Exception as e:
        print(f"[lyrics] fallback failed for {artist} - {title}: {e}")
        return {"synced": [], "plain": ""}
    if not lrc:
        return {"synced": [], "plain": ""}
    synced = _parse_lrc(lrc)
    # These providers match on title/artist alone, so they happily return a
    # different recording (a re-record, a live cut, an extended mix). Timings
    # from the wrong version are worse than none — they'd scroll out of sync all
    # song. If the last line lands past the end of THIS track, keep the words
    # but drop the timings.
    if synced and duration_sec:
        first = synced[0]["ms"] / 1000.0
        last = synced[-1]["ms"] / 1000.0
        words = "\n".join(l["line"] for l in synced)
        if last > duration_sec + 10:
            print(f"[lyrics] discarding synced fallback for '{title}': last line at "
                  f"{last:.0f}s but the track is {duration_sec:.0f}s — different recording")
            return {"synced": [], "plain": words}
        # Timings can also fit inside the track yet still belong to another
        # version — e.g. squeezed into the middle, leaving most of the song with
        # no words at all. A real lyric set covers most of its own song.
        coverage = (last - first) / duration_sec
        if len(synced) >= 8 and coverage < 0.4:
            print(f"[lyrics] discarding synced fallback for '{title}': {len(synced)} lines "
                  f"only span {first:.0f}s-{last:.0f}s ({coverage*100:.0f}% of a "
                  f"{duration_sec:.0f}s track) — different recording")
            return {"synced": [], "plain": words}
    if synced:
        return {"synced": synced, "plain": "\n".join(l["line"] for l in synced)}
    return {"synced": [], "plain": lrc.strip()}   # provider only had plain lyrics


def get_deezer_playlist_tracks_gw(playlist_id: int, arl: str) -> list:
    """Fetch all GW track data (includes TRACK_TOKEN) for a Deezer playlist."""
    _init_session(arl)
    _, tracks = dz.parse_deezer_playlist(str(playlist_id))
    return tracks


def get_deezer_playlists(arl: str):
    _init_session(arl)
    # Ensure cookie is scoped to .deezer.com so it's sent to api.deezer.com
    dz.session.cookies.set('arl', arl, domain='.deezer.com')

    # Get user_id from GW API — /user/me requires OAuth, not cookie auth
    gw = 'https://www.deezer.com/ajax/gw-light.php'
    resp = dz.session.post(gw, params={
        'method': 'deezer.getUserData', 'input': '3',
        'api_version': '1.0', 'api_token': '',
    }, json={})
    user_id = resp.json()['results']['USER']['USER_ID']

    resp = dz.session.get(f'https://api.deezer.com/user/{user_id}/playlists', params={'limit': 100})
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


def get_deezer_favorites(arl: str, limit: int = 300):
    """The user's liked/favorite tracks with full metadata (id/title/artist/cover)."""
    _init_session(arl)
    dz.session.cookies.set('arl', arl, domain='.deezer.com')

    gw = 'https://www.deezer.com/ajax/gw-light.php'
    resp = dz.session.post(gw, params={
        'method': 'deezer.getUserData', 'input': '3', 'api_version': '1.0', 'api_token': '',
    }, json={})
    user_id = resp.json()['results']['USER']['USER_ID']

    out = []
    url = f'https://api.deezer.com/user/{user_id}/tracks'
    params = {'limit': 100}
    while url and len(out) < limit:
        data = dz.session.get(url, params=params).json()
        for t in data.get('data', []):
            alb = t.get('album') or {}
            out.append({
                'id': str(t.get('id', '')),
                'title': t.get('title', ''),
                'artist': (t.get('artist') or {}).get('name', ''),
                'img_url': alb.get('cover_medium', '') or alb.get('cover', ''),
            })
        url = data.get('next')
        params = {}  # the 'next' URL already carries its params
    return out[:limit]


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
