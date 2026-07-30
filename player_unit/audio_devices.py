"""Audio-interface management for the player unit, via pactl (PipeWire/Pulse)
and bluetoothctl. Lets a unit play to one or several sinks at once (combine
sink) and manage Bluetooth speakers."""
import json
import os
import re
import subprocess
import threading
import time

COMBINE_SINK = "soundpool_out"   # our managed combine sink (multi-output)

# Bluetooth scan results live here (mac -> {name, paired, connected, last_seen})
_bt_seen = {}
_bt_scanning = False
_bt_last = None                  # outcome of the last BT action (surfaced in the UI)
_bt_busy = None                  # {mac, phase} while an action runs, so the UI can
                                 # show real progress instead of a silent spinner
_selected = []                   # last selected sink names (persisted in-memory)


# Force English output so we can parse pactl/bluetoothctl regardless of the
# system locale (e.g. a French box prints "Nom :"/"Volume :" and our parsing
# expects "Name:"/"Volume:").
_C_ENV = {**os.environ, "LC_ALL": "C", "LANG": "C"}


def _run(args, timeout=10):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=_C_ENV)
        return r.stdout
    except Exception as e:
        print(f"[audio] {' '.join(args)} failed: {e}")
        return ""


# ── Sinks ──
def _sink_info():
    """name -> {description, volume(0..100), mute} from a single `pactl list sinks`.
    Reads volume here (not via `get-sink-volume`, which doesn't exist on older
    pactl) and takes the first Volume line so we skip the later "Base Volume"."""
    out = _run(["pactl", "list", "sinks"])
    info, cur = {}, None
    for raw in out.splitlines():
        line = raw.strip()
        if line.startswith("Name:"):
            cur = line.split("Name:", 1)[1].strip()
            info[cur] = {"description": cur, "volume": 100, "mute": False, "_vol": False}
        elif not cur:
            continue
        elif line.startswith("Description:"):
            info[cur]["description"] = line.split("Description:", 1)[1].strip()
        elif line.startswith("Volume:") and not info[cur]["_vol"]:
            m = re.search(r"(\d+)%", line)
            if m:
                info[cur]["volume"] = int(m.group(1))
            info[cur]["_vol"] = True
        elif line.startswith("Mute:"):
            info[cur]["mute"] = line.split("Mute:", 1)[1].strip().lower().startswith("y")
    return info


def list_sinks():
    sinks = []
    for name, d in _sink_info().items():
        if name == COMBINE_SINK or ".monitor" in name or name == "auto_null":
            continue
        sinks.append({"name": name, "description": d["description"], "volume": d["volume"]})
    return sinks


def own_sink_input():
    """Find this process's playback stream id in `pactl list sink-inputs`."""
    pid = str(os.getpid())
    out = _run(["pactl", "list", "sink-inputs"])
    cur = None
    for line in out.splitlines():
        s = line.strip()
        m = re.match(r"Sink Input #(\d+)", s)
        if m:
            cur = m.group(1)
        elif "application.process.id" in s and f'"{pid}"' in s and cur:
            return cur
    # Fallback: if there's exactly one stream, assume it's ours
    ids = re.findall(r"Sink Input #(\d+)", out)
    return ids[0] if len(ids) == 1 else None


def _unload_combine():
    out = _run(["pactl", "list", "short", "modules"])
    for line in out.splitlines():
        if "module-combine-sink" in line and COMBINE_SINK in line:
            mod = line.split("\t")[0]
            _run(["pactl", "unload-module", mod])


_SELECTED_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".selected_outputs")


def _save_selected():
    try:
        with open(_SELECTED_FILE, "w") as f:
            json.dump(_selected, f)
    except Exception as e:
        print(f"[audio] could not save output selection: {e}")


