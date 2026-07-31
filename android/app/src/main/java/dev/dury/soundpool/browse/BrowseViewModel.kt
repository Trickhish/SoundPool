package dev.dury.soundpool.browse

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import dev.dury.soundpool.Config
import dev.dury.soundpool.net.DeviceAuth
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient

class BrowseViewModel(app: Application) : AndroidViewModel(app) {

    private val cfg = Config(app)
    private val http = OkHttpClient()

    private val _host = MutableStateFlow(cfg.host)
    val host = _host.asStateFlow()

    /** Rebuilt per attempt: the host is editable on the sign-in screen. */
    private fun auth() = DeviceAuth(cfg.host, http)

    fun setHost(h: String) {
        cfg.host = h
        _host.value = h
    }

    private val _signIn = MutableStateFlow(SignInState())
    val signIn = _signIn.asStateFlow()

    private val _signedIn = MutableStateFlow(cfg.signedIn)
    val signedIn = _signedIn.asStateFlow()

    private val _account = MutableStateFlow(cfg.accountName)
    val account = _account.asStateFlow()

    private var pollJob: Job? = null

    /** Ask for a code and poll until the user approves it elsewhere. */
    fun beginSignIn() {
        pollJob?.cancel()
        _signIn.value = SignInState()
        pollJob = viewModelScope.launch {
            val start = try {
                withContext(Dispatchers.IO) { auth().start() }
            } catch (e: Exception) {
                _signIn.value = SignInState(error = e.message ?: "Could not reach the server")
                return@launch
            }
            _signIn.value = SignInState(userCode = start.userCode)

            // Poll for the code's whole lifetime, then stop rather than spin
            // forever against a dead code.
            val deadline = System.currentTimeMillis() + start.expiresIn * 1000L
            while (System.currentTimeMillis() < deadline) {
                delay(3000)
                val r = try {
                    withContext(Dispatchers.IO) { auth().poll(start.deviceCode) }
                } catch (e: Exception) {
                    continue        // transient network trouble: keep waiting
                }
                when (r) {
                    is DeviceAuth.Poll.Pending -> {}
                    is DeviceAuth.Poll.Expired -> {
                        _signIn.value = SignInState(error = r.reason)
                        return@launch
                    }
                    is DeviceAuth.Poll.Approved -> {
                        cfg.authToken = r.token
                        cfg.accountName = r.username.ifEmpty { r.email }
                        // The unit registers against an owner's email. Now that
                        // we know who signed in, take it from here instead of
                        // making someone type an address with a D-pad.
                        if (r.email.isNotEmpty()) cfg.ownerMail = r.email
                        _account.value = cfg.accountName
                        _signedIn.value = true
                        return@launch
                    }
                }
            }
            _signIn.value = SignInState(error = "That code expired — try again.")
        }
    }

    fun cancelSignIn() {
        pollJob?.cancel()
        pollJob = null
    }

    fun signOut() {
        cancelSignIn()
        cfg.authToken = ""
        cfg.accountName = ""
        cfg.roomId = 0
        _account.value = ""
        _signedIn.value = false
    }

    override fun onCleared() {
        pollJob?.cancel()
        super.onCleared()
    }
}
