import deezer as dz
import tracks_manager as tm

rr=tm.search("sweet dreams are made of this")
print(rr[0])

song = dz.get_song_infos_from_deezer_website(dz.TYPE_TRACK, rr[0]["id"])

song, url, extension, key = tm.getDownloadData(song)

tm.downloadSong(song, url, key, "out.mp3")