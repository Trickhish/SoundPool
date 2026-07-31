package dev.dury.soundpool.browse

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.material.icons.filled.QueueMusic
import androidx.compose.material.icons.filled.MoreHoriz
import androidx.compose.material.icons.filled.SwapVert
import androidx.compose.material.icons.filled.VolumeUp
import androidx.compose.ui.input.key.type
import androidx.compose.ui.input.key.onKeyEvent
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.Key
import androidx.compose.foundation.focusable
import androidx.compose.material.icons.filled.PlaylistPlay
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Shuffle
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Speaker
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusProperties
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import dev.dury.soundpool.ui.Sp
import dev.dury.soundpool.ui.spClickable
import dev.dury.soundpool.ui.tvFocus

// ── search ──────────────────────────────────────────────────────────────────

@Composable
fun SearchPage(ui: BrowseUi, actions: PlayerActions) {
    var q by remember { mutableStateOf(ui.query) }
    val firstResult = remember { FocusRequester() }
    val field = remember { FocusRequester() }
    LaunchedEffect(Unit) { runCatching { field.requestFocus() } }

    // Hand focus to the results as soon as they land: a focused TextField
    // swallows D-pad down as well as left/right, so without this the remote has
    // no way off the search box once you've typed.
    LaunchedEffect(ui.results) {
        if (ui.results.isNotEmpty()) runCatching { firstResult.requestFocus() }
    }

    Column(Modifier.fillMaxSize()) {
        OutlinedTextField(
            value = q,
            onValueChange = { q = it; actions.setQuery(it) },
            singleLine = true,
            placeholder = { Text("Search songs, artists…", color = Sp.Faint, fontSize = 17.sp) },
            // Search from the keyboard's own action key: a focused TextField
            // eats D-pad left/right, so the remote can't step off to a button.
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
            keyboardActions = KeyboardActions(onSearch = { actions.search(q) }),
            shape = RoundedCornerShape(999.dp),
            textStyle = TextStyle(color = Sp.Text, fontSize = 17.sp),
            colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = Sp.Accent,
                unfocusedBorderColor = Color(0x1AFFFFFF),
                focusedContainerColor = Sp.Surface1,
                unfocusedContainerColor = Sp.Surface1,
                cursorColor = Sp.Accent,
            ),
            modifier = Modifier.fillMaxWidth(0.75f)
                .focusRequester(field)
                .focusProperties { if (ui.results.isNotEmpty()) down = firstResult },
        )

        Spacer(Modifier.height(18.dp))
        ui.error?.let {
            Text(it, color = Sp.Danger, fontSize = 14.sp)
            Spacer(Modifier.height(10.dp))
        }

        when {
            ui.searching -> CircularProgressIndicator(color = Sp.Accent)
            ui.results.isEmpty() -> Text(
                "Anything you pick is added to the room's queue.",
                fontSize = 16.sp, color = Sp.Muted,
            )
            else -> LazyColumn(
                verticalArrangement = Arrangement.spacedBy(10.dp),
                // The mini bar sits over the bottom of the page, so the last
                // row would otherwise be half-hidden behind it.
                contentPadding = PaddingValues(bottom = 12.dp),
            ) {
                items(ui.results.size) { i ->
                    TrackRow(
                        ui.results[i],
                        onClick = { actions.openTrackMenu(ui.results[i]) },
                        modifier = if (i == 0) Modifier.focusRequester(firstResult) else Modifier,
                    )
                }
            }
        }
    }
}

