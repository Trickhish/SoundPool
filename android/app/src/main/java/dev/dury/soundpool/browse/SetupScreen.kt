package dev.dury.soundpool.browse

import android.graphics.Bitmap
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import dev.dury.soundpool.net.qrBitmap

private val MUTED = Color(0xFFB9A9D8)
private val ACCENT = Color(0xFF7C3AED)

/**
 * First screen: scan to sign in.
 *
 * The QR carries /link?code=XXXXXX so the phone lands on the approval page with
 * nothing to type. The code is printed underneath as well, for anyone who'd
 * rather type it than scan, and the host is editable for a non-default server.
 */
@Composable
fun SetupScreen(
    state: SignInState,
    host: String,
    onHostChange: (String) -> Unit,
    onRetry: () -> Unit,
) {
    Row(
        Modifier.fillMaxSize().padding(horizontal = 56.dp, vertical = 28.dp),
        horizontalArrangement = Arrangement.spacedBy(48.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        // ── left: what to do ──
        Column(Modifier.weight(1f)) {
            Text("SoundPool", fontSize = 38.sp, fontWeight = FontWeight.Bold, color = Color.White)
            Spacer(Modifier.height(10.dp))
            Text(
                "Scan this code with your phone to sign in.",
                fontSize = 19.sp, color = MUTED,
            )

            Spacer(Modifier.height(20.dp))
            if (state.userCode != null) {
                Text("Or go to ${webOrigin(host)}/link and enter",
                     fontSize = 14.sp, color = Color(0xFF7C6F93))
                Spacer(Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                    state.userCode.forEach { ch ->
                        Box(
                            Modifier.size(38.dp, 48.dp)
                                .clip(RoundedCornerShape(8.dp))
                                .background(Color(0xFF1B1229)),
                            contentAlignment = Alignment.Center,
                        ) {
                            Text("$ch", fontSize = 22.sp, fontWeight = FontWeight.Bold,
                                 color = Color.White)
                        }
                    }
                }
            }

            Spacer(Modifier.height(26.dp))
            // The field stays read-only until asked for. A focusable text field
            // here grabs focus on launch and the leanback IME covers the QR —
            // and the default host is right for everyone but a self-hoster.
            var editing by remember { mutableStateOf(false) }
            var draft by remember(host) { mutableStateOf(host) }
            val changeFocus = remember { FocusRequester() }
            LaunchedEffect(Unit) { runCatching { changeFocus.requestFocus() } }

            if (!editing) {
                Row(verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                    Column {
                        Text("Server", fontSize = 12.sp, color = Color(0xFF7C6F93))
                        Text(host, fontSize = 16.sp, color = MUTED)
                    }
                    OutlinedButton(onClick = { editing = true },
                                   modifier = Modifier.focusRequester(changeFocus)) {
                        Text("Change")
                    }
                }
            } else {
                OutlinedTextField(
                    value = draft,
                    onValueChange = { draft = it },
                    label = { Text("Server") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(0.85f),
                )
                Spacer(Modifier.height(10.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Button(onClick = { editing = false; onHostChange(draft.trim()) }) {
                        Text("Save")
                    }
                    OutlinedButton(onClick = { editing = false; draft = host }) { Text("Cancel") }
                }
                Text(
                    "Saving restarts the sign-in code.",
                    fontSize = 12.sp, color = Color(0xFF7C6F93),
                    modifier = Modifier.padding(top = 6.dp),
                )
            }
        }

        // ── right: the code ──
        Box(
            Modifier.size(300.dp).clip(RoundedCornerShape(16.dp)).background(Color.White),
            contentAlignment = Alignment.Center,
        ) {
            when {
                state.error != null -> Column(
                    Modifier.padding(20.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Text(state.error, color = Color(0xFF7C1D2E), fontSize = 15.sp,
                         textAlign = TextAlign.Center)
                    Spacer(Modifier.height(14.dp))
                    Button(onClick = onRetry) { Text("Try again") }
                }

                state.userCode == null -> CircularProgressIndicator(color = ACCENT)

                else -> {
                    val link = "${webOrigin(host)}/link?code=${state.userCode}"
                    val bmp by produceState<Bitmap?>(null, link) {
                        value = runCatching { qrBitmap(link) }.getOrNull()
                    }
                    bmp?.let {
                        Image(it.asImageBitmap(), contentDescription = "Sign-in QR code",
                              modifier = Modifier.fillMaxSize().padding(12.dp))
                    }
                }
            }
        }
    }
}

/**
 * The QR must point at the web app, but the box is configured with the API host.
 * They're the same site with an `api.` prefix, so derive one from the other
 * rather than making the user fill in two fields that must agree.
 */
fun webOrigin(apiHost: String): String =
    "https://" + apiHost.trim().removePrefix("api.")
