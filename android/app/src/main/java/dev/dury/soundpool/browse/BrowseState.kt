package dev.dury.soundpool.browse

data class RoomSummary(val id: Int, val name: String, val isMember: Boolean)

data class Track(
    val id: String,
    val title: String,
    val artist: String,
    val cover: String,
)

data class QueueEntry(val title: String, val artist: String, val cover: String)

data class PlayerState(
    val roomName: String = "",
    val title: String = "",
    val artist: String = "",
    val cover: String = "",
    val playing: Boolean = false,
    val durationMs: Long = 0,
    val queue: List<QueueEntry> = emptyList(),
    val connected: Boolean = false,
)

data class BrowseUi(
    val rooms: List<RoomSummary> = emptyList(),
    val roomsLoading: Boolean = false,
    val roomId: Int = 0,

    val query: String = "",
    val results: List<Track> = emptyList(),
    val searching: Boolean = false,

    val player: PlayerState = PlayerState(),
    val toast: String? = null,
    val error: String? = null,
)
