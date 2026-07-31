package dev.dury.soundpool.unit

import android.Manifest
import android.content.Context
import android.content.Intent
import android.media.AudioManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.annotation.OptIn
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.media3.common.util.UnstableApi
import kotlinx.coroutines.delay

private val BG = Color(0xFF0E0E1D)
private val ACCENT = Color(0xFFFF2B6D)
private val MUTED = Color(0xFF8B8BAE)
private val OK = Color(0xFF4ADE80)

/**
 * The whole app: point it at a server, name it, sign it to an owner's email,
 * and start the background player. Deliberately plain — this device is a
 * speaker, not something you look at.
 */
class MainActivity : ComponentActivity() {

    @OptIn(UnstableApi::class)
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val cfg = Config(this)

        if (cfg.autoStart) startUnit()

        setContent {
            MaterialTheme(colorScheme = darkColorScheme()) {
                Surface(Modifier.fillMaxSize(), color = BG) {
                    UnitScreen(cfg, ::startUnit, ::stopUnit)
                }
            }
        }
    }

    @OptIn(UnstableApi::class)
    private fun startUnit() {
        val i = Intent(this, PlayerUnitService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            ContextCompat.startForegroundService(this, i)
        } else {
            startService(i)
        }
    }

    private fun stopUnit() {
        stopService(Intent(this, PlayerUnitService::class.java))
    }
}

@OptIn(UnstableApi::class)
@Composable
private fun UnitScreen(cfg: Config, onStart: () -> Unit, onStop: () -> Unit) {
    val ctx = LocalContext.current

    var host by remember { mutableStateOf(cfg.host) }
    var name by remember { mutableStateOf(cfg.name) }
    var mail by remember { mutableStateOf(cfg.ownerMail) }
    var autoStart by remember { mutableStateOf(cfg.autoStart) }

    // Live service state.
    var connected by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf("") }
    var playing by remember { mutableStateOf("") }
    var running by remember { mutableStateOf(false) }
    var uid by remember { mutableStateOf(cfg.uid) }
    LaunchedEffect(Unit) {
        while (true) {
            connected = PlayerUnitService.connected
            status = PlayerUnitService.status
            playing = PlayerUnitService.nowPlaying
            running = PlayerUnitService.running
            uid = cfg.uid
            delay(500)
        }
    }

    // Permission grants (notifications + Bluetooth) all in one prompt.
    var btGranted by remember { mutableStateOf(BtAudio.hasPermission(ctx)) }
    val permLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { btGranted = BtAudio.hasPermission(ctx) }

    fun requestPerms() {
        val perms = mutableListOf<String>()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU)
            perms += Manifest.permission.POST_NOTIFICATIONS
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            perms += Manifest.permission.BLUETOOTH_CONNECT
            perms += Manifest.permission.BLUETOOTH_SCAN
        }
        if (perms.isNotEmpty()) permLauncher.launch(perms.toTypedArray())
    }

    Column(
        Modifier.fillMaxSize().padding(24.dp).verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Text("SoundPool speaker", fontSize = 26.sp, fontWeight = FontWeight.Bold, color = Color.White)

        // ── status ──
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                if (!running) "○ stopped" else if (connected) "● connected" else "○ connecting",
                color = if (running && connected) OK else MUTED, fontSize = 18.sp,
            )
            Spacer(Modifier.width(12.dp))
            Text(status, color = MUTED, fontSize = 15.sp)
        }
        if (uid.isNotEmpty()) Text("id ${uid.take(8)}…", color = Color(0xFF52527A), fontSize = 13.sp)
        if (playing.isNotEmpty()) Text(playing, color = Color.White, fontSize = 17.sp)

        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            if (!running) {
                Button(onClick = { requestPerms(); onStart() },
                       colors = ButtonDefaults.buttonColors(containerColor = ACCENT)) {
                    Text("Start speaker")
                }
            } else {
                OutlinedButton(onClick = onStop) { Text("Stop") }
            }
        }

        Divider(Modifier.padding(vertical = 4.dp), color = Color(0x22FFFFFF))

        // ── config ──
        Text("Connection", fontSize = 15.sp, color = MUTED)
        Field("Server host", host) { host = it; cfg.host = it }
        Field("Speaker name", name) { name = it; cfg.name = it }
        Field("Owner email", mail) { mail = it; cfg.ownerMail = it }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Switch(checked = autoStart, onCheckedChange = { autoStart = it; cfg.autoStart = it })
            Spacer(Modifier.width(10.dp))
            Text("Start automatically when opened", color = MUTED, fontSize = 14.sp)
        }
        Text("Changes apply when the speaker is (re)started.",
             color = Color(0xFF52527A), fontSize = 12.sp)

        Divider(Modifier.padding(vertical = 4.dp), color = Color(0x22FFFFFF))

        // ── volume ──
        VolumeControl(ctx)

        Divider(Modifier.padding(vertical = 4.dp), color = Color(0x22FFFFFF))

        // ── bluetooth ──
        BluetoothSection(ctx, btGranted, onRequest = { requestPerms() })
    }
}

