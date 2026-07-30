# Player unit host setup

Host-level tweaks a player unit needs. These live outside the Python app because
they configure the machine's audio stack, not SoundPool itself.

## `wireplumber-60-disable-logind.lua` — required for Bluetooth speakers

Install to `/etc/wireplumber/bluetooth.lua.d/60-disable-logind.lua`, then
`systemctl --user restart wireplumber` (as the unit's audio user).

WirePlumber only starts its BlueZ monitor while the audio user's logind seat is
**active**. A player unit runs headless via `loginctl enable-linger`, so when a
display manager (lightdm/gdm) sits on the login screen, *its* session holds
`Active=yes` on seat0 and the unit's user stays `online`. The BlueZ monitor then
never starts, no A2DP endpoint is registered with bluez, and every connect fails
with:

    Failed to connect: org.bluez.Error.Failed br-connection-profile-unavailable

Symptom: the speaker pairs fine but never connects, and no `bluez_output.*` sink
appears in `pactl list sinks short`.

A unit is a single-user audio appliance, so the "which user gets Bluetooth audio"
arbitration this flag controls has nothing to arbitrate — disabling it makes the
monitor load unconditionally.

Verify:

    bluetoothctl connect <MAC>          # -> "Connection successful"
    pactl list sinks short              # -> bluez_output.<MAC>
    pactl list cards | grep "Active Profile"   # -> a2dp-sink (stereo, not HFP mono)

## Related host fixes (not files, one-time commands)

- **Greeter steals the sound card** — mask the display manager's own PipeWire:
  `systemctl --user -M lightdm@.host mask --now pipewire.socket pipewire-pulse.socket wireplumber.service pipewire.service pipewire-pulse.service`
  and `usermod -aG audio <unit-user>`.
- **Bluetooth adapter soft-blocked** (common on Lenovo ideapad): `rfkill unblock bluetooth`.
- **Linger** so `/run/user/<uid>` exists at boot: `loginctl enable-linger <unit-user>`.
