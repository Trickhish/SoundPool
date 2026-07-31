package dev.dury.soundpool.browse

import androidx.activity.compose.BackHandler
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.blur
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusProperties
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import dev.dury.soundpool.ui.Sp
import dev.dury.soundpool.ui.SpBackground
import dev.dury.soundpool.ui.tvFocus
import kotlinx.coroutines.delay

private enum class Page(val label: String, val glyph: String) {
    NowPlaying("Now playing", "♪"),
    Search("Search", "⌕"),
    Queue("Queue", "☰"),
    Settings("Settings", "⚙"),
}

/**
 * The app's home once signed in: a full player in the shape people already know
 * from Deezer or Spotify — nav rail on the left, content in the middle, the
 * current track always present at the bottom.
 */
@Composable
fun PlayerScreen(vm: BrowseViewModel, onSignOut: () -> Unit, onOpenDisplay: () -> Unit,
                 onOpenUnit: () -> Unit) {
    val ui by vm.ui.collectAsState()
    var page by remember { mutableStateOf(Page.NowPlaying) }

    LaunchedEffect(Unit) { vm.enterBrowse() }
    BackHandler(enabled = page != Page.NowPlaying) { page = Page.NowPlaying }

    SpBackground {
        // The artwork tints the whole screen, the way Deezer's player does.
        if (ui.player.cover.isNotEmpty()) {
            AsyncImage(
                model = ui.player.cover, contentDescription = null,
                modifier = Modifier.fillMaxSize().blur(110.dp).alpha(0.35f),
                contentScale = ContentScale.Crop,
            )
            Box(
                Modifier.fillMaxSize().background(
                    Brush.verticalGradient(
                        listOf(Sp.Bg.copy(alpha = 0.50f), Sp.Bg.copy(alpha = 0.94f))
                    )
                )
            )
        }

        if (ui.roomId == 0) {
            RoomPicker(ui, onPick = vm::chooseRoom, onReload = vm::loadRooms)
            return@SpBackground
        }

        Row(Modifier.fillMaxSize()) {
            NavRail(page, onSelect = { page = it })

            Column(
                Modifier.weight(1f).padding(end = Sp.SafeH, top = Sp.SafeV, bottom = 18.dp)
            ) {
                Box(Modifier.weight(1f)) {
                    when (page) {
                        Page.NowPlaying -> NowPlayingPage(ui, vm)
                        Page.Search -> SearchPage(ui, vm)
                        Page.Queue -> QueuePage(ui)
                        Page.Settings -> SettingsPage(ui, vm, onSignOut, onOpenDisplay, onOpenUnit)
                    }
                }
                // Always-present transport, like the bar at the bottom of a
                // desktop music app.
                if (page != Page.NowPlaying) {
                    Spacer(Modifier.height(12.dp))
                    MiniBar(ui, vm)
                }
            }
        }

        ui.toast?.let {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.BottomCenter) {
                Box(
                    Modifier.padding(bottom = 26.dp).clip(RoundedCornerShape(999.dp))
                        .background(Sp.Accent).padding(horizontal = 26.dp, vertical = 12.dp)
                ) {
                    Text(it, color = Color.White, fontSize = 16.sp,
                         fontWeight = FontWeight.SemiBold)
                }
            }
        }
    }
}

// ── nav rail ────────────────────────────────────────────────────────────────

@Composable
private fun NavRail(current: Page, onSelect: (Page) -> Unit) {
    Column(
        Modifier.width(196.dp).fillMaxHeight()
            .background(Color(0x66000000))
            .padding(start = 24.dp, top = Sp.SafeV, end = 12.dp, bottom = 18.dp),
    ) {
        Text("SoundPool", fontSize = 19.sp, fontWeight = FontWeight.Bold, color = Sp.Text)
        Spacer(Modifier.height(28.dp))
        Page.entries.forEach { p ->
            NavItem(p, selected = p == current, onClick = { onSelect(p) })
            Spacer(Modifier.height(6.dp))
        }
    }
}

