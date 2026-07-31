package dev.dury.soundpool.unit

import android.util.Log
import dev.dury.soundpool.Config
import okhttp3.*
import org.json.JSONArray
import java.util.concurrent.TimeUnit
import kotlin.math.min

/**
 * The unit side of the central server's WebSocket protocol.
 *
 * Messages are bare JSON arrays with the verb first — ["render", song, url,
 * key, pos, playing, vol] and so on. Kept deliberately close to the Python
 * unit's wire format so both can talk to the same server without a version
 * negotiation.
 */
class UnitSocket(
    private val cfg: Config,
    private val http: OkHttpClient,
    private val onCommand: (JSONArray) -> Unit,
    private val onConnected: (Boolean) -> Unit,
) {
    companion object {
        private const val TAG = "SoundPool/ws"
    }

    private var ws: WebSocket? = null
    private var closed = false
    private var attempt = 0

    fun connect() {
        closed = false
        open()
    }

    private fun open() {
        if (closed) return
        Log.i(TAG, "connecting to ${cfg.wsUrl}")
        val req = Request.Builder().url(cfg.wsUrl).build()
        ws = http.newWebSocket(req, object : WebSocketListener() {

            override fun onOpen(webSocket: WebSocket, response: Response) {
                attempt = 0
                onConnected(true)
                // A known id re-claims this unit; otherwise ask the server to
                // mint one, which we then persist.
                if (cfg.uid.isNotEmpty()) {
                    send(listOf("id", cfg.uid, cfg.name, cfg.ownerMail))
                } else {
                    send(listOf("ask_id", cfg.name, cfg.ownerMail))
                }
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                try {
                    onCommand(JSONArray(text))
                } catch (e: Exception) {
                    Log.e(TAG, "bad message: $text", e)
                }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                Log.w(TAG, "socket failed: ${t.message}")
                onConnected(false)
                reconnect()
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                onConnected(false)
                reconnect()
            }
        })
    }

    /** Exponential backoff, capped — a TV may sit for hours with no network. */
    private fun reconnect() {
        if (closed) return
        val delay = min(30_000L, 1000L * (1L shl min(attempt, 5)))
        attempt++
        http.dispatcher.executorService.execute {
            Thread.sleep(delay)
            open()
        }
    }

    fun send(parts: List<Any?>) {
        val arr = JSONArray()
        parts.forEach { arr.put(it) }
        ws?.send(arr.toString())
    }

    /** Raw variant for payloads that already contain JSON objects. */
    fun sendRaw(arr: JSONArray) {
        ws?.send(arr.toString())
    }

    fun close() {
        closed = true
        ws?.close(1000, null)
        ws = null
    }
}
