package dev.dury.soundpool.browse

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.text.input.ImeAction
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage

private val MUTED = Color(0xFFB9A9D8)
private val ACCENT = Color(0xFF7C3AED)
private val PANEL = Color(0xFF17111F)

@Composable
fun BrowseScreen(vm: BrowseViewModel, onExit: () -> Unit) {
    val ui by vm.ui.collectAsState()

    LaunchedEffect(Unit) { vm.enterBrowse() }

    // Otherwise BACK leaves the app entirely instead of going back a screen.
    BackHandler { onExit() }

    Box(Modifier.fillMaxSize()) {
        if (ui.roomId == 0) {
            RoomPicker(ui, onPick = { vm.chooseRoom(it) }, onReload = { vm.loadRooms() },
                       onExit = onExit)
        } else {
            Browser(ui, vm, onExit)
        }

        ui.toast?.let {
            Box(
                Modifier.align(Alignment.BottomCenter).padding(bottom = 28.dp)
                    .clip(RoundedCornerShape(999.dp)).background(ACCENT).padding(20.dp, 10.dp)
            ) { Text(it, color = Color.White, fontSize = 15.sp) }
        }
    }
}

@Composable
private fun RoomPicker(ui: BrowseUi, onPick: (Int) -> Unit, onReload: () -> Unit,
                       onExit: () -> Unit) {
    val first = remember { FocusRequester() }
    LaunchedEffect(ui.rooms) { runCatching { first.requestFocus() } }

    Column(Modifier.fillMaxSize().padding(48.dp)) {
        Text("Choose a room", fontSize = 32.sp, fontWeight = FontWeight.Bold, color = Color.White)
        Text("This TV will play and queue into it.", fontSize = 16.sp, color = MUTED)
        Spacer(Modifier.height(24.dp))

        when {
            ui.roomsLoading -> CircularProgressIndicator(color = ACCENT)
            ui.error != null -> Column {
                Text(ui.error, color = Color(0xFFF87171), fontSize = 16.sp)
                Spacer(Modifier.height(14.dp))
                Button(onClick = onReload, modifier = Modifier.focusRequester(first)) {
                    Text("Retry")
                }
            }
            ui.rooms.isEmpty() -> Text("No rooms yet — create one from the web app.",
                                       color = MUTED, fontSize = 16.sp)
            else -> LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                itemsIndexed(ui.rooms) { i, r ->
                    Button(
                        onClick = { onPick(r.id) },
                        modifier = Modifier.fillMaxWidth(0.6f)
                            .then(if (i == 0) Modifier.focusRequester(first) else Modifier),
                    ) {
                        Text(r.name, fontSize = 18.sp, modifier = Modifier.weight(1f))
                    }
                }
            }
        }

        Spacer(Modifier.height(24.dp))
        OutlinedButton(onClick = onExit) { Text("Back") }
    }
}

private fun <T> androidx.compose.foundation.lazy.LazyListScope.itemsIndexed(
    list: List<T>, content: @Composable (Int, T) -> Unit,
) = items(list.size) { i -> content(i, list[i]) }

