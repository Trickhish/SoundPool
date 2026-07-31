package dev.dury.soundpool.browse

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.material.icons.filled.QueueMusic
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
import dev.dury.soundpool.ui.tvFocus

// ── search ──────────────────────────────────────────────────────────────────

@Composable
fun SearchPage(ui: BrowseUi, vm: BrowseViewModel) {
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
            onValueChange = { q = it; vm.setQuery(it) },
            singleLine = true,
            placeholder = { Text("Search songs, artists…", color = Sp.Faint, fontSize = 17.sp) },
            // Search from the keyboard's own action key: a focused TextField
            // eats D-pad left/right, so the remote can't step off to a button.
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
            keyboardActions = KeyboardActions(onSearch = { vm.search(q) }),
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
                        onClick = { vm.addToQueue(ui.results[i]) },
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
            .clickable(onClick = onClick)
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
        Text("+ QUEUE", fontSize = 12.sp, color = Sp.Accent,
             fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
    }
}

// ── queue ───────────────────────────────────────────────────────────────────

@Composable
fun QueuePage(ui: BrowseUi) {
    Column(Modifier.fillMaxSize()) {
        Text("Up next", fontSize = 30.sp, fontWeight = FontWeight.Bold, color = Sp.Text)
        Spacer(Modifier.height(16.dp))
        if (ui.player.queue.isEmpty()) {
            Text("Nothing queued.", fontSize = 16.sp, color = Sp.Muted)
            return@Column
        }
        LazyColumn(
            verticalArrangement = Arrangement.spacedBy(10.dp),
            contentPadding = PaddingValues(bottom = 12.dp),
        ) {
            items(ui.player.queue.size) { i ->
                val q = ui.player.queue[i]
                Row(
                    Modifier.fillMaxWidth(0.9f).clip(RoundedCornerShape(12.dp))
                        .background(Color(0x14FFFFFF)).padding(10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text("${i + 1}", fontSize = 13.sp, color = Sp.Faint,
                         modifier = Modifier.width(30.dp))
                    if (q.cover.isNotEmpty()) {
                        AsyncImage(model = q.cover, contentDescription = null,
                                   modifier = Modifier.size(42.dp).clip(RoundedCornerShape(7.dp)),
                                   contentScale = ContentScale.Crop)
                        Spacer(Modifier.width(12.dp))
                    }
                    Column {
                        Text(q.title, fontSize = 16.sp, color = Sp.Text, maxLines = 1,
                             overflow = TextOverflow.Ellipsis)
                        Text(q.artist, fontSize = 13.sp, color = Sp.Muted, maxLines = 1,
                             overflow = TextOverflow.Ellipsis)
                    }
                }
            }
        }
    }
}

// ── playlists ───────────────────────────────────────────────────────────────

@Composable
fun PlaylistsPage(ui: BrowseUi, vm: BrowseViewModel) {
    LaunchedEffect(Unit) { vm.loadPlaylists() }
    // Back out of a drilled-in playlist before leaving the page.
    BackHandler(enabled = ui.openPlaylist != null) { vm.closePlaylist() }

    if (ui.openPlaylist != null) {
        PlaylistDetail(ui, vm)
    } else {
        PlaylistGrid(ui, vm)
    }
}

@Composable
private fun PlaylistGrid(ui: BrowseUi, vm: BrowseViewModel) {
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
                        onClick = { vm.openPlaylist(ui.playlists[i]) },
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
            .clickable(onClick = onClick)
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
private fun PlaylistDetail(ui: BrowseUi, vm: BrowseViewModel) {
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
                         onClick = { vm.playPlaylist(p, shuffle = false) },
                         primary = true, modifier = Modifier.focusRequester(first))
                IconPill(Icons.Filled.Shuffle, "Shuffle",
                         onClick = { vm.playPlaylist(p, shuffle = true) })
                IconPill(Icons.Filled.Add, "Queue all",
                         onClick = { vm.queueWholePlaylist(p) })
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
                             onClick = { vm.addToQueue(ui.playlistTracks[i]) })
                }
            }
        }
    }
}

// ── settings ────────────────────────────────────────────────────────────────

@Composable
fun SettingsPage(ui: BrowseUi, vm: BrowseViewModel, onSignOut: () -> Unit,
                 onOpenDisplay: () -> Unit, onOpenUnit: () -> Unit) {
    val first = remember { FocusRequester() }
    LaunchedEffect(Unit) { runCatching { first.requestFocus() } }

    Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text("Settings", fontSize = 30.sp, fontWeight = FontWeight.Bold, color = Sp.Text)
        Spacer(Modifier.height(2.dp))
        Text("Room: ${ui.player.roomName.ifEmpty { "—" }}", fontSize = 16.sp, color = Sp.Muted)

        Spacer(Modifier.height(6.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            PillButton("Change room", onClick = vm::leaveRoom,
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
                            .clickable { onPick(r.id) }
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
            .clickable(onClick = onClick)
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
            .clickable(onClick = onClick)
            .padding(horizontal = 26.dp, vertical = 13.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(label, fontSize = 16.sp, fontWeight = FontWeight.SemiBold,
             color = if (primary) Color.White else Sp.Text)
    }
}
