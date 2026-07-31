package dev.dury.soundpool.unit

import android.Manifest
import android.annotation.SuppressLint
import android.bluetooth.BluetoothA2dp
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothClass
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothProfile
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.provider.Settings
import android.util.Log
import androidx.core.content.ContextCompat

data class BtDevice(val name: String, val address: String)

/**
 * Minimal Bluetooth audio helper.
 *
 * Android routes media to whatever A2DP sink the *system* has active, so the
 * reliable path for the user is the system Bluetooth settings. On top of that we
 * offer a best-effort in-app connect: list bonded audio devices and ask the
 * A2DP profile to connect one. `connect()` on BluetoothA2dp is a hidden API, so
 * it's called by reflection and may be unavailable on some builds — hence the
 * settings shortcut as a fallback.
 */
object BtAudio {

    private const val TAG = "SPUnit/bt"

    fun hasPermission(ctx: Context): Boolean {
        // Only 12+ needs the runtime BLUETOOTH_CONNECT grant.
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) return true
        return ContextCompat.checkSelfPermission(ctx, Manifest.permission.BLUETOOTH_CONNECT) ==
            PackageManager.PERMISSION_GRANTED
    }

    private fun adapter(ctx: Context): BluetoothAdapter? =
        (ctx.getSystemService(Context.BLUETOOTH_SERVICE) as? android.bluetooth.BluetoothManager)?.adapter

    @SuppressLint("MissingPermission")
    fun pairedAudioDevices(ctx: Context): List<BtDevice> {
        if (!hasPermission(ctx)) return emptyList()
        val a = adapter(ctx) ?: return emptyList()
        return try {
            a.bondedDevices
                .filter { it.isAudioSink() }
                .map { BtDevice(it.name ?: it.address, it.address) }
        } catch (e: SecurityException) {
            emptyList()
        }
    }

    @SuppressLint("MissingPermission")
    private fun BluetoothDevice.isAudioSink(): Boolean {
        val major = bluetoothClass?.majorDeviceClass ?: return true
        return major == BluetoothClass.Device.Major.AUDIO_VIDEO
    }

    /** Best-effort: connect the given device as an A2DP sink. Result via callback. */
    @SuppressLint("MissingPermission")
    fun connect(ctx: Context, address: String, done: (Boolean) -> Unit) {
        if (!hasPermission(ctx)) { done(false); return }
        val a = adapter(ctx) ?: run { done(false); return }
        val device = try { a.getRemoteDevice(address) } catch (e: Exception) { done(false); return }

        a.getProfileProxy(ctx, object : BluetoothProfile.ServiceListener {
            override fun onServiceConnected(profile: Int, proxy: BluetoothProfile) {
                val ok = try {
                    val m = BluetoothA2dp::class.java.getMethod("connect", BluetoothDevice::class.java)
                    m.invoke(proxy, device) as? Boolean ?: true
                } catch (e: Exception) {
                    Log.w(TAG, "A2DP connect unavailable: ${e.message}")
                    false
                }
                a.closeProfileProxy(profile, proxy)
                done(ok)
            }
            override fun onServiceDisconnected(profile: Int) {}
        }, BluetoothProfile.A2DP)
    }

    /** The reliable path: hand the user off to system Bluetooth settings. */
    fun openSettings(ctx: Context) {
        ctx.startActivity(android.content.Intent(Settings.ACTION_BLUETOOTH_SETTINGS)
            .addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK))
    }
}
