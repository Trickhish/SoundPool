package dev.dury.soundpool.net

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject

/** Authenticated calls the standalone browse UI needs. */
class RoomApi(private val host: String, private val token: String,
              private val http: OkHttpClient) {

    private val base = "https://$host"
    private val json = "application/json".toMediaType()

    private fun req(path: String) = Request.Builder()
        .url("$base$path").header("x-token", token)

    private fun body(r: okhttp3.Response): String {
        val b = r.body?.string().orEmpty()
        if (!r.isSuccessful) throw ApiException(r.code, b)
        return b
    }

    private fun getArray(path: String): JSONArray =
        http.newCall(req(path).build()).execute().use { JSONArray(body(it)) }

    private fun getObject(path: String): JSONObject =
        http.newCall(req(path).build()).execute().use { JSONObject(body(it)) }

    private fun post(path: String, payload: JSONObject? = null): String =
        http.newCall(req(path).post((payload?.toString() ?: "{}").toRequestBody(json)).build())
            .execute().use { body(it) }

    fun rooms(): JSONArray = getArray("/room")

    fun room(id: Int): JSONObject = getObject("/room/$id")

    fun search(query: String): JSONArray {
        val url = "$base/song/search".toHttpUrl().newBuilder()
            .addQueryParameter("q", query).build()
        return http.newCall(Request.Builder().url(url).header("x-token", token).build())
            .execute().use { JSONArray(body(it)) }
    }

    /** Attach this box's unit as an output of the room. */
    fun attachOutput(roomId: Int, unitId: String) =
        post("/room/$roomId/output", JSONObject().put("unit_id", unitId))

    fun queueAdd(roomId: Int, songId: String, title: String, artist: String,
                 cover: String, atNext: Boolean = false) =
        post("/room/$roomId/queue/add", JSONObject()
            .put("song_id", songId).put("title", title)
            .put("artist", artist).put("img_url", cover).put("at_next", atNext))

    fun play(roomId: Int) = post("/room/$roomId/play")
    fun pause(roomId: Int) = post("/room/$roomId/pause")
    fun next(roomId: Int) = post("/room/$roomId/next")
    fun prev(roomId: Int) = post("/room/$roomId/prev")
}
