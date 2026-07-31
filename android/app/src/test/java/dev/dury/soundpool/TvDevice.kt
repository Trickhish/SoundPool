package dev.dury.soundpool

import app.cash.paparazzi.DeviceConfig
import com.android.resources.Density
import com.android.resources.ScreenOrientation

/** The KM6 output: 1080p landscape at 320dpi (≈ 960×540 dp). */
val TV_1080P = DeviceConfig(
    screenWidth = 1920,
    screenHeight = 1080,
    xdpi = 320,
    ydpi = 320,
    density = Density.XHIGH,
    orientation = ScreenOrientation.LANDSCAPE,
    nightMode = com.android.resources.NightMode.NOTNIGHT,
    softButtons = false,
)