def load_selected():
    """Restore the chosen output(s) after a restart and re-apply the routing —
    otherwise the unit silently falls back to the system default sink."""
    global _selected
    try:
        with open(_SELECTED_FILE) as f:
            _selected = [n for n in (json.load(f) or []) if n]
    except FileNotFoundError:
        return
    except Exception as e:
        print(f"[audio] could not load output selection: {e}")
        return
    if _selected:
        print(f"[audio] restoring outputs: {_selected}")
        set_outputs(_selected)


def _existing_sinks():
    names = set()
    for line in _run(["pactl", "list", "short", "sinks"]).splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            names.add(parts[1])
    return names


def _target_sink():
    """The sink our playback should land on for the current selection.

    Filters out sinks that aren't currently present: a saved choice can point at
    a Bluetooth speaker that's switched off, and routing to (or defaulting to) a
    non-existent sink just loses the audio. The selection is kept either way, so
    it takes effect again as soon as the speaker comes back.
    """
    if not _selected:
        return None
    if len(_selected) >= 2:
        return COMBINE_SINK if COMBINE_SINK in _existing_sinks() else None
    return _selected[0] if _selected[0] in _existing_sinks() else None


def _apply_routing():
    """Point our playback stream at the selected sink.

    Called both when the selection changes and whenever a new stream appears:
    `set_outputs` alone only moved a stream that already existed, so choosing an
    output while nothing was playing did nothing, and the next track opened on
    the default sink instead.
    """
    target = _target_sink()
    if not target:
        return
    si = own_sink_input()
    if si:
        _run(["pactl", "move-sink-input", si, target])


def set_outputs(names):
    """Route the unit's playback to the given sink name(s)."""
    global _selected
    names = [n for n in (names or []) if n]
    _selected = names
    _save_selected()
    _unload_combine()

    if len(names) >= 2:
        _run(["pactl", "load-module", "module-combine-sink",
              f"sink_name={COMBINE_SINK}", "slaves=" + ",".join(names)])
        target = COMBINE_SINK
        time.sleep(0.3)  # let the combine sink settle
    elif len(names) == 1:
        target = names[0]
    else:
        target = None  # leave on default

    if target and target in _existing_sinks():
        # Also make it the default so a stream opened later (pygame reopens the
        # device between tracks) starts on the right sink instead of racing the
        # move below. Skipped when the sink isn't there (speaker switched off).
        _run(["pactl", "set-default-sink", target])
    _apply_routing()


def set_sink_volume(name, level):
    pct = max(0, min(150, int(round(float(level) * 100))))
    _run(["pactl", "set-sink-volume", name, f"{pct}%"])


_TEST_WAV = None


def _make_test_wav(path, seg=0.8, gap=0.15, freq=520, rate=44100, vol=0.4):
    """Stereo left/right test: a tone on the left channel, a gap, then the right,
    so users can verify channel wiring and that each speaker works."""
    import wave, math, struct
    frames = bytearray()

    def tone(nsamples, left, right):
        for i in range(nsamples):
            env = min(1.0, i / (rate * 0.03), (nsamples - i) / (rate * 0.03))  # de-click fade
            s = int(vol * env * 32767 * math.sin(2 * math.pi * freq * i / rate))
            frames.extend(struct.pack("<hh", s if left else 0, s if right else 0))

    seg_n, gap_n = int(seg * rate), int(gap * rate)
    tone(seg_n, True, False)                    # LEFT
    frames.extend(b"\x00\x00\x00\x00" * gap_n)  # silence (2ch * 2 bytes)
    tone(seg_n, False, True)                    # RIGHT

    with wave.open(path, "w") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))


def test_output(sink=None):
    """Play a short test tone on `sink` (or the default) via paplay, off-thread
    so it doesn't block the connection."""
    global _TEST_WAV
    if not _TEST_WAV or not os.path.exists(_TEST_WAV):
        import tempfile
        fd, _TEST_WAV = tempfile.mkstemp(suffix="_sptest.wav")
        os.close(fd)
        try:
            _make_test_wav(_TEST_WAV)
        except Exception as e:
            print(f"[audio] test tone generation failed: {e}")
            return
    args = ["paplay"]
    if sink:
        args += ["--device", sink]
    args.append(_TEST_WAV)
    threading.Thread(target=lambda: _run(args, timeout=15), daemon=True).start()


