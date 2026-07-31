package dev.dury.soundpool.display

import android.graphics.Bitmap
import androidx.activity.compose.BackHandler
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.blur
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import dev.dury.soundpool.net.qrBitmap
import kotlinx.coroutines.delay

private val BG = Color(0xFF0E0B14)
private val ACCENT = Color(0xFF7C3AED)
private val MUTED = Color(0xFFB9A9D8)

@Composable
fun DisplayScreen(vm: DisplayViewModel, onExit: () -> Unit) {
    val s by vm.state.collectAsState()

    // Re-poll the admin-controlled config (message, party QR, toggles); the
    // live feed only carries playback.
    LaunchedEffect(s.paired) {
        while (s.paired) {
            vm.refreshInfo()
            delay(5000)
        }
    }

    // Without this there's no way off the display once it's paired — BACK
    // would drop straight out of the app instead of returning to settings.
    BackHandler { onExit() }

    Box(Modifier.fillMaxSize().background(BG)) {
        if (!s.paired) PairScreen(s, vm, onExit) else BigScreen(s, vm)
    }
}

// ── pairing ─────────────────────────────────────────────────────────────────

@Composable
private fun PairScreen(s: DisplayState, vm: DisplayViewModel, onExit: () -> Unit) {
    var code by remember { mutableStateOf("") }

    Column(
        Modifier.fillMaxSize().padding(horizontal = 48.dp, vertical = 28.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text("Pair this screen", fontSize = 34.sp, fontWeight = FontWeight.Bold, color = Color.White)
        Spacer(Modifier.height(8.dp))
        Text(
            "Open the room settings on your phone, choose \"Pair a screen\", and enter the 4-digit code.",
            fontSize = 18.sp, color = MUTED, textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(24.dp))

        // Four separate boxes rather than a list over identical values — the
        // web client had a bug where a repeated empty string made digits land
        // in the wrong box.
        Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
            for (i in 0 until 4) {
                Box(
                    Modifier.size(64.dp, 78.dp)
                        .clip(RoundedCornerShape(12.dp))
                        .background(Color(0xFF1B1229)),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        code.getOrNull(i)?.toString() ?: "",
                        fontSize = 38.sp, fontWeight = FontWeight.Bold, color = Color.White,
                    )
                }
            }
        }

        Spacer(Modifier.height(20.dp))
        // A TV remote has a D-pad, not a keyboard, so offer the digits directly
        // instead of relying on the leanback IME.
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            for (row in listOf(listOf(1, 2, 3, 4, 5), listOf(6, 7, 8, 9, 0))) {
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    row.forEach { d ->
                        Button(
                            onClick = { if (code.length < 4) code += d.toString() },
                            modifier = Modifier.size(56.dp),
                            contentPadding = PaddingValues(0.dp),
                        ) { Text("$d", fontSize = 22.sp) }
                    }
                }
            }
            Row(
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                modifier = Modifier.heightIn(min = 48.dp),
            ) {
                OutlinedButton(onClick = { code = code.dropLast(1) }) { Text("Delete") }
                Button(
                    onClick = { vm.submitPairCode(code) },
                    enabled = code.length == 4 && !s.pairing,
                ) { Text(if (s.pairing) "Pairing…" else "Pair") }
                OutlinedButton(onClick = onExit) { Text("Back") }
            }
        }

        s.error?.let {
            Spacer(Modifier.height(20.dp))
            Text(it, color = Color(0xFFF87171), fontSize = 18.sp)
        }
    }
}

// ── the screen itself ───────────────────────────────────────────────────────

