package dev.dury.soundpool.unit

import android.app.*
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.ProgressiveMediaSource
import dev.dury.soundpool.Config
import dev.dury.soundpool.MainActivity
import dev.dury.soundpool.net.DeezerDataSource
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.TimeUnit
import kotlin.math.abs

/**
 * Runs the device as a SoundPool player unit: a room output that plays exactly
 * what the server's conductor dictates.
 *
 * Deliberately a foreground service — Android will otherwise freeze a
 * background process and the room would silently lose an output.
 */
@UnstableApi
class UnitService : Service() {

    companion object {
        private const val TAG = "SoundPool/unit"
        private const val CHANNEL = "soundpool_unit"
        private const val NOTIF_ID = 1

        /** Re-seek only past this drift, so routine render re-sends don't stutter. */
        private const val SEEK_TOLERANCE_MS = 1500L

        @Volatile var connected = false
        @Volatile var status: String = "starting"
        @Volatile var nowPlaying: String = ""
        @Volatile var unitId: String = ""
    }

    private lateinit var cfg: Config
    private lateinit var player: ExoPlayer
    private var socket: UnitSocket? = null
    private val main = Handler(Looper.getMainLooper())

    private val http = OkHttpClient.Builder()
        .pingInterval(20, TimeUnit.SECONDS)   // keep the socket alive through NAT
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .build()

    /** Song currently loaded into the player, so a repeated render is a no-op. */
    private var currentSongId: String? = null
    /** Song we still owe the server a "ready" for. */
    private var pendingReady: String? = null
    private var currentDurationMs: Long = 0
    private var currentTitle = ""
    private var currentArtist = ""
    private var currentCover = ""

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        cfg = Config(this)
        createChannel()
        startForeground(NOTIF_ID, buildNotification("Connecting…"))

