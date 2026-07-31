package dev.dury.soundpool

import app.cash.paparazzi.Paparazzi
import dev.dury.soundpool.browse.NoPlayerActions
import dev.dury.soundpool.browse.Page
import dev.dury.soundpool.browse.PlayerShell
import org.junit.Rule
import org.junit.Test

/**
 * Off-device renders of every player page. This is the fast design loop: change
 * a screen, run `gradlew recordPaparazziDebug`, and look at the PNGs under
 * src/test/snapshots — no build/install/screenshot on the KM6.
 */
class PlayerSnapshotTest {
    @get:Rule
    val paparazzi = Paparazzi(deviceConfig = TV_1080P)

    private fun shell(ui: dev.dury.soundpool.browse.BrowseUi, page: Page) {
        paparazzi.snapshot {
            PlayerShell(
                ui = ui, actions = NoPlayerActions, page = page,
                onSelectPage = {}, onPickRoom = {}, onReloadRooms = {},
                onSignOut = {}, onOpenDisplay = {}, onOpenUnit = {},
            )
        }
    }

    @Test fun nowPlaying() = shell(uiNowPlaying(), Page.NowPlaying)
    @Test fun search() = shell(uiSearch(), Page.Search)
    @Test fun playlists() = shell(uiPlaylists(), Page.Playlists)
    @Test fun playlistDetail() = shell(uiPlaylistDetail(), Page.Playlists)
    @Test fun queue() = shell(uiQueue(), Page.Queue)
    @Test fun settings() = shell(uiNowPlaying(), Page.Settings)
    @Test fun roomPicker() = shell(uiRoomPicker(), Page.NowPlaying)
}
