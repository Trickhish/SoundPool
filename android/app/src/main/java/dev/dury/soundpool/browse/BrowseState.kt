package dev.dury.soundpool.browse

data class RoomSummary(val id: Int, val name: String, val isMember: Boolean)

data class Track(
    val id: String,
    val title: String,
    val artist: String,
    val cover: String,
)

data class QueueEntry(val title: String, val artist: String, val cover: String)

/** A row in the full queue, carrying its real position so it can be jumped to
 *  or moved. */
data class QueueItem(val index: Int, val id: String, val title: String,
                     val artist: String, val cover: String)

data class Playlist(val id: Long, val title: String, val trackCount: Int, val cover: String)

data class PlayerState(
    val roomName: String = "",
    val title: String = "",
    val artist: String = "",
    val cover: String = "",
    val playing: Boolean = false,
    val durationMs: Long = 0,
    val queue: List<QueueEntry> = emptyList(),   // upcoming only (mini bar / next up)
    val fullQueue: List<QueueItem> = emptyList(), // whole queue (Queue page)
    val currentIndex: Int = -1,
    val connected: Boolean = false,
)

data class BrowseUi(
    val rooms: List<RoomSummary> = emptyList(),
    val roomsLoading: Boolean = false,
    val roomId: Int = 0,
    val previousRoomId: Int = 0,   // room to return to if a change is cancelled

    val query: String = "",
    val results: List<Track> = emptyList(),
    val searching: Boolean = false,

    val playlists: List<Playlist> = emptyList(),
    val playlistsLoading: Boolean = false,
    val playlistsLoaded: Boolean = false,     // don't refetch every tab visit
    // The playlist currently drilled into, with its tracks. Null = list view.
    val openPlaylist: Playlist? = null,
    val playlistTracks: List<Track> = emptyList(),
    val playlistTracksLoading: Boolean = false,

    val player: PlayerState = PlayerState(),
    val avatarUrl: String = "",   // linked Deezer profile picture, for the rail
    // A track whose action menu (play now / next / queue) is open. Null = closed.
    val trackMenu: Track? = null,
    val toast: String? = null,
    val error: String? = null,
)
