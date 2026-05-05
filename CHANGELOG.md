# Changelog

Notable changes to the raukaute fork of `xtend_tuya`. Newest at the top.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions match the integration `manifest.json` version field — bump that
when shipping anything user-visible so HACS picks the release up.

## [Unreleased]

_Nothing yet._

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

[Unreleased]: https://github.com/raukaute/xtend_tuya/compare/v4.4.112...HEAD
[4.4.112]: https://github.com/raukaute/xtend_tuya/compare/v4.4.111...v4.4.112
