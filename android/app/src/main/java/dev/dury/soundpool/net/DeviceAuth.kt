package dev.dury.soundpool.net

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

/**
 * Device-code sign-in. The box shows a six-character code, the user approves it
 * from an already-signed-in browser, and we poll until a token comes back.
 *
 * Beats typing a password with a D-pad, and keeps the password off a screen the
 * whole room can see.
 */
class DeviceAuth(private val host: String, private val http: OkHttpClient) {

    private val base = "https://$host"
    private val json = "application/json".toMediaType()

    data class Start(val userCode: String, val deviceCode: String, val expiresIn: Int)

    /** Result of one poll: still waiting, signed in, or the code died. */
    sealed class Poll {
        object Pending : Poll()
        data class Approved(val token: String, val username: String, val email: String) : Poll()
        data class Expired(val reason: String) : Poll()
    }

    fun start(): Start {
        val req = Request.Builder().url("$base/auth/device/start")
            .post("{}".toRequestBody(json)).build()
        http.newCall(req).execute().use { r ->
            val body = r.body?.string().orEmpty()
            if (!r.isSuccessful) throw ApiException(r.code, body)
            val o = JSONObject(body)
            return Start(o.getString("user_code"), o.getString("device_code"),
                         o.optInt("expires_in", 600))
        }
    }

    fun poll(deviceCode: String): Poll {
        val req = Request.Builder().url("$base/auth/device/poll?device_code=$deviceCode").build()
        http.newCall(req).execute().use { r ->
            val body = r.body?.string().orEmpty()
            // 410 is the server saying this code is spent or timed out — the
            // screen has to start over rather than keep polling forever.
            if (r.code == 410) return Poll.Expired(ApiException(410, body).detail)
            if (!r.isSuccessful) throw ApiException(r.code, body)
            val o = JSONObject(body)
            return if (o.optString("status") == "approved") {
                Poll.Approved(o.getString("token"), o.optString("username"), o.optString("email"))
            } else {
                Poll.Pending
            }
        }
    }
}
