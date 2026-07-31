package dev.dury.soundpool.display

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import dev.dury.soundpool.Config
import dev.dury.soundpool.net.Api
import dev.dury.soundpool.net.ApiException
import dev.dury.soundpool.net.SseClient
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import org.json.JSONObject

data class LyricLine(val ms: Long, val line: String, val dur: Long = 0)

data class QueueItem(val title: String, val artist: String, val cover: String, val score: Int)

data class DisplayState(
    val paired: Boolean = false,
    val pairing: Boolean = false,
    val error: String? = null,
    val connected: Boolean = false,

    val roomName: String = "",
    val memberCount: Int = 0,
    val partyCode: String? = null,
    val message: String = "",

    val songId: String? = null,
    val title: String = "",
    val artist: String = "",
    val cover: String = "",
    val durationMs: Long = 0,
    val playing: Boolean = false,

    val queue: List<QueueItem> = emptyList(),
    val votingEnabled: Boolean = false,
    val voteCount: Int = 0,
    val voteThreshold: Int = 0,

    val lyrics: List<LyricLine> = emptyList(),
    val plainLyrics: String = "",
    val lyricsLoading: Boolean = false,

    val showPlayer: Boolean = true,
    val showLyrics: Boolean = true,
    val showQueue: Boolean = true,
    val showSkipVotes: Boolean = true,
    val showMembers: Boolean = true,
    val showQr: Boolean = true,
    val showMessage: Boolean = true,
    val lyricsFull: Boolean = false,
)

class DisplayViewModel(app: Application) : AndroidViewModel(app) {

    private val cfg = Config(app)
    private val http = OkHttpClient()
    private val api = Api(cfg.host, http)

    private val _state = MutableStateFlow(DisplayState())
    val state = _state.asStateFlow()

    private var sse: SseClient? = null

    /** Server-reported position and when we heard it, so the bar can advance
     *  smoothly between the ~1Hz updates instead of stepping. */
    @Volatile private var lastPosMs = 0L
    @Volatile private var lastPosAt = 0L

    fun positionMs(): Long {
        val s = _state.value
        if (!s.playing) return lastPosMs
        return lastPosMs + (System.currentTimeMillis() - lastPosAt)
    }

    init {
        if (cfg.displayCode.isNotEmpty()) start()
    }

    fun submitPairCode(code: String) {
        _state.update { it.copy(pairing = true, error = null) }
        viewModelScope.launch {
            try {
                val r = withContext(Dispatchers.IO) { api.pair(code) }
                cfg.displayCode = r.optString("display_code")
                _state.update { it.copy(pairing = false, roomName = r.optString("name")) }
                start()
            } catch (e: ApiException) {
                _state.update { it.copy(pairing = false, error = e.detail) }
            } catch (e: Exception) {
                _state.update { it.copy(pairing = false, error = e.message ?: "Network error") }
            }
        }
    }

    fun unpair() {
        sse?.stop(); sse = null
        cfg.displayCode = ""
        cfg.displayToken = ""
        _state.value = DisplayState()
    }

    private fun start() {
        _state.update { it.copy(paired = true) }
        viewModelScope.launch(Dispatchers.IO) {
            try {
                // The guest token is per-device and reusable; only mint a new
                // one when we don't already have it.
                if (cfg.displayToken.isEmpty()) {
                    val t = api.displayToken(cfg.displayCode)
                    cfg.displayToken = t.optString("token")
                    cfg.displayRoomId = t.optInt("room_id")
                }
                refreshInfo()
                openFeed()
            } catch (e: Exception) {
                // A stale token (server-side cleanup reaps expired display
                // guests) can only be fixed by minting a fresh one.
                cfg.displayToken = ""
                _state.update { it.copy(error = e.message) }
            }
        }
    }

    private fun openFeed() {
        sse?.stop()
        sse = SseClient(
            baseUrl = api.base,
            token = cfg.displayToken,
            event = "room_${cfg.displayRoomId}",
            onEvent = { _, payload -> onEvent(payload) },
            onState = { up -> _state.update { it.copy(connected = up) } },
        ).also { it.start() }
    }

