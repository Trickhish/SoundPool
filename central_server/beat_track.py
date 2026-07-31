"""Beat detection, so the big screen can move in time with the music.

The display can't analyse anything itself — audio plays on the player unit (and
usually out over Bluetooth), not in the browser. So the tempo and beat grid are
worked out here, once per track, and the display animates against them using the
playback position it already tracks.

Deliberately numpy-only: decode with ffmpeg, spectral flux for onsets,
autocorrelation for tempo. About 2.5s for a 4-minute track on this box, no GPU
and no extra dependencies — unlike the lyric-alignment idea, which needed source
separation we can't run here.

`strength` says how periodic the track actually is. A driving rock song scores
~0.95, a rubato ballad ~0.59, and callers are expected to skip the effect below
MIN_STRENGTH rather than flash confidently at the wrong moments.
"""
import subprocess
import threading

import numpy as np

SR = 22050
HOP = 512
WIN = 1024
FPS = SR / HOP

MIN_STRENGTH = 0.70     # below this the track has no beat worth following
_cache = {}             # song_id -> result
_lock = threading.Lock()


def _decode(path):
    out = subprocess.run(
        ["ffmpeg", "-v", "quiet", "-i", path, "-f", "s16le",
         "-ac", "1", "-ar", str(SR), "-"],
        capture_output=True, timeout=180)
    if out.returncode != 0 or not out.stdout:
        raise RuntimeError("ffmpeg could not decode the audio")
    return np.frombuffer(out.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def _onset_envelope(pcm):
    """Spectral flux — how much the spectrum brightens frame to frame. Peaks
    line up with drum hits and note attacks."""
    n = 1 + (len(pcm) - WIN) // HOP
    if n < 8:
        raise RuntimeError("audio too short")
    w = np.hanning(WIN).astype(np.float32)
    frames = np.lib.stride_tricks.sliding_window_view(pcm, WIN)[::HOP][:n] * w
    mag = np.log1p(np.abs(np.fft.rfft(frames, axis=1)) * 10)
    flux = np.maximum(0.0, np.diff(mag, axis=0)).sum(axis=1)
    env = np.concatenate([[0], flux]).astype(np.float32)
    env -= env.mean()
    env /= (env.std() or 1)
    return env


def _tempo(env):
    """Returns (bpm, strength). Scores each candidate together with its octaves:
    plain autocorrelation happily reports half or double tempo (it called a
    123 BPM track 61 BPM), because those peaks are just as periodic."""
    ac = np.correlate(env, env, mode="full")[len(env) - 1:]
    ac = ac / (ac[0] or 1)

    def at(bpm):
        lag = int(round(60.0 / bpm * FPS))
        return ac[lag] if 1 <= lag < len(ac) else 0.0

    bpms = np.arange(70, 190, 0.1)
    score = np.array([at(b) + 0.6 * at(b / 2) + 0.4 * at(b * 2) for b in bpms])
    # Mild pull toward ordinary tempos, but weak enough that a genuinely fast
    # track still wins — 'Run For Cover' resolves to 164, not 82 or 120.
    prior = np.exp(-0.5 * ((np.log2(bpms / 120.0)) / 0.9) ** 2)
    total = score * prior
    i = int(np.argmax(total))
    return float(bpms[i]), float(score[i])


def _beats(env, bpm):
    """Align a pulse train to the onsets to find the downbeat phase."""
    period = 60.0 / bpm * FPS
    best_off, best = 0.0, -1e9
    for off in np.arange(0, period, max(1.0, period / 48)):
        idx = np.round(np.arange(off, len(env), period)).astype(int)
        idx = idx[idx < len(env)]
        s = float(env[idx].sum())
        if s > best:
            best, best_off = s, off
    return (np.arange(best_off, len(env), period) / FPS)


def analyse(path, song_id=None):
    """{'bpm', 'strength', 'beats' (ms), 'usable'} — cached per song."""
    if song_id:
        with _lock:
            if song_id in _cache:
                return _cache[song_id]
    try:
        env = _onset_envelope(_decode(path))
        bpm, strength = _tempo(env)
        beats = _beats(env, bpm)
        res = {
            "bpm": round(bpm, 1),
            "strength": round(strength, 3),
            "usable": strength >= MIN_STRENGTH,
            "beats": [int(t * 1000) for t in beats],
        }
    except Exception as e:
        print(f"[beat] analysis failed: {e}")
        res = {"bpm": 0, "strength": 0.0, "usable": False, "beats": []}
    if song_id:
        with _lock:
            _cache[song_id] = res
            if len(_cache) > 300:
                _cache.pop(next(iter(_cache)))
    return res
