/** Timer mode — matches Tuya DP encoding */
export enum TimerMode {
  Duration = 0,
  Volume = 1,
}

/** Single timer slot data */
export interface TimerSlot {
  slot: number;
  mode: TimerMode;
  /** Seconds when mode=Duration, liters when mode=Volume */
  value: number;
  hour: number;
  minute: number;
  /** Bitmask: bit0=Mon, bit1=Tue, ..., bit6=Sun */
  daysMask: number;
  enabled: boolean;
}

/** Days of week for UI display */
export const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;

/** Maximum number of timer slots supported by the fdm5kw device firmware. */
export const NUM_SLOTS = 7;

/** Card configuration */
export interface IrrigationTimerCardConfig {
  type: string;
  /** Entity ID of the timer registry sensor (exposes `slots` attribute) */
  entity: string;
  /** Tuya device ID for sending commands */
  device_id: string;
  /** Name override */
  name?: string;
}

/** One valve entry rendered as a row in the valve-matrix card. */
export interface ValveMatrixRow {
  /** Display name (SmartLife custom name). */
  name: string;
  /** Valve on/off switch entity — drives the watering timeline bar. */
  switch?: string;
  /** Battery level sensor entity — drives the battery % column. */
  battery?: string;
  /** Relative dashboard view path for the per-valve detail view. */
  path?: string;
}

/** Configuration for the irrigation-valve-matrix card.
 *
 * Renders one fixed-height row per valve — name | watering on/off
 * timeline | battery % — so the watering history and battery columns line
 * up exactly (two separate stock cards never align row-for-row). */
export interface IrrigationValveMatrixConfig {
  type: string;
  /** Card header. */
  title?: string;
  /** Hours of switch history to render in the timeline bars. */
  hours?: number;
  /** Per-valve rows, in display order. */
  valves: ValveMatrixRow[];
}

/** Configuration for the irrigation-control-card. */
export interface IrrigationControlCardConfig {
  type: string;
  /** Valve switch entity (required) */
  valve: string;
  /** Number entity for default watering duration (seconds) */
  duration?: string;
  /** Sensor with cumulative water volume (liters) */
  volume_sensor?: string;
  /** Sensor with last watering start timestamp */
  start_time_sensor?: string;
  /** Sensor with last watering end timestamp */
  end_time_sensor?: string;
  /** Sensor reporting active mode (idle / duration / volume) */
  mode_sensor?: string;
  /** Sensor reporting current target value (sec or L) */
  value_sensor?: string;
  /** Tuya device ID — required for the start_watering service */
  device_id: string;
  /** Optional registry entity for valve_name discovery */
  registry_entity?: string;
  /** Header override */
  name?: string;
}
