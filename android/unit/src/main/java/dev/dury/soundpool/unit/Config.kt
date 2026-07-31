package dev.dury.soundpool.unit

import android.content.Context

/**
 * Mirrors the Python unit's pu_config.ini. The unit id is assigned by the
 * server on first contact and must then survive restarts — re-asking would
 * register a second unit and orphan whatever the user configured against the
 * old one.
 */
class Config(ctx: Context) {
    private val sp = ctx.getSharedPreferences("soundpool_unit", Context.MODE_PRIVATE)

    var host: String
        get() = sp.getString("host", "api.soundpool.dury.dev")!!
        set(v) = sp.edit().putString("host", v).apply()

    var port: Int
        get() = sp.getInt("port", 443)
        set(v) = sp.edit().putInt("port", v).apply()

    var secure: Boolean
        get() = sp.getBoolean("wss", true)
        set(v) = sp.edit().putBoolean("wss", v).apply()

    var name: String
        get() = sp.getString("name", android.os.Build.MODEL ?: "Android speaker")!!
        set(v) = sp.edit().putString("name", v).apply()

    var ownerMail: String
        get() = sp.getString("owner_mail", "")!!
        set(v) = sp.edit().putString("owner_mail", v).apply()

    /** Empty until the server assigns one via id_assign. */
    var uid: String
        get() = sp.getString("uid", "")!!
        set(v) = sp.edit().putString("uid", v).apply()

    /** Whether the unit should auto-start on app launch. */
    var autoStart: Boolean
        get() = sp.getBoolean("auto_start", false)
        set(v) = sp.edit().putBoolean("auto_start", v).apply()

    val wsUrl: String
        get() = "${if (secure) "wss" else "ws"}://$host:$port/unit"
}
