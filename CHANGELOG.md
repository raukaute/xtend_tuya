# Changelog

Notable changes to the raukaute fork of `xtend_tuya`. Newest at the top.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions match the integration `manifest.json` version field — bump that
when shipping anything user-visible so HACS picks the release up.

## [4.4.216] - 2026-07-15

### Added
- **QT-08W-T3 valve support, phase 1 — read sensors** (new valve type on the
  Mavronero farm, product `rjnqkjk1pct15ku2`, HM Olive/verbs 701-706). The T3
  is a different DP model from the QT-08W (indexed `_0` DPs, no
  `vbat_state`/`cur_cap`/`one_control`), so HA showed only a generic switch.
  Adds three sensors, all DP-presence-gated (zero effect on old valves):
  - **Battery level** — byte-packed in `sat_0` (byte3 & 0x7F); the T3 has no
    battery DP, the value is inside the status heartbeat. Matches SmartLife.
  - **Watering volume** — `flow_sta_0` bytes1-4 BE (live-cumulative during a
    run, last-run total when idle), with the same 9000 L glitch ceiling.
  - **Next watering** — `sat_0` bytes7-11 datetime.
  - On/off already works via the base Tuya integration (`switch_1`).
  Decoders validated against live captures (see
  `entity_parser/fdm5kw/test_t3_decode.py`). Timers (cloud-registry read +
  12-byte `time_task_0` write) are phase 2.

## [4.4.215] - 2026-07-14

### Added
- **Per-valve "Resync from cloud" button on the timer card** (Simon request) —
  clears live orphan (zombie) timers the Tuya cloud no longer knows about but
  that still fire on the device. Read-first: GETs the cloud timer registry
  (draws the 26k/mo API-call pool, *not* the 10-controllable-device cap) and
  reconciles the HA slot registry against it. A live orphan = an *enabled* HA
  slot with no cloud entry (would water offline — the 969 04:20 case); it's
  cleared with a device write, 1 controllable-device unit. Disabled slots are
  left alone: `set_timer` never posts disabled timers to the cloud, so a
  user-disabled timer is indistinguishable from a disabled ghost by cloud
  state — dropping it would delete a real timer. User-triggered per valve, so
  it can't runaway the quota the way a periodic sweep would. New service
  `xtend_tuya.fdm5kw_resync_timers` returns reconcile counts; button reports
  "Cleared N zombies / All in sync". Orphan writes deferred (not failed) under
  quota lockout.

## [4.4.205] - 2026-06-10

### Fixed
- **Completed-calendar events no longer merge two runs when an end report
  was lost.** The recorder pairing matched each watering start with the
  first end event after it — if a cycle's end report never arrived (valve
  lost signal mid-run), the start was paired with the NEXT cycle's end,
  producing a single event with a wrong completion time (e.g. 06:00→10:45
  spanning two separate runs, passing the 6 h sanity cap). A start whose
  next recorder event is another start is now treated as an interrupted
  cycle and dropped; the genuine run keeps its own end. Also fixes the
  last-10 averages (l/min, per-cycle liters) that fed on the merged runs.
- **"Irrigation Planned" calendar icon shows again.** It was set to
  `mdi:water-pump-outline`, which does not exist in MDI, so the calendar
  rendered without an icon (the completed calendar's `mdi:water-check` is
  valid, hence the asymmetry). Now `mdi:water-pump`.

## [4.4.204] - 2026-06-10

### Fixed
- **Battery column no longer shifts one row up after the first state
  update.** 4.4.203's header row added a `.battery` cell that the
  incremental battery updater also matched, so every battery value moved
  into the row above it (and the header showed a percentage). The updater
  now targets data rows only.

## [4.4.203] - 2026-06-10

### Added
- **"ran" and "water" columns on the valve overview list.** Each row of the
  valve-matrix card now shows how long the valve was open (min) and how many
  liters flowed through within the visible history window (24 h by default),
  right next to the watering timeline. Runtime is summed from the same
  switch history that draws the bars; liters are summed from the volume
  sensor's history (positive increments, so per-cycle counter resets are
  handled). Valves without a flow meter show "–" for water; valves that
  never reported in the window (offline) show "–" for both.
