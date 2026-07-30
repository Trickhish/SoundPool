"""Audio playback backend for the player unit.

Wraps the handful of operations the unit needs (load/play/pause/seek/volume/
position) behind one small object, so the rest of the code doesn't care what's
underneath.

Prefers **mpv** (libmpv) and falls back to pygame.mixer when it isn't available,
which keeps older units working unchanged. mpv is preferred because it fixes
real limitations we hit with pygame:

  * absolute position — pygame's `get_pos()` is relative to the last `play()`
    and ignores the seek offset (seek to 90s then read: pygame says ~1s, mpv
    says 90.1s), so room sync had to track its own offset;
  * per-stream output selection — mpv takes `audio-device=pulse/<sink>`, while
    pygame can only follow the default sink, which forced move-sink-input
    juggling;
  * gapless playback, reliable duration, and no global-singleton mixer state
    (a failed pygame load used to leave the unit permanently stuck).

Volume is 0..1 everywhere in this API, matching the old pygame calls.
"""
import os
import threading

_BACKEND = None          # "mpv" | "pygame"


def _mpv_volume(level):
    """Convert a 0..1 linear amplitude into mpv's volume property.

    mpv's `volume` is CUBIC — measured on hardware: volume=50 yields 0.125 gain
    (0.5³) and volume=25 yields 0.0156 (0.25³). pygame's set_volume() is linear,
    so passing level*100 straight through made everything ~16 dB quieter at a
    room volume of 0.4 (0.064 gain instead of 0.40). Take the cube root so the
    volume control keeps the meaning it has everywhere else in SoundPool.
    """
    level = max(0.0, min(1.0, float(level)))
    return 100.0 * (level ** (1.0 / 3.0))


class _MpvBackend:
    name = "mpv"

    def __init__(self):
        import mpv
        self._mpv_mod = mpv
        self._m = None
        self._path = None
        self._sink = None
        self._volume = 1.0
        self._lock = threading.Lock()

    # ── lifecycle ──
    def init(self, sink=None):
        with self._lock:
            if self._m is not None:
                return
            kwargs = dict(video=False, gapless_audio=True,
                          # keep the player alive between tracks instead of
                          # exiting when the file ends
                          idle=True, terminal=False)
            if sink:
                kwargs["audio_device"] = f"pulse/{sink}"
                self._sink = sink
            self._m = self._mpv_mod.MPV(**kwargs)
            self._m.volume = _mpv_volume(self._volume)

    def get_init(self):
        return self._m is not None

    def shutdown(self):
        with self._lock:
            if self._m is not None:
                try:
                    self._m.terminate()
                except Exception:
                    pass
                self._m = None

    def set_sink(self, sink):
        """Point playback at a specific PulseAudio/PipeWire sink."""
        if not sink or sink == self._sink:
            return
        self._sink = sink
        if self._m is not None:
            try:
                self._m.audio_device = f"pulse/{sink}"
            except Exception as e:
                print(f"[audio] could not set mpv sink: {e}")

    # ── transport ──
    def load(self, path):
        self._path = path

    def play(self, start=0.0, path=None):
        self.init()
        if path:
            self._path = path
        if not self._path:
            raise RuntimeError("no track loaded")
        # loadfile with start= avoids a separate blocking seek, so this returns
        # immediately and playback begins at the right position.
        self._m.loadfile(self._path, "replace", start=str(max(0.0, float(start))))
        self._m.pause = False

    def pause(self):
        if self._m is not None:
            self._m.pause = True

    def unpause(self):
        if self._m is not None:
            self._m.pause = False

    def stop(self):
        if self._m is not None:
            try:
                self._m.command("stop")
            except Exception:
                pass

    def seek(self, seconds):
        if self._m is not None:
            try:
                self._m.seek(max(0.0, float(seconds)), reference="absolute")
            except Exception as e:
                print(f"[audio] seek failed: {e}")

    # ── state ──
    def set_volume(self, level):
        self._volume = max(0.0, min(1.0, float(level)))
        if self._m is not None:
            try:
                self._m.volume = _mpv_volume(self._volume)
            except Exception:
                pass

    def position_ms(self):
        """Absolute position in the current track (ms)."""
        if self._m is None:
            return 0
        try:
            p = self._m.time_pos
            return int(p * 1000) if p else 0
        except Exception:
            return 0

    def duration_ms(self):
        if self._m is None:
            return 0
        try:
            d = self._m.duration
            return int(d * 1000) if d else 0
        except Exception:
            return 0

    def get_busy(self):
        """True while a track is actively playing (not idle/ended/paused-at-end)."""
        if self._m is None:
            return False
        try:
            if self._m.idle_active:
                return False
            if self._m.pause:
                return True      # loaded and paused still counts as "has a track"
            return self._m.time_pos is not None and not self._m.eof_reached
        except Exception:
            return False


class _PygameBackend:
    """Fallback for units without libmpv (e.g. the Python 3.8 box)."""
    name = "pygame"

    def __init__(self):
        import pygame.mixer as mix
        self._mix = mix
        self._offset_ms = 0      # pygame's get_pos() ignores the seek offset
        self._volume = 1.0
        self._path = None

    def init(self, sink=None):
        if not self._mix.get_init():
            self._mix.init()

    def get_init(self):
        return bool(self._mix.get_init())

    def shutdown(self):
        try:
            self._mix.music.stop()
        except Exception:
            pass

    def set_sink(self, sink):
        return  # pygame follows the default sink; routing is done with pactl

    def load(self, path):
        self._path = path
        self._mix.music.load(path)

    def play(self, start=0.0, path=None):
        self.init()
        if path and path != self._path:
            self.load(path)
        self._mix.music.play(start=max(0.0, float(start)))
        self._mix.music.set_volume(self._volume)
        self._offset_ms = int(max(0.0, float(start)) * 1000)

    def pause(self):
        self._mix.music.pause()

    def unpause(self):
        self._mix.music.unpause()

    def stop(self):
        self._mix.music.stop()

    def seek(self, seconds):
        self.play(start=seconds)

    def set_volume(self, level):
        self._volume = max(0.0, min(1.0, float(level)))
        try:
            self._mix.music.set_volume(self._volume)
        except Exception:
            pass

    def position_ms(self):
        p = self._mix.music.get_pos()   # ms since the last play(); -1 when idle
        if p is None or p < 0:
            p = 0
        return self._offset_ms + p

    def duration_ms(self):
        return 0    # not available from pygame; callers fall back to metadata

    def get_busy(self):
        return bool(self._mix.music.get_busy())


def make_backend(prefer=None):
    """Build the best available backend. `prefer` forces one ("mpv"/"pygame")."""
    global _BACKEND
    order = [prefer] if prefer else ["mpv", "pygame"]
    errors = []
    for name in order:
        try:
            be = _MpvBackend() if name == "mpv" else _PygameBackend()
            _BACKEND = be.name
            print(f"[audio] playback backend: {be.name}")
            return be
        except Exception as e:
            errors.append(f"{name}: {e}")
    raise RuntimeError("no usable audio backend — " + "; ".join(errors))