def _current_outputs():
    """Best-effort: the sinks we're currently feeding."""
    if len(_selected) >= 2:
        return list(_selected)
    si = own_sink_input()
    if not si:
        return list(_selected)
    out = _run(["pactl", "list", "short", "sink-inputs"])
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0] == si:
            sink_idx = parts[1]
            short = _run(["pactl", "list", "short", "sinks"])
            for sl in short.splitlines():
                sp = sl.split("\t")
                if len(sp) >= 2 and sp[0] == sink_idx:
                    return [sp[1]] if sp[1] != COMBINE_SINK else list(_selected)
    return list(_selected)


# ── Bluetooth ──
_ANSI = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")

# Human-readable meanings for the bluez errors we actually hit, so the UI can
# say what to do instead of showing a raw D-Bus string (or, as before, silently
# claiming success).
_BT_ERRORS = [
    ("br-connection-profile-unavailable",
     "No audio profile available on the unit — its Bluetooth audio stack isn't ready."),
    ("br-connection-page-timeout",
     "The device didn't respond. Make sure it's powered on and in pairing mode."),
    ("page-timeout",
     "The device didn't respond. Make sure it's powered on and in pairing mode."),
    # The adapter can hold only one A2DP audio stream at a time: a second
    # speaker links up but never gets an audio profile.
    ("br-connection-busy",
     "Another Bluetooth speaker is already playing. Disconnect it first — this "
     "unit can only use one Bluetooth speaker at a time."),
    ("Device or resource busy",
     "Another Bluetooth speaker is already playing. Disconnect it first — this "
     "unit can only use one Bluetooth speaker at a time."),
    ("br-connection-canceled", "The connection was canceled."),
    ("AuthenticationFailed", "The device refused pairing."),
    ("AuthenticationRejected", "The device rejected pairing."),
    ("AuthenticationCanceled", "Pairing was canceled."),
    ("ConnectionAttemptFailed", "Connection attempt failed — try again."),
    ("NotReady", "The Bluetooth adapter is off."),
    ("InProgress", "Another Bluetooth operation is still running — try again."),
    ("NotAvailable", "The device is out of range or switched off."),
    ("not available", "The device is out of range, off, or not in pairing mode."),
    ("DoesNotExist", "The unit no longer knows this device — scan again."),
]


def _friendly_bt_error(out):
    for needle, msg in _BT_ERRORS:
        if needle.lower() in out.lower():
            return msg
    for line in out.splitlines():
        line = line.strip()
        if line.lower().startswith("failed to"):
            return line
    return "Bluetooth command failed."


def _btctl(*args, timeout=25):
    """Run ONE bluetoothctl command non-interactively.

    Must be one-shot: piping several commands into an interactive session feeds
    them before bluetoothctl has finished connecting to bluetoothd, so the agent
    fails to register ("Failed to register agent object") and `pair` is issued
    with no agent — then stdin closes and the process exits before the async
    result arrives. One-shot mode waits for the operation to actually finish.
    """
    try:
        r = subprocess.run(["bluetoothctl", *args], capture_output=True,
                           text=True, timeout=timeout, env=_C_ENV)
        return _ANSI.sub("", r.stdout or "") + _ANSI.sub("", r.stderr or "")
    except subprocess.TimeoutExpired:
        return "Failed to complete: the operation timed out."
    except Exception as e:
        print(f"[bt] {args} failed: {e}")
        return f"Failed to run bluetoothctl: {e}"


