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
| `reef_dose.create_group` | `group_id`, `name`, `pump_ids`, optional `scale_percent`, optional `auto_sync` |
| `reef_dose.update_group` | Partial update — `name`, `pump_ids`, `scale_percent`, `auto_sync`, any subset |
| `reef_dose.delete_group` | `group_id` |
| `reef_dose.get_group_schedule` | Reads a group's own canonical schedule. Response-only. |
| `reef_dose.update_group_schedule` | Partial edit to a group's schedule — `slots`, pushed to every member only if `auto_sync` is true |
| `reef_dose.auto_divide_group_schedule` | Same as the group's Apply Auto-Divide Schedule button, but with an arbitrary `daily_total_ml` |
| `reef_dose.sync_group_member` | Explicitly pushes a group's current template to one member — the action an `auto_sync: false` group needs |
| `reef_dose.sync_group` | Explicitly pushes a group's current template to every current member |

Full field descriptions: `services.yaml`, or Developer Tools → Actions in HA's own UI once this
integration is loaded.

### `auto_sync`

Every group defaults to `auto_sync: true` — any template/scale/membership change pushes
immediately to every current member, same as before this flag existed. Set it to `false` for a
group whose members are **mutually exclusive variants of the same dose** (e.g. two interchangeable
Part 1 formulas, only one of which should ever actually be dosing at a time). With `auto_sync:
false`, template edits only update the stored template — nothing reaches a device until
`reef_dose.sync_group_member`/`reef_dose.sync_group` is called explicitly, typically from an
automation that decides which variant should be active right now (see Blueprint below).

## Blueprint: pH-boost Part 1 variant switch

`blueprints/automation/reef_dose/ph_boost_switch.yaml` implements requirements.md §6 — the
ReefZelements use case above, made concrete: Part 1 has a no-boost pump and a pH-boost pump that
must never both be enabled at once, decided hourly from the Apex's real pH and time of day, with
Part 2 always kept in sync with whichever variant is active.

**Setup:**

1. Create an `input_boolean` helper first (Settings → Devices & Services → Helpers → + Add Helper
   → Toggle) — this is the season gate, not a pH fallback. ON = pH-boost season is active, so the
   blueprint examines live pH and time of day each run. OFF = out of season, so it forces no-boost
   every run without even checking pH.
2. Set the real ReefZelements group to `auto_sync: false` once (Developer Tools → Actions →
   `reef_dose.update_group` with `group_id: "Reef Zelements"`, `auto_sync: false`) — otherwise the
   group itself will keep fighting the blueprint by re-pushing the template to all three members on
   every template edit.
3. Settings → Automations & Scenes → Blueprints → Import Blueprint, point it at this file (or the
   raw GitHub URL once pushed), then create an automation from it with:
   - **Apex pH Sensor**: `sensor.apex_ph`
   - **Group ID**: `Reef Zelements`
   - **No-Boost Pump ID**: `1`
   - **pH-Boost Pump ID**: `2`
   - **Always-On Pump IDs**: `4` (Part 2)
   - **pH Boost Enabled**: the `input_boolean` created in step 1

The automation runs at :50 past every hour, deciding which variant doses the upcoming hour, and
can be tested immediately via its own "Run actions" button in the HA UI rather than waiting for a
real trigger.

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
