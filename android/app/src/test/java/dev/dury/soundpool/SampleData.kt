package dev.dury.soundpool

import dev.dury.soundpool.browse.BrowseUi
import dev.dury.soundpool.browse.PlayerState
import dev.dury.soundpool.browse.Playlist
import dev.dury.soundpool.browse.QueueEntry
import dev.dury.soundpool.browse.RoomSummary
import dev.dury.soundpool.browse.Track

// Snapshots run off-device with no network, so Coil can't fetch covers — they
// render as empty placeholders. That's fine: we're iterating on layout, type
// and focus, and the placeholder is itself a real state to check.

private fun q(t: String, a: String) = QueueEntry(t, a, "")

val samplePlayer = PlayerState(
    roomName = "Living room",
    title = "What You Know",
    artist = "Two Door Cinema Club",
    cover = "",
    playing = true,
    durationMs = 189_000,
    connected = true,
    queue = listOf(
        q("River", "BRKN LOVE"),
        q("Heathens", "Twenty One Pilots"),
        q("The Man", "The Killers"),
        q("Hotel California", "Eagles"),
        q("Lonely Boy", "The Black Keys"),
    ),
)

val sampleResults = listOf(
    Track("1", "One More Time", "Daft Punk", ""),
    Track("2", "Get Lucky", "Daft Punk", ""),
    Track("3", "Harder, Better, Faster, Stronger", "Daft Punk", ""),
    Track("4", "Instant Crush", "Daft Punk", ""),
)

val samplePlaylists = List(11) { i ->
    Playlist(i.toLong(), listOf(
        "50s irish folk", "50s rock", "Acoustic Country", "Road trip",
        "Focus", "Late night", "Workout", "Chill", "Party", "Discover", "Favourites",
    )[i], (12..140).random(), "")
}

fun uiNowPlaying() = BrowseUi(roomId = 1, player = samplePlayer)

fun uiSearch() = BrowseUi(roomId = 1, player = samplePlayer,
    query = "daft punk", results = sampleResults)

fun uiPlaylists() = BrowseUi(roomId = 1, player = samplePlayer,
    playlists = samplePlaylists, playlistsLoaded = true)

fun uiPlaylistDetail() = BrowseUi(roomId = 1, player = samplePlayer,
    playlists = samplePlaylists, playlistsLoaded = true,
    openPlaylist = samplePlaylists[0], playlistTracks = sampleResults)

fun uiQueue() = BrowseUi(roomId = 1, player = samplePlayer)

fun uiTrackMenu() = BrowseUi(roomId = 1, player = samplePlayer,
    query = "daft punk", results = sampleResults, trackMenu = sampleResults[0])

fun uiRoomPicker() = BrowseUi(roomId = 0, rooms = listOf(
    RoomSummary(1, "Living room", true),
    RoomSummary(2, "Kitchen", false),
    RoomSummary(3, "Garden party", true),
))