@Composable
private fun BigScreen(s: DisplayState, vm: DisplayViewModel) {
    // Tick locally so the progress bar and lyrics move smoothly between the
    // server's ~1Hz updates.
    var pos by remember { mutableStateOf(0L) }
    LaunchedEffect(Unit) {
        while (true) { pos = vm.positionMs(); delay(100) }
    }

    Box(Modifier.fillMaxSize()) {
        // Blurred cover backdrop, so the colour comes from the artwork.
        if (s.cover.isNotEmpty()) {
            AsyncImage(
                model = s.cover, contentDescription = null,
                modifier = Modifier.fillMaxSize().blur(64.dp),
                contentScale = ContentScale.Crop,
            )
        }
        Box(
            Modifier.fillMaxSize().background(
                Brush.verticalGradient(listOf(BG.copy(alpha = 0.75f), BG.copy(alpha = 0.96f)))
            )
        )

        Column(Modifier.fillMaxSize().padding(horizontal = 40.dp, vertical = 24.dp)) {
            Header(s)
            Spacer(Modifier.height(16.dp))

            Row(Modifier.weight(1f), horizontalArrangement = Arrangement.spacedBy(32.dp)) {
                if (s.showPlayer && !s.lyricsFull) {
                    NowPlaying(s, pos, Modifier.weight(1f))
                }
                if (s.showLyrics) {
                    Lyrics(s, pos, Modifier.weight(1.3f))
                } else if (s.showQueue) {
                    Queue(s, Modifier.weight(1f), compact = false)
                }
                // The QR gets a column of its own. Floated over the corner it
                // sat on top of the lyrics.
                if (s.showQr) s.partyCode?.let {
                    PartyQr(it, Modifier.width(180.dp).align(Alignment.Bottom))
                }
            }

            if (s.showMessage && s.message.isNotEmpty()) {
                Spacer(Modifier.height(16.dp))
                Box(
                    Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp))
                        .background(ACCENT.copy(alpha = 0.25f)).padding(20.dp),
                    contentAlignment = Alignment.Center,
                ) { Text(s.message, fontSize = 24.sp, color = Color.White) }
            }
        }
    }
}

@Composable
private fun Header(s: DisplayState) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(s.roomName, fontSize = 22.sp, fontWeight = FontWeight.Bold, color = Color.White)
        if (s.showMembers && s.memberCount > 0) {
            Spacer(Modifier.width(16.dp))
            Text("👥 ${s.memberCount}", fontSize = 20.sp, color = MUTED)
        }
        Spacer(Modifier.weight(1f))
        if (s.showSkipVotes && s.voteCount > 0) {
            Text("⏭ ${s.voteCount}/${s.voteThreshold} voting to skip", fontSize = 18.sp, color = MUTED)
        }
        if (!s.connected) {
            Spacer(Modifier.width(16.dp))
            Text("○ reconnecting", fontSize = 16.sp, color = Color(0xFFF87171))
        }
    }
}

@Composable
private fun NowPlaying(s: DisplayState, pos: Long, mod: Modifier) {
    Column(mod, verticalArrangement = Arrangement.Center) {
        if (s.cover.isNotEmpty()) {
            AsyncImage(
                model = s.cover, contentDescription = null,
                modifier = Modifier.size(180.dp).clip(RoundedCornerShape(14.dp)),
                contentScale = ContentScale.Crop,
            )
        }
        Spacer(Modifier.height(14.dp))
        Text(
            s.title.ifEmpty { "Nothing playing" },
            fontSize = 26.sp, fontWeight = FontWeight.Bold, color = Color.White, maxLines = 2,
        )
        Text(s.artist, fontSize = 18.sp, color = MUTED, maxLines = 1)

        if (s.durationMs > 0) {
            Spacer(Modifier.height(12.dp))
            val pct = (pos.toFloat() / s.durationMs).coerceIn(0f, 1f)
            Box(
                Modifier.fillMaxWidth(0.9f).height(6.dp)
                    .clip(RoundedCornerShape(3.dp)).background(Color(0x33FFFFFF))
            ) {
                Box(Modifier.fillMaxWidth(pct).fillMaxHeight().background(ACCENT))
            }
            Spacer(Modifier.height(6.dp))
            Row(Modifier.fillMaxWidth(0.9f)) {
                Text(fmt(pos), color = MUTED, fontSize = 13.sp)
                Spacer(Modifier.weight(1f))
                Text(fmt(s.durationMs), color = MUTED, fontSize = 13.sp)
            }
        }

        if (s.showQueue && s.showLyrics && s.queue.isNotEmpty()) {
            Spacer(Modifier.height(16.dp))
            Text("Up next", fontSize = 14.sp, color = MUTED)
            Spacer(Modifier.height(4.dp))
            s.queue.take(2).forEach { QueueRow(it, s.votingEnabled) }
        }
    }
}