@Composable
private fun Browser(ui: BrowseUi, vm: BrowseViewModel, onExit: () -> Unit) {
    // Park focus on play/pause. Left to itself the first focusable wins, which
    // is the prev button — and focusing the search field instead would throw
    // the leanback keyboard over the screen on arrival.
    val playFocus = remember { FocusRequester() }
    val searchFocus = remember { FocusRequester() }
    val searchBtnFocus = remember { FocusRequester() }
    LaunchedEffect(Unit) { runCatching { playFocus.requestFocus() } }

    Row(Modifier.fillMaxSize().padding(32.dp), horizontalArrangement = Arrangement.spacedBy(28.dp)) {

        // ── left: what's on, and the transport ──
        Column(Modifier.width(300.dp)) {
            if (ui.player.cover.isNotEmpty()) {
                AsyncImage(
                    model = ui.player.cover, contentDescription = null,
                    modifier = Modifier.size(220.dp).clip(RoundedCornerShape(14.dp)),
                    contentScale = ContentScale.Crop,
                )
                Spacer(Modifier.height(12.dp))
            }
            Text(ui.player.title.ifEmpty { "Nothing playing" }, fontSize = 20.sp,
                 fontWeight = FontWeight.Bold, color = Color.White, maxLines = 2)
            Text(ui.player.artist, fontSize = 15.sp, color = MUTED, maxLines = 1)

            Spacer(Modifier.height(14.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedButton(onClick = { vm.prev() }, contentPadding = PaddingValues(12.dp, 6.dp)) {
                    Text("⏮", fontSize = 17.sp)
                }
                Button(onClick = { vm.playPause() },
                       contentPadding = PaddingValues(18.dp, 6.dp),
                       // Explicit hop across the columns: 2D focus search sent
                       // RIGHT to whatever was nearest, which was the Back
                       // button rather than the search box.
                       modifier = Modifier.focusRequester(playFocus)
                           .focusProperties { right = searchFocus }) {
                    Text(if (ui.player.playing) "⏸" else "▶", fontSize = 17.sp)
                }
                OutlinedButton(onClick = { vm.next() }, contentPadding = PaddingValues(12.dp, 6.dp)) {
                    Text("⏭", fontSize = 17.sp)
                }
            }

            Spacer(Modifier.height(20.dp))
            Text("Up next", fontSize = 13.sp, color = MUTED)
            Spacer(Modifier.height(6.dp))
            if (ui.player.queue.isEmpty()) {
                Text("Nothing queued", fontSize = 13.sp, color = Color(0xFF7C6F93))
            }
            LazyColumn(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                items(ui.player.queue.size) { i ->
                    val q = ui.player.queue[i]
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("${i + 1}.", fontSize = 12.sp, color = Color(0xFF7C6F93),
                             modifier = Modifier.width(22.dp))
                        Column {
                            Text(q.title, fontSize = 13.sp, color = Color.White, maxLines = 1)
                            Text(q.artist, fontSize = 11.sp, color = MUTED, maxLines = 1)
                        }
                    }
                }
            }
        }

        // ── right: search ──
        Column(Modifier.weight(1f)) {
            var q by remember { mutableStateOf(ui.query) }
            // Explicit focus order. Left to itself, DOWN from the search box
            // jumped across to the transport controls in the other column,
            // because 2D focus search picks the geometrically nearest target
            // rather than the obviously-intended one.
            val firstResult = remember { FocusRequester() }

            // Hand focus to the results as soon as they land. A focused
            // TextField swallows D-pad down as well as left/right, so without
            // this the remote has no way off the search box once you've typed.
            LaunchedEffect(ui.results) {
                if (ui.results.isNotEmpty()) runCatching { firstResult.requestFocus() }
            }

            // Every direction is pinned. Relying on Compose's 2D focus search
            // here sent RIGHT from the field back across to the transport and
            // DOWN into the other column, so presses landed on play/pause
            // instead of the search button and results.
            Row(verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedTextField(
                    value = q,
                    onValueChange = { q = it; vm.setQuery(it) },
                    label = { Text("Search songs") },
                    singleLine = true,
                    // Search straight from the keyboard's action key. A focused
                    // TextField eats D-pad left/right to move the caret, so
                    // there is no way to step off it to a button — the remote
                    // simply cannot reach one while the field holds focus.
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                    keyboardActions = KeyboardActions(onSearch = { vm.search(q) }),
                    modifier = Modifier.weight(1f)
                        .focusRequester(searchFocus)
                        .focusProperties {
                            left = playFocus
                            if (ui.results.isNotEmpty()) down = firstResult
                        },
                )
                Button(
                    onClick = { vm.search(q) },
                    modifier = Modifier.focusRequester(searchBtnFocus)
                        .focusProperties {
                            left = searchFocus
                            if (ui.results.isNotEmpty()) down = firstResult
                        },
                ) { Text("Search") }
            }

            Spacer(Modifier.height(14.dp))
            ui.error?.let {
                Text(it, color = Color(0xFFF87171), fontSize = 14.sp)
                Spacer(Modifier.height(8.dp))
            }
            when {
                ui.searching -> CircularProgressIndicator(color = ACCENT)
                ui.results.isEmpty() -> Text(
                    "Search for something to add to the queue.",
                    color = Color(0xFF7C6F93), fontSize = 15.sp,
                )
                else -> LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(ui.results.size) { i ->
                        val t = ui.results[i]
                        ResultRow(
                            t,
                            onAdd = { vm.addToQueue(t) },
                            modifier = if (i == 0) Modifier.focusRequester(firstResult)
                                       else Modifier,
                        )
                    }
                }
            }

            Spacer(Modifier.height(12.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedButton(onClick = { vm.leaveRoom() }) { Text("Change room") }
                OutlinedButton(onClick = onExit) { Text("Back") }
            }
        }
    }
}

@Composable
private fun ResultRow(t: Track, onAdd: () -> Unit, modifier: Modifier = Modifier) {
    // The whole row is the button: on a D-pad there's no cursor to aim at a
    // small "+" target, so the focused row and the action are the same thing.
    Surface(
        onClick = onAdd,
        color = PANEL,
        shape = RoundedCornerShape(10.dp),
        modifier = modifier.fillMaxWidth(),
    ) {
        Row(Modifier.padding(10.dp), verticalAlignment = Alignment.CenterVertically) {
            AsyncImage(
                model = t.cover, contentDescription = null,
                modifier = Modifier.size(44.dp).clip(RoundedCornerShape(6.dp)),
                contentScale = ContentScale.Crop,
            )
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(t.title, fontSize = 16.sp, color = Color.White, maxLines = 1)
                Text(t.artist, fontSize = 13.sp, color = MUTED, maxLines = 1)
            }
            Text("+ Queue", fontSize = 13.sp, color = ACCENT)
        }
    }
}
