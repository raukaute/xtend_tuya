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
