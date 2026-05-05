# Changelog

Notable changes to the raukaute fork of `xtend_tuya`. Newest at the top.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions match the integration `manifest.json` version field — bump that
when shipping anything user-visible so HACS picks the release up.

## [Unreleased]

_Nothing yet._

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

[Unreleased]: https://github.com/raukaute/xtend_tuya/compare/v4.4.113...HEAD
[4.4.113]: https://github.com/raukaute/xtend_tuya/compare/v4.4.112...v4.4.113
[4.4.112]: https://github.com/raukaute/xtend_tuya/compare/v4.4.111...v4.4.112
