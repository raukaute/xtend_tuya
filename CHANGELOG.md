# Changelog

Notable changes to the raukaute fork of `xtend_tuya`. Newest at the top.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions match the integration `manifest.json` version field — bump that
when shipping anything user-visible so HACS picks the release up.

## [Unreleased]

_Nothing yet._

## [4.4.134] — 2026-05-12

Two fixes verified against the Mavronero account by direct API probing
on 2026-05-12:

- **POST body**: include `date` in each `instruct[]` and `startTime`,
  `start`, `current` inside `functions[].value`. Tuya accepted the
  minimal body in v4.4.132 but SmartLife's scheduler UI rendered the
  result as a half-broken "Single watering" entry and the SL edit flow
  hung; the rich shape matches what SmartLife itself POSTs and renders
  cleanly.
- **Selective DELETE**: use the query-string form
  `DELETE /v1.0/devices/{id}/timers?group_id={gid}`. Every path-style
  variant (`/timers/{group_id}`, `/timer/group/{id}`,
  `/timer/groups/{id}`, …) returns `1108 "uri path invalid"`.
  v4.4.132 left stale cloud entries because the path-style DELETE in
  `_delete_cloud_timer_by_match` silently failed every time.

## [4.4.133] — 2026-05-12

(skipped — tag created against a partial fix during a tooling hiccup;
content is rolled forward into 4.4.134.)

## [4.4.132] — 2026-05-12

