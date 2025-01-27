import struct
import requests
from Crypto.Hash import MD5
from Crypto.Cipher import AES, Blowfish
import aiohttp
import aiofiles
import asyncio
from binascii import a2b_hex, b2a_hex

import logging

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')


def downloadpicture(cvid, size=200):
    url = f"https://e-cdns-images.dzcdn.net/images/cover/{cvid}/{size}x{size}.jpg"
    return(requests.get(url, stream=True))

async def Adownloadpicture(cvid, size=200):
    url = f"https://e-cdns-images.dzcdn.net/images/cover/{cvid}/{size}x{size}.jpg"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.read()

async def writeid3v2(fo, song, cover=True, cover_size=200):

    def make28bit(x):
        return ((x << 3) & 0x7F000000) | ((x << 2) & 0x7F0000) | (
               (x << 1) & 0x7F00) | (x & 0x7F)

    def maketag(tag, content):
        return struct.pack(">4sLH", tag.encode("ascii"), len(content), 0) + content

    def album_get(key):
        global album_Data
        try:
            return album_Data.get(key)
        except:
            #raise
            return ""

    def song_get(song, key):
        try:
            return song[key]
        except:
            #raise
            return ""

    def makeutf8(txt):
        #return b"\x03" + txt.encode('utf-8')
        return "\x03{}".format(txt).encode()

    def makepic(data):
        # Picture type:
        # 0x00     Other
        # 0x01     32x32 pixels 'file icon' (PNG only)
        # 0x02     Other file icon
        # 0x03     Cover (front)
        # 0x04     Cover (back)
        # 0x05     Leaflet page
        # 0x06     Media (e.g. lable side of CD)
        # 0x07     Lead artist/lead performer/soloist
        # 0x08     Artist/performer
        # 0x09     Conductor
        # 0x0A     Band/Orchestra
        # 0x0B     Composer
        # 0x0C     Lyricist/text writer
        # 0x0D     Recording Location
        # 0x0E     During recording
        # 0x0F     During performance
        # 0x10     Movie/video screen capture
        # 0x11     A bright coloured fish
        # 0x12     Illustration
        # 0x13     Band/artist logotype
        # 0x14     Publisher/Studio logotype        
        imgframe = (b"\x00",                 # text encoding
                    b"image/jpeg", b"\0",    # mime type
                    b"\x03",                 # picture type: 'Cover (front)'
                    b""[:64], b"\0",         # description
                    data
                    )

        return b'' .join(imgframe)

    # get Data as DDMM
    try:
        phyDate_YYYYMMDD = album_get("PHYSICAL_RELEASE_DATE") .split('-') #'2008-11-21'
        phyDate_DDMM = phyDate_YYYYMMDD[2] + phyDate_YYYYMMDD[1]
    except:
        phyDate_DDMM = ''

    # get size of first item in the list that is not 0
    try:
        FileSize = [
            song_get(song, i)
            for i in (
                'FILESIZE_AAC_64',
                'FILESIZE_MP3_320',
                'FILESIZE_MP3_256',
                'FILESIZE_MP3_64',
                'FILESIZE',
                ) if song_get(song, i)
            ][0]
    except:
        FileSize = 0

    try:
        track = "%02s" % song["TRACK_NUMBER"]
        track += "/%02s" % album_get("TRACKS")
    except:
        pass

    # http://id3.org/id3v2.3.0#Attached_picture
    id3 = [
        maketag("TRCK", makeutf8(track)),     # The 'Track number/Position in set' frame is a numeric string containing the order number of the audio-file on its original recording. This may be extended with a "/" character and a numeric string containing the total numer of tracks/elements on the original recording. E.g. "4/9".
        maketag("TLEN", makeutf8(str(int(song["DURATION"]) * 1000))),     # The 'Length' frame contains the length of the audiofile in milliseconds, represented as a numeric string.
        maketag("TORY", makeutf8(str(album_get("PHYSICAL_RELEASE_DATE")[:4]))),     # The 'Original release year' frame is intended for the year when the original recording was released. if for example the music in the file should be a cover of a previously released song
        maketag("TYER", makeutf8(str(album_get("DIGITAL_RELEASE_DATE")[:4]))),     # The 'Year' frame is a numeric string with a year of the recording. This frames is always four characters long (until the year 10000).
        maketag("TDAT", makeutf8(str(phyDate_DDMM))),     # The 'Date' frame is a numeric string in the DDMM format containing the date for the recording. This field is always four characters long.
        maketag("TPUB", makeutf8(album_get("LABEL_NAME"))),     # The 'Publisher' frame simply contains the name of the label or publisher.
        maketag("TSIZ", makeutf8(str(FileSize))),     # The 'Size' frame contains the size of the audiofile in bytes, excluding the ID3v2 tag, represented as a numeric string.
        maketag("TFLT", makeutf8("MPG/3")),

        ]  # decimal, no term NUL
    id3.extend([
        maketag(ID_id3_frame, makeutf8(song_get(song, ID_song))) for (ID_id3_frame, ID_song) in \
        (
            ("TALB", "ALB_TITLE"),   # The 'Album/Movie/Show title' frame is intended for the title of the recording(/source of sound) which the audio in the file is taken from.
            ("TPE1", "ART_NAME"),   # The 'Lead artist(s)/Lead performer(s)/Soloist(s)/Performing group' is used for the main artist(s). They are seperated with the "/" character.
            ("TPE2", "ART_NAME"),   # The 'Band/Orchestra/Accompaniment' frame is used for additional information about the performers in the recording.
            ("TPOS", "DISK_NUMBER"),   # The 'Part of a set' frame is a numeric string that describes which part of a set the audio came from. This frame is used if the source described in the "TALB" frame is divided into several mediums, e.g. a double CD. The value may be extended with a "/" character and a numeric string containing the total number of parts in the set. E.g. "1/2".
            ("TIT2", "SNG_TITLE"),   # The 'Title/Songname/Content description' frame is the actual name of the piece (e.g. "Adagio", "Hurricane Donna").
            ("TSRC", "ISRC"),   # The 'ISRC' frame should contain the International Standard Recording Code (ISRC) (12 characters).
        )
    ])

    if cover:
        try:
            id3.append(maketag("APIC", makepic(Adownloadpicture(song["ALB_PICTURE"], cover_size))))
        except Exception as e:
            print("ERROR: no album cover?", e)

    id3data = b"".join(id3)
