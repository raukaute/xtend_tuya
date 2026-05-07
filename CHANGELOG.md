# Changelog

Notable changes to the raukaute fork of `xtend_tuya`. Newest at the top.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions match the integration `manifest.json` version field — bump that
when shipping anything user-visible so HACS picks the release up.

## [Unreleased]

_Nothing yet._

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

[Unreleased]: https://github.com/raukaute/xtend_tuya/compare/v4.4.118...HEAD
[4.4.118]: https://github.com/raukaute/xtend_tuya/compare/v4.4.117...v4.4.118
[4.4.117]: https://github.com/raukaute/xtend_tuya/compare/v4.4.116...v4.4.117
[4.4.116]: https://github.com/raukaute/xtend_tuya/compare/v4.4.115...v4.4.116
[4.4.115]: https://github.com/raukaute/xtend_tuya/compare/v4.4.114...v4.4.115
[4.4.114]: https://github.com/raukaute/xtend_tuya/compare/v4.4.113...v4.4.114
[4.4.113]: https://github.com/raukaute/xtend_tuya/compare/v4.4.112...v4.4.113
[4.4.112]: https://github.com/raukaute/xtend_tuya/compare/v4.4.111...v4.4.112
