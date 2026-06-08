/**
 * Custom Lovelace dashboard strategy for FDM5KW irrigation valves.
 *
 * Drop-in replacement for the hand-maintained valve-dashboard.yaml. Picks
 * up every FDM5KW valve currently registered in HA and generates:
 *
 *   - View 0: an "Overview" with one tile per valve (status, battery,
 *     last watering) that navigates to the valve's detail view on tap.
 *   - View 1..N: per-valve detail view replicating the existing
 *     valve-dashboard.yaml structure (irrigation-control-card,
 *     Other settings, irrigation-timer-card, history graphs, last
 *     watering panel, battery tile + history).
 *
 * Usage in a Lovelace YAML dashboard:
 *
 *     strategy:
 *       type: custom:irrigation-valves
 *
 * That's it — the dashboard is fully auto-generated. New valves added to
 * HA appear after a reload; renamed valves pick up the new SmartLife
 * custom name automatically (the registry sensor exposes `valve_name`).
 *
 * Discovery anchor: every FDM5KW valve has exactly one
 * `sensor.<slug>_irrigation_timer_registry` entity with `device_id` and
 * `valve_name` attributes. We use that as the unique per-valve marker
 * and pull all sibling entities from the entity registry filtered by the
 * same device_id, mapping them by `translation_key` so we don't depend
 * on entity-id naming conventions (the older S 809 valve has legacy ids
 * like `sensor.s_809` / `sensor.s_809_2` that don't fit the descriptive
 * pattern used for newer valves).
 */

interface HassState {
  state: string;
  attributes: Record<string, unknown>;
}

interface HassEntityRegistryEntry {
  entity_id: string;
  device_id: string | null;
  platform: string;
  translation_key?: string | null;
}

interface HassDeviceRegistryEntry {
  id: string;
  name: string | null;
  name_by_user: string | null;
}

interface HomeAssistantLike {
  states: Record<string, HassState>;
  entities: Record<string, HassEntityRegistryEntry>;
  devices: Record<string, HassDeviceRegistryEntry>;
}

interface StrategyConfig {
  type: string;
  /** Optional override for the overview view's title. */
  overview_title?: string;
  /** Hours of history to render in the watering / battery graphs. */
  hours_to_show?: number;
}

interface DashboardView {
  title: string;
  path?: string;
  type?: string;
  max_columns?: number;
  sections?: unknown[];
  cards?: unknown[];
}

interface DashboardConfig {
  title: string;
  views: DashboardView[];
}

interface ValveEntities {
  device_id: string;
  registry_entity: string;
  valve_name: string;
  factory_name: string;
  view_path: string;
  switch?: string;
  duration?: string;
  volume_sensor?: string;
  flow_rate_sensor?: string;
  start_time_sensor?: string;
  end_time_sensor?: string;
  mode_sensor?: string;
  value_sensor?: string;
  battery_level?: string;
  sleep_mode?: string;
  rain_snow_delay?: string;
}

const REGISTRY_TRANSLATION_KEY_SUFFIX = "irrigation_timer_registry";
// v4.4.111 baseline names the registry entity sensor.<slug>_time_task_registry.
// Keep matching it so the dashboard discovers valves on the reverted code.
const REGISTRY_LEGACY_SUFFIX = "_time_task_registry";

const TRANSLATION_KEY_TO_FIELD: Record<string, keyof ValveEntities> = {
  // Sensors / numbers exposed by the integration (translation_key →
  // field on ValveEntities). Anything not in this map is ignored.
  start_time: "start_time_sensor",
  close_time: "end_time_sensor",
  // v4.4.111 baseline uses `end_time` for the CLOSE_TIME sensor.
  end_time: "end_time_sensor",
  watering_mode: "mode_sensor",
  watering_value: "value_sensor",
  watering_volume: "volume_sensor",
  watering_flow_rate: "flow_rate_sensor",
  battery_level: "battery_level",
  watering_duration: "duration",
  rain_snow_delay: "rain_snow_delay",
};

// Existing entities created before 4.4.150 have null `translation_key`
// in the entity registry (HA only writes translation_key on first
// registration). The strategy must fall back to entity-id suffix
// matching for those installs. Suffix patterns are checked AFTER the
// translation_key map so newly-registered entities take precedence.
// Order matters: longer / more specific suffixes first.
const ENTITY_ID_SUFFIX_TO_FIELD: Array<[RegExp, keyof ValveEntities]> = [
  [/_last_watering_start$/, "start_time_sensor"],
  [/_last_watering_end$/, "end_time_sensor"],
  [/_watering_flow_rate$/, "flow_rate_sensor"],
  [/_watering_value$/, "value_sensor"],
  [/_watering_volume$/, "volume_sensor"],
  [/_watering_duration$/, "duration"],
  [/_watering_mode$/, "mode_sensor"],
  [/_rain_snow_delay$/, "rain_snow_delay"],
  [/_battery_level$/, "battery_level"],
];

