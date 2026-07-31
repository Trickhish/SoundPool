package dev.dury.soundpool.net

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

/** Thin REST wrapper for the display role's few calls. */
class Api(private val host: String, private val http: OkHttpClient) {

    val base = "https://$host"
    private val json = "application/json".toMediaType()

    private fun get(path: String, token: String? = null): JSONObject {
        val req = Request.Builder().url("$base$path")
            .apply { token?.let { header("x-token", it) } }
            .build()
        http.newCall(req).execute().use { r ->
            val body = r.body?.string().orEmpty()
            if (!r.isSuccessful) throw ApiException(r.code, body)
            return JSONObject(body)
        }
    }

    private fun post(path: String, payload: JSONObject?, token: String? = null): JSONObject {
        val req = Request.Builder().url("$base$path")
            .post((payload?.toString() ?: "{}").toRequestBody(json))
            .apply { token?.let { header("x-token", it) } }
            .build()
        http.newCall(req).execute().use { r ->
            val body = r.body?.string().orEmpty()
            if (!r.isSuccessful) throw ApiException(r.code, body)
            return JSONObject(body)
        }
    }

    /** 4-digit code -> the room's durable display code. */
    fun pair(code: String): JSONObject =
        post("/room/display/pair", JSONObject().put("code", code))

    /** Mint a throwaway guest token so this screen can use the live feed. */
    fun displayToken(displayCode: String): JSONObject =
        post("/room/display/$displayCode/token", null)

    fun displayInfo(displayCode: String): JSONObject =
        get("/room/display/$displayCode")

    fun lyrics(displayCode: String, songId: String): JSONObject =
        get("/room/display/$displayCode/lyrics/$songId")
}

class ApiException(val code: Int, val body: String) : Exception("HTTP $code: $body") {
    /** The server puts a human-readable reason in `detail`; surface that on a TV. */
    val detail: String
        get() = try {
            JSONObject(body).optString("detail").ifEmpty { message ?: "Error" }
        } catch (e: Exception) {
            message ?: "Error"
        }
}
