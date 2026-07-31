package dev.dury.soundpool

import android.content.Intent
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.annotation.OptIn
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.media3.common.util.UnstableApi
import androidx.lifecycle.viewmodel.compose.viewModel
import dev.dury.soundpool.browse.BrowseViewModel
import dev.dury.soundpool.browse.BrowseScreen
import dev.dury.soundpool.browse.SetupScreen
import dev.dury.soundpool.display.DisplayScreen
import dev.dury.soundpool.unit.UnitService
import kotlinx.coroutines.delay

/**
 * Milestone 1 UI: enough to point the box at a server, name it, and watch the
 * unit connect. The browse/display surfaces come later — this screen exists to
 * make the unit role observable without a laptop and adb.
 */
class MainActivity : ComponentActivity() {

    @OptIn(UnstableApi::class)
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val cfg = Config(this)

        // Only once signed in: the unit registers against the owner's email,
        // which we don't have until then. After that it starts on launch so the
        // box is usable without walking over and pressing anything.
        if (cfg.signedIn) startUnit()

        setContent {
            MaterialTheme(colorScheme = darkColorScheme()) {
                Surface(Modifier.fillMaxSize(), color = Color(0xFF0E0B14)) {
                    val bvm: BrowseViewModel = viewModel()
                    val signedIn by bvm.signedIn.collectAsState()

                    // Outside the branch below on purpose: signing in removes
                    // that branch from composition, so an effect declared
                    // inside it gets disposed rather than run.
                    LaunchedEffect(signedIn) { if (signedIn) startUnit() }

                    // Signing in is the first thing, not a button buried in
                    // settings: it also tells the unit which account owns it.
                    if (!signedIn) {
                        val st by bvm.signIn.collectAsState()
                        val host by bvm.host.collectAsState()
                        LaunchedEffect(Unit) { bvm.beginSignIn() }
                        SetupScreen(
                            state = st,
                            host = host,
                            // Re-issue the code against the new server; one
                            // issued by the old host is meaningless to the new.
                            onHostChange = { bvm.setHost(it); bvm.beginSignIn() },
                            onRetry = { bvm.beginSignIn() },
                        )
                        return@Surface
                    }

                    // The unit role is a background service, so the TV can be a
                    // speaker and a screen at once; this only picks what's shown.
                    var screen by remember { mutableStateOf(cfg.startMode) }
                    when (screen) {
                        "browse" -> BrowseScreen(
                            vm = bvm,
                            onExit = { cfg.startMode = "status"; screen = "status" },
                        )
                        "display" -> DisplayScreen(
                            vm = viewModel(),
                            onExit = { cfg.startMode = "status"; screen = "status" },
                        )
                        else -> UnitScreen(
                            cfg = cfg,
                            onStart = { startUnit() },
                            onStop = { stopService(Intent(this, UnitService::class.java)) },
                            onDisplay = { cfg.startMode = "display"; screen = "display" },
                            onBrowse = { cfg.startMode = "browse"; screen = "browse" },
                            onSignOut = { bvm.signOut() },
                        )
                    }
                }
            }
        }
    }

    /** Keep the screen awake — a display that blanks after 30s is useless. */
    override fun onResume() {
        super.onResume()
        window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
    }

    @OptIn(UnstableApi::class)
    private fun startUnit() {
        val i = Intent(this, UnitService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            ContextCompat.startForegroundService(this, i)
        } else {
            startService(i)
        }
    }
}

@OptIn(UnstableApi::class)
@Composable
private fun UnitScreen(cfg: Config, onStart: () -> Unit, onStop: () -> Unit,
                       onDisplay: () -> Unit, onBrowse: () -> Unit,
                       onSignOut: () -> Unit) {
    var host by remember { mutableStateOf(cfg.host) }
    var name by remember { mutableStateOf(cfg.name) }

    // The service publishes its state statically; poll it so the screen tracks
    // the socket without wiring a binder for a handful of strings.
    var connected by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf("") }
    var playing by remember { mutableStateOf("") }
    var uid by remember { mutableStateOf(cfg.uid) }
    LaunchedEffect(Unit) {
        while (true) {
            connected = UnitService.connected
            status = UnitService.status
            playing = UnitService.nowPlaying
            uid = cfg.uid
            delay(500)
        }
    }

    // Without this the first text field takes focus on launch and the leanback
    // IME covers the whole screen before you've done anything.
    val restartFocus = remember { FocusRequester() }
    LaunchedEffect(Unit) { runCatching { restartFocus.requestFocus() } }

    Column(
        Modifier.fillMaxSize().padding(48.dp).verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("SoundPool", fontSize = 34.sp, fontWeight = FontWeight.Bold, color = Color.White)
        Text("Player unit", fontSize = 18.sp, color = Color(0xFFB9A9D8))

        Spacer(Modifier.height(8.dp))

        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                if (connected) "● connected" else "○ offline",
                color = if (connected) Color(0xFF4ADE80) else Color(0xFFF87171),
                fontSize = 22.sp,
            )
            Spacer(Modifier.width(16.dp))
            Text(status, color = Color(0xFFB9A9D8), fontSize = 18.sp)
        }
        Text(
            if (uid.isNotEmpty()) "unit id  ${uid.take(8)}…" else "not registered yet",
            color = Color(0xFF7C6F93), fontSize = 14.sp,
        )
        if (playing.isNotEmpty()) {
            Text(playing, color = Color.White, fontSize = 24.sp, fontWeight = FontWeight.Medium)
        }

        Spacer(Modifier.height(8.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
            Button(onClick = onStart, modifier = Modifier.focusRequester(restartFocus)) {
                Text("Restart unit")
            }
            OutlinedButton(onClick = onStop) { Text("Stop") }
            Button(onClick = onDisplay) { Text("Big screen display") }
            Button(onClick = onBrowse) { Text("Browse & play") }
        }

        Row(verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(16.dp)) {
            Text("signed in as ${cfg.accountName}", color = Color(0xFF4ADE80), fontSize = 15.sp)
            OutlinedButton(onClick = onSignOut) { Text("Sign out") }
        }

        Spacer(Modifier.height(24.dp))
        Text("Settings", fontSize = 18.sp, color = Color(0xFFB9A9D8))
        OutlinedTextField(
            value = host, onValueChange = { host = it; cfg.host = it },
            label = { Text("Server host") }, singleLine = true,
            modifier = Modifier.fillMaxWidth(0.6f),
        )
        OutlinedTextField(
            value = name, onValueChange = { name = it; cfg.name = it },
            label = { Text("Unit name") }, singleLine = true,
            modifier = Modifier.fillMaxWidth(0.6f),
        )
        Text(
            "Changes apply on the next unit restart.",
            color = Color(0xFF7C6F93), fontSize = 13.sp,
        )
    }
}