class IrrigationValvesStrategy extends HTMLElement {
  static async generate(
    config: StrategyConfig,
    hass: HomeAssistantLike
  ): Promise<DashboardConfig> {
    const valves = discoverValves(hass);
    const hours = config.hours_to_show ?? 24;
    const overviewTitle = config.overview_title ?? "Valves";

    if (valves.length === 0) {
      return {
        title: "Solar Valves",
        views: [emptyOverviewView(overviewTitle)],
      };
    }

    const views: DashboardView[] = [
      buildOverviewView(overviewTitle, valves, hours),
      ...valves.map((v) => buildValveView(v, hours)),
    ];

    return {
      title: "Solar Valves",
      views,
    };
  }
}

/* ------------------------------------------------------------------ *
 * Discovery                                                           *
 * ------------------------------------------------------------------ */

function discoverValves(hass: HomeAssistantLike): ValveEntities[] {
  // Find every registry entity. Prefer the entity registry's
  // translation_key when available (stable), and fall back to entity_id
  // suffix matching for installs predating that field.
  const registryIds = new Set<string>();
  for (const e of Object.values(hass.entities)) {
    if (e.translation_key === REGISTRY_TRANSLATION_KEY_SUFFIX) {
      registryIds.add(e.entity_id);
    }
  }
  for (const id of Object.keys(hass.states)) {
    if (
      id.startsWith("sensor.") &&
      (id.endsWith(REGISTRY_TRANSLATION_KEY_SUFFIX) ||
        id.endsWith(REGISTRY_LEGACY_SUFFIX))
    ) {
      registryIds.add(id);
    }
  }

  const valves: ValveEntities[] = [];
  for (const regId of registryIds) {
    const regState = hass.states[regId];
    const regEntry = hass.entities[regId];
    if (!regState || !regEntry || !regEntry.device_id) continue;

    // HA's device-registry id is used to discover sibling entities;
    // Tuya's own device id (exposed by the registry sensor as the
    // `device_id` attribute) is what the fdm5kw timer services expect.
    // Manual YAML dashboards always passed the Tuya id; the strategy
    // previously fed the HA UUID, breaking set/delete service lookups.
    const tuyaDeviceId =
      (regState.attributes.device_id as string | undefined) ??
      regEntry.device_id;
    const valve = collectValveEntities(
      hass,
      regId,
      regEntry.device_id,
      tuyaDeviceId,
      regState
    );
    if (valve) valves.push(valve);
  }

  // Stable ordering for deterministic dashboard layout.
  valves.sort((a, b) => a.valve_name.localeCompare(b.valve_name));
  return valves;
}

function collectValveEntities(
  hass: HomeAssistantLike,
  registryEntityId: string,
  haDeviceId: string,
  tuyaDeviceId: string,
  registryState: HassState
): ValveEntities | null {
  // When the registry sensor is unavailable HA strips its custom
  // attributes (valve_name, valve_factory_name, device_id), so fall back
  // to the device-registry name before the raw Tuya id. Without this
  // every offline valve renders as a 32-char HA device UUID.
  const device = hass.devices[haDeviceId];
  const valve_name =
    (registryState.attributes.valve_name as string | undefined) ??
    (registryState.attributes.valve_factory_name as string | undefined) ??
    device?.name_by_user ??
    device?.name ??
    tuyaDeviceId;
  const factory_name =
    (registryState.attributes.valve_factory_name as string | undefined) ??
    device?.name ??
    valve_name;

  const view_path = makeViewPath(tuyaDeviceId, valve_name);

  const v: ValveEntities = {
    device_id: tuyaDeviceId,
    registry_entity: registryEntityId,
    valve_name,
    factory_name,
    view_path,
  };

  const setField = (field: keyof ValveEntities, entity_id: string) => {
    if (!v[field]) {
      (v as unknown as Record<string, string | undefined>)[field] = entity_id;
    }
  };

  for (const e of Object.values(hass.entities)) {
    if (e.device_id !== haDeviceId) continue;

    // Only reference entities that are actually loaded as states. When a hub
    // fails setup (e.g. expired Tuya auth) its entities stay in the registry
    // but drop out of hass.states; emitting those entity_ids made HA-core
    // tile / history-graph / entities cards throw "Cannot read properties of
    // undefined (reading 'friendly_name')", which errored the whole view.
    // Skipping them degrades a down valve gracefully (fewer cards) instead of
    // taking the dashboard down with it.
    if (!hass.states[e.entity_id]) continue;

    // The valve on/off switch carries translation_key "valve". Its
    // entity_id is normally <slug>_valve, but when the unique_id collides
    // with the official Tuya integration HA renames it (e.g.
    // <slug>_switch_2), so the old endsWith("_valve") check missed every
    // valve that also lives in the official integration — leaving the
    // control widget empty. Match the stable translation_key first, fall
    // back to the suffix for legacy entities with no translation_key.
    if (
      e.entity_id.startsWith("switch.") &&
      (e.translation_key === "valve" || e.entity_id.endsWith("_valve"))
    ) {
      if (!v.switch) v.switch = e.entity_id;
      continue;
    }
    if (
      e.entity_id.startsWith("switch.") &&
      e.entity_id.endsWith("_sleep_mode")
    ) {
      v.sleep_mode = e.entity_id;
      continue;
    }

    const tk = e.translation_key;
    if (tk) {
      const field = TRANSLATION_KEY_TO_FIELD[tk];
      if (field) {
        setField(field, e.entity_id);
        continue;
      }
    }

    // Legacy entities (created before 4.4.150) have no translation_key.
    // Match the entity-id suffix instead so the dashboard still finds
    // start/end/mode/etc. for older installs.
    for (const [pattern, field] of ENTITY_ID_SUFFIX_TO_FIELD) {
      if (pattern.test(e.entity_id)) {
        setField(field, e.entity_id);
        break;
      }
    }
  }

  return v;
}