@Composable
private fun Field(label: String, value: String, onChange: (String) -> Unit) {
    OutlinedTextField(
        value = value, onValueChange = onChange, singleLine = true,
        label = { Text(label) }, modifier = Modifier.fillMaxWidth(),
    )
}

@Composable
private fun VolumeControl(ctx: Context) {
    val am = remember { ctx.getSystemService(Context.AUDIO_SERVICE) as AudioManager }
    val max = remember { am.getStreamMaxVolume(AudioManager.STREAM_MUSIC).toFloat() }
    var vol by remember { mutableStateOf(am.getStreamVolume(AudioManager.STREAM_MUSIC).toFloat()) }
    // Reflect external volume-key changes.
    LaunchedEffect(Unit) {
        while (true) { vol = am.getStreamVolume(AudioManager.STREAM_MUSIC).toFloat(); delay(700) }
    }
    Column {
        Text("Output volume", fontSize = 15.sp, color = MUTED)
        Slider(
            value = vol, valueRange = 0f..max, steps = (max - 1).toInt().coerceAtLeast(0),
            onValueChange = {
                vol = it
                am.setStreamVolume(AudioManager.STREAM_MUSIC, it.toInt(), 0)
            },
            colors = SliderDefaults.colors(thumbColor = ACCENT, activeTrackColor = ACCENT),
        )
    }
}

@Composable
private fun BluetoothSection(ctx: Context, granted: Boolean, onRequest: () -> Unit) {
    var devices by remember { mutableStateOf(BtAudio.pairedAudioDevices(ctx)) }
    var note by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(granted) { if (granted) devices = BtAudio.pairedAudioDevices(ctx) }

    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("Bluetooth speaker", fontSize = 15.sp, color = MUTED)
        if (!granted) {
            Text("Grant Bluetooth access to connect a speaker.", color = MUTED, fontSize = 13.sp)
            Button(onClick = onRequest, colors = ButtonDefaults.buttonColors(containerColor = ACCENT)) {
                Text("Allow Bluetooth")
            }
        } else {
            if (devices.isEmpty()) {
                Text("No paired audio devices.", color = Color(0xFF52527A), fontSize = 13.sp)
            }
            devices.forEach { d ->
                OutlinedButton(
                    onClick = {
                        note = "Connecting ${d.name}…"
                        BtAudio.connect(ctx, d.address) { ok ->
                            note = if (ok) "Connected ${d.name}"
                                   else "Couldn't connect — use system settings"
                        }
                    },
                    modifier = Modifier.fillMaxWidth(),
                ) { Text(d.name) }
            }
            OutlinedButton(onClick = { BtAudio.openSettings(ctx) }, modifier = Modifier.fillMaxWidth()) {
                Text("Open Bluetooth settings")
            }
            note?.let { Text(it, color = MUTED, fontSize = 13.sp) }
        }
    }
}
