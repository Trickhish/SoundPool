package dev.dury.soundpool

import android.content.Context

/**
 * Mirrors the Python unit's pu_config.ini. The unit id is assigned by the
 * server on first contact and must then survive restarts — re-asking would
 * register a second unit and orphan whatever the user configured against the
 * old one.
 */
class Config(ctx: Context) {
    private val sp = ctx.getSharedPreferences("soundpool", Context.MODE_PRIVATE)

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
        get() = sp.getString("name", android.os.Build.MODEL ?: "Android TV")!!
        set(v) = sp.edit().putString("name", v).apply()

    var ownerMail: String
        get() = sp.getString("owner_mail", "")!!
        set(v) = sp.edit().putString("owner_mail", v).apply()

    /** Empty until the server assigns one via id_assign. */
    var uid: String
        get() = sp.getString("uid", "")!!
        set(v) = sp.edit().putString("uid", v).apply()

    // ── display role ──
    /** Durable code identifying the room's display, from the 4-digit pairing. */
    var displayCode: String
        get() = sp.getString("display_code", "")!!
        set(v) = sp.edit().putString("display_code", v).apply()

    /** Throwaway guest token this screen uses for the live feed. */
    var displayToken: String
        get() = sp.getString("display_token", "")!!
        set(v) = sp.edit().putString("display_token", v).apply()

    var displayRoomId: Int
        get() = sp.getInt("display_room_id", 0)
        set(v) = sp.edit().putInt("display_room_id", v).apply()

    /** Which screen the app opens on: "status" or "display". */
    var startMode: String
        get() = sp.getString("start_mode", "status")!!
        set(v) = sp.edit().putString("start_mode", v).apply()

    // ── account (standalone browse) ──
    /** Session token from device-code sign-in. Empty when signed out. */
    var authToken: String
        get() = sp.getString("auth_token", "")!!
        set(v) = sp.edit().putString("auth_token", v).apply()

    var accountName: String
        get() = sp.getString("account_name", "")!!
        set(v) = sp.edit().putString("account_name", v).apply()

    /** Room this box browses and plays into. */
    var roomId: Int
        get() = sp.getInt("room_id", 0)
        set(v) = sp.edit().putInt("room_id", v).apply()

    val signedIn: Boolean get() = authToken.isNotEmpty()

    val wsUrl: String
        get() = "${if (secure) "wss" else "ws"}://$host:$port/unit"
}