function makeViewPath(deviceId: string, valveName: string): string {
  // Prefer a slug derived from the valve name (e.g. "S 809 (Green Carpet)"
  // → "s-809-green-carpet"), fall back to the device_id.
  const slug = valveName
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug || deviceId;
}

/* ------------------------------------------------------------------ *
 * View builders                                                       *
 * ------------------------------------------------------------------ */

function emptyOverviewView(title: string): DashboardView {
  return {
    title,
    path: "overview",
    cards: [
      {
        type: "markdown",
        content:
          "# No irrigation valves detected\n\n" +
          "This dashboard auto-discovers FDM5KW valves via the " +
          "`*_irrigation_timer_registry` sensor each device exposes. " +
          "Add a valve in Xtend Tuya and reload the dashboard.",
      },
    ],
  };
}

function buildOverviewView(
  title: string,
  valves: ValveEntities[],
  hours: number
): DashboardView {
  // Tiles take a fraction of the row inside the inner 4-column grid; the
  // grid card itself spans the full row via layout_options below.
  // navigation_path is relative to the current dashboard (no leading
  // slash) — an absolute "/s-810-…" would jump off this dashboard and
  // land on whichever dashboard owns the root URL (usually the default
  // "Overview"), instead of opening the per-valve view in this same
  // dashboard.
  const tiles = valves.map((v) => ({
    type: "tile",
    entity: v.switch ?? v.registry_entity,
    name: v.valve_name,
    icon: "mdi:water-pump",
    state_content: ["state", "last-changed"],
    tap_action: {
      action: "navigate",
      navigation_path: v.view_path,
    },
    layout_options: { grid_columns: 3, grid_rows: "auto" },
  }));

  const batteryEntities = valves
    .filter((v) => v.battery_level)
    .map((v) => ({
      entity: v.battery_level,
      name: v.valve_name,
      // Tap a valve's battery row to jump straight into its detail view
      // (Simon 2026-06-04 — every section should reach the detail board).
      tap_action: { action: "navigate", navigation_path: v.view_path },
    }));

  // Combined flow-rate history across every valve — the > arrow on the
  // card opens HA's built-in range/date selector so the overview gets
  // the same range filter as the per-valve detail view.
  const flowEntities = valves
    .filter((v) => v.flow_rate_sensor)
    .map((v) => ({ entity: v.flow_rate_sensor as string, name: v.valve_name }));

  // Single combined card: one fixed-height row per valve — name |
  // watering on/off timeline | battery % — so the watering-history and
  // battery columns line up exactly (Simon 2026-06-04). Two separate stock
  // cards (history-graph + entities) never align row-for-row because of
  // differing row heights, headers and axis offsets. The custom
  // irrigation-valve-matrix card draws both per row instead. Every valve
  // is included (switchless ones show an empty bar); rows navigate to the
  // valve's detail view on click.
  const matrixValves = valves.map((v) => ({
    name: v.valve_name,
    switch: v.switch,
    battery: v.battery_level,
    path: v.view_path,
  }));

  return {
    title,
    path: "overview",
    type: "sections",
    max_columns: 3,
    sections: [
      // Refresh button — re-runs the strategy (full page reload) so valve
      // renames/removals on the Tuya side show up without a manual browser
      // refresh (Simon 2026-06-04, mid-edit-session convenience).
      {
        type: "grid",
        column_span: 3,
        cards: [
          {
            type: "custom:irrigation-refresh-button",
            layout_options: { grid_columns: 3, grid_rows: "auto" },
          },
        ],
      },
      // Cards inside a `column_span: 3` section default to grid_columns=4
      // (≈1/3 width), so each card declares grid_columns=12 to fill the
      // full row. Without this every card on the overview renders
      // squeezed into the left third of the screen.
      {
        type: "grid",
        column_span: 3,
        cards: [
          {
            type: "grid",
            columns: 4,
            square: false,
            cards: tiles,
            layout_options: { grid_columns: 12, grid_rows: "auto" },
          },
        ],
      },
      {
        type: "grid",
        column_span: 3,
        cards: [
          {
            type: "custom:irrigation-valve-matrix",
            title: "Watering history & battery (all valves)",
            hours,
            valves: matrixValves,
            layout_options: { grid_columns: 12, grid_rows: "auto" },
          },
        ],
      },
      ...(flowEntities.length > 0
        ? [
            {
              type: "grid",
              column_span: 3,
              cards: [
                {
                  type: "history-graph",
                  title: "Flow rate (all valves)",
                  hours_to_show: hours,
                  entities: flowEntities,
                  layout_options: { grid_columns: 12, grid_rows: "auto" },
                },
              ],
            },
          ]
        : []),
      ...(batteryEntities.length > 0
        ? [
            {
              type: "grid",
              column_span: 3,
              cards: [
                {
                  // Trend view — spot declining batteries before they die.
                  type: "history-graph",
                  title: "Battery trend (all valves)",
                  hours_to_show: hours,
                  entities: batteryEntities.map((b) => ({
                    entity: b.entity,
                    name: b.name,
                  })),
                  layout_options: { grid_columns: 12, grid_rows: "auto" },
                },
              ],
            },
          ]
        : []),
    ],
  };
}

