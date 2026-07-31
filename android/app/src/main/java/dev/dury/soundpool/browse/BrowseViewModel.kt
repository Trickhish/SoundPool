package dev.dury.soundpool.browse

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import dev.dury.soundpool.Config
import dev.dury.soundpool.net.DeviceAuth
import dev.dury.soundpool.net.RoomApi
import dev.dury.soundpool.net.SseClient
import org.json.JSONObject
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient

class BrowseViewModel(app: Application) : AndroidViewModel(app) {

    private val cfg = Config(app)
    private val http = OkHttpClient()

    private val _host = MutableStateFlow(cfg.host)
    val host = _host.asStateFlow()

    /** Rebuilt per attempt: the host is editable on the sign-in screen. */
    private fun auth() = DeviceAuth(cfg.host, http)

    fun setHost(h: String) {
        cfg.host = h
        _host.value = h
    }

    private val _signIn = MutableStateFlow(SignInState())
    val signIn = _signIn.asStateFlow()

    private val _signedIn = MutableStateFlow(cfg.signedIn)
    val signedIn = _signedIn.asStateFlow()

    private val _account = MutableStateFlow(cfg.accountName)
    val account = _account.asStateFlow()

    private var pollJob: Job? = null

    // ── standalone browse ──
    private val _ui = MutableStateFlow(BrowseUi(roomId = cfg.roomId))
    val ui = _ui.asStateFlow()

    private var sse: SseClient? = null
    private var searchJob: Job? = null

    /** Server-reported position and when it arrived, so the bar advances
     *  smoothly between the roughly 1Hz updates instead of stepping. */
    @Volatile private var lastPosMs = 0L
    @Volatile private var lastPosAt = 0L

    fun positionMs(): Long {
        if (!_ui.value.player.playing) return lastPosMs
        return lastPosMs + (System.currentTimeMillis() - lastPosAt)
    }

    private fun api() = RoomApi(cfg.host, cfg.authToken, http)

