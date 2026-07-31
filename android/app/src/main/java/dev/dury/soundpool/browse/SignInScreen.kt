package dev.dury.soundpool.browse

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

private val MUTED = Color(0xFFB9A9D8)

/**
 * Shows the pairing code and waits. Purely a display — every character the user
 * types happens on their phone or laptop, not here.
 */
@Composable
fun SignInScreen(state: SignInState, onRetry: () -> Unit, onBack: () -> Unit) {
    Column(
        Modifier.fillMaxSize().padding(horizontal = 48.dp, vertical = 32.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text("Sign in", fontSize = 34.sp, fontWeight = FontWeight.Bold, color = Color.White)
        Spacer(Modifier.height(8.dp))
        Text(
            "On your phone or computer, open  soundpool.dury.dev/link  and enter this code:",
            fontSize = 17.sp, color = MUTED, textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(24.dp))

        when {
            state.error != null -> {
                Text(state.error, fontSize = 18.sp, color = Color(0xFFF87171),
                     textAlign = TextAlign.Center)
                Spacer(Modifier.height(20.dp))
                Button(onClick = onRetry) { Text("Try again") }
            }

            state.userCode == null -> CircularProgressIndicator()

            else -> {
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    state.userCode.forEach { ch ->
                        Box(
                            Modifier.size(58.dp, 74.dp)
                                .clip(RoundedCornerShape(10.dp))
                                .background(Color(0xFF1B1229)),
                            contentAlignment = Alignment.Center,
                        ) {
                            Text("$ch", fontSize = 34.sp, fontWeight = FontWeight.Bold,
                                 color = Color.White)
                        }
                    }
                }
                Spacer(Modifier.height(22.dp))
                Text("Waiting for approval…", fontSize = 15.sp, color = MUTED)
            }
        }

        Spacer(Modifier.height(28.dp))
        OutlinedButton(onClick = onBack) { Text("Back") }
    }
}

data class SignInState(
    val userCode: String? = null,
    val error: String? = null,
)