Fix cloud timer POST body layout to match Tuya's create-timer schema
([Tuya docs](https://developer.tuya.com/en/docs/cloud/timing-management?id=K95zu050h5m53)):

- `time` belongs inside each `instruct[]` element, not at the top level.
- `timezone_id` (IANA, e.g. `Asia/Nicosia`) and `time_zone` (UTC offset,
  e.g. `+3:00` during EEST) are required top-level fields. Derived from
  HA's configured `time_zone` so the timer fires when the operator
  expects.
- `instruct[].functions[]` carries `{code, value}` — same key the GET
  response uses for the read shape, but nested one level deeper on the
  write side.
- Dropped non-input fields `time`, `is_app_push`, `status` from the
  top level; they were responsible for the `1109 "param is illegal"`
  responses observed on v4.4.130 / v4.4.131.

## [4.4.131] — 2026-05-12

POST body uses `instruct` instead of `functions` for the action array.
Tuya's create-timer endpoint is asymmetric: the GET response renders
the same data under `functions`, but the POST input expects `instruct`.
v4.4.130 still returned `1109 "param is illegal"` for this reason.

## [4.4.130] — 2026-05-12

Fix two cloud-timer write bugs identified by the v4.4.129 diagnostic
logs against the Mavronero fleet:

- **POST body**: outer `category` must be the literal `"timer"` (Tuya's
  timer-group container), not the DP code `"time_task"`. Sending the
  DP code returned `1109 "param is illegal"` and the cloud refused to
  persist HA edits, allowing the device-side rollback path to win
  ~10 s later.
- **DELETE URL**: Tuya's delete works on the timer-**group** id (the
  container holding one or more timers), not the inner `timer_id`.
  Sending the timer id returned `1108 "uri path invalid"` and left
  stale cloud entries behind, producing duplicated SmartLife schedule
  entries after a time/day edit.

## [4.4.129] — 2026-05-12

Diagnostic-only release: bump every step of the fdm5kw cloud-timer
write path to WARNING so the SL-sync regression on the Mavronero fleet
shows up at the default log level without needing a debug-logger
config. Logs every URL, body, response, and matched/unmatched slot for
set_timer and delete_timer. Once the broken step is identified the
log levels will drop back to debug.

## [4.4.128] — 2026-05-12

Apply the v4.4.124 sub-minute timer-duration fix to the xtend_tuya
in-tree copy of `irrigation-timer-card.ts`. The original v4.4.124 fix
patched the standalone `raukaute/irrigation-timer-card` repo, but
xtend_tuya carries its own copy under `frontend/src/`; the next
rebuild (v4.4.127) regenerated the bundled card from the unpatched
in-tree copy and brought the `0min` display bug back. Both source
trees now match.

## [4.4.127] — 2026-05-12

Strategy dashboard now passes the Tuya device id (read from the
registry sensor's `device_id` attribute) to per-valve cards instead of
HA's entity-registry device UUID. The fdm5kw timer services look up
multi-managers by Tuya id; the v4.4.126 dual-write release silently
no-op'd from strategy-built dashboards because `_find_multi_manager`
got the HA UUID and returned None (log line: "No multi_manager found
for device c0d0d4ba..."). Hand-written YAML dashboards still worked
because they hard-coded Tuya ids.

The entity-discovery loop inside the strategy keeps using HA's
device-registry id; only the value handed to cards changed.

## [4.4.126] — 2026-05-12

Dual-write timer mutations to the device DP **and** the Tuya cloud
timer registry. v4.4.122 assumed the device DP was authoritative, but
empirical testing on 2026-05-12 with the Mavronero fleet showed that
Tuya's cloud rolls the device DP back from the cloud timer registry
~10s after a direct DP write. The result: HA → SmartLife edits and
deletes appeared to take, then reverted on the dashboard a few seconds
later.

`set_timer` / `delete_timer` now:
1. Look up the slot's prior state from the registry entity so we can
   delete the cloud entry that's about to be replaced (avoids duplicate
   SmartLife schedule entries on time/day edits).
2. Write the DP for immediate local execution (offline-safe, fast).
3. POST / DELETE the cloud timer registry so the cloud doesn't roll
   back our DP change.

Cost: 1–2 OpenAPI calls per user-initiated timer mutation. Negligible
vs the historical periodic-poll regressions — these mutations are
interactive, not on a timer. Boot-time cloud resync is still removed.

## [4.4.125] — 2026-05-12

Force a state write at the end of `Fdm5kwTimerRegistryEntity.async_added_to_hass`
so the registry sensor's attributes (`valve_name`, `slots`, ...) reach
the frontend immediately on integration boot. Pre-fix, devices that
hadn't received a fresh `time_task` DP push since the last restart kept
the prior boot's attributes; the dashboard strategy then fell back to
the raw `device_id` for tile/tab names, producing the "raw hex titles +
Configuration error" overview seen after the OpenAPI credential swap.

## [4.4.124] — 2026-05-12

Rebundle `irrigation-timer-card.js` with fixed duration display.
Pre-fix: any sub-minute duration rendered as `0min` because the value
was floored to integer minutes. Sub-minute timers (common for manual
short-burst tests) looked broken in the card even though the underlying
DP was correct. Now renders `Ns` for sub-minute, `Nmin` for whole
minutes, `Nmin Ms` for the mixed case.

## [4.4.123] — 2026-05-12

Restore `state_class=TOTAL_INCREASING` on the `cur_cap` (watering_volume)
sensor for `sfkzq` valves. The v4.4.120 hard revert to the v4.4.111
baseline dropped the attribute, which surfaced as 28 "no longer has a
state class" repair notifications and broke lifetime-water statistics.
The FDM5KW spec exposes no `water_total` DP, so `cur_cap` (per-run
cumulative, resets each cycle) is HA's only path to an all-time figure
via TOTAL_INCREASING reset semantics.

## [4.4.122] — 2026-05-07

Strip the Tuya OpenAPI dependency from the fdm5kw irrigation valve path.
The OpenAPI channel is the metered tier (Trial Edition $0.20/month
budget); the sharing-API + cloud-MQTT push channel is free and
push-based. With this release, the fdm5kw services and registry rely
exclusively on the sharing channel.

The device-side `time_task` DP is now treated as the single source of
truth for schedules. The Tuya cloud timer registry — a redundant
server-side mirror that the fork previously read on boot and on every
service call — is no longer consulted or written. SmartLife displays
schedules from the DP shadow that propagates through cloud MQTT
regardless, so the valve detail screen still shows live state; only the
SmartLife "Schedule" editor tab will appear empty (HA owns scheduling).

See `docs/migration_strategy.md` for the broader plan (Phase 2:
LocalTuya, Phase 3: Cloudcutter + ESPHome).

### Removed
- **Cloud timer registry sync** in
  `entity_parser/fdm5kw/sensor.py`: `_sync_cloud_timers()`,
  `_extract_cloud_timers()`, `_sync_custom_name()`, and
  `resync_cloud_timers()`. The boot sync was the largest historical
  quota burner — every restart fetched timers for every valve via
  `GET /v1.0/devices/{id}/timers` and `GET /v2.0/cloud/thing/{id}`.
- **Cloud timer registry write** in
  `entity_parser/fdm5kw/timer_service.py`: `_post_cloud_timer()` and
  `_delete_cloud_timer_by_match()`. Schedule writes go to the device
  DP only.
- **`fdm5kw_resync_timers` service** (and `services.yaml` entry).
  There is nothing to resync from once the cloud registry is out of
  the loop; the registry hydrates from HA state restoration plus DP
  push events.
- **`DPCodeTimeTaskRegistryWrapper.reconcile_with_cloud` /
  `merge_cloud_timers` / `_parse_cloud_timer`** — cloud-specific
  reconciliation logic.

### Changed
- **DP writes go through the multi-manager** rather than directly
  hitting `account.call_api("POST", "/v1.0/devices/{id}/commands")`
  on the `tuya_iot` (OpenAPI) account:
  - `entity_parser/fdm5kw/timer_service.py:_write_time_task`
  - `entity_parser/fdm5kw/control_service.py:_write_one_control`
  Both now call `multi_manager.send_commands(device_id, [...])`,
  which prefers the sharing channel and only falls back to OpenAPI
  if sharing is unavailable.
- **Registry entity attributes** in `Fdm5kwTimerRegistryEntity`:
  dropped `valve_custom_name` and `valve_factory_name`; `valve_name`
  is now `device.name`. The SmartLife user-set custom name is no
  longer fetched. Rename in HA (Settings → Devices) if desired —
  one-time, persists.

### Why
- **Quota.** Trial Edition is hard-capped at $0.20/month
  (~54k EU calls). Per-restart sync × 21 valves and per-service-call
  list+delete burned through it in days. Sharing channel is free and
  has no per-call meter.
- **Device cap.** Trial Edition limits 50 devices per cloud project.
  Fleet is expected to exceed 50; sharing-only operation removes the
  OpenAPI device-cap pressure on the schedule path (account-link cap
  still applies, but is the next problem to solve via Cloudcutter, not
  this release).
- **Source-of-truth drift.** The two-tier model (cloud registry +
  device DP) was the root cause of multiple regressions in 4.4.112–119.
  One tier is simpler and correct.

### Trade-off
- SmartLife's "Schedule" editor tab will show no entries for fdm5kw
  valves. Workers diagnosing in the field still see live state in
  SmartLife's valve detail screen (open/closed, last run, battery)
  via DP shadow. Editing schedules is owned by HA Companion or the
  custom irrigation-timer card. Acceptable per migration plan.

### Notes
- This is Phase 1 of a three-phase migration documented in
  `docs/migration_strategy.md`. Phase 2 (LocalTuya in parallel) and
  Phase 3 (Cloudcutter → ESPHome) follow.

## [4.4.121] — 2026-05-07

Follow-up to 4.4.120. The hard revert restored the Python integration
to v4.4.111 but the kept-at-HEAD frontend strategy was looking for
entity names that only exist in 4.4.112+ code, leaving the
`strategy: custom:irrigation-valves` dashboard to render with empty /
Unavailable cards.

### Fixed
- **Strategy entity discovery** in
  `frontend/src/irrigation-valves-strategy.ts`:
  - Also accepts entity_id suffix `_time_task_registry` (the v4.4.111
    name for the Irrigation timer registry sensor) in addition to the
    newer `_irrigation_timer_registry`.
  - Maps both `close_time` and `end_time` translation_keys to the
    "End" sensor field; v4.4.111 uses `end_time` for the CLOSE_TIME
    DP.
- Compiled JS rebuilt to match.

## [4.4.120] — 2026-05-07

Hard revert. The 4.4.112-119 series — per-second polling, dashboard
strategy, atomic single-watering writes, DP decoders, schedule-sync
fixes, lifetime water graph — caused cascading regressions including
quota exhaustion, device entities going Unavailable, and config-entry
auth churn.

### Changed
- `binary_sensor.py`, `sensor.py`,
  `entity_parser/fdm5kw/control_service.py`,
  `entity_parser/fdm5kw/sensor.py`,
  `entity_parser/fdm5kw/timer_service.py`
  reverted byte-for-byte to v4.4.111. This is the pre-customization
  baseline. The Single-watering button, schedule registry, valve
  control, status sensors, etc. all behave exactly as they did in
  v4.4.111.
- Frontend `irrigation-control-card.js` and
  `irrigation-valves-strategy.js` retained at HEAD — pure JS, no API
  cost, keeps the user's `strategy: custom:irrigation-valves`
  dashboard YAML working without YAML changes on their side.

### Why
Working baseline took priority over feature accumulation. Quota was
exhausted; Single watering, timers and schedule sync were no longer
reliable; users were getting `Configuration error` banners and
Unavailable entities. Best path forward is a clean baseline we can
re-add features to deliberately, with quota-awareness from the start.

## [4.4.119] — 2026-05-07

API quota cut. The Mavronero Solar Valves Tuya project hit
`code=28841004 "Your quota of Trial Edition is used up"` because the
4.4.112 per-second active-run poll plus the 4.4.113 5-minute
safety-net resync burned through the 1M-call/month Trial cap on a
21-valve fleet. Reverting both.

### Removed
- **Per-second active-run poll** (`active_run_poller.py`,
  `Fdm5kwActiveRunPoller`). It GET'd `/v1.0/devices/{id}/status` at 1Hz
  while `switch=true` to make `cur_cap` / `cur_time` graphs smooth —
  but at fleet scale this is ~75K calls/hour during active windows,
  the single biggest quota burner. Tuya's MQTT push still updates the
  same DPs every several seconds; per-cycle history graph just
  staircases instead of curving. Acceptable.
- **5-minute periodic safety-net resync** in
  `Fdm5kwTimerRegistryEntity` (`async_track_time_interval` with
  `RESYNC_PERIODIC_INTERVAL = timedelta(minutes=5)`). 12 GETs/hr/valve
  → ~181K calls/month for a 21-valve fleet, all unconditional. Removed.

### Kept (no API cost)
- Event-driven debounced cloud resync on DP push (rare; only fires
  when device pushes a change).
- Immediate resync after `xtend_tuya.fdm5kw_set_timer` /
  `_delete_timer` services (user-initiated, rare).
- Atomic `switch + one_control` writes in start/stop watering.
- Frontend dashboard strategy + lifetime water statistics-graph.
- DP decoding (`run_task_sta` mapping, `vbat_state` clamp,
  `malfunction` per-bit auto sensors).
- `_prefer_device_enabled` schedule reconciliation.

### Trade-off
Cloud-only edits in SmartLife that don't echo back to a device DP
(e.g. toggling `enabled` on a timer slot) are no longer picked up
within 5 minutes — only on next HA boot or next service-triggered
write. If this becomes a real problem, a config-flag opt-in for the
safety net is the right shape, not unconditional.

## [4.4.118] — 2026-05-07

Second hotfix for 4.4.116. The `run_task_sta` ENUM declaration crashed
the entire `sensor` platform setup with
`KeyError: <SensorDeviceClass.ENUM: 'enum'>` raised by upstream
`tuya/sensor.py:1719` — `SENSOR_DEVICE_CLASS_UNITS` doesn't carry an
ENUM key, and the device's `run_task_sta` DP advertises unit `"无"`
which trips the validator.

### Changed
- `run_task_sta` sensor in `custom_components/xtend_tuya/sensor.py` no
  longer declares `device_class=ENUM` / `options=[...]`. Mapping to
  `idle / scheduled / running / complete / error` is preserved as a
  plain string sensor with `native_unit_of_measurement=None`.

## [4.4.117] — 2026-05-06

Hotfix for 4.4.116. The `sfkzq` block I activated used `is_on=` lambdas
that aren't a valid field on `XTBinarySensorEntityDescription` — the
import failure took down the entire `binary_sensor` platform for every
config entry, which in turn prevented the integration from ever
finishing setup (HA showed a cascading "Tuya OpenAPI credentials
expired" repair as collateral; the OpenAPI was fine).

### Removed
- `sfkzq` explicit binary_sensor block in `binary_sensor.py`. The six
  `malfunction` bits still appear automatically via the existing BITMAP
  auto-discovery path (`async_add_generic_entities`), so no functional
  loss for the per-bit error sensors. Composite `error` and
  `battery_charging` are dropped for now — to be reimplemented via
  proper `bitmap_key=` / a small entity subclass in a follow-up.

## [4.4.116] — 2026-05-05

DP-cross-check follow-up to 4.4.115. Several fdm5kw DPs were either
exposed as raw integers or only partially decoded — fixed.

### Added
- **`run_task_sta` enum sensor**. Was rendered as `"1"`, `"2"`, …;
  now maps to `idle / scheduled / running / complete / error` with
  `device_class=ENUM`. Mapping is observation-derived; values
  outside 0..4 fall back to `"unknown"`.
- **fdm5kw binary_sensor block** activated in
  `binary_sensor.py` (the upstream-authored definitions were sitting
  commented out). Adds:
  - `error` — composite `malfunction != 0` problem indicator.
  - Per-bit `error_flow_meter`, `error_valve_low_battery`,
    `error_sensor_low_battery`, `error_sensor_offline`,
    `error_water_shortage`, `error_other` for the 6 documented
    malfunction bits.
  - `battery_charging` derived from `vbat_state` bit 7 (charging
    when raw value > 127).

### Changed
- **`vbat_state` battery level** now `min(value & 0x7F, 100)`
  (was just `& 0x7F`). Raw range is 0..127 but valid percentage is
  0..100; the clamp prevents a value like 100% with bit 6 set
  appearing as 100 instead of 100.

## [4.4.115] — 2026-05-05

Fixes the case where the registry showed a timer as OFF while the
valve was actually still going to fire it.

### Changed
- **`reconcile_with_cloud` now defers to device DP for `enabled`** when
  the schedule shape (hour/min/days/mode/value) of an existing slot
  matches the cloud entry being placed. Cloud is still authoritative
  for slot identity and shape; the firmware-side `enabled` bit wins
  for "will this fire?" because that's what the device actually
  checks at fire time.

### Why
Observed on S 809: cloud `/v1.0/devices/{id}/timers` returned
`status: 0` for a timer with `is_app_push: true`, but the device's
`time_task` DP carried `enabled=1` for the same schedule. The valve
fires from its local DP, not from cloud, so the cloud-only "OFF"
display was misleading. New logic preserves the device's enabled bit
when shapes match, so the registry reflects what will actually run.

### Trade-off
If a user toggles enabled in SmartLife and the device hasn't pulled
the change yet, the card lags behind cloud until the device echoes
a fresh `time_task` DP (typically seconds). Eventually consistent.

## [4.4.114] — 2026-05-05

Fixes the misleading Watering History graph (`cur_cap` flat-lining at
the last run's per-cycle total) by adding a dedicated lifetime card.

### Changed
- **`custom:irrigation-valves` strategy** now renders a
  `statistics-graph` "Lifetime water" tile per valve in addition to the
  existing per-cycle history graph. Driven by the `sum` statistic of
  the `cur_cap` TOTAL_INCREASING sensor (added in 4.4.112), so the
  lifetime total is correct across per-run resets. Default window 30
  days, daily buckets.
- **Renamed** the per-cycle line in "Watering History" from "Volume"
  to "Run volume" so it's no longer confused with lifetime total.

### Operational notes
- The lifetime curve only contains data from the 4.4.112 upgrade
  onwards — pre-existing history can't be retroactively classified.
- Device-reported volume is still a calibration estimate
  (flow_rate × open_seconds), not a real flow meter. Inflated readings
  (4,000+ L on a single short cycle) point at miscalibrated flow rate
  in SmartLife rather than an HA-side issue.

## [4.4.113] — 2026-05-05

Fixes the timer / schedule sync drift Simon reported (timer ON in
SmartLife, OFF in HA). Cloud is now treated as the authoritative state
on a continuous basis instead of only at HA boot.

### Changed
- **Event-driven cloud timer resync** in `Fdm5kwTimerRegistryEntity`
  (`entity_parser/fdm5kw/sensor.py`). Subscribes to the per-device
  `tuya_entry_update_<device_id>` dispatch signal — any DP push for the
  valve schedules a 3 s debounced cloud resync. Coalesces bursts
  triggered by user actions (timer edit echoes, schedule firings,
  switch flips). Wraps existing `reconcile_with_cloud` logic; no slot
  matching changes.
- **Sparse safety-net resync** every 5 minutes via
  `async_track_time_interval`. Catches cloud-only edits in SmartLife
  that produce no device-side DP traffic at all (e.g. toggling
  `enabled` without altering schedule).
- **Immediate resync after `xtend_tuya.fdm5kw_set_timer` and
  `_delete_timer`**. We know cloud changed; no need to wait for a
  debounce or interval tick.
- **Re-prime `DPCodeTimeTaskRegistryWrapper._last_applied_payload`**
  after every cloud reconciliation (new `prime_idempotency_guard`
  helper). Prevents a delayed device-side `time_task` echo from
  replaying a stale slot edit over the cloud-truth state.

### Operational notes
- API cost: 1 GET / valve / DP-burst (debounced) + 12 GETs / hour /
  valve safety-net. For the current 52-valve fleet, well under
  Tuya OpenAPI rate limits.
- Cloud-only "delete all timers" is still not propagated — the early
  return on empty cloud response in `_sync_cloud_timers` is preserved
  to avoid spurious clears on transient API failures. Track separately.

## [4.4.112] — 2026-05-04

Focused session on Simon's irrigation-card feedback (Mattermost DM,
2026-04-25 to 2026-04-30). Card UX rework, atomic DP writes for the
Single watering button, per-second polling so the watering graph
actually plots a curve, and a custom Lovelace strategy that
auto-generates the multi-valve dashboard.

### Added
- **Per-second active-run polling** for FDM5KW valves
  (`entity_parser/fdm5kw/active_run_poller.py`). While
  `device.status["switch"] == True` the poller GETs
  `/v1.0/devices/{id}/status` every 1 s, writes any changed DPs into
  `device.status`, and dispatches `multi_device_listener.update_device`
  so `cur_cap` / `cur_time` / etc. tick smoothly into the recorder.
  Idle interval is 5 s with no API traffic. Lifecycle is anchored to
  `Fdm5kwTimerRegistryEntity` (one per valve).
- **Lifetime water total** — `cur_cap` sensor now declares
  `state_class=TOTAL_INCREASING`, so HA's long-term statistics treat
  each per-cycle reset as a new accumulator window and compute a real
  lifetime sum. Statistics tile / utility_meter now usable for
  "all-time water through this valve."
- **Custom Lovelace dashboard strategy** `custom:irrigation-valves`
  (`frontend/src/irrigation-valves-strategy.ts`). Auto-discovers every
  FDM5KW valve via its `*_irrigation_timer_registry` sensor, looks up
  sibling entities by `device_id` + `translation_key` (so legacy
  S 809 entity-ids keep working), and generates an Overview view
  (tile per valve + battery levels) plus one detail view per valve
  matching the previous hand-maintained `valve-dashboard.yaml`.
  Replaces all of `valve-dashboard.yaml` with one YAML stanza:
  ```yaml
  strategy:
    type: custom:irrigation-valves
  ```
  Optional config: `overview_title`, `hours_to_show`.

### Changed
- **irrigation-control-card layout** (per Simon's screenshot annotation):
  - Single watering button moved into the Duration/Volume input row
    (saves vertical space, fills the empty area he flagged).
  - Manual ON button kept, full-width below the input row.
  - "Last start / Last end" lines removed — they duplicate the
    "Last Watering" entities panel.
- **`xtend_tuya.fdm5kw_start_watering` service** now writes
  `one_control` AND `switch=true` in a single command batch. The
  `one_control` DP alone has been observed to silently no-op on the
  device's current firmware (the DP value is accepted but the valve
  doesn't open). Bundling both writes matches what SmartLife sends.
  `fdm5kw_stop_watering` mirrors this: `one_control` idle + `switch=false`.

### Fixed
- **"Manual ON jumps into the timer/progress view"** — the card now
  tracks an `_initiatedHere` flag and only renders progress when the
  active cycle was started via the Single watering button. Manual ON
  toggles the valve without taking over the controls. Flag is reset
  on Stop / Manual OFF / page reload.
- **"Single watering does nothing"** — direct consequence of the
  service-side fix above; the button now actually starts a cycle.

### Operational notes
- Long-term statistics start fresh from the upgrade — pre-existing
  history can't be retroactively classified as `TOTAL_INCREASING`.
- The watering volume reported is still a device-side estimate
  (flow-rate calibration × open time), not a real flow meter. Lifetime
  totals are accurate proportionally to that calibration.
- The strategy looks up entities through HA's entity registry
  (`hass.entities.translation_key`), not entity-id pattern matching,
  so it survives the legacy S 809 vs descriptive S 810/S 812 naming
  split without rename.

[Unreleased]: https://github.com/raukaute/xtend_tuya/compare/v4.4.121...HEAD
[4.4.121]: https://github.com/raukaute/xtend_tuya/compare/v4.4.120...v4.4.121
[4.4.120]: https://github.com/raukaute/xtend_tuya/compare/v4.4.119...v4.4.120
[4.4.119]: https://github.com/raukaute/xtend_tuya/compare/v4.4.118...v4.4.119
[4.4.118]: https://github.com/raukaute/xtend_tuya/compare/v4.4.117...v4.4.118
[4.4.117]: https://github.com/raukaute/xtend_tuya/compare/v4.4.116...v4.4.117
[4.4.116]: https://github.com/raukaute/xtend_tuya/compare/v4.4.115...v4.4.116
[4.4.115]: https://github.com/raukaute/xtend_tuya/compare/v4.4.114...v4.4.115
[4.4.114]: https://github.com/raukaute/xtend_tuya/compare/v4.4.113...v4.4.114
[4.4.113]: https://github.com/raukaute/xtend_tuya/compare/v4.4.112...v4.4.113
[4.4.112]: https://github.com/raukaute/xtend_tuya/compare/v4.4.111...v4.4.112
