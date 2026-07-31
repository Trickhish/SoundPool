package dev.dury.soundpool.net

import android.util.Log
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONArray
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread
import kotlin.math.min

/**
 * Client for the server's live feed.
 *
 * Two steps, and the order matters: GET /event/sse opens the stream and is what
 * registers this connection as a listener, and only then does
 * /event/subscribe/{event} have somewhere to attach — it 400s otherwise. The
 * subscribe call is therefore retried until the stream is actually up.
 *
 * Frames are `data: ["room_7", {...}]` — the event name travels inside the
 * payload rather than in an SSE `event:` field, so a plain line reader is
 * enough and no SSE library is needed.
 */
class SseClient(
    private val baseUrl: String,
    private val token: String,
    private val event: String,
    private val onEvent: (String, org.json.JSONObject) -> Unit,
    private val onState: (Boolean) -> Unit = {},
) {
    companion object { private const val TAG = "SoundPool/sse" }

    private val http = OkHttpClient.Builder()
        .readTimeout(0, TimeUnit.MILLISECONDS)     // the stream never idles out
        .build()

    @Volatile private var stopped = false
    private var worker: Thread? = null

    fun start() {
        stopped = false
        worker = thread(isDaemon = true, name = "sse") {
            var attempt = 0
            while (!stopped) {
                try {
                    runStream { attempt = 0 }
                } catch (e: Exception) {
                    if (!stopped) Log.w(TAG, "stream ended: ${e.message}")
                }
                onState(false)
                if (stopped) break
                Thread.sleep(min(15_000L, 1000L * (1L shl min(attempt, 4))))
                attempt++
            }
        }
    }

    private fun runStream(onUp: () -> Unit) {
        val req = Request.Builder()
            .url("$baseUrl/event/sse")
            .header("x-token", token)
            .header("Accept", "text/event-stream")
            .build()

        http.newCall(req).execute().use { resp ->
            if (!resp.isSuccessful) throw IllegalStateException("sse HTTP ${resp.code}")
            val src = resp.body?.source() ?: throw IllegalStateException("no body")

            // The stream is live now, so the subscription has something to bind
            // to. Done off-thread so it can't block reading the feed.
            thread(isDaemon = true) { subscribe() }
            onUp()
            onState(true)

            while (!stopped) {
                val line = src.readUtf8Line() ?: break
                if (!line.startsWith("data:")) continue
                val body = line.removePrefix("data:").trim()
                if (body.isEmpty()) continue
                try {
                    val arr = JSONArray(body)
                    val name = arr.optString(0)
                    val payload = arr.optJSONObject(1) ?: continue
                    onEvent(name, payload)
                } catch (e: Exception) {
                    Log.w(TAG, "unparsable frame: $body")
                }
            }
        }
    }

    private fun subscribe() {
        repeat(10) {
            if (stopped) return
            try {
                val req = Request.Builder()
                    .url("$baseUrl/event/subscribe/$event")
                    .header("x-token", token)
                    .build()
                http.newCall(req).execute().use { r ->
                    if (r.isSuccessful) {
                        Log.i(TAG, "subscribed to $event")
                        return
                    }
                    Log.w(TAG, "subscribe returned ${r.code}, retrying")
                }
            } catch (e: Exception) {
                Log.w(TAG, "subscribe failed: ${e.message}")
            }
            Thread.sleep(500)
        }
    }

    fun stop() {
        stopped = true
        worker?.interrupt()
        http.dispatcher.cancelAll()
    }
}
