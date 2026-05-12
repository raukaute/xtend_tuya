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
  watering_volume: "volume_sensor",
  watering_flow_rate: "flow_rate_sensor",
  battery_level: "battery_level",
  watering_duration: "duration",
  rain_snow_delay: "rain_snow_delay",
};

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
      buildOverviewView(overviewTitle, valves),
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
  const valve_name =
    (registryState.attributes.valve_name as string | undefined) ??
    (registryState.attributes.valve_factory_name as string | undefined) ??
    tuyaDeviceId;
  const factory_name =
    (registryState.attributes.valve_factory_name as string | undefined) ??
    valve_name;

  const view_path = makeViewPath(tuyaDeviceId, valve_name);

  const v: ValveEntities = {
    device_id: tuyaDeviceId,
    registry_entity: registryEntityId,
    valve_name,
    factory_name,
    view_path,
  };

  for (const e of Object.values(hass.entities)) {
    if (e.device_id !== haDeviceId) continue;

    // The valve switch entity has no translation_key in this
    // integration's switch platform — pick it up by entity_id pattern.
    if (e.entity_id.startsWith("switch.") && e.entity_id.endsWith("_valve")) {
      v.switch = e.entity_id;
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
    if (!tk) continue;
    const field = TRANSLATION_KEY_TO_FIELD[tk];
    if (!field) continue;
    // Don't overwrite an already-set entity (defensive — translation_keys
    // are unique per device for this integration).
    if (!v[field]) {
      (v as unknown as Record<string, string | undefined>)[field] = e.entity_id;
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
  valves: ValveEntities[]
): DashboardView {
  const tiles = valves.map((v) => ({
    type: "tile",
    entity: v.switch ?? v.registry_entity,
    name: v.valve_name,
    icon: "mdi:water-pump",
    state_content: ["state", "last-changed"],
    tap_action: {
      action: "navigate",
      navigation_path: `/${v.view_path}`,
    },
    features: v.battery_level
      ? [
          {
            type: "tile-tap-area",
          },
        ]
      : undefined,
  }));

  // A second row of compact battery indicators so the overview gives
  // the at-a-glance "which valves need solar attention" answer Simon
  // asked for in the DM.
  const batteryEntities = valves
    .filter((v) => v.battery_level)
    .map((v) => ({
      entity: v.battery_level,
      name: v.valve_name,
    }));

  const cards: unknown[] = [
    {
      type: "grid",
      columns: 2,
      square: false,
      cards: tiles,
    },
  ];

  if (batteryEntities.length > 0) {
    cards.push({
      type: "entities",
      title: "Battery levels",
      show_header_toggle: false,
      entities: batteryEntities,
    });
  }

  return {
    title,
    path: "overview",
    cards,
  };
}

function buildValveView(v: ValveEntities, hours: number): DashboardView {
  const sections: unknown[] = [];

  // Section 1: control card + other settings + timer card
  sections.push({
    type: "grid",
    cards: [
      buildControlCard(v),
      buildOtherSettingsCard(v),
      buildTimerCard(v),
    ].filter(Boolean),
  });

  // Section 2: watering history graph + last watering entities + lifetime sum
  sections.push({
    type: "grid",
    cards: [
      buildWateringHistoryCard(v, hours),
      buildLastWateringCard(v),
      buildLifetimeVolumeCard(v),
      buildHourlyVolumeCard(v),
    ].filter(Boolean),
  });

  // Section 3: battery tile + battery history
  if (v.battery_level) {
    sections.push({
      type: "grid",
      cards: [buildBatteryTile(v), buildBatteryHistoryCard(v, hours)],
    });
  }

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
  const entities: unknown[] = [];
  if (v.switch) entities.push({ entity: v.switch, name: "Valve" });
  if (v.flow_rate_sensor)
    entities.push({ entity: v.flow_rate_sensor, name: "Flow rate" });
  else if (v.volume_sensor)
    entities.push({ entity: v.volume_sensor, name: "Run volume" });
  if (entities.length === 0) return null;
  return {
    type: "history-graph",
    title: "Watering History",
    hours_to_show: hours,
    entities,
    layout_options: { grid_columns: 12, grid_rows: "auto" },
  };
}

function buildLifetimeVolumeCard(v: ValveEntities): unknown | null {
  // The cur_cap sensor declares state_class=TOTAL_INCREASING (4.4.112+),
  // so HA's long-term statistics treat each per-cycle reset as a new
  // accumulator window and the `sum` stat is the lifetime cumulative.
  // Plotting it as a daily bucket gives a monotonic "total water through
  // this valve" curve — answers "how much water has flowed at any point
  // in time" without a real flow meter.
  if (!v.volume_sensor) return null;
  return {
    type: "statistics-graph",
    title: "Lifetime water",
    entities: [v.volume_sensor],
    stat_types: ["sum"],
    period: "day",
    days_to_show: 30,
    chart_type: "line",
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
    layout_options: { grid_columns: 12, grid_rows: "auto" },
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
  return {
    type: "tile",
    grid_options: { columns: 12, rows: 3 },
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
    grid_options: { rows: "auto", columns: 12 },
    max_y_axis: 100,
    hours_to_show: hours,
  };
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