function buildValveView(v: ValveEntities, hours: number): DashboardView {
  // 3 fixed columns organised by domain (Simon 2026-06-04):
  //   LEFT   = Watering control & timers (switch + timer)
  //   MIDDLE = Watering history — Last Watering pinned to the TOP, then the
  //            flow-rate history graph below it
  //   RIGHT  = Battery monitoring (tile + history) + Other settings
  //            (sleep / rain-snow delay) at the bottom
  // Lifetime/Hourly water cards dropped — duplicate the Watering History
  // flow curve + footer totals.
  const leftCards: unknown[] = [];
  const middleCards: unknown[] = [];
  const rightCards: unknown[] = [];

  const control = buildControlCard(v);
  if (control) leftCards.push(control);
  leftCards.push(buildTimerCard(v));

  // Last Watering at the top of the history column, per Simon 2026-06-04.
  const last = buildLastWateringCard(v);
  if (last) middleCards.push(last);
  const watering = buildWateringHistoryCard(v, hours);
  if (watering) middleCards.push(watering);

  if (v.battery_level) {
    rightCards.push(buildBatteryTile(v));
    rightCards.push(buildBatteryHistoryCard(v, hours));
  }
  // Other settings (sleep / rain-snow delay) stays in the right column,
  // below battery, where it lived before — Simon 2026-06-04.
  const other = buildOtherSettingsCard(v);
  if (other) rightCards.push(other);

  const sections: unknown[] = [];
  if (leftCards.length) sections.push({ type: "grid", cards: leftCards });
  if (middleCards.length) sections.push({ type: "grid", cards: middleCards });
  if (rightCards.length) sections.push({ type: "grid", cards: rightCards });

  return {
    title: v.valve_name,
    path: v.view_path,
    type: "sections",
    max_columns: 3,
    sections,
  };
}

function buildControlCard(v: ValveEntities): unknown | null {
  if (!v.switch) return null;
  return {
    type: "custom:irrigation-control-card",
    valve: v.switch,
    duration: v.duration,
    volume_sensor: v.volume_sensor,
    start_time_sensor: v.start_time_sensor,
    end_time_sensor: v.end_time_sensor,
    mode_sensor: v.mode_sensor,
    value_sensor: v.value_sensor,
    registry_entity: v.registry_entity,
    device_id: v.device_id,
    layout_options: { grid_columns: 4, grid_rows: "auto" },
  };
}

function buildOtherSettingsCard(v: ValveEntities): unknown | null {
  const entities: unknown[] = [];
  if (v.sleep_mode) entities.push({ entity: v.sleep_mode, name: "Sleep Mode" });
  if (v.rain_snow_delay)
    entities.push({ entity: v.rain_snow_delay, name: "Rain/Snow Delay" });
  if (entities.length === 0) return null;
  return {
    type: "entities",
    title: "Other settings",
    show_header_toggle: false,
    entities,
    layout_options: { grid_columns: 4, grid_rows: "auto" },
  };
}

