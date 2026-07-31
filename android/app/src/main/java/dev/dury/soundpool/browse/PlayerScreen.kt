package dev.dury.soundpool.browse

import androidx.activity.compose.BackHandler
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.focusGroup
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.LibraryMusic
import androidx.compose.material.icons.filled.MusicNote
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.QueueMusic
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.SkipNext
import androidx.compose.material.icons.filled.SkipPrevious
import androidx.compose.material3.*
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.blur
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusProperties
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.input.key.type
import androidx.compose.ui.input.key.onKeyEvent
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import dev.dury.soundpool.ui.Sp
import dev.dury.soundpool.ui.SpBackground
import dev.dury.soundpool.ui.spClickable
import dev.dury.soundpool.ui.tvFocus
import kotlinx.coroutines.delay

internal enum class Page(val label: String, val icon: ImageVector) {
    NowPlaying("Now playing", Icons.Filled.MusicNote),
    Search("Search", Icons.Filled.Search),
    Playlists("Playlists", Icons.Filled.LibraryMusic),
    Queue("Queue", Icons.Filled.QueueMusic),
    Settings("Settings", Icons.Filled.Settings),
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
    // Disabled while a playlist is drilled in, so that page's own BACK (which
    // closes the playlist) runs first instead of both firing.
    BackHandler(enabled = page != Page.NowPlaying && ui.openPlaylist == null) {
        page = Page.NowPlaying
    }

    val actions = remember(vm) { vm.asActions() }
    PlayerShell(
        ui = ui, actions = actions, page = page, onSelectPage = { page = it },
        onPickRoom = vm::chooseRoom, onReloadRooms = vm::loadRooms,
        onSignOut = onSignOut, onOpenDisplay = onOpenDisplay, onOpenUnit = onOpenUnit,
    )
}

/**
 * The player, with no view model: it takes state and callbacks so it can be
 * rendered off-device for design snapshots (see the Paparazzi tests).
 */
