package dev.dury.soundpool.net

import android.content.Context
import android.util.Log
import dev.dury.soundpool.Config
import okhttp3.OkHttpClient
import java.util.concurrent.Executors

/**
 * Transport commands aimed at the room rather than the local player.
 *
 * This box is a room output: the conductor owns the timeline. Pausing ExoPlayer
 * directly would only desync it — the next render would resume it anyway — so a
 * remote's play/pause has to travel to the server and come back as a decision
 * for every output.
 */
class RoomControl(private val ctx: Context) {

    companion object { private const val TAG = "SoundPool/ctl" }

    private val io = Executors.newSingleThreadExecutor()
    private val http = OkHttpClient()

    /** False when this box isn't signed in or isn't pointed at a room. */
    fun available(): Boolean {
        val cfg = Config(ctx)
        return cfg.signedIn && cfg.roomId != 0
    }

    private fun send(name: String, block: (RoomApi, Int) -> Unit) {
        val cfg = Config(ctx)
        if (!cfg.signedIn || cfg.roomId == 0) return
        io.execute {
            try {
                block(RoomApi(cfg.host, cfg.authToken, http), cfg.roomId)
            } catch (e: Exception) {
                Log.w(TAG, "$name failed: ${e.message}")
            }
        }
    }

    fun play() = send("play") { a, r -> a.play(r) }
    fun pause() = send("pause") { a, r -> a.pause(r) }
    fun next() = send("next") { a, r -> a.next(r) }
    fun prev() = send("prev") { a, r -> a.prev(r) }
}