function buildTimerCard(v: ValveEntities): unknown {
  return {
    type: "custom:irrigation-timer-card",
    entity: v.registry_entity,
    device_id: v.device_id,
    layout_options: { grid_columns: 4, grid_rows: "auto" },
  };
}

function buildWateringHistoryCard(v: ValveEntities, hours: number): unknown | null {
  // Per-Simon spec (2026-05-12): graph should show flow rate while the
  // valve is open so the area under the curve equals total liters.
  // FDM5KW has no flow meter; the integration derives l/min from
  // cur_cap and elapsed-since-start, publishing fresh state every 10 s
  // while a run is active. Fall back to the volume sensor for legacy
  // installs that lack the derived flow entity.
  //
  // grid_columns=12: span the full row. The 10 s sample spacing is
  // narrow, and at 1/3-width on a 24h window the on-pulse rectangle
  // collapses to a single hairline; full-width gives Simon's team a
  // legible flow curve.
  // Footer (the history-graph legend) shows each entity's current value.
  // Per Simon/Uli 2026-06-03 it should carry BOTH the live flow rate and
  // the volume watered so far in the current cycle. `volume_sensor`
  // (cur_cap) resets to 0 between runs, so it reads as the running total
  // for the active cycle; on the graph it ramps up during a run,
  // complementing the flow curve.
  const entities: unknown[] = [];
  if (v.switch) entities.push({ entity: v.switch, name: "Valve" });
  if (v.flow_rate_sensor)
    entities.push({ entity: v.flow_rate_sensor, name: "Flow rate" });
  if (v.volume_sensor)
    entities.push({ entity: v.volume_sensor, name: "Watered (cycle)" });
  if (entities.length === 0) return null;
  return {
    type: "history-graph",
    title: "Watering History",
    hours_to_show: hours,
    entities,
    layout_options: { grid_columns: 4, grid_rows: "auto" },
  };
}

function buildHourlyVolumeCard(v: ValveEntities): unknown | null {
  // The `change` stat over hourly buckets gives liters per hour for
  // every hour we have recorder data — past runs included. This is the
  // best "historical flow rate" view available without backfilling
  // synthetic states; the live flow_rate sensor only covers data
  // recorded after its first appearance.
  // grid_columns=12 to match the Watering History card and give 168
  // hourly buckets visible breathing room.
  if (!v.volume_sensor) return null;
  return {
    type: "statistics-graph",
    title: "Hourly water (past 7 days)",
    entities: [v.volume_sensor],
    stat_types: ["change"],
    period: "hour",
    days_to_show: 7,
    chart_type: "bar",
    layout_options: { grid_columns: 4, grid_rows: "auto" },
  };
}

function buildLastWateringCard(v: ValveEntities): unknown | null {
  const entities: unknown[] = [];
  if (v.start_time_sensor)
    entities.push({ entity: v.start_time_sensor, name: "Start" });
  if (v.end_time_sensor)
    entities.push({ entity: v.end_time_sensor, name: "End" });
  if (v.volume_sensor)
    entities.push({ entity: v.volume_sensor, name: "Volume" });
  if (v.mode_sensor) entities.push({ entity: v.mode_sensor, name: "Mode" });
  if (entities.length === 0) return null;
  return {
    type: "entities",
    title: "Last Watering",
    show_header_toggle: false,
    entities,
    layout_options: { grid_columns: 4, grid_rows: "auto" },
  };
}

function buildBatteryTile(v: ValveEntities): unknown {
  // Inside HA sections layout the inner grid is 4 columns wide and only
  // `layout_options.grid_columns` is honoured — tile-level `grid_options`
  // gets dropped, which let the tile collapse to its 1-col default and
  // sit beside the history graph instead of stacking on top.
  return {
    type: "tile",
    layout_options: { grid_columns: 4, grid_rows: 3 },
    entity: v.battery_level,
    name: { type: "entity" },
    state_content: "state",
    vertical: false,
    features: [{ type: "bar-gauge" }, { type: "trend-graph" }],
    features_position: "bottom",
  };
}

function buildBatteryHistoryCard(v: ValveEntities, hours: number): unknown {
  return {
    type: "history-graph",
    title: "Battery History",
    entities: [{ entity: v.battery_level, name: "Battery" }],
    layout_options: { grid_columns: 4, grid_rows: "auto" },
    max_y_axis: 100,
    hours_to_show: hours,
  };
}

/* ------------------------------------------------------------------ *
 * Refresh button                                                      *
 * ------------------------------------------------------------------ */