@Composable
private fun NavItem(page: Page, selected: Boolean, onClick: () -> Unit) {
    val shape = RoundedCornerShape(12.dp)
    Row(
        Modifier.fillMaxWidth()
            .tvFocus(shape, scale = 1.03f)
            .clip(shape)
            .background(if (selected) Sp.Accent.copy(alpha = 0.18f) else Color.Transparent)
            .clickable(onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(page.glyph, fontSize = 17.sp, color = if (selected) Sp.Accent else Sp.Muted)
        Spacer(Modifier.width(12.dp))
        Text(page.label, fontSize = 15.sp,
             fontWeight = if (selected) FontWeight.Bold else FontWeight.Normal,
             color = if (selected) Sp.Text else Sp.Muted)
    }
}

// ── now playing ─────────────────────────────────────────────────────────────

@Composable
private fun NowPlayingPage(ui: BrowseUi, vm: BrowseViewModel) {
    var pos by remember { mutableStateOf(0L) }
    LaunchedEffect(Unit) { while (true) { pos = vm.positionMs(); delay(250) } }

    val playFocus = remember { FocusRequester() }
    LaunchedEffect(Unit) { runCatching { playFocus.requestFocus() } }

    Row(Modifier.fillMaxSize(), verticalAlignment = Alignment.CenterVertically) {
        Cover(ui.player.cover, 300.dp, glyph = 60)
        Spacer(Modifier.width(44.dp))

        Column(Modifier.weight(1f)) {
            Text(ui.player.title.ifEmpty { "Nothing playing" }, fontSize = 40.sp,
                 fontWeight = FontWeight.Bold, color = Sp.Text, maxLines = 2,
                 overflow = TextOverflow.Ellipsis, lineHeight = 46.sp)
            Spacer(Modifier.height(6.dp))
            Text(ui.player.artist, fontSize = 22.sp, color = Sp.Muted, maxLines = 1,
                 overflow = TextOverflow.Ellipsis)

            Spacer(Modifier.height(26.dp))
            Progress(pos, ui.player.durationMs)

            Spacer(Modifier.height(24.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(18.dp),
                verticalAlignment = Alignment.CenterVertically) {
                CircleIcon("⏮", vm::prev)
                CircleIcon(if (ui.player.playing) "⏸" else "▶", vm::playPause, primary = true,
                           modifier = Modifier.focusRequester(playFocus))
                CircleIcon("⏭", vm::next)
            }

            ui.player.queue.firstOrNull()?.let {
                Spacer(Modifier.height(26.dp))
                Text("NEXT UP", fontSize = 11.sp, color = Sp.Faint,
                     fontWeight = FontWeight.Bold, letterSpacing = 1.6.sp)
                Spacer(Modifier.height(6.dp))
                Text("${it.title} — ${it.artist}", fontSize = 15.sp, color = Sp.Muted,
                     maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
    }
}

@Composable
private fun Cover(url: String, size: Dp, glyph: Int = 40) {
    Box(
        Modifier.size(size).clip(RoundedCornerShape(20.dp)).background(Sp.Surface1),
        contentAlignment = Alignment.Center,
    ) {
        if (url.isNotEmpty()) {
            AsyncImage(model = url, contentDescription = null,
                       modifier = Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
        } else {
            Text("♪", fontSize = glyph.sp, color = Sp.Faint)
        }
    }
}

@Composable
private fun Progress(pos: Long, dur: Long) {
    val pct = if (dur > 0) (pos.toFloat() / dur).coerceIn(0f, 1f) else 0f
    Column(Modifier.fillMaxWidth(0.86f)) {
        Box(Modifier.fillMaxWidth().height(6.dp).clip(RoundedCornerShape(3.dp))
                .background(Color(0x24FFFFFF))) {
            Box(Modifier.fillMaxWidth(pct).fillMaxHeight()
                    .clip(RoundedCornerShape(3.dp)).background(Sp.Accent))
        }
        Spacer(Modifier.height(8.dp))
        Row(Modifier.fillMaxWidth()) {
            Text(fmt(pos), fontSize = 13.sp, color = Sp.Muted)
            Spacer(Modifier.weight(1f))
            Text(fmt(dur), fontSize = 13.sp, color = Sp.Muted)
        }
    }
}

@Composable
private fun CircleIcon(glyph: String, onClick: () -> Unit, primary: Boolean = false,
                       modifier: Modifier = Modifier) {
    val size = if (primary) 72.dp else 56.dp
    Box(
        modifier.size(size)
            .tvFocus(RoundedCornerShape(50), scale = 1.10f)
            .clip(CircleShape)
            .background(if (primary) Sp.Accent else Color(0x1FFFFFFF))
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Text(glyph, fontSize = if (primary) 26.sp else 20.sp,
             color = if (primary) Color.White else Sp.Text)
    }
}

// ── mini bar ────────────────────────────────────────────────────────────────

@Composable
private fun MiniBar(ui: BrowseUi, vm: BrowseViewModel) {
    var pos by remember { mutableStateOf(0L) }
    LaunchedEffect(Unit) { while (true) { pos = vm.positionMs(); delay(400) } }
    val pct = if (ui.player.durationMs > 0)
        (pos.toFloat() / ui.player.durationMs).coerceIn(0f, 1f) else 0f

    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp))
            .background(Color(0x99000000)).padding(14.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Cover(ui.player.cover, 46.dp, glyph = 16)
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Text(ui.player.title.ifEmpty { "Nothing playing" }, fontSize = 16.sp,
                     color = Sp.Text, maxLines = 1, fontWeight = FontWeight.SemiBold,
                     overflow = TextOverflow.Ellipsis)
                Text(ui.player.artist, fontSize = 13.sp, color = Sp.Muted, maxLines = 1,
                     overflow = TextOverflow.Ellipsis)
            }
            Spacer(Modifier.width(14.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                SmallIcon("⏮", vm::prev)
                SmallIcon(if (ui.player.playing) "⏸" else "▶", vm::playPause, primary = true)
                SmallIcon("⏭", vm::next)
            }
        }
        Spacer(Modifier.height(10.dp))
        Box(Modifier.fillMaxWidth().height(3.dp).clip(RoundedCornerShape(2.dp))
                .background(Color(0x1FFFFFFF))) {
            Box(Modifier.fillMaxWidth(pct).fillMaxHeight().background(Sp.Accent))
        }
    }
}

@Composable
private fun SmallIcon(glyph: String, onClick: () -> Unit, primary: Boolean = false) {
    Box(
        Modifier.size(if (primary) 44.dp else 38.dp)
            .tvFocus(RoundedCornerShape(50), scale = 1.12f)
            .clip(CircleShape)
            .background(if (primary) Sp.Accent else Color(0x1FFFFFFF))
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Text(glyph, fontSize = if (primary) 16.sp else 14.sp,
             color = if (primary) Color.White else Sp.Text)
    }
}

private fun fmt(ms: Long): String {
    val t = (ms / 1000).coerceAtLeast(0)
    return "%d:%02d".format(t / 60, t % 60)
}
