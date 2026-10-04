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
- **Manual Dose** button + **Manual Dose Amount** number — fires a one-off dose of whatever ml
  amount the number entity currently holds, on every pump regardless of schedule capability
- **Start Calibration** / **Apply Calibration** buttons + **Calibration Measured Amount** number —
  only for pumps with a product assigned. Press Start Calibration first (it stashes the returned
  session id), dial in the measured ml from a graduated cylinder into the number entity, then press
  Apply Calibration. A stale/missing session is rejected by the firmware itself; pressing Apply
  without ever pressing Start raises a clear error instead of silently no-op'ing.
- **Reservoir Remaining** / **Reservoir Full Volume** (diagnostic) / **Reservoir Days Remaining**
  sensors + **Refill Reservoir** button — only for pumps with a product assigned. Both
  Remaining and Days Remaining are whole numbers, rounded *down* ("do I need to refill soon"
  should never read more time/volume than is actually left) and projected from the pump's
  *current* schedule total (not historical usage — the device tracks no such history), so Days
  Remaining is `unknown` whenever the schedule is off or every slot is 0ml rather than showing a
  misleading number.
- **Daily Total (Auto-Divide)** number + **Apply Auto-Divide Schedule** button — only for pumps
  with a product assigned. Give it a total ml/day and press the button to evenly split that across
  all 24 hourly slots and write it straight to the device — the schedule's *starting point*, not
  its end state (individual hourly slots aren't editable from HA yet; use `reef-dose-service`'s
  `PATCH /pumps/:id/schedule` directly for that until a real schedule screen exists).
- **Label** sensor (diagnostic) — the pump's current product/OLED display label, live. This is
  where the "what's actually dosed through this pump" info lives, kept separate from the device
  name on purpose: the label can be renamed anytime (`PATCH /pumps/:id/name`, no reflash) and this
  sensor just follows it on the next poll, where the device name itself would otherwise go stale
  until a reload.

Polled once a minute via a `DataUpdateCoordinator`, same pattern as `alkatronic` in
[focustronic-ha](https://github.com/kevin-willoughby/focustronic-ha).

### Scaling groups

One additional Home Assistant device per *scaling group* (requirements.md Section 5), named after
the group, each with a single **Scale** number entity (0–1000%). Unlike every pump number entity
above, this one writes straight through on change — there's no separate "Apply" button, since the
`PATCH /groups/:id` call itself is what rescales every member pump's schedule on
`reef-dose-service`'s side.

Groups are genuinely dynamic — created via `reef-dose-service`'s API (`POST /groups/:id`), not
hardcoded here or there (pumps 5/6 are still generic placeholders as of this writing, so group
membership can't be derived from product assignments yet). This integration only creates a Scale
entity for groups that already exist when it starts up; **a group created later needs a reload of
this integration** (Settings → Devices & Services → Reef Dose → ⋮ → Reload) to show up. Creating a
group itself isn't exposed from HA yet — use the API directly, e.g.:

```bash
curl -X POST http://<host>/groups/complete-parts \
  -H "x-api-key: <service_api_key>" -H "content-type: application/json" \
  -d '{"name": "Complete Parts", "pumpIds": ["1", "4"]}'
```

## Adding more later

`api.py` holds the REST calls (mirrors `reef-dose-service`'s routes 1:1), `switch.py`'s
`SWITCH_DESCRIPTIONS` holds one entry per schedule-backed boolean — extending either is additive,
not a rewrite. The manual-dose, calibration, and daily-total number entities hold their values on
the pump coordinator (`manual_dose_ml`, `calibration_measured_ml`, `calibration_sessions`,
`daily_total_ml` in `coordinator.py`), not polled from the device, so the matching button can read
them at press time without a cross-platform entity lookup. Groups poll through a separate
`ReefDoseGroupsCoordinator` (`groups_coordinator.py`), keyed by group id rather than pump id, so
group records never collide with pump-keyed entities' assumptions about `coordinator.data`'s shape.

Still open: per-slot schedule editing from HA (the real "schedule screen" — a Lovelace dashboard or
bespoke frontend, still undecided), creating/deleting groups from HA, and the Cloudflare Access
policy for the service's tunnel — see `AquariumDosing/scratchpad/docs/architecture.md`'s "Next
Session — Start Here" list.
