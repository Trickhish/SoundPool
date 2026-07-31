package dev.dury.soundpool.ui

import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.scale
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

/**
 * Mirrors the web app's palette (styles/_vars.scss) so the TV doesn't look like
 * a different product.
 */
object Sp {
    val Accent = Color(0xFFFF2B6D)
    val AccentCyan = Color(0xFF00DFFF)
    val AccentGlow = Color(0x40FF2B6D)

    val Bg = Color(0xFF07070F)
    val Surface1 = Color(0xFF0E0E1D)
    val Surface2 = Color(0xFF15152A)
    val SurfaceHover = Color(0xFF1A1A30)

    val Text = Color(0xFFEEEDF7)
    val Muted = Color(0xFF8B8BAE)      // lifted from #52527A: too dark to read across a room
    val Faint = Color(0xFF52527A)

    val Danger = Color(0xFFFF3B5C)
    val Ok = Color(0xFF4ADE80)

    /** TV-safe inset. Many panels overscan and clip the outer ~4%. */
    val SafeH = 56.dp
    val SafeV = 34.dp
}

/**
 * The app's background: the same two-radial-gradient wash the web uses —
 * violet from the top-left, pink from the bottom-right, over near-black.
 */
@Composable
fun SpBackground(content: @Composable () -> Unit) {
    Box(Modifier.fillMaxSize().background(Sp.Bg)) {
        Box(
            Modifier.fillMaxSize().background(
                Brush.radialGradient(
                    colors = listOf(Color(0x615014BE), Color.Transparent),
                    center = Offset(200f, 100f),
                    radius = 1500f,
                )
            )
        )
        Box(
            Modifier.fillMaxSize().background(
                Brush.radialGradient(
                    colors = listOf(Color(0x47FF1E64), Color.Transparent),
                    center = Offset(1800f, 1000f),
                    radius = 1400f,
                )
            )
        )
        content()
    }
}

/**
 * Focus treatment for TV. Across a room you need more than a subtle tint to see
 * where you are, so focus lifts the element, rings it in the accent colour and
 * casts a glow.
 */
@Composable
fun Modifier.tvFocus(
    shape: RoundedCornerShape = RoundedCornerShape(14.dp),
    scale: Float = 1.04f,
): Modifier {
    var focused by remember { mutableStateOf(false) }
    val s by animateFloatAsState(if (focused) scale else 1f, spring(), label = "focusScale")
    val ring by animateDpAsState(if (focused) 2.dp else 1.dp, label = "focusRing")
    return this
        .onFocusChanged { focused = it.isFocused }
        .scale(s)
        .shadow(if (focused) 18.dp else 0.dp, shape, ambientColor = Sp.Accent,
                spotColor = Sp.Accent)
        .border(ring, if (focused) Sp.Accent else Color(0x1AFFFFFF), shape)
}
