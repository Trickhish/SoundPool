"""Audio-interface management for the player unit, via pactl (PipeWire/Pulse)
and bluetoothctl. Lets a unit play to one or several sinks at once (combine
sink) and manage Bluetooth speakers."""
import os
import re
import subprocess
import threading
import time

COMBINE_SINK = "soundpool_out"   # our managed combine sink (multi-output)

# Bluetooth scan results live here (mac -> {name, paired, connected, last_seen})
_bt_seen = {}
_bt_scanning = False
_selected = []                   # last selected sink names (persisted in-memory)


def _run(args, timeout=10):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.stdout
    except Exception as e:
        print(f"[audio] {' '.join(args)} failed: {e}")
        return ""


# ── Sinks ──
def _sink_descriptions():
    """name -> human description from `pactl list sinks`."""
    out = _run(["pactl", "list", "sinks"])
    desc, cur = {}, None
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("Name:"):
            cur = line.split("Name:", 1)[1].strip()
        elif line.startswith("Description:") and cur:
            desc[cur] = line.split("Description:", 1)[1].strip()
    return desc


def _sink_volume(name):
    out = _run(["pactl", "get-sink-volume", name])
    m = re.search(r"(\d+)%", out)
    return int(m.group(1)) if m else 100


def list_sinks():
    out = _run(["pactl", "list", "short", "sinks"])
    desc = _sink_descriptions()
    sinks = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        name = parts[1]
        if name == COMBINE_SINK or ".monitor" in name or name == "auto_null":
            continue
        sinks.append({"name": name, "description": desc.get(name, name),
                      "volume": _sink_volume(name)})
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


def set_outputs(names):
    """Route the unit's playback to the given sink name(s)."""
    global _selected
    names = [n for n in (names or []) if n]
    _selected = names
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

    si = own_sink_input()
    if target and si:
        _run(["pactl", "move-sink-input", si, target])


def set_sink_volume(name, level):
    pct = max(0, min(150, int(round(float(level) * 100))))
    _run(["pactl", "set-sink-volume", name, f"{pct}%"])


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
def _btctl(*cmds, timeout=8):
    """Run a sequence of bluetoothctl commands non-interactively."""
    inp = "\n".join(cmds) + "\n"
    try:
        r = subprocess.run(["bluetoothctl"], input=inp, capture_output=True,
                           text=True, timeout=timeout)
        return r.stdout
    except Exception as e:
        print(f"[bt] {cmds} failed: {e}")
        return ""


def _bt_refresh_devices():
    out = _run(["bluetoothctl", "devices"])
    for line in out.splitlines():
        m = re.match(r"Device (\S+) (.+)", line.strip())
        if m:
            _bt_seen.setdefault(m.group(1), {})["name"] = m.group(2)
    # enrich with the real advertised name (the devices list falls back to the
    # MAC when unresolved) + paired/connected status from `info`.
    for mac, d in _bt_seen.items():
        info = _run(["bluetoothctl", "info", mac])
        name = None
        for ln in info.splitlines():
            ln = ln.strip()
            if ln.startswith("Name:"):
                name = ln.split("Name:", 1)[1].strip()
            elif ln.startswith("Alias:") and not name:
                alias = ln.split("Alias:", 1)[1].strip()
                if alias and alias.replace("-", ":").upper() != mac.upper():
                    name = alias
        if name:
            d["name"] = name
        d["paired"] = "Paired: yes" in info
        d["connected"] = "Connected: yes" in info


def bt_scan(seconds=8):
    global _bt_scanning
    if _bt_scanning:
        return
    _bt_scanning = True

    def worker():
        global _bt_scanning
        _run(["bluetoothctl", "power", "on"])
        # `--timeout N scan on` keeps a session alive scanning for N seconds,
        # then exits (a piped session would stop scanning immediately).
        _run(["bluetoothctl", "--timeout", str(seconds), "scan", "on"], timeout=seconds + 6)
        _bt_refresh_devices()
        _bt_scanning = False
        _notify()
    threading.Thread(target=worker, daemon=True).start()


def bt_pair(mac):
    _btctl("power on", "agent on", "default-agent",
           f"pair {mac}", f"trust {mac}", timeout=25)
    _bt_refresh_devices()


def bt_connect(mac):
    _btctl(f"connect {mac}", timeout=15)
    _bt_refresh_devices()


def bt_disconnect(mac):
    _btctl(f"disconnect {mac}", timeout=10)
    _bt_refresh_devices()


def bt_remove(mac):
    _btctl(f"remove {mac}", timeout=10)
    _bt_seen.pop(mac, None)


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
    return {
        "powered": "Powered: yes" in info,
        "scanning": _bt_scanning,
        "devices": devices,
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