- **Re-sync button integrated into the valve-count row** of the matrix card
  (was a standalone card at the top of the overview; the standalone element
  stays registered so dashboards on an older saved config keep working).

## [4.4.202] - 2026-06-10

### Fixed
- **Device renames in Smart Life now propagate to Home Assistant.** The HA
  device-registry name was only ever set when a device was first created;
  the `nameUpdate` MQTT event from Tuya updated the in-memory device cache
  but never the registry, so renames (especially of offline valves, which
  get no other refresh) never showed up in HA. `MultiDeviceListener` now
  syncs the registry name whenever a device update carries a changed name —
  this covers the live MQTT rename event and any later status update, and
  a restart/reload also picks up renames done while HA was down. Renames
  made inside HA itself (`name_by_user`) keep display precedence and are
  not touched.

## [4.4.201] - 2026-06-09

### Fixed
- **Watering-mode sensor now labels single-waterings correctly (duration / volume / idle).**
  The `one_control` mode decoder used a stale map (`0=idle, 1=duration, 3=volume`)
  from a pre-4.4.183 capture. A live capture on valve 964 (triggering both a
  duration and a 5 L volume single-watering and reading device status) showed the
  status mirrors the command payload `[lead, value(4B BE), flag]`: **lead 0 =
  duration (value=seconds), lead 1 = volume (value=liters)** — same encoding as
  `time_task`'s mode byte. Decoder is now value-aware: zero value → idle (covers a
  truly idle valve and a just-finished run), else lead byte gives the mode. Fixes
  the old "S 806 Mode = Unknown" and duration runs mislabelling as idle. Verified
  against live status of 901/964/977/902/984/985.

## [4.4.200] - 2026-06-09

