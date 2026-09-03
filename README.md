# ControlByWeb WebRelay-Quad — Home Assistant integration

Control a ControlByWeb WebRelay-Quad relay board from Home Assistant. See whether each relay is
on, pulse one to trigger a door or gate, and get told when a pulse does not happen.

Works entirely on your own network. No cloud account and no internet connection.

**Supported model:** WebRelay-Quad — X-WR-4R3-I and X-WR-4R3-E.

Other ControlByWeb devices are **not** supported. Their register maps differ, and shipping a map
nobody has tested against real hardware would be a support claim rather than a feature.

## Before you install: two things this device makes you choose

**1. You can have the control password, or you can have this integration. Not both.**

The WebRelay-Quad switches Modbus off completely whenever a control password is set, because
Modbus has no way to carry one (manual §2.4.3, §3.3). If you need the web control page password
protected, this integration cannot work. Nothing here can change that.

**2. Home Assistant identifies the board by its address.**

The device offers no serial number and no model string — it answers no read at all except the
relay states. So a board is identified by the address you gave it. **If you change its IP address,
Home Assistant sees a new device**, and you will need to add it again and move your automations
across. Give it a static address or a DHCP reservation.

## Requirements

Home Assistant **2026.9.0 or newer**. This integration is built on the shared Modbus connection
that release introduced, so it will not load on anything earlier.

Nothing needs to be installed on the relay board, and nothing needs to be configured beyond
leaving the control password off.

## Installation

Through [HACS](https://hacs.xyz): add `https://github.com/ajguerre1/ha-controlbyweb-webrelay` as a
custom repository of type **Integration**, install it, and restart Home Assistant.

Then go to **Settings → Devices & services → Add integration** and search for **ControlByWeb**.
You will be asked for the board's address, its Modbus port (502 unless you changed it) and its
unit ID (255, which is what the manual specifies — leave it alone unless you have a reason not to).

Before creating anything, Home Assistant checks that a WebRelay-Quad is really what answered. If
something else is at that address you will be told so rather than ending up with relay controls
pointed at another device.

## What you get

| In Home Assistant | For each | What it does |
|---|---|---|
| Binary sensor | Relay | Whether the relay is currently on |
| Button | Relay | Pulse the relay — on, then off again after a set time |
| Switch | Relay | Hold the relay on until you turn it off. **Off by default** — see below |

### Why the switch is hidden to begin with

A WebRelay-Quad is usually wired to something momentary: a door release, a gate trigger, a
doorbell. For those, a relay that stays on is a fault, not a feature — and a switch on a dashboard
is one accidental tap away from leaving it that way.

So the switches exist but are turned off. If you have a relay that genuinely should latch — a
lamp, a pump, a heater — enable it under **Settings → Devices & services → ControlByWeb →
Entities**. It is also how you release a relay that has stuck on.

### Pulse length

Each relay has its own pulse length, set in the integration's options. **This is not read from the
board, and it cannot be** — the device has no way to report it over Modbus. If you have set a
*Pulse Duration* on the board's own setup page and you want the same behaviour here, type the same
number in.

Pulse lengths that differ per relay are normal and usually deliberate: a gate controller and a
door strike rarely want the same trigger. Check each one rather than assuming they match.

The default is **1 second**, chosen because too short is a nuisance and too long holds a relay
closed. Anything from 0.1 to 86400 seconds is accepted.

### Knowing whether a pulse actually happened

By default, pressing a pulse button also *watches* the relay to confirm it operated, and the press
fails if it never did — so an automation or script that pulses a gate stops rather than carrying on
as though it worked.

This is on by default and can be turned off in the integration's options.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Setup says it cannot connect | Wrong address or port, or the **control password is enabled** on the board |
| Setup says it is not a WebRelay-Quad | Something else answered at that address — check the IP |
| Everything went unavailable at once | Check the control password first; enabling it disables Modbus |
| A relay appears stuck on | Enable that relay's switch and turn it off |
| The binary sensor never reacts to a pulse | Expected. A short pulse is over long before the next poll — that sensor is for spotting a relay stuck **on**, not for confirming a press. Use pulse confirmation for that |

## Licence

MIT. Not affiliated with, endorsed by, or supported by Xytronix Research & Design, Inc.