    /** Slow poll for the admin-controlled config that isn't on the live feed. */
    fun refreshInfo() {
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val i = api.displayInfo(cfg.displayCode)
                _state.update {
                    it.copy(
                        roomName = i.optString("name"),
                        memberCount = i.optInt("member_count"),
                        partyCode = if (i.optBoolean("party_active")) i.optString("party_code").ifEmpty { null } else null,
                        message = i.optString("message"),
                        showPlayer = i.optBoolean("show_player", true),
                        showLyrics = i.optBoolean("show_lyrics", true),
                        showQueue = i.optBoolean("show_queue", true),
                        showSkipVotes = i.optBoolean("show_skipvotes", true),
                        showMembers = i.optBoolean("show_members", true),
                        showQr = i.optBoolean("show_qr", true),
                        showMessage = i.optBoolean("show_message", true),
                        lyricsFull = i.optBoolean("lyrics_full", false),
                    )
                }
            } catch (e: Exception) {
                // Non-fatal: the live feed carries playback regardless.
            }
        }
    }

    private fun onEvent(p: JSONObject) {
        when (p.optString("type")) {
            "state" -> {
                val np = p.optJSONObject("now_playing")
                val id = np?.optString("id")
                lastPosMs = p.optLong("position")
                lastPosAt = System.currentTimeMillis()

                val q = p.optJSONArray("queue")
                val ci = p.optInt("current_index", -1)
                val upcoming = mutableListOf<QueueItem>()
                if (q != null) {
                    val all = (0 until q.length()).map { q.getJSONObject(it) }
                    var rest = if (ci >= 0) all.drop(ci + 1) else all
                    // Repeat-all wraps, so "up next" continues from the top
                    // rather than looking empty on the last track.
                    if (p.optString("repeat") == "all" && ci >= 0) rest = rest + all.take(ci)
                    rest.take(12).forEach {
                        upcoming += QueueItem(
                            it.optString("title"), it.optString("artist"),
                            it.optString("cover"), it.optInt("score"),
                        )
                    }
                }

                _state.update {
                    it.copy(
                        songId = id,
                        title = np?.optString("title") ?: "",
                        artist = np?.optString("artist") ?: "",
                        cover = np?.optString("cover") ?: "",
                        durationMs = np?.optLong("duration") ?: 0,
                        playing = p.optBoolean("playing"),
                        queue = upcoming,
                        votingEnabled = p.optBoolean("voting_enabled"),
                        voteCount = p.optInt("vote_count"),
                        voteThreshold = p.optInt("vote_threshold"),
                    )
                }
                if (id != null && id.isNotEmpty() && id != loadedLyricsFor) loadLyrics(id)
            }

            "progress" -> {
                lastPosMs = p.optLong("progress")
                lastPosAt = System.currentTimeMillis()
                _state.update { it.copy(durationMs = p.optLong("duration", it.durationMs)) }
            }

            "status" -> _state.update {
                when (p.optString("status")) {
                    "playing" -> it.copy(playing = true)
                    "paused" -> it.copy(playing = false)
                    else -> it
                }
            }
        }
    }

    private var loadedLyricsFor: String? = null

    private fun loadLyrics(songId: String) {
        loadedLyricsFor = songId
        _state.update { it.copy(lyrics = emptyList(), plainLyrics = "", lyricsLoading = true) }
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val r = api.lyrics(cfg.displayCode, songId)
                val arr = r.optJSONArray("synced")
                val lines = buildList {
                    if (arr != null) for (i in 0 until arr.length()) {
                        val o = arr.getJSONObject(i)
                        add(LyricLine(o.optLong("ms"), o.optString("line"), o.optLong("dur")))
                    }
                }
                // Guard against a slow response for a track that's since changed.
                if (loadedLyricsFor == songId) {
                    _state.update {
                        it.copy(lyrics = lines, plainLyrics = r.optString("plain"), lyricsLoading = false)
                    }
                }
            } catch (e: Exception) {
                if (loadedLyricsFor == songId) _state.update { it.copy(lyricsLoading = false) }
            }
        }
    }

    override fun onCleared() {
        sse?.stop()
        super.onCleared()
    }
}