    fun loadRooms() {
        _ui.update { it.copy(roomsLoading = true, error = null) }
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val arr = api().rooms()
                val list = (0 until arr.length()).map { i ->
                    val o = arr.getJSONObject(i)
                    RoomSummary(o.getInt("id"), o.optString("name"),
                                o.optBoolean("is_member"))
                }
                _ui.update { it.copy(rooms = list, roomsLoading = false) }
            } catch (e: Exception) {
                _ui.update { it.copy(roomsLoading = false, error = e.message) }
            }
        }
    }

    /** Pick the room this box plays into, and make it an output of that room. */
    fun chooseRoom(id: Int) {
        cfg.roomId = id
        val name = _ui.value.rooms.find { it.id == id }?.name ?: ""
        _ui.update { it.copy(roomId = id, player = it.player.copy(roomName = name)) }
        viewModelScope.launch(Dispatchers.IO) {
            try {
                // Standalone means the TV is both the controller and the
                // speaker, so attach its own unit rather than making the user
                // do it from the phone.
                if (cfg.uid.isNotEmpty()) api().attachOutput(id, cfg.uid)
            } catch (e: Exception) {
                _ui.update { it.copy(error = "Could not attach this TV as an output: ${e.message}") }
            }
            openFeed(id)
        }
    }

    fun leaveRoom() {
        sse?.stop(); sse = null
        cfg.roomId = 0
        _ui.update { it.copy(roomId = 0, player = PlayerState(), results = emptyList(), query = "") }
        loadRooms()
    }

    private fun openFeed(roomId: Int) {
        sse?.stop()
        sse = SseClient(
            baseUrl = "https://${cfg.host}",
            token = cfg.authToken,
            event = "room_$roomId",
            onEvent = { _, p -> onRoomEvent(p) },
            onState = { up -> _ui.update { it.copy(player = it.player.copy(connected = up)) } },
        ).also { it.start() }
    }

    private fun onRoomEvent(p: JSONObject) {
        when (p.optString("type")) {
            "state" -> {
                val np = p.optJSONObject("now_playing")
                lastPosMs = p.optLong("position")
                lastPosAt = System.currentTimeMillis()
                val q = p.optJSONArray("queue")
                val ci = p.optInt("current_index", -1)
                val upcoming = buildList {
                    if (q != null) {
                        val all = (0 until q.length()).map { q.getJSONObject(it) }
                        (if (ci >= 0) all.drop(ci + 1) else all).take(20).forEach {
                            add(QueueEntry(it.optString("title"), it.optString("artist"),
                                           it.optString("cover")))
                        }
                    }
                }
                _ui.update {
                    it.copy(player = it.player.copy(
                        title = np?.optString("title") ?: "",
                        artist = np?.optString("artist") ?: "",
                        cover = np?.optString("cover") ?: "",
                        durationMs = np?.optLong("duration") ?: 0,
                        playing = p.optBoolean("playing"),
                        queue = upcoming,
                    ))
                }
            }
            "progress" -> {
                lastPosMs = p.optLong("progress")
                lastPosAt = System.currentTimeMillis()
                _ui.update {
                    it.copy(player = it.player.copy(
                        durationMs = p.optLong("duration", it.player.durationMs)))
                }
            }

            "status" -> _ui.update {
                when (p.optString("status")) {
                    "playing" -> it.copy(player = it.player.copy(playing = true))
                    "paused" -> it.copy(player = it.player.copy(playing = false))
                    else -> it
                }
            }
        }
    }

    fun setQuery(q: String) {
        _ui.update { it.copy(query = q) }
    }

    fun search(q: String = _ui.value.query) {
        val term = q.trim()
        if (term.isEmpty()) return
        searchJob?.cancel()
        _ui.update { it.copy(searching = true, error = null) }
        searchJob = viewModelScope.launch(Dispatchers.IO) {
            try {
                val arr = api().search(term)
                val list = (0 until arr.length()).map { i ->
                    val o = arr.getJSONObject(i)
                    Track(o.optString("id"), o.optString("title"), o.optString("artist"),
                          o.optString("img_url_big").ifEmpty { o.optString("img_url") })
                }
                _ui.update { it.copy(results = list, searching = false) }
            } catch (e: Exception) {
                _ui.update { it.copy(searching = false, error = e.message) }
            }
        }
    }

    fun addToQueue(t: Track, atNext: Boolean = false) {
        val room = _ui.value.roomId
        if (room == 0) return
        viewModelScope.launch(Dispatchers.IO) {
            try {
                api().queueAdd(room, t.id, t.title, t.artist, t.cover, atNext)
                flash("Added ${t.title}")
            } catch (e: Exception) {
                flash("Could not add that song")
            }
        }
    }

    fun playPause() = control { if (_ui.value.player.playing) it.pause(_ui.value.roomId)
                                else it.play(_ui.value.roomId) }
    fun next() = control { it.next(_ui.value.roomId) }
    fun prev() = control { it.prev(_ui.value.roomId) }

    private fun control(block: (RoomApi) -> Unit) {
        val room = _ui.value.roomId
        if (room == 0) return
        viewModelScope.launch(Dispatchers.IO) {
            try { block(api()) } catch (e: Exception) { flash("That didn't work") }
        }
    }

    private fun flash(msg: String) {
        _ui.update { it.copy(toast = msg) }
        viewModelScope.launch {
            delay(2200)
            _ui.update { if (it.toast == msg) it.copy(toast = null) else it }
        }
    }

    /** Called when the browse screen opens. */
    fun enterBrowse() {
        if (cfg.roomId != 0) {
            openFeed(cfg.roomId)
            // Re-opening straight into a saved room means we never saw the
            // list, so the header would have no name to show.
            if (_ui.value.player.roomName.isEmpty()) {
                viewModelScope.launch(Dispatchers.IO) {
                    runCatching {
                        val name = api().room(cfg.roomId).optString("name")
                        _ui.update { it.copy(player = it.player.copy(roomName = name)) }
                    }
                }
            }
        } else {
            loadRooms()
        }
    }

    /** Ask for a code and poll until the user approves it elsewhere. */
    fun beginSignIn() {
        pollJob?.cancel()
        _signIn.value = SignInState()
        pollJob = viewModelScope.launch {
            val start = try {
                withContext(Dispatchers.IO) { auth().start() }
            } catch (e: Exception) {
                _signIn.value = SignInState(error = e.message ?: "Could not reach the server")
                return@launch
            }
            _signIn.value = SignInState(userCode = start.userCode)

            // Poll for the code's whole lifetime, then stop rather than spin
            // forever against a dead code.
            val deadline = System.currentTimeMillis() + start.expiresIn * 1000L
            while (System.currentTimeMillis() < deadline) {
                delay(3000)
                val r = try {
                    withContext(Dispatchers.IO) { auth().poll(start.deviceCode) }
                } catch (e: Exception) {
                    continue        // transient network trouble: keep waiting
                }
                when (r) {
                    is DeviceAuth.Poll.Pending -> {}
                    is DeviceAuth.Poll.Expired -> {
                        _signIn.value = SignInState(error = r.reason)
                        return@launch
                    }
                    is DeviceAuth.Poll.Approved -> {
                        cfg.authToken = r.token
                        cfg.accountName = r.username.ifEmpty { r.email }
                        // The unit registers against an owner's email. Now that
                        // we know who signed in, take it from here instead of
                        // making someone type an address with a D-pad.
                        if (r.email.isNotEmpty()) cfg.ownerMail = r.email
                        _account.value = cfg.accountName
                        _signedIn.value = true
                        return@launch
                    }
                }
            }
            _signIn.value = SignInState(error = "That code expired — try again.")
        }
    }

    fun cancelSignIn() {
        pollJob?.cancel()
        pollJob = null
    }

    fun signOut() {
        cancelSignIn()
        cfg.authToken = ""
        cfg.accountName = ""
        cfg.roomId = 0
        _account.value = ""
        _signedIn.value = false
    }

    override fun onCleared() {
        pollJob?.cancel()
        sse?.stop()
        super.onCleared()
    }
}