#>      big-endian
#s      char[]  bytes
#H      unsigned short  integer 2
#B      unsigned char   integer 1
#L      unsigned long   integer 4

    hdr = struct.pack(">"
                      "3s" "H" "B" "L",
                      "ID3".encode("ascii"),
                      0x300,   # version
                      0x00,    # flags
                      make28bit(len(id3data)))

    await asyncio.to_thread(fo.write, hdr)
    await asyncio.to_thread(fo.write, id3data)
    #fo.write(hdr)
    #fo.write(id3data)

async def blowfishDecrypt(data, key):
    iv = a2b_hex("0001020304050607")
    c = Blowfish.new(key.encode(), Blowfish.MODE_CBC, iv)
    return c.decrypt(data)

async def decryptfile(fh, key, fo):
    """
    Decrypt data from file <fh>, and write to file <fo>.
    decrypt using blowfish with <key>.
    Only every third 2048 byte block is encrypted.
    """
    blockSize = 2048
    i = 0

    async for data in fh.iter_content(blockSize):
        if not data:
            break

        isEncrypted = ((i % 3) == 0)
        isWholeBlock = len(data) == blockSize

        if isEncrypted and isWholeBlock:
            #data = blowfishDecrypt(data, key)
            data = await asyncio.to_thread(blowfishDecrypt, data, key)

        #fo.write(data)
        await asyncio.to_thread(fo.write, data)
        i += 1



async def writeid3v1_1(fo, song):

    # Bugfix changed song["SNG_TITLE... to song.get("SNG_TITLE... to avoid 'key-error' in case the key does not exist
    def song_get(song, key):
        try:
            return song.get(key).encode('utf-8')
        except:
            return b""

    def album_get(key):
        global album_Data
        try:
            return album_Data.get(key).encode('utf-8')
        except:
            return b""

    # what struct.pack expects
    # B => int
    # s => bytes
    data = struct.pack("3s" "30s" "30s" "30s" "4s" "28sB" "H"  "B",
                       b"TAG",                                            # header
                       song_get(song, "SNG_TITLE"),                       # title
                       song_get(song, "ART_NAME"),                        # artist
                       song_get(song, "ALB_TITLE"),                       # album
                       album_get("PHYSICAL_RELEASE_DATE"),                # year
                       album_get("LABEL_NAME"), 0,                        # comment
                       int(song_get(song, "TRACK_NUMBER")),               # tracknum
                       255                                                # genre
                       )

    #fo.write(data)
    await asyncio.to_thread(fo.write, data)




def downloadSong(song, url, key, output_file="out.mp3", cover=True, cover_size=200):
    fh = requests.get(url, stream=True)

    print(output_file)

    with open(output_file, "w+b") as fo:
        writeid3v2(fo, song, cover, cover_size)
        decryptfile(fh, key, fo)
        writeid3v1_1(fo, song)


async def AdownloadSong(song, url, key, output_file="out.mp3", cover=True, cover_size=200):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as fh:
            print(output_file)

            async with aiofiles.open(output_file, "w+b") as fo:
                await asyncio.to_thread(writeid3v2, fo, song, cover, cover_size)
                await asyncio.to_thread(decryptfile, fh, key, fo)
                await asyncio.to_thread(writeid3v1_1, fo, song)