package dev.dury.soundpool.browse

/**
 * What the player screens can *do*, separated from how it's done.
 *
 * The page composables take this instead of the concrete BrowseViewModel so
 * they can be rendered with fake data off-device (Paparazzi) — which is the
 * fast design-iteration loop — and so they don't reach into an AndroidViewModel
 * that a JVM test can't construct.
 */
interface PlayerActions {
    fun positionMs(): Long
    fun prev()
    fun next()
    fun playPause()

    fun setQuery(q: String)
    fun search(q: String)
    fun addToQueue(t: Track)
    fun playNow(t: Track)
    fun playNext(t: Track)
    fun openTrackMenu(t: Track)
    fun closeTrackMenu()

    fun loadPlaylists()
    fun openPlaylist(p: Playlist)
    fun closePlaylist()
    fun queueWholePlaylist(p: Playlist)
    fun playPlaylist(p: Playlist, shuffle: Boolean)

    fun jumpTo(index: Int)
    fun moveQueue(from: Int, to: Int)

    fun leaveRoom()
}

/** Adapts the real view model to the interface without the VM depending on it. */
fun BrowseViewModel.asActions(): PlayerActions = object : PlayerActions {
    override fun positionMs() = this@asActions.positionMs()
    override fun prev() = this@asActions.prev()
    override fun next() = this@asActions.next()
    override fun playPause() = this@asActions.playPause()
    override fun setQuery(q: String) = this@asActions.setQuery(q)
    override fun search(q: String) { this@asActions.search(q) }
    override fun addToQueue(t: Track) = this@asActions.addToQueue(t)
    override fun playNow(t: Track) = this@asActions.playNow(t)
    override fun playNext(t: Track) = this@asActions.playNext(t)
    override fun openTrackMenu(t: Track) = this@asActions.openTrackMenu(t)
    override fun closeTrackMenu() = this@asActions.closeTrackMenu()
    override fun loadPlaylists() = this@asActions.loadPlaylists()
    override fun openPlaylist(p: Playlist) = this@asActions.openPlaylist(p)
    override fun closePlaylist() = this@asActions.closePlaylist()
    override fun queueWholePlaylist(p: Playlist) = this@asActions.queueWholePlaylist(p)
    override fun playPlaylist(p: Playlist, shuffle: Boolean) = this@asActions.playPlaylist(p, shuffle)
    override fun jumpTo(index: Int) = this@asActions.jumpTo(index)
    override fun moveQueue(from: Int, to: Int) = this@asActions.moveQueue(from, to)
    override fun leaveRoom() = this@asActions.leaveRoom()
}

/** No-op implementation for previews/snapshots. */
object NoPlayerActions : PlayerActions {
    override fun positionMs() = 79_000L
    override fun prev() {}
    override fun next() {}
    override fun playPause() {}
    override fun setQuery(q: String) {}
    override fun search(q: String) {}
    override fun addToQueue(t: Track) {}
    override fun playNow(t: Track) {}
    override fun playNext(t: Track) {}
    override fun openTrackMenu(t: Track) {}
    override fun closeTrackMenu() {}
    override fun loadPlaylists() {}
    override fun openPlaylist(p: Playlist) {}
    override fun closePlaylist() {}
    override fun queueWholePlaylist(p: Playlist) {}
    override fun playPlaylist(p: Playlist, shuffle: Boolean) {}
    override fun jumpTo(index: Int) {}
    override fun moveQueue(from: Int, to: Int) {}
    override fun leaveRoom() {}
}