def _parse_devices(out):
    devs = {}
    for line in _ANSI.sub("", out).splitlines():
        m = re.match(r"Device (\S+)\s+(.*)", line.strip())
        if m:
            devs[m.group(1)] = m.group(2).strip()
    return devs


def _bt_refresh_devices():
    # Three bulk calls instead of one `info` per device (which was slow with
    # many cached devices). `bluetoothctl devices` already gives the real name
    # for known devices (MAC-form only when unresolved).
    all_dev = _parse_devices(_run(["bluetoothctl", "devices"]))
    paired = set(_parse_devices(_run(["bluetoothctl", "devices", "Paired"])))
    connected = set(_parse_devices(_run(["bluetoothctl", "devices", "Connected"])))
    for mac, name in all_dev.items():
        d = _bt_seen.setdefault(mac, {})
        d["name"] = name
        d["paired"] = mac in paired
        d["connected"] = mac in connected
    for mac in paired | connected:  # connected device may not be in plain list
        d = _bt_seen.setdefault(mac, {"name": mac})
        d["paired"] = mac in paired
        d["connected"] = mac in connected


def bt_scan(seconds=8):
    global _bt_scanning
    if _bt_scanning:
        return
    _bt_scanning = True

    def worker():
        global _bt_scanning
        proc = None
        try:
            _run(["bluetoothctl", "power", "on"])
            # Scan in the background and surface results progressively so devices
            # appear as they're found instead of all at the end.
            proc = subprocess.Popen(["bluetoothctl", "--timeout", str(seconds), "scan", "on"],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            end = time.time() + seconds
            while time.time() < end:
                time.sleep(2)
                try:
                    _bt_refresh_devices()
                    _notify()
                except Exception as e:
                    print(f"[bt] refresh error: {e}")
            try:
                proc.wait(timeout=4)
            except Exception:
                pass
            _bt_refresh_devices()
        except Exception as e:
            print(f"[bt] scan error: {e}")
        finally:
            # Always stop the scan and clear the flag, so it never gets stuck.
            try:
                if proc and proc.poll() is None:
                    proc.kill()
            except Exception:
                pass
            _run(["bluetoothctl", "scan", "off"])
            _bt_scanning = False
            _notify()
    threading.Thread(target=worker, daemon=True).start()


def _bt_phase(mac, phase):
    """Publish what we're doing right now. Pair/connect can legitimately take
    tens of seconds (discovery + pairing + a connect retry), so push each step
    to the UI rather than leaving it on a silent spinner."""
    global _bt_busy
    _bt_busy = {"mac": mac, "phase": phase} if phase else None
    _notify()


def _bt_set_last(action, mac, ok, error=""):
    """Record the outcome of the last BT action so the UI can report it."""
    global _bt_last, _bt_busy
    _bt_last = {"action": action, "mac": mac, "ok": bool(ok),
                "error": "" if ok else (error or "Bluetooth command failed."),
                "ts": time.time()}
    _bt_busy = None
    print(f"[bt] {action} {mac}: {'ok' if ok else 'FAILED — ' + _bt_last['error']}")


def _bt_stop_scan():
    """Discovery in progress makes pair/connect flaky (and floods the output),
    so always settle the adapter before an operation."""
    global _bt_scanning
    if _bt_scanning:
        _bt_scanning = False
    _btctl("scan", "off", timeout=6)
    time.sleep(0.5)


def _bt_is(mac, kind):
    return mac in _parse_devices(_btctl("devices", kind, timeout=8))


def _bt_known(mac):
    return mac in _parse_devices(_btctl("devices", timeout=8))


def _bt_rediscover(mac, seconds=12):
    """Bring a device back into bluez's view.

    `remove` (Forget) makes bluez drop the device completely, and a later `pair`
    then fails with "Device not available" until it's discovered again. Rather
    than making the user press Scan first, rediscover it inline.
    """
    if _bt_known(mac):
        return True
    _bt_phase(mac, "Looking for the device…")
    proc = None
    try:
        proc = subprocess.Popen(["bluetoothctl", "--timeout", str(seconds), "scan", "on"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                env=_C_ENV)
        end = time.time() + seconds
        while time.time() < end:
            time.sleep(1.5)
            if _bt_known(mac):
                return True
    except Exception as e:
        print(f"[bt] rediscover failed: {e}")
    finally:
        try:
            if proc and proc.poll() is None:
                proc.kill()
        except Exception:
            pass
        _btctl("scan", "off", timeout=6)
        time.sleep(0.5)
    return _bt_known(mac)


def _other_bt_audio_holder(mac):
    """MAC of a different Bluetooth device that already holds the audio profile.

    The adapter supports only one A2DP stream at a time: a second speaker links
    up at the ACL level but never gets an audio sink, and bluez reports this
    inconsistently (br-connection-busy, br-connection-unknown, "Device or
    resource busy"), so detect it from the sinks rather than the error text.
    """
    want = mac.replace(":", "_").upper()
    for name in _existing_sinks():
        if name.startswith("bluez_output."):
            other = name.split(".")[1] if "." in name else ""
            if other and other.upper() != want:
                return other.replace("_", ":")
    return None


def _bt_do_connect(mac, attempts=2):
    """Connect, retrying once — BR/EDR connects fail spuriously fairly often.
    A good connect lands in a few seconds; the timeout only bites on failure,
    so keep it short enough that a doomed attempt doesn't stall the UI."""
    if _bt_is(mac, "Connected"):
        return True, ""          # nothing to do — don't spend 20s "reconnecting"
    busy = _other_bt_audio_holder(mac)
    if busy:
        name = (_bt_seen.get(busy) or {}).get("name") or busy
        return False, (f"“{name}” is already using Bluetooth audio. Disconnect it "
                       f"first — this unit can only play to one Bluetooth speaker "
                       f"at a time.")
    out = ""
    for i in range(attempts):
        _bt_phase(mac, "Connecting…" if i == 0 else "Connecting… (retry)")
        # NOTE: never pass --timeout here. It makes bluetoothctl stay alive for
        # the whole duration even after the operation finishes (measured: 12.07s
        # with `--timeout 12` vs 0.20s without), so every connect paid the full
        # timeout. The subprocess timeout below is the real safety net.
        out = _btctl("connect", mac, timeout=25)
        # Trust the device list, not the message: bluez can answer
        # "br-connection-already-connected" from a stale controller link while
        # the device is neither paired nor connected, so the text alone would be
        # a false success.
        if "Connection successful" in out or _bt_is(mac, "Connected"):
            return True, ""
        if "already-connected" in out:
            _btctl("disconnect", mac, timeout=10)   # clear the stale link
            time.sleep(1.5)
        elif i + 1 < attempts:
            time.sleep(1.5)
    return False, _friendly_bt_error(out)


def bt_pair(mac):
    """Pair + trust + connect in one action.

    Previously this only paired and trusted, so the user had to press Pair and
    then Connect; and because no output was checked, a failed pair still
    reported success. Trusting matters for auto-reconnect after a reboot.
    """
    _bt_phase(mac, "Starting…")
    _btctl("power", "on", timeout=8)
    _bt_stop_scan()

    if not _bt_is(mac, "Paired"):
        if not _bt_rediscover(mac):   # e.g. straight after a Forget
            _bt_refresh_devices()
            return _bt_set_last("pair", mac, False,
                                "Couldn't find the device. Make sure it's on and in pairing mode.")
        _bt_phase(mac, "Pairing…")
        out = _btctl("pair", mac, timeout=35)   # no --timeout: see _bt_do_connect
        paired = ("Pairing successful" in out or "AlreadyExists" in out
                  or "already" in out.lower() or _bt_is(mac, "Paired"))
        if not paired:
            _bt_refresh_devices()
            return _bt_set_last("pair", mac, False, _friendly_bt_error(out))

    _btctl("trust", mac, timeout=8)   # auto-reconnect later; failure isn't fatal
    ok, err = _bt_do_connect(mac)
    _bt_refresh_devices()
    _bt_set_last("pair", mac, ok, err)


def bt_connect(mac):
    _bt_phase(mac, "Starting…")
    _btctl("power", "on", timeout=8)
    _bt_stop_scan()
    ok, err = _bt_do_connect(mac)
    _bt_refresh_devices()
    _bt_set_last("connect", mac, ok, err)


def bt_disconnect(mac):
    _bt_phase(mac, "Disconnecting…")
    out = _btctl("disconnect", mac, timeout=15)
    ok = "Successful disconnected" in out or "Disconnection successful" in out \
        or not _bt_is(mac, "Connected")
    _bt_refresh_devices()
    _bt_set_last("disconnect", mac, ok, _friendly_bt_error(out))


def bt_remove(mac):
    _bt_phase(mac, "Forgetting…")
    out = _btctl("remove", mac, timeout=15)
    ok = "has been removed" in out or not _bt_is(mac, "Paired")
    _bt_seen.pop(mac, None)
    _bt_set_last("remove", mac, ok, _friendly_bt_error(out))


def bt_state():
    info = _run(["bluetoothctl", "show"])
    devices = []
    for m, d in _bt_seen.items():
        name = d.get("name", m)
        has_real_name = name.replace("-", ":").upper() != m.upper()
        # Hide the ephemeral, nameless BLE advertisers (phones/wearables with
        # random addresses) — only show named or paired/connected devices.
        if has_real_name or d.get("paired") or d.get("connected"):
            devices.append({"mac": m, "name": name,
                            "paired": d.get("paired", False),
                            "connected": d.get("connected", False)})
    # Devices that already have an audio sink are actually usable, not just
    # "connected" at the BR/EDR level — surface that so the UI can say so.
    sinks = "\n".join(_run(["pactl", "list", "sinks", "short"]).splitlines())
    for d in devices:
        d["has_audio"] = f"bluez_output.{d['mac'].replace(':', '_')}" in sinks
    return {
        "powered": "Powered: yes" in info,
        "scanning": _bt_scanning,
        "devices": devices,
        "last": _bt_last,
        "busy": _bt_busy,
    }


# ── State + change notification ──
_notify_cb = None
def set_notify(cb):
    global _notify_cb
    _notify_cb = cb
def _notify():
    if _notify_cb:
        try:
            _notify_cb()
        except Exception:
            pass


def audio_state():
    return {"sinks": list_sinks(), "outputs": _current_outputs(), "bt": bt_state()}


def watch_sinks():
    """Blocking loop: notify whenever a sink is added/removed (USB DAC or
    Bluetooth speaker plugged in/out) so the outputs list stays live."""
    last = 0.0
    while True:
        try:
            proc = subprocess.Popen(["pactl", "subscribe"], stdout=subprocess.PIPE, text=True)
            for line in proc.stdout:
                # A new playback stream (pygame starting a track) must be routed
                # to the selected output — otherwise it plays on whatever sink
                # it happened to open on.
                if "on sink-input #" in line and "'new'" in line:
                    try:
                        _apply_routing()
                    except Exception as e:
                        print(f"[audio] re-route failed: {e}")
                    continue
                if "on sink #" in line and ("'new'" in line or "'remove'" in line):
                    now = time.monotonic()
                    if now - last > 0.8:   # debounce bursts
                        last = now
                        # A selected speaker that just reconnected should take
                        # over again without the user re-picking it.
                        if "'new'" in line:
                            try:
                                set_outputs(_selected) if _selected else None
                            except Exception as e:
                                print(f"[audio] re-apply outputs failed: {e}")
                        _notify()
        except Exception as e:
            print(f"[audio] sink watch error: {e}")
        time.sleep(3)  # pactl died — reconnect
