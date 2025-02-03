import deezer as dz
import tracks_manager as tm

if not dz.test_deezer_login():
    exit()

rr=tm.search("sweet dreams are made of this")
print(rr[0])

song = dz.get_song_infos_from_deezer_website(dz.TYPE_TRACK, rr[0]["id"])

url,key = tm.getDownloadData(song)

print(url, key)

try:
    tm.downloadSong(song, url, key, "out.mp3")
except:
    print("Failed")

dz.download_song(song, "out2.mp3")