### Added
- **Timer card on the valve detail view now shows the "Home · Room" sub-line**
  under its name, matching the control card (Simon's request). Same source —
  the registry sensor's `valve_home` / `valve_room` attributes — so it helps
  locate the valve in SmartLife from the timer card too. Renders nothing until
  the location is known.

## [4.4.199] - 2026-06-09

### Fixed
- **Offline valves no longer show a trailing " Valve" in the detail card name.**
  When a valve is offline its live timer-registry is `unavailable`, so the
  control card's `valve_name` lookup returns null and it fell back to the valve
  *switch* entity's friendly name — which HA composes as `"<device> Valve"`
  (the switch's `translation_key` is `valve`). The card now strips a trailing
  `" Valve"` from that fallback, so e.g. `985 (Dry view middle)` reads as its
  device name instead of `985 (Dry view middle) Valve`. Online valves are
  unaffected (they read the clean `valve_name` from the live registry).

## [4.4.198] - 2026-06-09

### Fixed
- **Valve home/room now populates for every hub, not just the solar one.**
  The fdm5kw home/room map (`valve_home` / `valve_room` attributes) only built
  when a timer-registry entity spawned. Valves that dropped to the bare "Valve"
  entity never triggered it, so an entire hub's map went missing — only the
  solar account's ~64 valves ever got a home/room, simon-account valves none.
  The builder is now kicked off per hub at the end of `async_setup_entry`,
  decoupled from entity spawn, so each hub walks its own linked SmartLife
  account's homes and unions them into the shared map (verified 90/90 valves,
  e.g. `985 → Mavronero Solar Valve · Big Farm`, `901 → Mavronero · Olive East`).
  Cross-enrolled valves (in one Cloud project but bound to another account's
  home) are covered by whichever hub owns that account's home, since the map is
  keyed globally by `device_id`.
- `_build_map` now tolerates both `{"rooms": [...]}` and bare-list shapes from
  `/v1.0/homes/{id}/rooms`.

## [Unreleased]

Alarm-panel platform still needs the py3.14 port: upstream `ALARM` is now
`dict[category, AlarmControlPanelEntityDescription]` (single, not a tuple) and
`TuyaAlarmEntity.__init__` takes `(device, device_manager, description,
definition)`. Needs the descriptor-merge to tolerate single values + the
constructor to pass a `TuyaAlarmControlPanelDefinition` (mirror the camera
fix). Deferred — alarm devices are non-irrigation and the platform error is
isolated (non-fatal).

## [4.4.170] — 2026-06-03

Overview battery monitoring (per Simon): the "Battery levels" card is now
"Battery & last seen" — each valve shows battery % plus last-changed (≈ last
cloud report), so a valve whose battery is dying is caught before it drops
off. Added a "Battery trend (all valves)" history-graph to spot declines
early. (Validated via Tuya online/offline logs that these solar valves stay
continuously connected when powered — they don't nap; offline = dead battery
or a real outage. Battery % is the early-warning signal.) Rebuilt cards;
regenerate static dashboards.

## [4.4.169] — 2026-06-03

Valve detail view (per Simon/Uli): removed the "Hourly water (past 7 days)"
statistics-graph card — redundant with the Watering History flow curve. The
**Watering History** footer now shows both the live **Flow rate** and
**Watered (cycle)** — `volume_sensor` (cur_cap) resets between runs, so it
reads as the running total for the active watering cycle. Rebuilt `cards/*.js`.
Static dashboards must be regenerated (strategy generate → lovelace save) to
pick this up.

## [4.4.168] — 2026-06-02

Ported the camera platform to the rewritten py3.14 built-in Tuya. Upstream
`TuyaCameraEntity.__init__` is now `(device, device_manager, description,
definition)`; the fork only passed `definition`, so every camera raised
`TypeError: ... missing 1 required positional argument: 'description'` (caught
since 4.4.163, so cameras silently dropped). Now passes an empty-key
`CameraEntityDescription(key="")` (matching upstream's CAMERAS entries; the
unique_id derives from device.id, not the key) followed by the definition.

## [4.4.167] — 2026-06-02

Dashboard: fixed the missing on/off control widget on valves that also exist
in the official Tuya integration (most of the second account's valves). Their
switch unique_id collides with the built-in Tuya entity, so HA renames the
xtend switch (e.g. `switch.east_02_902_switch_2`) — the strategy's
`endsWith("_valve")` match missed it and the control card rendered empty. The
discovery now matches the stable `translation_key === "valve"` first, falling
back to the `_valve` suffix for legacy entities. Rebuilt `cards/*.js`.

## [4.4.166] — 2026-06-02

Guarded `xt_get_default_definition` (`sensor.py`) so a DP with an incomplete
type model (an integer DP missing `min`, e.g. valve `countdown`/`delay_task`
on the rewritten py3.14 built-in Tuya) can't raise `KeyError: 'min'` and fail
the whole account entry. Same isolation pattern as the 4.4.163 camera fix:
the malformed DP loses its auto-generated generic sensor (cosmetic) and the
entry finishes loading. (Shipped earlier in a separate session.)

## [4.4.165] — 2026-06-02

Fixed multi-device OpenAPI hubs (e.g. Simon's prod: 100 devices — valves,
sockets, cameras) failing to set up with `asyncio.CancelledError` in
`on_loading_finalized`. The lock / camera / IR / energy-statistic
subscription probes ran an unbounded blocking OpenAPI call each; under load
(many devices over the Nabu Casa relay) one would hang long enough for HA to
cancel the whole setup task — taking the entry down. Hubs with no such
devices (the solar valve-only hub) were unaffected, which is why solar loaded
and simon did not. Each probe now runs through `_safe_subscription_test`:
bounded to 15s and best-effort (any error/timeout is swallowed, returning
"assume subscribed" so no spurious warning and setup always continues). A
genuine task cancellation still propagates (CancelledError is a
BaseException, not caught).

## [4.4.164] — 2026-06-02

Fixed the options/reconfigure flow crashing with `AttributeError: 'ConfigEntry'
object has no attribute 'runtime_data'` (`config_flow.py:316`). `runtime_data`
only exists while an entry is loaded, so clicking **Configure** on a hub in an
error / not-loaded state (or mid-removal) 500'd the flow — which is why
re-entered OpenAPI credentials never appeared to persist. Now guarded with
`getattr`, so the options flow opens regardless of entry state.

## [4.4.163] — 2026-06-01

Fixed a camera-entity crash taking down an entire account (Simon's prod:
`<redacted-account-email>` "Failed to set up", which also pulled all 34
valves offline).

Newer HA-Tuya requires a `description` arg on `TuyaCameraEntity.__init__`
(the camera platform moved to the description-based descriptor model, the
same upstream change behind the `alarm_control_panel` "object is not
iterable" and `fan` "non-matching include/exclude set VS dict" errors).
xtend's `camera.py` still calls the old signature → `TypeError:
TuyaCameraEntity.__init__() missing 1 required positional argument:
'description'`. Camera entities are built inside the `on_loading_finalized`
post-setup callback, so that exception propagated to `async_setup_entry`
and failed the whole config entry — every other device on the account
(valves, sensors) went unavailable with it.

- `camera.py`: wrap per-device camera-entity construction in `add_camera_devices`
  in try/except — log and skip a device that fails to build instead of
  letting it abort the entry. Cameras on affected accounts stay
  non-functional, but the account (and its valves) loads.

Not fixed here: the underlying camera/alarm/fan platforms still need
porting to the upstream description-based descriptor model. Tracked
separately.

## [4.4.162] — 2026-06-01

Fixed valves with no resolved on/off switch rendering "1" in the
"Watering History (all valves)" overview graph (Simon's report).

The strategy detects the valve switch by entity-id string match
(`switch.*` ending `_valve`) because xtend's switch platform sets no
translation_key. When a valve has no matching switch entity (e.g.
unavailable / limited-DP valve), the overview graph fell back to
`v.registry_entity` — whose state is the active-timer COUNT, so the bar
showed "1" instead of On/Off.

- `irrigation-valves-strategy.ts`: the all-valves watering-history graph
  now filters to valves with a resolved switch and plots only that; no
  registry-sensor fallback (a timer count is meaningless in a watering
  graph). Such valves still appear as tiles + their own detail view. The
  tile/nav fallback is unchanged (it just needs a navigable entity).

Note: a valve showing "1" here also means its switch entity isn't
resolving — track separately whether that valve is unavailable or just
named off-pattern.

## [4.4.161] — 2026-06-01

Fixed "Timeout waiting for strategy element
`ll-strategy-dashboard-irrigation-valves` to be registered" on modern
browsers — the dashboard strategy never loaded.

4.4.159 registered the strategy bundle with
`add_extra_js_url(..., es5=True)`, believing it forced a blocking
classic `<script>`. It does no such thing: `es5=True` routes the URL to
HA's **ES5-legacy-only** bucket, served solely to browsers that can't
run ES modules. Modern browsers (Chrome/Firefox/Safari) load only the
module bucket, so they never fetched `irrigation-valves-strategy.js` at
all → the custom element was never defined → the panel timed out
waiting for it. .159 didn't fix the prior flaky race, it broke the
strategy outright on every current browser.

- `frontend.py`: register every bundle as a module URL (drop the
  `es5=True` special-case). The IIFE strategy runs fine inside a
  `type=module` script — it executes and defines the element. The
  `?v=<mtime>` cache-bust still keeps warm loads instant.

## [4.4.160] — 2026-06-01

Fixed entry setup crashing on installs where official Tuya is slow to
set up (many devices) — the sharing-account override raced ahead and
read Tuya's `runtime_data` before it was ready.

`util.get_config_entry_runtime_data` accessed `runtime_data.manager` /
`runtime_data.listener` unguarded in the `entry.runtime_data is not
None` branch. Mid-setup, official Tuya's `runtime_data` is a bare
`DeviceListener` lacking those attributes, raising
`AttributeError: 'DeviceListener' object has no attribute 'listener'`
and killing the whole xtend_tuya entry setup. Staging never hit it
(few devices → Tuya sets up fast → no race).

- `util.py`: guard every `runtime_data` attribute access with
  `hasattr`, mirroring the existing "old way" branch, so a not-ready
  shape yields `None` instead of crashing.
- `tuya_sharing/util.py`: when the overriden Tuya entry exists but its
  runtime_data isn't ready *and* the entry is still in a
  not-loaded/in-progress/retry state, raise `ConfigEntryNotReady` so HA
  retries xtend_tuya once Tuya has finished — instead of silently
  falling back to a degraded standalone setup. A genuinely
  loaded-but-unsupported shape still returns `None` (no retry loop).

## [4.4.153] — 2026-05-27

Overview tile clicks routed to the home dashboard instead of the
per-valve detail view.

`irrigation-valves-strategy.ts` emitted
`navigation_path: \`/${view_path}\``. The leading slash makes the
path absolute, so HA jumps off the current Solar Valves dashboard and
opens whichever dashboard owns `/<view_path>` — usually nothing,
which falls back to the default Overview dashboard. Dropped the slash
so navigation stays within this dashboard.

## [4.4.152] — 2026-05-27

`frontend.py`: cache the Lovelace card bundles in the browser to fix
the intermittent "Timeout waiting for strategy element
`ll-strategy-dashboard-irrigation-valves` to be registered" error.

Root cause: HA's frontend injects our card JS via an inline `import()`
in the index `<script>` block. That import is async; the dashboard
panel only waits ~5 s for the custom-element registration. A cold
fetch over the Nabu Casa relay sometimes exceeds that budget, leaving
the user with the timeout banner until refresh.

Switched the static-paths registration to `cache_headers=True` so the
browser caches the JS aggressively (one-day max-age). The URL still
carries `?v=<file-mtime>`, so a HACS update bumps the cache-bust query
and the next fetch is the fresh file — but every repeat load between
releases is now served from disk cache.

Also moved the cards-dir `scandir` off the event loop via
`async_add_executor_job` to silence the loop-detector warning logged
by `homeassistant.util.loop`.

## [4.4.151] — 2026-05-27

Overview-page hotfix: every card was rendering squeezed into the left
third of the screen.

`buildOverviewView` puts the tiles grid, "Watering History (all
valves)", "Flow rate (all valves)" and "Battery levels" cards inside
sections with `column_span: 3`. The section spans the full width, but
HA's sections-view defaults a child card's `grid_columns` to 4 (≈1/3
width), so the cards stayed narrow.

Added `layout_options: { grid_columns: 12, grid_rows: "auto" }` to
each of those cards so they fill their section. Per-valve detail view
already had this — only the overview was affected.

Tiles also got `grid_columns: 3, grid_rows: "auto"` so they tile 4-up
inside the inner 4-column grid instead of stacking one-per-row.

## [4.4.150] — 2026-05-27

Dashboard + calendar audit fixes (live-traced on Simon's fleet).

**Last Watering card was missing Start/End/Mode on every valve** —
`entity_parser/fdm5kw/sensor.py` declared the START_TIME / CLOSE_TIME /
ONE_CONTROL_MODE / TIME_TASK_* sensors without a `translation_key`, so
the strategy's `TRANSLATION_KEY_TO_FIELD` map couldn't resolve them.
Added `translation_key="start_time"` / `"close_time"` /
`"watering_mode"` / `"watering_value"` / `"timer_slot"` /
`"timer_schedule"` / `"irrigation_timer_registry"`.

Same root cause **zeroed the Completed calendar** (its
`_iter_fdm5kw_devices` couldn't resolve sibling entities → guard
short-circuited every device). Fixed alongside.

Existing entities created before this release have null
`translation_key` in the entity registry (HA writes it only at first
registration), so both the dashboard strategy and the calendar now
**fall back to entity-id suffix matching**
(`_last_watering_start`, `_last_watering_end`, `_watering_volume`, …)
for legacy installs.

**"Configuration error" badge on every overview tile** — strategy
emitted `features: [{ type: "tile-tap-area" }]` which isn't a valid
HA tile feature. Dropped the `features` block entirely; the existing
`tap_action` already handles navigation.

**21 valves rendering as 32-char hex UUIDs** instead of their
friendly names — happens when the registry sensor is `unavailable`
and HA strips the `valve_name` attribute. Both the strategy and the
calendar now fall back to `hass.devices[id].name_by_user || .name`
before the raw Tuya/HA UUID.

**Lifetime water was reading the wrong field** — `_lifetime_liters`
returned `state.state`, but `cur_cap` resets to 0 each cycle, so the
live state is per-cycle accumulator, not lifetime. Switched to a
`recorder.statistics_during_period` query for the long-term `sum`
stat (cur_cap's `state_class=TOTAL_INCREASING` means HA already
treats each per-cycle reset as a new accumulator window — we just
weren't reading the right place).

**Naive-datetime crash latent in `_query_recent_runs`** — sensors
like `sensor.s_809_last_watering_start` emit ISO strings without a
TZ (`"2026-05-27 10:00:00"`); comparing them with the tz-aware
window bounds would raise `TypeError`. `_parse_dt` now attaches the
local TZ when the parsed value is naive.

No new cloud-API traffic; all changes are read-side.

## [4.4.149] — 2026-05-27

Hotfix: integration fails to load on current HA core.

HA core renamed `homeassistant.components.tuya.fan.TUYA_SUPPORT_TYPE`
→ `FANS` (matching the EVENTS / HUMIDIFIERS / LIGHTS naming used by
sibling platforms). The xtend_tuya import in
`ha_tuya_integration/tuya_integration_imports_no_cc.py:43` was still
using the old name, raising

    ImportError: cannot import name 'TUYA_SUPPORT_TYPE'
    from 'homeassistant.components.tuya.fan'

at integration setup. Cascade effect: integration never loaded → no
entities → strategy element `ll-strategy-dashboard-irrigation-valves`
never registered → Solar Valves dashboard timed out trying to find it.

Fix: try the new `FANS` import first, fall back to `TUYA_SUPPORT_TYPE`
for older HA installs.

## [4.4.148] — 2026-05-27

Cloud-quota circuit breaker for fdm5kw timer writes.

Once the Tuya OpenAPI returns `60001001` ("controllable device pool
quota insufficient"), `entity_parser/fdm5kw/timer_service.py` engages a
6-hour module-level lockout: subsequent `_post_cloud_timer` and
`_delete_cloud_timer_by_match` calls short-circuit at entry with a
warning log, instead of burning calls that would all fail with the
same code. The on-device DP write path is unaffected, so timers keep
firing locally.

The lockout is account-wide (not per-device) because the Tuya quota
itself is account-wide. Resets on HA restart, or on demand via the new
`xtend_tuya.fdm5kw_clear_quota_lockout` service — call it after
bumping the IoT-Core plan or freeing devices so the next mutation
retries the cloud write.

## [4.4.147] — 2026-05-27

Calendar Phase 4 partial + cloud-quota UX.

Phase 4 follow-ups that don't need Simon's validation:

- `IrrigationCompletedCalendar` now emits an "in-progress" event when a
  device has a `start_time` without a matching `end_time` — title
  `{valve} — running (X m, Y l so far)`, end estimated from the
  last-10 averages (`avg_cycle / avg_lpm`). Lets Simon spot a stuck or
  long-running valve in Google Cal without waiting for the close DP.
- `IrrigationPlannedCalendar` now estimates duration for `mode=volume`
  timer slots from the historical avg flow (`target_l / avg_lpm * 60`).
  Previously volume-mode slots rendered as zero-length markers. The
  description notes the target liters so Simon's team can tell the
  modes apart.
- `_query_recent_runs`: dedupe repeated identical start/end timestamps
  (DP republish would otherwise count the same cycle twice in
  averages), and surface orphan starts as open runs when callers ask.
- Cycle expansion (`cyc_num > 1` sub-events) deferred: the `time_task`
  DP layout doesn't carry the cycle count, only mode/value/hour/
  minute/days/enabled. Would need a separate DP discovery pass on the
  live device to wire up.

Cloud-quota UX (Tuya error `60001001`):

- Define `TUYA_ERR_DEVICE_POOL_QUOTA = 60001001` + actionable message
  in `entity_parser/fdm5kw/const.py` (empirically validated 2026-05-13,
  not in Tuya's public docs).
- POST/GET/DELETE response paths in `entity_parser/fdm5kw/timer_service.py`
  inspect the response code; when it's the quota error, log a warning
  and raise a persistent notification ("Tuya quota exceeded") so the
  user sees *why* SmartLife/cloud sync stopped working. The on-device
  DP write still succeeded, so timers fire locally regardless.

Single-valve dashboard YAML:

- New `frontend/dashboards/single-valve-dashboard.yaml`. Mirrors the
  current strategy's per-valve detail view exactly (same 5-row layout,
  same cards), but as a vanilla editable Lovelace dashboard. Simon
  drags widgets in HA's visual editor; we mirror the resulting layout
  back into `irrigation-valves-strategy.ts` so every auto-built detail
  view inherits the changes. Defaults target S 810 (Verbs line North
  fence, `bf7d773582eedd85b8tyqv`).

## [4.4.146] — 2026-05-12

Phase 3 of the irrigation calendar: new ICS export endpoint at
`/api/xtend_tuya/calendar/{entity_id}.ics`. Returns a standards-
compliant iCalendar 2.0 feed for any xtend_tuya calendar entity, so
the planned and completed calendars can be subscribed in Google
Calendar via "Other calendars → From URL".

Google Cal can't send Authorization headers on its periodic polls,
so the endpoint also accepts `?token=<long_lived_bearer>` as a query
parameter; tokens are validated through `hass.auth.async_validate_
access_token` (same path as a header bearer). Window is configurable
via `?past_days=` and `?future_days=` (defaults 30 / 30); response is
cached server-side for 5 minutes.

`icalendar>=5.0.0` added to manifest requirements; HA usually ships
it transitively via the caldav integration but we declare it
explicitly so a stripped-down install still works.

## [4.4.145] — 2026-05-12

Phase 2 of the irrigation calendar: new `calendar.irrigation_completed`
entity. Sources historic watering cycles from the recorder by pairing
`start_time` and `end_time` state changes per device and reading the
matching `watering_volume` peak as that run's total liters. Window is
capped at 90 days to keep the recorder query bounded under Google Cal
pulls.

Both Planned and Completed calendars now display real averages:
description carries `Last 10 waterings (averages): water per minute,
per cycle`, and the Planned title's `l/min` slot — previously the
`?` placeholder — uses the historical average. Per-device average
results are cached for 30 s so the two calendars share a single
recorder hit per render pass.

## [4.4.144] — 2026-05-12

Phase 1 of the irrigation calendar (Trello aag9aw4k): new
`calendar.irrigation_planned` entity merges every enabled timer slot
across every fdm5kw valve under any xtend_tuya config entry into a
single calendar. Each slot expands to its weekly recurrence inside
the window HA queries. Title format follows Simon's spec:
`{valve} - {duration} m | {l/min} l | {total} l` (l/min placeholder
until Phase 2 lands the recorder-based averages).

Sibling watering_volume sensor is now resolved through device_registry
and entity_registry by translation_key, so the lifetime total no longer
depends on friendly-name heuristics.

Phase 2 (completed calendar) and Phase 3 (ICS export for Google Cal)
land in follow-up releases per `.claude/plans/irrigation-calendar.md`.

## [4.4.143] — 2026-05-12

Detail-view layout: split the control / other-settings / timers row
into three sections instead of one so HA's sections grid distributes
them across the 3 layout columns (one section = one column).
Previously all three landed in a single section and stacked vertically,
leaving the right two columns empty. Same fix for the last-watering +
lifetime row.

Overview: add a combined "Watering History (all valves)" and
"Flow rate (all valves)" history-graph, plus widen the tile grid to
4 columns and put the battery list in its own full-row section. The
history-graph cards' built-in `>` arrow opens HA's date-range picker,
so the overview now has the same range filter as the per-valve detail
view.

## [4.4.142] — 2026-05-12

Set `column_span: 3` on the Watering History and Hourly water
sections. HA's sections view treats each section as one column wide
regardless of `grid_columns` on the cards inside; column_span lifts
that section to span all 3 layout columns, finally giving the flow
graphs full-row width. v4.4.140 / v4.4.141 tried to fix this from the
card side, which was the wrong layer.

## [4.4.141] — 2026-05-12

Move the Watering History and Hourly water cards into their own
sections so the sections-grid layout (`max_columns: 3`) doesn't
sandwich them into 1/3 viewport. v4.4.140 set `grid_columns: 12` but
that only stretched the card to fill its parent section; HA's sections
view still gave each section 1/3 of the row when three sections fit
side-by-side. Each big graph now occupies its own full-width section.

## [4.4.140] — 2026-05-12

Widen "Watering History" and "Hourly water (past 7 days)" cards in the
per-valve view from 1/3 to full row (`grid_columns: 12`). The 10 s
flow samples and 168 hourly buckets were unreadable at 1/3 width.

## [4.4.139] — 2026-05-12

Two fixes on the new flow_rate sensor:

- **Unit**: hard-code `L/min` via a property override. Base
  `XTSensorEntity` was inheriting the `cur_cap` DP's Chinese unit
  (`升 (L)`) from the device data-model. Also force
  `device_class=None` to stop SensorDeviceClass.WATER from injecting a
  volume unit.
- **`ignore_other_dp_code_handler=True`** on the flow-rate descriptor
  so the upstream `cur_cap` `watering_volume` entity still registers.
  Without it the two descriptors fought over dpcode=`cur_cap`,
  flow_rate won, and the Last Watering card showed "Volume
  Unavailable" because watering_volume never spawned.

## [4.4.138] — 2026-05-12

Add an "Hourly water (past 7 days)" statistics-graph card to the
per-valve view in the dashboard strategy. Uses the `change` long-term
statistic over hourly buckets on `cur_cap`, which HA aggregates from
recorder state history regardless of whether the new live flow_rate
sensor existed at the time — so historic runs render immediately
after this upgrade. Complements the forward-only `Watering History`
card by giving Simon's team a "how much water came out, hour by hour"
view that goes back as far as the recorder retention allows.

## [4.4.137] — 2026-05-12

Two corrections to the v4.4.136 watering-flow sensor:

- **Differential algorithm**: flow_rate is now
  `(cur_cap_now − cur_cap_prev) × 60 / delta_seconds` between 10 s
  samples, not `cur_cap / total_elapsed`. The previous "average since
  start" smoothed out real-world variation; the differential reflects
  actual flow dips and surges during a run.
- **Hardware-fact correction**: v4.4.136 changelog claimed FDM5KW has
  no flow meter and `cur_cap` was firmware-estimated. Wrong. The
  device is the QOTO QT-08W (private-labeled as Moes / Girier), which
  contains a real Hall-effect impeller flowmeter (2–25 L/min). So
  `cur_cap` is a true measurement and the differential flow_rate
  captures genuine flow variations, not a plateau.

Caveat: below 2 L/min the impeller doesn't tick, so `cur_cap` stalls
and the derived rate reads 0 — hardware limit, mainly relevant for
drip-irrigation use cases.

## [4.4.136] — 2026-05-12

Add derived `Watering flow rate` sensor (l/min) per valve and wire the
dashboard strategy's "Watering History" card to use it. Per Simon's
2026-05-12 spec the area under the resulting graph equals the total
liters of the run.

- The sensor computes `cur_cap × 60 / elapsed-since-start_time` while
  `run_task_sta == 1`, otherwise reports 0.0.
- A 10 s in-process timer re-writes the entity state during a run so
  the recorder gets dense rows; computation reads only `device.status`
  (already populated by MQTT push) — no Tuya API calls.
- FDM5KW has no flow meter; the device's own `cur_cap` is firmware-
  estimated from a calibrated flow constant. The derived sensor will
  therefore plateau at that constant during a run. Mathematically
  correct (∫ flow dt = liters) and matches the graph shape Simon
  asked for; "true" instantaneous flow would need physical metering.
- Strategy falls back to the prior volume-sensor on installs that
  haven't picked up the new entity yet.

## [4.4.135] — 2026-05-12

HA timer disable now removes the cloud entry instead of POSTing a new
one with `enabled=False`. Tuya's OpenAPI has no per-timer
enable/disable toggle (verified 2026-05-12: `PUT
/timers/groups/{gid}/status` returns `1108 uri path invalid`; `PUT`
on the group body succeeds but always resets `status` to 1). The
device DP still carries the disabled bit for offline execution; in
SmartLife the entry disappears from the schedule tab when disabled
and reappears on re-enable. SL parity (greyed-out toggle visible) is
not possible via the OpenAPI surface.

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
