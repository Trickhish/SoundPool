package dev.dury.soundpool.net

import android.net.Uri
import androidx.media3.common.C
import androidx.media3.common.util.UnstableApi
import androidx.media3.datasource.BaseDataSource
import androidx.media3.datasource.DataSpec
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import java.io.EOFException
import java.io.IOException
import java.io.InputStream
import javax.crypto.Cipher
import javax.crypto.spec.IvParameterSpec
import javax.crypto.spec.SecretKeySpec
import kotlin.math.min

/**
 * Streams a track straight from Deezer's CDN, undoing its encryption on the fly.
 *
 * The layout is simple but unusual: the file is a run of 2048-byte blocks and
 * only every *third* one is encrypted, with Blowfish-CBC. Crucially each block
 * is encrypted independently, re-using the same fixed IV rather than chaining
 * from the previous block. That makes any 2048-aligned offset a valid entry
 * point, so we can serve a seek with a ranged request and start decrypting
 * there — no need to have seen the bytes before it.
 *
 * That independence is what lets this be a streaming source at all. The Python
 * unit downloads the whole MP3 before playing (measured 4-20s); here playback
 * can start on the first block and seeking stays cheap.
 */
@UnstableApi
class DeezerDataSource(
    private val http: OkHttpClient,
    /** 16-char ASCII Blowfish key the server derived from the song id. */
    private val key: String,
) : BaseDataSource(true) {

    companion object {
        const val BLOCK = 2048
        private val IV = byteArrayOf(0, 1, 2, 3, 4, 5, 6, 7)

        /** Factory ExoPlayer can hand to a MediaSource. */
        fun factory(http: OkHttpClient, key: String) =
            androidx.media3.datasource.DataSource.Factory { DeezerDataSource(http, key) }
    }

    private var uri: Uri? = null
    private var response: Response? = null
    private var stream: InputStream? = null

    /** Index of the block the read cursor sits in — decides encrypted-or-not. */
    private var blockIndex = 0L
    private var bytesRemaining = C.LENGTH_UNSET.toLong()

    /** One decrypted (or passthrough) block, drained before the next is read. */
    private val block = ByteArray(BLOCK)
    private var blockLen = 0
    private var blockPos = 0

    override fun getUri(): Uri? = uri

    override fun open(dataSpec: DataSpec): Long {
        uri = dataSpec.uri
        transferInitializing(dataSpec)

        // Round the requested position down to a block boundary: decryption is
        // only defined on whole blocks. The leftover is skipped after opening,
        // so the caller still lands on the exact byte it asked for.
        val start = dataSpec.position
        val alignedStart = start - (start % BLOCK)
        val skipIntoBlock = (start - alignedStart).toInt()
        blockIndex = alignedStart / BLOCK

        val req = Request.Builder()
            .url(dataSpec.uri.toString())
            .apply { if (alignedStart > 0) header("Range", "bytes=$alignedStart-") }
            .build()

        val resp = http.newCall(req).execute()
        if (!resp.isSuccessful) {
            resp.close()
            throw IOException("CDN returned HTTP ${resp.code}")
        }
        response = resp
        stream = resp.body?.byteStream() ?: throw IOException("empty body from CDN")

        val bodyLen = resp.body?.contentLength() ?: -1L
        bytesRemaining = when {
            dataSpec.length != C.LENGTH_UNSET.toLong() -> dataSpec.length
            bodyLen >= 0 -> bodyLen - skipIntoBlock
            else -> C.LENGTH_UNSET.toLong()
        }

        // Drop the partial head of the first block so the cursor matches the
        // position ExoPlayer requested.
        if (skipIntoBlock > 0) {
            fillBlock()
            blockPos = min(skipIntoBlock, blockLen)
        }

        transferStarted(dataSpec)
        return bytesRemaining
    }

    /** Pull the next whole block and decrypt it if it's one of the encrypted ones. */
    private fun fillBlock(): Boolean {
        val input = stream ?: return false
        var read = 0
        while (read < BLOCK) {
            val n = try {
                input.read(block, read, BLOCK - read)
            } catch (e: EOFException) {
                -1
            }
            if (n == -1) break
            read += n
        }
        if (read == 0) {
            blockLen = 0
            blockPos = 0
            return false
        }

        // A short block only ever happens at true EOF, and Deezer leaves that
        // tail in the clear — decrypting it would corrupt the final frames.
        if (blockIndex % 3 == 0L && read == BLOCK) {
            // Decrypt into a scratch buffer rather than in place: writing the
            // output over the input array is provider-dependent behaviour.
            val cipher = Cipher.getInstance("Blowfish/CBC/NoPadding")
            cipher.init(
                Cipher.DECRYPT_MODE,
                SecretKeySpec(key.toByteArray(Charsets.ISO_8859_1), "Blowfish"),
                IvParameterSpec(IV),
            )
            val plain = cipher.doFinal(block, 0, BLOCK)
            System.arraycopy(plain, 0, block, 0, BLOCK)
        }

        blockIndex++
        blockLen = read
        blockPos = 0
        return true
    }

    override fun read(buffer: ByteArray, offset: Int, length: Int): Int {
        if (length == 0) return 0
        if (bytesRemaining == 0L) return C.RESULT_END_OF_INPUT

        if (blockPos >= blockLen && !fillBlock()) return C.RESULT_END_OF_INPUT

        var n = min(length, blockLen - blockPos)
        if (bytesRemaining != C.LENGTH_UNSET.toLong()) n = min(n, bytesRemaining.toInt())
        System.arraycopy(block, blockPos, buffer, offset, n)
        blockPos += n
        if (bytesRemaining != C.LENGTH_UNSET.toLong()) bytesRemaining -= n
        bytesTransferred(n)
        return n
    }

    override fun close() {
        blockLen = 0
        blockPos = 0
        try {
            stream?.close()
        } catch (_: IOException) {
        } finally {
            stream = null
            response?.close()
            response = null
            if (uri != null) {
                uri = null
                transferEnded()
            }
        }
    }
}