@Composable
internal fun PlayerShell(
    ui: BrowseUi,
    actions: PlayerActions,
    page: Page,
    onSelectPage: (Page) -> Unit,
    onPickRoom: (Int) -> Unit,
    onReloadRooms: () -> Unit,
    onSignOut: () -> Unit,
    onOpenDisplay: () -> Unit,
    onOpenUnit: () -> Unit,
) {
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
            RoomPicker(ui, onPick = onPickRoom, onReload = onReloadRooms)
            return@SpBackground
        }

        val railFocus = remember { FocusRequester() }

        Row(Modifier.fillMaxSize()) {
            NavRail(page, selectedFocus = railFocus, avatarUrl = ui.avatarUrl,
                    onSelect = onSelectPage)

            Column(
                Modifier.weight(1f).padding(end = Sp.SafeH, top = Sp.SafeV, bottom = 18.dp)
            ) {
                Box(Modifier.weight(1f)) {
                    when (page) {
                        Page.NowPlaying -> NowPlayingPage(ui, actions, railFocus)
                        Page.Search -> SearchPage(ui, actions)
                        Page.Playlists -> PlaylistsPage(ui, actions)
                        Page.Queue -> QueuePage(ui)
                        Page.Settings -> SettingsPage(ui, actions, onSignOut, onOpenDisplay, onOpenUnit)
                    }
                }
                // Always-present transport, like the bar at the bottom of a
                // desktop music app.
                if (page != Page.NowPlaying) {
                    Spacer(Modifier.height(12.dp))
                    MiniBar(ui, actions)
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

/**
 * Icon-only rail that widens to show labels while it has focus — the pattern
 * Netflix and Spotify use on TV. Permanently expanded it just ate horizontal
 * space that the content wants.
 */
@Composable
private fun NavRail(current: Page, selectedFocus: FocusRequester, avatarUrl: String,
                    onSelect: (Page) -> Unit) {
    var railFocused by remember { mutableStateOf(false) }
    val width by animateDpAsState(if (railFocused) 208.dp else 76.dp, label = "rail")

    Column(
        Modifier.width(width).fillMaxHeight()
            .background(if (railFocused) Color(0x8A000000) else Color.Transparent)
            .onFocusChanged { railFocused = it.hasFocus }
            .focusGroup()
            .padding(top = Sp.SafeV, bottom = 18.dp, start = 14.dp, end = 14.dp),
        horizontalAlignment = Alignment.Start,
    ) {
        // The linked Deezer account's avatar; falls back to the app monogram
        // until it loads or if no Deezer is connected.
        Box(Modifier.size(34.dp).clip(CircleShape).background(Sp.Surface2),
            contentAlignment = Alignment.Center) {
            if (avatarUrl.isNotEmpty()) {
                AsyncImage(model = avatarUrl, contentDescription = "Account",
                           modifier = Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
            } else {
                Box(Modifier.fillMaxSize().background(Sp.Accent), contentAlignment = Alignment.Center) {
                    Text("S", fontSize = 16.sp, fontWeight = FontWeight.Black, color = Color.White)
                }
            }
        }
        Spacer(Modifier.height(26.dp))
        Page.entries.forEach { p ->
            // Coming back from content lands on the current page's item.
            NavItem(p, selected = p == current, expanded = railFocused,
                    onClick = { onSelect(p) },
                    modifier = if (p == current) Modifier.focusRequester(selectedFocus)
                               else Modifier)
            Spacer(Modifier.height(8.dp))
        }
    }
}

@Composable
private fun NavItem(page: Page, selected: Boolean, expanded: Boolean, onClick: () -> Unit,
                    modifier: Modifier = Modifier) {
    val shape = RoundedCornerShape(12.dp)
    Row(
        modifier.fillMaxWidth().height(48.dp)
            .tvFocus(shape, scale = 1.03f)
            .clip(shape)
            .background(if (selected) Sp.Accent.copy(alpha = 0.20f) else Color.Transparent)
            .spClickable(onClick)
            .padding(horizontal = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(page.icon, contentDescription = page.label,
             tint = if (selected) Sp.Accent else Sp.Muted,
             modifier = Modifier.size(22.dp))
        if (expanded) {
            Spacer(Modifier.width(14.dp))
            Text(page.label, fontSize = 15.sp, maxLines = 1,
                 fontWeight = if (selected) FontWeight.Bold else FontWeight.Normal,
                 color = if (selected) Sp.Text else Sp.Muted)
        }
    }
}

// ── now playing ─────────────────────────────────────────────────────────────

@Composable
private fun NowPlayingPage(ui: BrowseUi, actions: PlayerActions, railFocus: FocusRequester) {
    var pos by remember { mutableStateOf(0L) }
    LaunchedEffect(Unit) { while (true) { pos = actions.positionMs(); delay(250) } }

    val playFocus = remember { FocusRequester() }
    LaunchedEffect(Unit) { runCatching { playFocus.requestFocus() } }

    Row(Modifier.fillMaxSize(), verticalAlignment = Alignment.CenterVertically) {
        // A soft accent glow behind the artwork, drawn (not an elevation
        // shadow, which renders black on API 29).
        Box(contentAlignment = Alignment.Center) {
            Box(
                Modifier.size(340.dp).drawBehind {
                    drawRoundRect(
                        brush = Brush.radialGradient(
                            listOf(Sp.Accent.copy(alpha = 0.28f), Color.Transparent),
                            radius = size.minDimension * 0.72f,
                        ),
                        cornerRadius = CornerRadius(60f, 60f),
                    )
                }
            )
            Cover(ui.player.cover, 320.dp, glyph = 60)
        }
        Spacer(Modifier.width(52.dp))

        Column(Modifier.weight(1f)) {
            // Eyebrow: where the music is coming from, above the track.
            Text("PLAYING FROM · ${ui.player.roomName.ifEmpty { "SOUNDPOOL" }}".uppercase(),
                 fontSize = 12.sp, color = Sp.Accent, fontWeight = FontWeight.Bold,
                 letterSpacing = 2.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Spacer(Modifier.height(12.dp))
            Text(ui.player.title.ifEmpty { "Nothing playing" }, fontSize = 44.sp,
                 fontWeight = FontWeight.Bold, color = Sp.Text, maxLines = 2,
                 overflow = TextOverflow.Ellipsis, lineHeight = 48.sp)
            Spacer(Modifier.height(8.dp))
            Text(ui.player.artist, fontSize = 22.sp, color = Sp.Muted, maxLines = 1,
                 overflow = TextOverflow.Ellipsis)

            Spacer(Modifier.height(26.dp))
            Progress(pos, ui.player.durationMs)

            Spacer(Modifier.height(24.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(18.dp),
                verticalAlignment = Alignment.CenterVertically) {
                // LEFT off the first control returns to the rail. The cover art
                // sits between them so 2D focus search finds nothing, and a
                // declarative `left =` didn't fire — hop imperatively instead.
                CircleIcon(Icons.Filled.SkipPrevious, "Previous", actions::prev,
                           modifier = Modifier.onKeyEvent { e ->
                               if (e.type == KeyEventType.KeyDown &&
                                   e.key == Key.DirectionLeft) {
                                   runCatching { railFocus.requestFocus() }.isSuccess
                               } else false
                           })
                CircleIcon(
                    if (ui.player.playing) Icons.Filled.Pause else Icons.Filled.PlayArrow,
                    if (ui.player.playing) "Pause" else "Play",
                    actions::playPause, primary = true,
                    modifier = Modifier.focusRequester(playFocus),
                )
                CircleIcon(Icons.Filled.SkipNext, "Next", actions::next)
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
            Icon(Icons.Filled.MusicNote, contentDescription = null, tint = Sp.Faint,
                 modifier = Modifier.size((glyph * 1.4).dp))
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
private fun CircleIcon(icon: ImageVector, label: String, onClick: () -> Unit,
                       primary: Boolean = false, modifier: Modifier = Modifier) {
    val size = if (primary) 72.dp else 56.dp
    Box(
        modifier.size(size)
            .tvFocus(RoundedCornerShape(50), scale = 1.10f)
            .clip(CircleShape)
            .background(if (primary) Sp.Accent else Color(0x1FFFFFFF))
            .spClickable(onClick),
        contentAlignment = Alignment.Center,
    ) {
        Icon(icon, contentDescription = label,
             tint = if (primary) Color.White else Sp.Text,
             modifier = Modifier.size(if (primary) 34.dp else 26.dp))
    }
}

// ── mini bar ────────────────────────────────────────────────────────────────

@Composable
private fun MiniBar(ui: BrowseUi, actions: PlayerActions) {
    var pos by remember { mutableStateOf(0L) }
    LaunchedEffect(Unit) { while (true) { pos = actions.positionMs(); delay(400) } }
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
                SmallIcon(Icons.Filled.SkipPrevious, "Previous", actions::prev)
                SmallIcon(
                    if (ui.player.playing) Icons.Filled.Pause else Icons.Filled.PlayArrow,
                    if (ui.player.playing) "Pause" else "Play",
                    actions::playPause, primary = true,
                )
                SmallIcon(Icons.Filled.SkipNext, "Next", actions::next)
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
private fun SmallIcon(icon: ImageVector, label: String, onClick: () -> Unit,
                      primary: Boolean = false) {
    Box(
        Modifier.size(if (primary) 44.dp else 38.dp)
            .tvFocus(RoundedCornerShape(50), scale = 1.12f)
            .clip(CircleShape)
            .background(if (primary) Sp.Accent else Color(0x1FFFFFFF))
            .spClickable(onClick),
        contentAlignment = Alignment.Center,
    ) {
        Icon(icon, contentDescription = label,
             tint = if (primary) Color.White else Sp.Text,
             modifier = Modifier.size(if (primary) 22.dp else 19.dp))
    }
}

private fun fmt(ms: Long): String {
    val t = (ms / 1000).coerceAtLeast(0)
    return "%d:%02d".format(t / 60, t % 60)
}
