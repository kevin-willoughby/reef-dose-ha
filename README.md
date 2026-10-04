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
- **Start Calibration** / **Apply Calibration** buttons + **Calibration Measured Amount** number +
  **Calibrating** binary sensor — only for pumps with a product assigned. Press Start Calibration
  first (it stashes the returned session id and flips Calibrating on), dial in the measured ml from
  a graduated cylinder into the number entity, then press Apply Calibration (which flips Calibrating
  back off). A stale/missing session is rejected by the firmware itself; pressing Apply without ever
  pressing Start raises a clear error instead of silently no-op'ing. The Calibrating binary sensor
  exists specifically to drive a **guided** Lovelace flow — see below — rather than always showing
  all three controls at once.
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
  its end state. Per-slot editing itself is the [reef-dose-card](https://github.com/kevin-willoughby/reef-dose-card)
  custom Lovelace card's job, not an HA entity.
- **Manual Overall Adjustment** number + **Apply Adjustment** button — only for pumps with a
  product assigned, and only while the pump is **not** in a scaling group (a grouped pump adjusts
  via its group's own Manual Overall Adjustment instead — see "Scaling groups" below). Enter a
  +/- percentage (e.g. `-10`) and press Apply to compound it onto whatever the pump's schedule is
  *currently* at, same semantics as the group version.
- **Label** sensor (diagnostic) — the pump's current product/OLED display label, live. This is
  where the "what's actually dosed through this pump" info lives, kept separate from the device
  name on purpose: the label can be renamed anytime (`PATCH /pumps/:id/name`, no reflash) and this
  sensor just follows it on the next poll, where the device name itself would otherwise go stale
  until a reload.

Polled once a minute via a `DataUpdateCoordinator`, same pattern as `alkatronic` in
[focustronic-ha](https://github.com/kevin-willoughby/focustronic-ha).

### Guided calibration (stock Lovelace, no custom card)

The Calibrating binary sensor lets a dashboard show only the relevant step instead of all three
calibration controls at once — standard Lovelace `conditional` cards, nothing custom:

```yaml
type: vertical-stack
cards:
  - type: conditional
    conditions:
      - entity: binary_sensor.pump_1_calibrating
        state: "off"
    card:
      type: button
      entity: button.pump_1_start_calibration
  - type: conditional
    conditions:
      - entity: binary_sensor.pump_1_calibrating
        state: "on"
    card:
      type: entities
      entities:
        - number.pump_1_calibration_measured_amount
        - button.pump_1_apply_calibration
```

### Scaling groups

A group owns **one shared 24-hour schedule** — every current member pump is kept identical to it
(scaled by the group's Manual Overall Adjustment), not just nudged by a shared percentage over
independently-drifting per-pump schedules. This is what makes ReefZElements-style groups work: two
mutually-exclusive Part 1 variants (no-boost / pH-boost) plus Part 2, always 1:1 — editing the
schedule once, at the group level, pushes the exact same numbers to every member. See
`reef-dose-service`'s README for the full mechanics (base-slot bookkeeping, what happens when a
pump leaves).

One additional Home Assistant device per *scaling group* (requirements.md Section 5), named after
the group, each with:

- **Manual Overall Adjustment** number (−100 to 1000%, matching the existing Dosetronic app's own
  name for this exact action) — the delta to apply, not the group's absolute scale. Enter `-10` and
  press **Apply Adjustment** to decrease every member pump's schedule by 10% of whatever it's
  *currently* at (not 10 percentage points off a fixed 100% base) — compounds like any "adjust by
  X%" control: entering `-10` twice takes a group from 100% → 90% → 81%, not straight to 80%.
  Resets to 0 after each Apply.
- **Apply Adjustment** button — applies the pending delta above.
- **Current Scale** sensor (read-only) — the resulting absolute percentage (100 = the group's
  unscaled base), so you can see what the adjustments have compounded to without doing the math
  yourself.
- **Daily Total (Auto-Divide)** number + **Apply Auto-Divide Schedule** button — the group-level
  counterpart to the per-pump version above: evenly splits a total ml/day across all 24 hours and
  pushes it identically to every current member.

Groups are genuinely dynamic — created via `reef-dose-service`'s API (`POST /groups/:id`), not
hardcoded here or there (pumps 5/6 are still generic placeholders as of this writing, so group
membership can't be derived from product assignments yet). This integration only creates these
entities for groups that already exist when it starts up; **a group created later needs a reload of
this integration** (Settings → Devices & Services → Reef Dose → ⋮ → Reload) to show up. Creating a
group, editing its per-slot schedule, and managing membership are the
[reef-dose-card](https://github.com/kevin-willoughby/reef-dose-card) custom Lovelace card's job —
or call the `reef_dose.create_group`/`reef_dose.update_group_schedule` services below from
Developer Tools → Actions directly.

## Services (`reef_dose.*`)

Beyond the entities above, this integration registers services for the structured actions no
single entity can represent — a partial dict of 24 hourly slot values, an arbitrary pump-id list.
These exist for [reef-dose-card](https://github.com/kevin-willoughby/reef-dose-card) (the schedule
editor / group management custom Lovelace card) to call via `hass.callService`, not primarily for
hand-written automations, though they work fine from Developer Tools → Actions too. `service_api_key`
never leaves the integration — the card never sees it, only service names/data — same security
boundary every other entity in this integration already holds.

| Service | Does |
|---|---|
| `reef_dose.get_schedule` | Reads one pump's full schedule. Response-only. |
| `reef_dose.update_schedule` | Partial update — `slots`, `schedule_enabled`, `split_dose_enabled`, any subset |
| `reef_dose.auto_divide_schedule` | Same as the Apply Auto-Divide button, but with an arbitrary `daily_total_ml` instead of reading the number entity |
| `reef_dose.apply_pump_adjustment` | Same as the per-pump Apply Adjustment button, but with an arbitrary `delta_percent`. Rejected if the pump is in a group. |
| `reef_dose.get_groups` | Lists every scaling group. Response-only. |
| `reef_dose.create_group` | `group_id`, `name`, `pump_ids`, optional `scale_percent` |
| `reef_dose.update_group` | Partial update — `name`, `pump_ids`, `scale_percent`, any subset |
| `reef_dose.delete_group` | `group_id` |
| `reef_dose.get_group_schedule` | Reads a group's own canonical schedule. Response-only. |
| `reef_dose.update_group_schedule` | Partial edit to a group's schedule — `slots`, pushed identically to every current member |
| `reef_dose.auto_divide_group_schedule` | Same as the group's Apply Auto-Divide Schedule button, but with an arbitrary `daily_total_ml` |

Full field descriptions: `services.yaml`, or Developer Tools → Actions in HA's own UI once this
integration is loaded.

## Adding more later

`api.py` holds the REST calls (mirrors `reef-dose-service`'s routes 1:1), `switch.py`'s
`SWITCH_DESCRIPTIONS` holds one entry per schedule-backed boolean — extending either is additive,
not a rewrite. The manual-dose, calibration, daily-total, and adjustment number entities hold their
values on the pump coordinator (`manual_dose_ml`, `calibration_measured_ml`,
`calibration_sessions`, `daily_total_ml`, `pending_adjustment` in `coordinator.py`), not polled
from the device, so the matching button can read them at press time without a cross-platform
entity lookup. Groups poll through a separate `ReefDoseGroupsCoordinator`
(`groups_coordinator.py`), keyed by group id rather than pump id, so group records never collide
with pump-keyed entities' assumptions about `coordinator.data`'s shape — it carries the same two
pending-value dicts for its own Manual Overall Adjustment and Daily Total (Auto-Divide) entities.
A pump currently in a group gets its adjustment/auto-divide entities from the group instead of its
own (`grouped_pump_ids`, computed once at setup in `number.py`/`button.py`'s `async_setup_entry`).

Still open: the Cloudflare Access policy for the service's tunnel — see
`AquariumDosing/scratchpad/docs/architecture.md`'s "Next Session — Start Here" list.