@Composable
private fun TrackRow(t: Track, onClick: () -> Unit, modifier: Modifier = Modifier) {
    val shape = RoundedCornerShape(14.dp)
    // The whole row is the target: a D-pad has no cursor to aim at a small "+".
    Row(
        modifier.fillMaxWidth(0.92f)
            .tvFocus(shape)
            .clip(shape)
            .background(Sp.Surface1)
            .spClickable(onClick)
            .padding(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        AsyncImage(model = t.cover, contentDescription = null,
                   modifier = Modifier.size(54.dp).clip(RoundedCornerShape(8.dp)),
                   contentScale = ContentScale.Crop)
        Spacer(Modifier.width(14.dp))
        Column(Modifier.weight(1f)) {
            Text(t.title, fontSize = 18.sp, color = Sp.Text, maxLines = 1,
                 fontWeight = FontWeight.SemiBold, overflow = TextOverflow.Ellipsis)
            Text(t.artist, fontSize = 14.sp, color = Sp.Muted, maxLines = 1,
                 overflow = TextOverflow.Ellipsis)
        }
        Spacer(Modifier.width(12.dp))
        Icon(Icons.Filled.MoreHoriz, contentDescription = "Options", tint = Sp.Muted,
             modifier = Modifier.size(24.dp))
    }
}

// ── queue ───────────────────────────────────────────────────────────────────

@Composable
fun QueuePage(ui: BrowseUi, actions: PlayerActions) {
    val queue = ui.player.fullQueue
    // Which item (by song id, stable across the reorder) is in move mode.
    var movingId by remember { mutableStateOf<String?>(null) }
    // Re-grab focus onto the moving row after a reorder shuffles the list.
    val moveFocus = remember { FocusRequester() }
    LaunchedEffect(queue, movingId) {
        if (movingId != null) runCatching { moveFocus.requestFocus() }
    }
    // Leaving move mode should be handled before the page's own BACK.
    BackHandler(enabled = movingId != null) { movingId = null }

    // Keep the current track pinned to the top — on open and each time it
    // advances — but never yank the list while the user is reordering.
    val listState = rememberLazyListState()
    LaunchedEffect(ui.player.currentIndex) {
        val ci = ui.player.currentIndex
        if (ci >= 0 && movingId == null) {
            val row = queue.indexOfFirst { it.index == ci }
            if (row >= 0) runCatching { listState.scrollToItem(row) }
        }
    }

    Column(Modifier.fillMaxSize()) {
        Text(if (movingId != null) "Moving — ↑↓ reorder · → after current · OK to drop"
             else "Queue", fontSize = 30.sp, fontWeight = FontWeight.Bold,
             color = if (movingId != null) Sp.Accent else Sp.Text)
        Spacer(Modifier.height(16.dp))
        if (queue.isEmpty()) {
            Text("Nothing queued.", fontSize = 16.sp, color = Sp.Muted)
            return@Column
        }
        LazyColumn(
            state = listState,
            verticalArrangement = Arrangement.spacedBy(8.dp),
            contentPadding = PaddingValues(bottom = 12.dp),
        ) {
            items(queue.size, key = { queue[it].id + "@" + queue[it].index }) { i ->
                val q = queue[i]
                QueueRow(
                    item = q,
                    isCurrent = q.index == ui.player.currentIndex,
                    isMoving = q.id == movingId,
                    focusMod = if (q.id == movingId) Modifier.focusRequester(moveFocus)
                               else Modifier,
                    onActivate = {
                        if (movingId == q.id) movingId = null          // drop here
                        else actions.jumpTo(q.index)                   // play now
                    },
                    onEnterMove = { movingId = q.id },
                    onMove = { delta ->
                        // The server's move() compensates for removing the item
                        // first (frm<to -> to-=1), so a one-step move down is
                        // target index+2, not index+1.
                        when {
                            delta < 0 && q.index > 0 ->
                                actions.moveQueue(q.index, q.index - 1)
                            delta > 0 && q.index < queue.size - 1 ->
                                actions.moveQueue(q.index, q.index + 2)
                        }
                    },
                    onMoveAfterCurrent = {
                        // Same to= for any source: after popping, +1 lands it
                        // right after the current track either way.
                        val ci = ui.player.currentIndex
                        if (ci >= 0 && q.index != ci) actions.moveQueue(q.index, ci + 1)
                        movingId = null
                    },
                )
            }
        }
    }
}

@Composable
private fun QueueRow(item: QueueItem, isCurrent: Boolean, isMoving: Boolean,
                     focusMod: Modifier, onActivate: () -> Unit,
                     onEnterMove: () -> Unit, onMove: (Int) -> Unit,
                     onMoveAfterCurrent: () -> Unit) {
    val shape = RoundedCornerShape(12.dp)
    val bg = when {
        isMoving -> Sp.Accent.copy(alpha = 0.22f)
        isCurrent -> Sp.Accent.copy(alpha = 0.14f)
        else -> Color(0x14FFFFFF)
    }
    Row(
        focusMod.fillMaxWidth(0.92f)
            .tvFocus(shape, scale = 1.02f)
            .clip(shape)
            .background(bg)
            .onKeyEvent { e ->
                if (e.type != KeyEventType.KeyDown) return@onKeyEvent false
                when {
                    // RIGHT picks the row up; UP/DOWN then reorder it. While
                    // moving, LEFT/RIGHT are trapped so focus can't wander off
                    // the row being dragged — OK or BACK drops it.
                    !isMoving && e.key == Key.DirectionRight -> { onEnterMove(); true }
                    isMoving && e.key == Key.DirectionUp -> { onMove(-1); true }
                    isMoving && e.key == Key.DirectionDown -> { onMove(+1); true }
                    isMoving && e.key == Key.DirectionRight -> { onMoveAfterCurrent(); true }
                    isMoving && e.key == Key.DirectionLeft -> true
                    else -> false
                }
            }
            // OK plays the track, or drops it while moving.
            .spClickable(onActivate)
            .padding(10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (isCurrent) {
            Icon(Icons.Filled.VolumeUp, contentDescription = "Now playing", tint = Sp.Accent,
                 modifier = Modifier.width(30.dp).size(18.dp))
        } else {
            Text("${item.index + 1}", fontSize = 13.sp, color = Sp.Faint,
                 modifier = Modifier.width(30.dp))
        }
        if (item.cover.isNotEmpty()) {
            AsyncImage(model = item.cover, contentDescription = null,
                       modifier = Modifier.size(42.dp).clip(RoundedCornerShape(7.dp)),
                       contentScale = ContentScale.Crop)
            Spacer(Modifier.width(12.dp))
        }
        Column(Modifier.weight(1f)) {
            Text(item.title, fontSize = 16.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
                 color = if (isCurrent) Sp.Accent else Sp.Text,
                 fontWeight = if (isCurrent) FontWeight.Bold else FontWeight.Normal)
            Text(item.artist, fontSize = 13.sp, color = Sp.Muted, maxLines = 1,
                 overflow = TextOverflow.Ellipsis)
        }
        if (isMoving) {
            Icon(Icons.Filled.SwapVert, contentDescription = null, tint = Sp.Accent,
                 modifier = Modifier.size(22.dp))
        }
    }
}

// ── playlists ───────────────────────────────────────────────────────────────

@Composable
fun PlaylistsPage(ui: BrowseUi, actions: PlayerActions) {
    LaunchedEffect(Unit) { actions.loadPlaylists() }
    // Back out of a drilled-in playlist before leaving the page.
    BackHandler(enabled = ui.openPlaylist != null) { actions.closePlaylist() }

    if (ui.openPlaylist != null) {
        PlaylistDetail(ui, actions)
    } else {
        PlaylistGrid(ui, actions)
    }
}

@Composable
private fun PlaylistGrid(ui: BrowseUi, actions: PlayerActions) {
    val first = remember { FocusRequester() }
    LaunchedEffect(ui.playlists) {
        if (ui.playlists.isNotEmpty()) runCatching { first.requestFocus() }
    }

    Column(Modifier.fillMaxSize()) {
        Text("Your playlists", fontSize = 30.sp, fontWeight = FontWeight.Bold, color = Sp.Text)
        Spacer(Modifier.height(16.dp))
        when {
            ui.playlistsLoading -> CircularProgressIndicator(color = Sp.Accent)
            ui.playlists.isEmpty() -> Text(
                ui.error ?: "No playlists on your Deezer account.",
                fontSize = 16.sp, color = Sp.Muted,
            )
            else -> LazyVerticalGrid(
                // Fixed 5-wide keeps the cards a sensible size; Adaptive(220)
                // made each one huge on a 1080p TV.
                columns = GridCells.Fixed(5),
                horizontalArrangement = Arrangement.spacedBy(14.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
                contentPadding = PaddingValues(bottom = 14.dp),
            ) {
                items(ui.playlists.size) { i ->
                    PlaylistCard(
                        ui.playlists[i],
                        onClick = { actions.openPlaylist(ui.playlists[i]) },
                        modifier = if (i == 0) Modifier.focusRequester(first) else Modifier,
                    )
                }
            }
        }
    }
}

@Composable
private fun PlaylistCard(p: Playlist, onClick: () -> Unit, modifier: Modifier = Modifier) {
    val shape = RoundedCornerShape(12.dp)
    Column(
        modifier.fillMaxWidth()      // one grid cell — the column sizes the card
            .tvFocus(shape, scale = 1.05f)
            .clip(shape)
            .background(Sp.Surface1)
            .spClickable(onClick)
            .padding(8.dp),
    ) {
        Box(Modifier.fillMaxWidth().aspectRatio(1f).clip(RoundedCornerShape(8.dp))
                .background(Sp.Surface2), contentAlignment = Alignment.Center) {
            if (p.cover.isNotEmpty()) {
                AsyncImage(model = p.cover, contentDescription = null,
                           modifier = Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
            } else {
                Icon(Icons.Filled.QueueMusic, contentDescription = null, tint = Sp.Faint,
                     modifier = Modifier.size(36.dp))
            }
        }
        Spacer(Modifier.height(8.dp))
        Text(p.title, fontSize = 14.sp, color = Sp.Text, maxLines = 1,
             fontWeight = FontWeight.SemiBold, overflow = TextOverflow.Ellipsis)
        Text("${p.trackCount} tracks", fontSize = 12.sp, color = Sp.Muted)
    }
}

@Composable
private fun PlaylistDetail(ui: BrowseUi, actions: PlayerActions) {
    val p = ui.openPlaylist ?: return
    val first = remember { FocusRequester() }
    LaunchedEffect(Unit) { runCatching { first.requestFocus() } }

    Column(Modifier.fillMaxSize()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            if (p.cover.isNotEmpty()) {
                AsyncImage(model = p.cover, contentDescription = null,
                           modifier = Modifier.size(72.dp).clip(RoundedCornerShape(10.dp)),
                           contentScale = ContentScale.Crop)
                Spacer(Modifier.width(16.dp))
            }
            Column(Modifier.weight(1f)) {
                Text(p.title, fontSize = 26.sp, fontWeight = FontWeight.Bold, color = Sp.Text,
                     maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text("${p.trackCount} tracks", fontSize = 14.sp, color = Sp.Muted)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalAlignment = Alignment.CenterVertically) {
                // Play and Shuffle replace the queue with the playlist; Queue all
                // appends. Play is primary and takes initial focus.
                IconPill(Icons.Filled.PlayArrow, "Play",
                         onClick = { actions.playPlaylist(p, shuffle = false) },
                         primary = true, modifier = Modifier.focusRequester(first))
                IconPill(Icons.Filled.Shuffle, "Shuffle",
                         onClick = { actions.playPlaylist(p, shuffle = true) })
                IconPill(Icons.Filled.Add, "Queue all",
                         onClick = { actions.queueWholePlaylist(p) })
            }
        }
        Spacer(Modifier.height(16.dp))

        when {
            ui.playlistTracksLoading -> CircularProgressIndicator(color = Sp.Accent)
            else -> LazyColumn(
                verticalArrangement = Arrangement.spacedBy(10.dp),
                contentPadding = PaddingValues(bottom = 12.dp),
            ) {
                items(ui.playlistTracks.size) { i ->
                    TrackRow(ui.playlistTracks[i],
                             onClick = { actions.openTrackMenu(ui.playlistTracks[i]) })
                }
            }
        }
    }
}

// ── settings ────────────────────────────────────────────────────────────────

@Composable
fun SettingsPage(ui: BrowseUi, actions: PlayerActions, onSignOut: () -> Unit,
                 onOpenDisplay: () -> Unit, onOpenUnit: () -> Unit) {
    val first = remember { FocusRequester() }
    LaunchedEffect(Unit) { runCatching { first.requestFocus() } }

    Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text("Settings", fontSize = 30.sp, fontWeight = FontWeight.Bold, color = Sp.Text)
        Spacer(Modifier.height(2.dp))
        Text("Room: ${ui.player.roomName.ifEmpty { "—" }}", fontSize = 16.sp, color = Sp.Muted)

        Spacer(Modifier.height(6.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            PillButton("Change room", onClick = actions::leaveRoom,
                       modifier = Modifier.focusRequester(first))
            PillButton("Big screen mode", onClick = onOpenDisplay, primary = false)
        }
        Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            PillButton("Unit status", onClick = onOpenUnit, primary = false)
            PillButton("Sign out", onClick = onSignOut, primary = false)
        }
    }
}

// ── room picker ─────────────────────────────────────────────────────────────

@Composable
fun RoomPicker(ui: BrowseUi, onPick: (Int) -> Unit, onReload: () -> Unit) {
    // BACK cancels a room change and returns to the room you were in. At first
    // launch there's no previous room, so BACK falls through (exits the app,
    // which is the normal Android root behaviour).
    BackHandler(enabled = ui.previousRoomId != 0) { onPick(ui.previousRoomId) }
    val first = remember { FocusRequester() }
    LaunchedEffect(ui.rooms) {
        if (ui.rooms.isNotEmpty()) runCatching { first.requestFocus() }
    }

    Column(Modifier.fillMaxSize().padding(horizontal = Sp.SafeH, vertical = Sp.SafeV)) {
        Text("Choose a room", fontSize = 38.sp, fontWeight = FontWeight.Bold, color = Sp.Text)
        Spacer(Modifier.height(4.dp))
        Text("This TV will play and queue into it.", fontSize = 17.sp, color = Sp.Muted)
        Spacer(Modifier.height(26.dp))

        when {
            ui.roomsLoading -> CircularProgressIndicator(color = Sp.Accent)
            ui.rooms.isEmpty() && ui.error != null -> Column {
                Text(ui.error, color = Sp.Danger, fontSize = 16.sp)
                Spacer(Modifier.height(16.dp))
                PillButton("Retry", onClick = onReload, modifier = Modifier.focusRequester(first))
            }
            ui.rooms.isEmpty() -> Text("No rooms yet — create one from the web app.",
                                       color = Sp.Muted, fontSize = 17.sp)
            else -> LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                items(ui.rooms.size) { i ->
                    val r = ui.rooms[i]
                    val shape = RoundedCornerShape(16.dp)
                    Row(
                        (if (i == 0) Modifier.focusRequester(first) else Modifier)
                            .fillMaxWidth(0.55f)
                            .tvFocus(shape)
                            .clip(shape)
                            .background(Sp.Surface1)
                            .spClickable { onPick(r.id) }
                            .padding(horizontal = 22.dp, vertical = 18.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Box(Modifier.size(38.dp).clip(CircleShape).background(Sp.Surface2),
                            contentAlignment = Alignment.Center) {
                            Icon(Icons.Filled.Speaker, contentDescription = null,
                                 tint = Sp.Accent, modifier = Modifier.size(20.dp))
                        }
                        Spacer(Modifier.width(16.dp))
                        Text(r.name, fontSize = 21.sp, fontWeight = FontWeight.SemiBold,
                             color = Sp.Text)
                    }
                }
            }
        }
    }
}

@Composable
fun IconPill(icon: androidx.compose.ui.graphics.vector.ImageVector, label: String,
             onClick: () -> Unit, primary: Boolean = false, modifier: Modifier = Modifier) {
    val shape = RoundedCornerShape(999.dp)
    val fg = if (primary) Color.White else Sp.Text
    Row(
        modifier
            .tvFocus(shape, scale = 1.06f)
            .clip(shape)
            .background(if (primary) Sp.Accent else Color(0x1FFFFFFF))
            .spClickable(onClick)
            .padding(horizontal = 20.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(icon, contentDescription = null, tint = fg, modifier = Modifier.size(20.dp))
        Spacer(Modifier.width(8.dp))
        Text(label, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, color = fg)
    }
}

@Composable
fun PillButton(label: String, onClick: () -> Unit, primary: Boolean = true,
               modifier: Modifier = Modifier) {
    val shape = RoundedCornerShape(999.dp)
    Box(
        modifier
            .tvFocus(shape, scale = 1.06f)
            .clip(shape)
            .background(if (primary) Sp.Accent else Color(0x1FFFFFFF))
            .spClickable(onClick)
            .padding(horizontal = 26.dp, vertical = 13.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(label, fontSize = 16.sp, fontWeight = FontWeight.SemiBold,
             color = if (primary) Color.White else Sp.Text)
    }
}

// ── per-track action menu ─────────────────────────────────────────────────

/**
 * The play-now / play-next / add-to-queue chooser shown when a track is
 * activated. A centered card of full-width rows — a D-pad has no cursor, so
 * each choice is its own big focus target.
 */
@Composable
fun TrackActionSheet(track: Track, actions: PlayerActions) {
    val first = remember { FocusRequester() }
    LaunchedEffect(Unit) { runCatching { first.requestFocus() } }
    BackHandler { actions.closeTrackMenu() }

    Box(
        Modifier.fillMaxSize().background(Color(0xC0000000))
            .spClickable { actions.closeTrackMenu() },
        contentAlignment = Alignment.Center,
    ) {
        Column(
            Modifier.width(440.dp).clip(RoundedCornerShape(20.dp))
                .background(Sp.Surface1).padding(20.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                AsyncImage(model = track.cover, contentDescription = null,
                           modifier = Modifier.size(52.dp).clip(RoundedCornerShape(8.dp)),
                           contentScale = ContentScale.Crop)
                Spacer(Modifier.width(14.dp))
                Column {
                    Text(track.title, fontSize = 17.sp, color = Sp.Text, maxLines = 1,
                         fontWeight = FontWeight.SemiBold, overflow = TextOverflow.Ellipsis)
                    Text(track.artist, fontSize = 13.sp, color = Sp.Muted, maxLines = 1,
                         overflow = TextOverflow.Ellipsis)
                }
            }
            Spacer(Modifier.height(18.dp))
            ActionRow(Icons.Filled.PlayArrow, "Play now", { actions.playNow(track) },
                      Modifier.focusRequester(first))
            Spacer(Modifier.height(8.dp))
            ActionRow(Icons.Filled.PlaylistPlay, "Play next", { actions.playNext(track) })
            Spacer(Modifier.height(8.dp))
            ActionRow(Icons.Filled.Add, "Add to queue",
                      { actions.addToQueue(track); actions.closeTrackMenu() })
        }
    }
}

@Composable
private fun ActionRow(icon: androidx.compose.ui.graphics.vector.ImageVector, label: String,
                      onClick: () -> Unit, modifier: Modifier = Modifier) {
    val shape = RoundedCornerShape(12.dp)
    Row(
        modifier.fillMaxWidth()
            .tvFocus(shape, scale = 1.03f)
            .clip(shape)
            .background(Sp.Surface2)
            .spClickable(onClick)
            .padding(horizontal = 16.dp, vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(icon, contentDescription = null, tint = Sp.Accent, modifier = Modifier.size(22.dp))
        Spacer(Modifier.width(14.dp))
        Text(label, fontSize = 17.sp, color = Sp.Text, fontWeight = FontWeight.Medium)
    }
}