        player = ExoPlayer.Builder(this)
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(C.USAGE_MEDIA)
                    .setContentType(C.AUDIO_CONTENT_TYPE_MUSIC)
                    .build(),
                /* handleAudioFocus = */ true,
            )
            .build()

        player.addListener(object : Player.Listener {
            override fun onPlaybackStateChanged(state: Int) {
                if (state == Player.STATE_READY) {
                    // The conductor holds every output at the start position
                    // until they all report in, so the room starts together.
                    pendingReady?.let {
                        socket?.send(listOf("ready", it))
                        pendingReady = null
                    }
                    if (currentDurationMs <= 0 && player.duration > 0) {
                        currentDurationMs = player.duration
                    }
                }
                pushStatus(if (player.playWhenReady && state == Player.STATE_READY) "playing" else "paused")
            }

            override fun onPlayerError(error: androidx.media3.common.PlaybackException) {
                Log.e(TAG, "playback error", error)
                // Never leave the room waiting on an output that just failed.
                pendingReady?.let {
                    socket?.send(listOf("ready", it))
                    pendingReady = null
                }
            }
        })

        socket = UnitSocket(cfg, http, ::onCommand) { up ->
            connected = up
            main.post { note(if (up) "Connected" else "Reconnecting…") }
        }
        socket!!.connect()
        main.post(progressTick)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int) = START_STICKY

    override fun onDestroy() {
        main.removeCallbacks(progressTick)
        socket?.close()
        player.release()
        super.onDestroy()
    }

    // ── protocol ────────────────────────────────────────────────────────────

    private fun onCommand(r: JSONArray) {
        when (r.optString(0)) {
            "id_assign" -> {
                cfg.uid = r.optString(1)
                unitId = cfg.uid
                Log.i(TAG, "assigned unit id ${cfg.uid}")
            }

            "error" -> {
                // An id the server doesn't know: clear it so the next connect
                // registers cleanly rather than looping on a dead identity.
                if (r.optString(1) == "unknown_id") {
                    Log.w(TAG, "server rejected unit id ${cfg.uid}; clearing")
                    cfg.uid = ""
                }
            }

            "render" -> main.post {
                doRender(
                    song = r.optJSONObject(1) ?: JSONObject(),
                    url = r.optString(2),
                    key = r.optString(3),
                    posMs = r.optLong(4),
                    playing = r.optBoolean(5),
                    vol = if (r.length() > 6) r.optDouble(6) else null,
                )
            }

            "prefetch" -> warmUp(r.optString(2))

            "stop" -> main.post {
                player.stop()
                player.clearMediaItems()
                currentSongId = null
                pendingReady = null
                nowPlaying = ""
                pushStatus("idle")
                note("Idle")
            }

            "control" -> main.post {
                when (r.optString(1)) {
                    "play" -> { player.playWhenReady = true; pushStatus("playing") }
                    "pause" -> { player.playWhenReady = false; pushStatus("paused") }
                    "volume" -> player.volume = r.optDouble(2, 1.0).toFloat()
                    "seek" -> if (currentDurationMs > 0) {
                        player.seekTo((r.optDouble(2) / 100.0 * currentDurationMs).toLong())
                    }
                }
            }

            // Audio routing is a PulseAudio concept on the Linux units; on
            // Android the platform owns it, so report nothing selectable
            // rather than leaving the server's request unanswered.
            "audio" -> socket?.sendRaw(JSONArray().put("audio_state").put(JSONObject().apply {
                put("sinks", JSONArray())
                put("outputs", JSONArray())
                put("bluetooth", JSONArray())
                put("managed", false)
            }))
        }
    }

    /**
     * Load and position a track the way the conductor asked.
     *
     * The server re-sends `render` for the same song when it releases a
     * two-phase load, so reloading unconditionally would restart the track at
     * the exact moment it should begin. Only a genuine song change rebuilds.
     */
    private fun doRender(song: JSONObject, url: String, key: String,
                         posMs: Long, playing: Boolean, vol: Double?) {
        val songId = song.optString("SNG_ID")
        vol?.let { player.volume = it.toFloat() }

        if (songId == currentSongId && currentSongId != null) {
            if (abs(player.currentPosition - posMs) > SEEK_TOLERANCE_MS) player.seekTo(posMs)
            player.playWhenReady = playing
            return
        }

        currentSongId = songId
        currentTitle = song.optString("SNG_TITLE")
        currentArtist = song.optString("ART_NAME")
        val pic = song.optString("ALB_PICTURE")
        currentCover = if (pic.isNotEmpty())
            "https://e-cdns-images.dzcdn.net/images/cover/$pic/500x500-000000-80-0-0.jpg" else ""
        currentDurationMs = song.optLong("DURATION") * 1000L
        nowPlaying = "$currentArtist — $currentTitle"

        pendingReady = songId
        pushStatus("loading")
        note(nowPlaying)

        val source = ProgressiveMediaSource
            .Factory(DeezerDataSource.factory(http, key))
            .createMediaSource(MediaItem.fromUri(url))

        player.setMediaSource(source)
        player.prepare()
        if (posMs > 0) player.seekTo(posMs)
        player.playWhenReady = playing
        pushState()
    }

    /**
     * Best-effort warm-up for the next track. Streaming already removes most of
     * the delay the Linux units fight (they download the whole MP3 first), so
     * this only pays for DNS, TLS and the CDN edge cache — it does not buffer
     * audio, and is intentionally cheap.
     */
    private fun warmUp(url: String) {
        if (url.isEmpty()) return
        val req = Request.Builder().url(url)
            .header("Range", "bytes=0-${DeezerDataSource.BLOCK * 4 - 1}")
            .build()
        http.newCall(req).enqueue(object : okhttp3.Callback {
            override fun onFailure(call: okhttp3.Call, e: java.io.IOException) {}
            override fun onResponse(call: okhttp3.Call, response: okhttp3.Response) {
                response.close()
            }
        })
    }

    // ── outbound state ──────────────────────────────────────────────────────

    private fun pushStatus(s: String) {
        if (status == s) return
        status = s
        socket?.send(listOf("status", s))
    }

    private fun pushState() {
        val np = if (currentSongId == null) JSONObject.NULL else JSONObject().apply {
            put("id", currentSongId)
            put("title", currentTitle)
            put("artist", currentArtist)
            put("cover", currentCover)
            put("duration", currentDurationMs)
        }
        val state = JSONObject().apply {
            put("now_playing", np)
            put("position", player.currentPosition)
            put("playing", player.isPlaying)
            put("volume", player.volume.toDouble())
            put("queue", JSONArray())          // the room owns the queue, not the unit
            put("current_index", -1)
        }
        socket?.sendRaw(JSONArray().put("state").put(state))
    }

    private val progressTick = object : Runnable {
        private var n = 0
        override fun run() {
            if (player.isPlaying) {
                socket?.send(listOf("progress", player.currentPosition, currentDurationMs))
            }
            if (++n % 5 == 0) pushState()      // heartbeat, self-heals any desync
            main.postDelayed(this, 1000)
        }
    }

    // ── notification ────────────────────────────────────────────────────────

    private fun createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val ch = NotificationChannel(CHANNEL, "SoundPool unit", NotificationManager.IMPORTANCE_LOW)
            getSystemService(NotificationManager::class.java).createNotificationChannel(ch)
        }
    }

    private fun buildNotification(text: String): Notification {
        val pi = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        return NotificationCompat.Builder(this, CHANNEL)
            .setContentTitle("SoundPool unit")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_media_play)
            .setContentIntent(pi)
            .setOngoing(true)
            .build()
    }

    private fun note(text: String) {
        getSystemService(NotificationManager::class.java).notify(NOTIF_ID, buildNotification(text))
    }
}