@Composable
private fun Queue(s: DisplayState, mod: Modifier, compact: Boolean) {
    Column(mod) {
        Text("Up next", fontSize = 20.sp, color = MUTED)
        Spacer(Modifier.height(12.dp))
        if (s.queue.isEmpty()) {
            Text("Nothing queued", fontSize = 18.sp, color = Color(0xFF7C6F93))
        }
        LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            items(s.queue.size) { i -> QueueRow(s.queue[i], s.votingEnabled) }
        }
    }
}

@Composable
private fun QueueRow(q: QueueItem, voting: Boolean) {
    Row(
        Modifier.fillMaxWidth().padding(vertical = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (q.cover.isNotEmpty()) {
            AsyncImage(
                model = q.cover, contentDescription = null,
                modifier = Modifier.size(34.dp).clip(RoundedCornerShape(5.dp)),
                contentScale = ContentScale.Crop,
            )
            Spacer(Modifier.width(12.dp))
        }
        Column(Modifier.weight(1f)) {
            Text(q.title, fontSize = 15.sp, color = Color.White, maxLines = 1)
            Text(q.artist, fontSize = 12.sp, color = MUTED, maxLines = 1)
        }
        // Hidden at zero — a badge on every row is noise.
        if (voting && q.score != 0) {
            Text(
                if (q.score < 0) "▼ ${-q.score}" else "▲ ${q.score}",
                fontSize = 15.sp,
                color = if (q.score < 0) Color(0xFFF87171) else Color(0xFF4ADE80),
            )
        }
    }
}

@Composable
private fun Lyrics(s: DisplayState, pos: Long, mod: Modifier) {
    val active = remember(s.lyrics, pos) {
        s.lyrics.indexOfLast { it.ms <= pos }
    }
    val listState = rememberLazyListState()

    LaunchedEffect(active) {
        if (active >= 0) {
            // Centre the sung line rather than putting it at the top of the
            // viewport: scrolling to (active - 2) still left it drifting to the
            // bottom edge, which is the exact problem the web version had.
            // A negative scrollOffset pushes the item down into view by that
            // many pixels, so half the viewport centres it.
            val half = listState.layoutInfo.viewportSize.height / 2
            listState.animateScrollToItem(active, -half)
        }
    }

    Box(mod.fillMaxHeight(), contentAlignment = Alignment.Center) {
        when {
            s.lyricsLoading -> Text("Loading lyrics…", color = MUTED, fontSize = 20.sp)
            s.lyrics.isNotEmpty() -> LazyColumn(
                state = listState,
                verticalArrangement = Arrangement.spacedBy(10.dp),
                contentPadding = PaddingValues(vertical = 0.dp),
            ) {
                items(s.lyrics.size) { i ->
                    val isActive = i == active
                    val alpha by animateFloatAsState(
                        if (isActive) 1f else if (i < active) 0.30f else 0.55f, label = "lyr",
                    )
                    Text(
                        s.lyrics[i].line.ifBlank { "♪" },
                        fontSize = if (isActive) 28.sp else 21.sp,
                        fontWeight = if (isActive) FontWeight.Bold else FontWeight.Normal,
                        color = Color.White.copy(alpha = alpha),
                    )
                }
            }
            s.plainLyrics.isNotEmpty() -> Column {
                Text(s.plainLyrics, fontSize = 22.sp, color = Color.White.copy(alpha = 0.8f))
                Spacer(Modifier.height(8.dp))
                Text("approximate timing", fontSize = 14.sp, color = Color(0xFF7C6F93))
            }
            else -> Text("No lyrics for this track", color = Color(0xFF7C6F93), fontSize = 20.sp)
        }
    }
}

@Composable
private fun PartyQr(partyCode: String, mod: Modifier) {
    val bmp by produceState<Bitmap?>(null, partyCode) {
        value = runCatching { qrBitmap("https://soundpool.dury.dev/party/$partyCode") }.getOrNull()
    }
    Column(mod, horizontalAlignment = Alignment.CenterHorizontally) {
        bmp?.let {
            Image(
                it.asImageBitmap(), contentDescription = "Join the party",
                modifier = Modifier.size(160.dp).clip(RoundedCornerShape(8.dp)),
            )
        }
        Spacer(Modifier.height(8.dp))
        Text("Scan to add songs", fontSize = 15.sp, color = MUTED)
    }
}

private fun fmt(ms: Long): String {
    val t = (ms / 1000).coerceAtLeast(0)
    return "%d:%02d".format(t / 60, t % 60)
}
