import deezer as dz
import tracks_manager as tm

rr=tm.search("emmenez moi")
print(rr[0])

song = dz.get_song_infos_from_deezer_website(dz.TYPE_TRACK, rr[0]["id"])

url,key = tm.getDownloadData(song)

print(url, key)

tm.downloadSong(song, url, key, "out.mp3")