// Minimal Lovelace custom card: a "Re-sync valves" button.
//
// The prod dashboard is saved as STATIC config (running the strategy live
// reliably hit HA's ~5 s "Timeout waiting for strategy element" over the
// Nabu Casa relay). Static means it does NOT auto-pick-up valve renames,
// additions or removals. This button re-runs the strategy on demand,
// saves the fresh output back over the dashboard config, then reloads —
// so Simon gets up-to-date valves (names included; valve_name is read
// fresh from each registry sensor) without ever loading the strategy in
// the dashboard's timeout-bound load path.
//
// Self-contained in this bundle (no Lit dep) so it ships and registers
// alongside the strategy IIFE.
class IrrigationRefreshButton extends HTMLElement {
  private _hass: HomeAssistantLike | null = null;
  private _btn: HTMLButtonElement | null = null;

  // Lovelace sets `.hass` on every card whenever state changes; keep the
  // latest so the click handler can regenerate against current entities.
  set hass(value: HomeAssistantLike) {
    this._hass = value;
  }

  setConfig(_config: unknown): void {
    if (this.childElementCount) return;
    const card = document.createElement("ha-card");
    const btn = document.createElement("button");
    this._btn = btn;
    btn.textContent = "↻ Re-sync valves";
    btn.style.cssText =
      "width:100%;padding:12px 16px;border:none;background:none;" +
      "color:var(--primary-color);font-size:1rem;font-weight:500;" +
      "cursor:pointer;border-radius:var(--ha-card-border-radius,12px);";
    btn.addEventListener("click", () => void this._resync());
    card.appendChild(btn);
    this.appendChild(card);
  }

  private async _resync(): Promise<void> {
    const hass = this._hass;
    const btn = this._btn;
    // No hass yet (card not bound) — fall back to a plain reload.
    if (!hass) {
      window.location.reload();
      return;
    }
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Syncing…";
    }
    try {
      // Same bundle defines the strategy class; regenerate against the
      // live registry, then persist over the current dashboard's config.
      const config = await IrrigationValvesStrategy.generate({ type: "" }, hass);
      const urlPath = window.location.pathname.split("/").filter(Boolean)[0];
      await (
        hass as unknown as {
          callWS: (msg: Record<string, unknown>) => Promise<unknown>;
        }
      ).callWS({
        type: "lovelace/config/save",
        url_path: urlPath,
        config,
      });
      window.location.reload();
    } catch (err) {
      if (btn) {
        btn.disabled = false;
        btn.textContent = "↻ Re-sync failed — retry";
      }
      // eslint-disable-next-line no-console
      console.error("xtend_tuya: valve re-sync failed", err);
    }
  }

  getCardSize(): number {
    return 1;
  }
}

if (!customElements.get("irrigation-refresh-button")) {
  customElements.define("irrigation-refresh-button", IrrigationRefreshButton);
}

/* ------------------------------------------------------------------ *
 * Valve matrix card                                                   *
 * ------------------------------------------------------------------ */

// One fixed-height row per valve — name | watering on/off timeline |
// battery % — so the watering-history and battery columns line up exactly
// (two separate stock cards never align row-for-row). Lives INSIDE the
// strategy bundle (vanilla, no Lit) rather than its own file: HACS does
// not reliably deploy a newly-added bundle file, but this existing bundle
// always updates, and add_extra_js_url already loads it.

interface MatrixRow {
  name: string;
  switch?: string;
  battery?: string;
  path?: string;
}
interface MatrixConfig {
  type: string;
  title?: string;
  hours?: number;
  valves: MatrixRow[];
}
interface MatrixSegment {
  left: number;
  width: number;
  // "on" = watering, "off" = reporting-but-closed. Unavailable / unknown
  // periods produce NO segment — the bare track shows through as a gap, so
  // a non-reporting valve reads as an empty lane (real-state signal Simon
  // relied on; a solid track for every valve hid offline valves).
  kind: "on" | "off";
}
interface HistoryPoint {
  s: string;
  lu: number;
}

const MATRIX_REFRESH_MS = 60_000;

