-- SoundPool player unit: disable WirePlumber's logind arbitration for Bluetooth.
--
-- By default (bluetooth.lua.d/50-bluez-config.lua) `with-logind = true` makes the
-- bluez monitor start ONLY while the user's logind seat is "active". On this box
-- the lightdm greeter session holds Active=yes on seat0, so the player-unit user
-- (trickish, running headless via `loginctl enable-linger`) stays "online" and the
-- bluez monitor never starts. bluez then has no A2DP endpoint registered and every
-- connect fails with `br-connection-profile-unavailable`.
--
-- This box is a single-purpose audio appliance with exactly one audio user, so the
-- "which user gets bluetooth audio" arbitration has nothing to arbitrate — turning
-- it off makes the monitor load unconditionally (see scripts/monitors/bluez.lua:405,
-- which falls back to createMonitor() when the logind plugin is absent).
--
-- Related: the same active-seat conflict previously stole the ALSA card (fixed by
-- masking the greeter's PipeWire + adding trickish to the audio group).

bluez_monitor.properties["with-logind"] = false

if bluez_midi_monitor ~= nil and bluez_midi_monitor.properties ~= nil then
  bluez_midi_monitor.properties["with-logind"] = false
end
