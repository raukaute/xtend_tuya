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