function escapeHtml(s: string): string {
  return s.replace(
    /[&<>"]/g,
    (c) =>
      (({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }) as Record<
        string,
        string
      >)[c]
  );
}

class IrrigationValveMatrix extends HTMLElement {
  private _hass: HomeAssistantLike | null = null;
  private _config: MatrixConfig | null = null;
  private _segments: Record<string, MatrixSegment[]> = {};
  private _root: ShadowRoot;
  private _refreshHandle: number | null = null;
  private _fetching = false;

  constructor() {
    super();
    this._root = this.attachShadow({ mode: "open" });
  }

  setConfig(config: MatrixConfig): void {
    if (!config.valves || !Array.isArray(config.valves)) {
      throw new Error("irrigation-valve-matrix: `valves` list is required");
    }
    this._config = config;
    this._segments = {};
    this._render();
  }

  set hass(value: HomeAssistantLike) {
    this._hass = value;
    if (Object.keys(this._segments).length === 0) {
      void this._fetchHistory();
    } else {
      this._updateBattery();
    }
    this._updateCounts();
  }

  getCardSize(): number {
    return Math.max(3, Math.ceil((this._config?.valves?.length ?? 0) / 2));
  }

  connectedCallback(): void {
    this._refreshHandle = window.setInterval(
      () => void this._fetchHistory(),
      MATRIX_REFRESH_MS
    );
  }

  disconnectedCallback(): void {
    if (this._refreshHandle !== null) {
      window.clearInterval(this._refreshHandle);
      this._refreshHandle = null;
    }
  }

  private _hours(): number {
    return this._config?.hours ?? 24;
  }

  private async _fetchHistory(): Promise<void> {
    if (!this._hass || !this._config || this._fetching) return;
    const entities = this._config.valves
      .map((v) => v.switch)
      .filter((e): e is string => !!e);
    if (entities.length === 0) return;
    this._fetching = true;
    const now = Date.now();
    const start = now - this._hours() * 3_600_000;
    try {
      const raw = await (
        this._hass as unknown as {
          callWS: (msg: Record<string, unknown>) => Promise<
            Record<string, HistoryPoint[]>
          >;
        }
      ).callWS({
        type: "history/history_during_period",
        start_time: new Date(start).toISOString(),
        end_time: new Date(now).toISOString(),
        entity_ids: entities,
        minimal_response: true,
        no_attributes: true,
      });
      const next: Record<string, MatrixSegment[]> = {};
      for (const entity of entities) {
        next[entity] = this._buildSegments(raw[entity] ?? [], start, now);
      }
      this._segments = next;
      this._render();
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("irrigation-valve-matrix: history fetch failed", err);
    } finally {
      this._fetching = false;
    }
  }

  private _buildSegments(
    points: HistoryPoint[],
    startMs: number,
    endMs: number
  ): MatrixSegment[] {
    const span = endMs - startMs;
    if (span <= 0 || points.length === 0) return [];
    const segs: MatrixSegment[] = [];
    for (let i = 0; i < points.length; i++) {
      const p = points[i];
      const tStart = Math.max(p.lu * 1000, startMs);
      const tEnd =
        i + 1 < points.length ? Math.min(points[i + 1].lu * 1000, endMs) : endMs;
      if (tEnd <= tStart) continue;
      // Three visual states (Simon 2026-06-04):
      //   on  = watering        → amber (prominent)
      //   off = idle + reachable→ light blue (calm "online" tint)
      //   unavailable/unknown/no-data → NO segment → empty lane = gap
      // Idle is a LIGHT colour on purpose: a valve closed all day is a
      // light lane, not a heavy gray block, so amber watering marks pop and
      // an empty gap (offline) stays clearly distinct.
      const kind = p.s === "on" ? "on" : p.s === "off" ? "off" : null;
      if (!kind) continue;
      segs.push({
        left: (tStart - startMs) / span,
        width: (tEnd - tStart) / span,
        kind,
      });
    }
    return segs;
  }

  private _batteryText(entity?: string): string {
    if (!entity || !this._hass) return "—";
    const e = this._hass.states[entity];
    if (!e || e.state === "unavailable" || e.state === "unknown") {
      return "Unavailable";
    }
    const n = parseFloat(e.state);
    if (!Number.isFinite(n)) return e.state;
    const unit = (e.attributes?.unit_of_measurement as string) ?? "%";
    return `${Math.round(n)}${unit}`;
  }

  private _batteryClass(entity?: string): string {
    if (!entity || !this._hass) return "muted";
    const e = this._hass.states[entity];
    if (!e || e.state === "unavailable" || e.state === "unknown") return "muted";
    const n = parseFloat(e.state);
    if (Number.isFinite(n) && n <= 20) return "low";
    return "";
  }

  private _updateBattery(): void {
    if (!this._config) return;
    const cells = this._root.querySelectorAll<HTMLElement>(".battery");
    this._config.valves.forEach((v, i) => {
      const cell = cells[i];
      if (!cell) return;
      cell.textContent = this._batteryText(v.battery);
      cell.className = `battery ${this._batteryClass(v.battery)}`;
    });
  }

  // A valve is "online" when its switch reports a real state (on/off);
  // unavailable/unknown/missing = offline. Read-only against hass.states,
  // so this can never affect device behaviour (Simon 2026-06-06: show the
  // online/offline count so the user always sees how many valves they have).
  private _counts(): { online: number; offline: number; total: number } {
    const valves = this._config?.valves ?? [];
    let online = 0;
    for (const v of valves) {
      const e = v.switch && this._hass ? this._hass.states[v.switch] : undefined;
      if (e && e.state !== "unavailable" && e.state !== "unknown") online++;
    }
    return { online, offline: valves.length - online, total: valves.length };
  }

  private _countsText(): string {
    const c = this._counts();
    return `${c.online} online · ${c.offline} offline · ${c.total} total`;
  }

  private _updateCounts(): void {
    const el = this._root.querySelector<HTMLElement>("#valve-counts");
    if (el) el.textContent = this._countsText();
  }

  private _navigate(path?: string): void {
    if (!path) return;
    const base = window.location.pathname.split("/")[1] || "lovelace";
    const url = path.startsWith("/") ? path : `/${base}/${path}`;
    window.history.pushState(null, "", url);
    this.dispatchEvent(
      new Event("location-changed", { bubbles: true, composed: true })
    );
  }

  private _render(): void {
    if (!this._config) return;
    const c = this._config;
    const rows = c.valves
      .map((v) => {
        const segs = v.switch ? this._segments[v.switch] ?? [] : [];
        const bars = segs
          .map(
            (s) =>
              `<span class="seg ${s.kind}" style="left:${(s.left * 100).toFixed(
                3
              )}%;width:${(s.width * 100).toFixed(3)}%"></span>`
          )
          .join("");
        return `<div class="row ${
          v.path ? "clickable" : ""
        }" data-path="${escapeHtml(v.path || "")}">
          <div class="name" title="${escapeHtml(v.name)}">${escapeHtml(
            v.name
          )}</div>
          <div class="bar">${bars}</div>
          <div class="battery ${this._batteryClass(
            v.battery
          )}">${escapeHtml(this._batteryText(v.battery))}</div>
        </div>`;
      })
      .join("");
    this._root.innerHTML = `
      <style>
        ha-card { padding-bottom: 8px; }
        .card-header { font-size: 1.4rem; font-weight: 400; padding: 16px 16px 4px; margin: 0; }
        .card-subtitle { padding: 0 16px 10px; margin: 0; color: var(--secondary-text-color); font-size: 0.95rem; font-variant-numeric: tabular-nums; }
        .grid { display: flex; flex-direction: column; }
        .row { display: grid; grid-template-columns: 150px 1fr 64px; align-items: center; gap: 12px; height: 32px; padding: 0 16px; }
        .row.clickable { cursor: pointer; }
        .row.clickable:hover { background: var(--secondary-background-color); }
        .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 0.9rem; }
        /* Track is EMPTY (no fill) — a no-data / unreachable period renders
           as bare background, so a gap is unmistakable. Reported states draw
           colour: idle = light blue ("online, closed"), watering = amber.
           A faint outline keeps the lane locatable when a row is all-gap. */
        .bar { position: relative; height: 18px; border-radius: 3px; background: transparent; box-shadow: inset 0 0 0 1px var(--divider-color, #e0e0e0); overflow: hidden; }
        .seg { position: absolute; top: 0; bottom: 0; }
        .seg.off { background: rgba(3, 169, 244, 0.30); }
        .seg.on { background: var(--state-switch-active-color, #f9a825); }
        .battery { text-align: right; font-variant-numeric: tabular-nums; font-size: 0.9rem; }
        .battery.muted { color: var(--secondary-text-color); }
        .battery.low { color: var(--error-color, #db4437); font-weight: 600; }
      </style>
      <ha-card>
        ${c.title ? `<h1 class="card-header">${escapeHtml(c.title)}</h1>` : ""}
        <div class="card-subtitle" id="valve-counts">${escapeHtml(
          this._countsText()
        )}</div>
        <div class="grid">${rows}</div>
      </ha-card>`;
    this._root.querySelectorAll<HTMLElement>(".row.clickable").forEach((el) => {
      el.addEventListener("click", () => this._navigate(el.dataset.path));
    });
  }
}

if (!customElements.get("irrigation-valve-matrix")) {
  customElements.define("irrigation-valve-matrix", IrrigationValveMatrix);
}

/* ------------------------------------------------------------------ *
 * Registration                                                        *
 * ------------------------------------------------------------------ */

// HA looks up dashboard strategies as `ll-strategy-dashboard-<type>`
// (and the older `ll-strategy-<type>` for back-compat). Define both so
// the same bundle works regardless of HA frontend version.
const elementName = "ll-strategy-dashboard-irrigation-valves";
if (!customElements.get(elementName)) {
  customElements.define(elementName, IrrigationValvesStrategy);
}
const legacyElementName = "ll-strategy-irrigation-valves";
if (!customElements.get(legacyElementName)) {
  customElements.define(
    legacyElementName,
    class extends IrrigationValvesStrategy {}
  );
}
