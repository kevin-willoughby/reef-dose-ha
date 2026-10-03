# Reef Dose for Home Assistant

Home Assistant integration for the [reef-dose](https://github.com/kevin-willoughby/reef-dose) ESP32
dosing controller — talks to it through [reef-dose-service](https://github.com/kevin-willoughby/reef-dose-service),
not directly to the device, so this integration stays a thin REST client with no ESPHome/Noise
protocol code of its own.

## Installation (via HACS)

1. HACS → Integrations → ⋮ (top right) → **Custom repositories**
2. Add this repo's URL, category **Integration**
3. Install **Reef Dose**, restart Home Assistant
4. Settings → Devices & Services → **+ Add Integration** → search **Reef Dose**
5. Enter `reef-dose-service`'s host (including port, e.g. `192.168.80.225:3000`) and its
   `service_api_key`

## What you get

One Home Assistant device per physical pump, **named "Pump 1".."Pump 6"** — deliberately fixed,
not derived from whatever product is currently assigned to that pump. Each has:

- **Schedule Enabled** / **Split Dose (2x Per Hour)** switches — only for pumps with a product
  assigned (a pump with no schedule capability still shows up, just without these two)
- **Prime** button — fires a 10s prime pulse, on every pump regardless of schedule capability
- **Label** sensor (diagnostic) — the pump's current product/OLED display label, live. This is
  where the "what's actually dosed through this pump" info lives, kept separate from the device
  name on purpose: the label can be renamed anytime (`PATCH /pumps/:id/name`, no reflash) and this
  sensor just follows it on the next poll, where the device name itself would otherwise go stale
  until a reload.

Polled once a minute via a single `DataUpdateCoordinator`, same pattern as `alkatronic` in
[focustronic-ha](https://github.com/kevin-willoughby/focustronic-ha).

## Adding more later

`api.py` holds the REST calls (mirrors `reef-dose-service`'s routes 1:1), `switch.py`'s
`SWITCH_DESCRIPTIONS` holds one entry per schedule-backed boolean — extending either is additive,
not a rewrite. Manual dose (needs an ml amount) and calibration (needs a session id round-trip)
aren't exposed yet — `reef-dose-service`'s own routes for those are still in flux.
