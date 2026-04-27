import { LitElement, html, css, nothing, PropertyValues } from "lit";
import { property, state } from "lit/decorators.js";
import { IrrigationControlCardConfig } from "./models";

// HA types (minimal — same shape used in irrigation-timer-card)
interface HomeAssistant {
  states: Record<string, HassEntity>;
  callService(
    domain: string,
    service: string,
    data: Record<string, unknown>
  ): Promise<void>;
}

interface HassEntity {
  state: string;
  attributes: Record<string, unknown>;
}

type Mode = "duration" | "volume";

const MODE_DURATION_DEFAULT = 60; // seconds
const MODE_VOLUME_DEFAULT = 10; // liters

export class IrrigationControlCard extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @state() private _config!: IrrigationControlCardConfig;

  /** User-selected mode for the next Start (separate from device's last-used mode). */
  @state() private _mode: Mode = "duration";

  /** Target value the user typed for the next Start (sec or L). */
  @state() private _target: number = MODE_DURATION_DEFAULT;

  /** Tick state for live progress refresh while a cycle is running. */
  @state() private _tick = 0;
  private _tickHandle: number | null = null;

  setConfig(config: IrrigationControlCardConfig): void {
    if (!config.valve) {
      throw new Error("Please define a valve switch entity");
    }
    if (!config.device_id) {
      throw new Error("Please define a device_id");
    }
    this._config = config;
  }

  getCardSize(): number {
    return 3;
  }

  connectedCallback(): void {
    super.connectedCallback();
    // Tick once a second so the duration countdown stays fresh without
    // waiting for HA state updates. The truth is still server-side.
    this._tickHandle = window.setInterval(() => (this._tick = Date.now()), 1000);
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    if (this._tickHandle !== null) {
      window.clearInterval(this._tickHandle);
      this._tickHandle = null;
    }
  }

  protected updated(changedProps: PropertyValues): void {
    if (changedProps.has("hass") && this.hass && this._config) {
      // Keep the user's target field in sync with HA's number entity once
      // we've seen state. After that, edits are local until Start.
      if (changedProps.get("hass") === undefined) {
        this._initTargetFromState();
      }
    }
  }

  private _initTargetFromState(): void {
    if (!this._config.duration) return;
    const e = this.hass.states[this._config.duration];
    if (!e) return;
    const n = parseFloat(e.state);
    if (Number.isFinite(n) && n > 0) {
      this._target = n;
    }
  }

  // ----- State derivations -----

  private _isOn(): boolean {
    const v = this.hass.states[this._config.valve];
    return v?.state === "on";
  }

  private _activeMode(): Mode | null {
    if (!this._config.mode_sensor) return null;
    const e = this.hass.states[this._config.mode_sensor];
    if (!e) return null;
    if (e.state === "duration") return "duration";
    if (e.state === "volume") return "volume";
    return null;
  }

  private _targetValue(): number | null {
    if (!this._config.value_sensor) return null;
    const e = this.hass.states[this._config.value_sensor];
    if (!e) return null;
    const n = parseFloat(e.state);
    return Number.isFinite(n) ? n : null;
  }

  private _startTime(): Date | null {
    if (!this._config.start_time_sensor) return null;
    const e = this.hass.states[this._config.start_time_sensor];
    if (!e || !e.state) return null;
    const d = new Date(e.state.replace(" ", "T"));
    return Number.isFinite(d.getTime()) ? d : null;
  }

  private _endTime(): Date | null {
    if (!this._config.end_time_sensor) return null;
    const e = this.hass.states[this._config.end_time_sensor];
    if (!e || !e.state) return null;
    const d = new Date(e.state.replace(" ", "T"));
    return Number.isFinite(d.getTime()) ? d : null;
  }

  private _currentVolume(): number | null {
    if (!this._config.volume_sensor) return null;
    const e = this.hass.states[this._config.volume_sensor];
    if (!e) return null;
    const n = parseFloat(e.state);
    return Number.isFinite(n) ? n : null;
  }

  private _valveName(): string | null {
    if (!this._config.registry_entity) return null;
    const e = this.hass.states[this._config.registry_entity];
    return (e?.attributes?.valve_name as string) ?? null;
  }

  // ----- Actions -----

  private async _toggleManual(): Promise<void> {
    if (!this.hass) return;
    const turn = this._isOn() ? "turn_off" : "turn_on";
    await this.hass.callService("switch", turn, {
      entity_id: this._config.valve,
    });
  }

  private async _startSingleWatering(): Promise<void> {
    if (!this.hass) return;
    // Write one_control directly via xtend_tuya.fdm5kw_start_watering so
    // mode + value land atomically. This sidesteps the "duration ignored
    // on second start" bug, where toggling the valve switch reuses a
    // stale value because the number-entity update isn't strictly ordered
    // with the switch turn_on.
    await this.hass.callService("xtend_tuya", "fdm5kw_start_watering", {
      device_id: this._config.device_id,
      mode: this._mode,
      value: Math.max(1, Math.round(this._target)),
    });
  }

  private async _stop(): Promise<void> {
    if (!this.hass) return;
    // Write one_control idle (mode=0). Falls back to switch turn_off if
    // the user is on an integration version without the new service.
    try {
      await this.hass.callService("xtend_tuya", "fdm5kw_stop_watering", {
        device_id: this._config.device_id,
      });
    } catch {
      await this.hass.callService("switch", "turn_off", {
        entity_id: this._config.valve,
      });
    }
  }

  // ----- Rendering -----

  protected render() {
    if (!this._config || !this.hass) return nothing;

    const name =
      this._config.name ??
      this._valveName() ??
      (this.hass.states[this._config.valve]?.attributes?.friendly_name as
        | string
        | undefined) ??
      "Watering";

    const running = this._isOn();
    const start = this._startTime();
    const end = this._endTime();
    // A cycle is "in progress" if the valve is on AND start is more recent
    // than end (or end is null). Otherwise the start_time is the *previous*
    // cycle and we shouldn't show progress.
    const inProgress =
      running && start !== null && (end === null || start > end);

    return html`
      <ha-card>
        <div class="card-header">
          <ha-icon icon="mdi:water-pump"></ha-icon>
          <span>${name}</span>
          ${this._renderStatusPill(running, inProgress)}
        </div>
        <div class="card-content">
          ${inProgress ? this._renderProgress(start!) : this._renderControls()}
        </div>
      </ha-card>
    `;
  }

  private _renderStatusPill(running: boolean, inProgress: boolean) {
    if (inProgress) {
      return html`<span class="pill running">Watering</span>`;
    }
    if (running) {
      return html`<span class="pill manual">Manual ON</span>`;
    }
    return html`<span class="pill idle">Idle</span>`;
  }

  private _renderProgress(start: Date) {
    void this._tick; // re-render trigger
    const activeMode = this._activeMode() ?? this._mode;
    const target = this._targetValue() ?? this._target;

    if (activeMode === "volume") {
      const cur = this._currentVolume() ?? 0;
      const pct = target > 0 ? Math.min(100, (cur / target) * 100) : 0;
      const remaining = Math.max(0, target - cur);
      return html`
        <div class="progress">
          <div class="progress-text">
            <span class="big">${cur.toFixed(1)} L</span>
            <span class="dim"> / ${target} L</span>
          </div>
          <div class="bar">
            <div class="fill" style="width:${pct}%"></div>
          </div>
          <div class="progress-sub">${remaining.toFixed(1)} L remaining</div>
        </div>
        <button class="stop-btn" @click=${this._stop}>Stop</button>
      `;
    }

    // Duration mode
    const elapsed = (Date.now() - start.getTime()) / 1000;
    const pct = target > 0 ? Math.min(100, (elapsed / target) * 100) : 0;
    const remaining = Math.max(0, target - elapsed);
    return html`
      <div class="progress">
        <div class="progress-text">
          <span class="big">${formatDuration(remaining)}</span>
          <span class="dim"> left of ${formatDuration(target)}</span>
        </div>
        <div class="bar">
          <div class="fill" style="width:${pct}%"></div>
        </div>
        <div class="progress-sub">
          ${formatDuration(elapsed)} elapsed
        </div>
      </div>
      <button class="stop-btn" @click=${this._stop}>Stop</button>
    `;
  }

  private _renderControls() {
    const lastStart = this._startTime();
    const lastEnd = this._endTime();

    return html`
      <div class="mode-tabs">
        <button
          class=${this._mode === "duration" ? "tab active" : "tab"}
          @click=${() => this._setMode("duration")}
        >
          <ha-icon icon="mdi:timer-outline"></ha-icon>
          Duration
        </button>
        <button
          class=${this._mode === "volume" ? "tab active" : "tab"}
          @click=${() => this._setMode("volume")}
        >
          <ha-icon icon="mdi:water"></ha-icon>
          Volume
        </button>
      </div>

      <div class="target-row">
        <label>${this._mode === "duration" ? "Duration" : "Volume"}</label>
        <div class="target-input">
          <input
            type="number"
            min="1"
            max=${this._mode === "duration" ? 86400 : 9999}
            .value=${String(
              this._mode === "duration"
                ? Math.max(1, Math.round(this._target))
                : this._target
            )}
            @change=${(e: Event) => {
              const raw = parseFloat((e.target as HTMLInputElement).value);
              if (Number.isFinite(raw) && raw > 0) {
                this._target = raw;
              }
            }}
          />
          <span class="unit">${this._mode === "duration" ? "sec" : "L"}</span>
        </div>
      </div>

      <div class="primary-actions">
        <button class="start-btn" @click=${this._startSingleWatering}>
          <ha-icon icon="mdi:play"></ha-icon>
          Single watering
        </button>
        <button
          class="manual-btn ${this._isOn() ? "on" : ""}"
          @click=${this._toggleManual}
          title=${this._isOn()
            ? "Manually stop the valve"
            : "Manually open the valve (no auto-stop)"}
        >
          <ha-icon icon=${this._isOn() ? "mdi:toggle-switch" : "mdi:toggle-switch-off-outline"}></ha-icon>
          Manual ${this._isOn() ? "OFF" : "ON"}
        </button>
      </div>

      ${lastStart || lastEnd
        ? html`
            <div class="last-cycle">
              ${lastStart
                ? html`<div><span class="dim">Last start</span> ${this._fmtDate(lastStart)}</div>`
                : nothing}
              ${lastEnd
                ? html`<div><span class="dim">Last end</span> ${this._fmtDate(lastEnd)}</div>`
                : nothing}
            </div>
          `
        : nothing}
    `;
  }

  private _setMode(m: Mode): void {
    if (this._mode === m) return;
    // Carry over a sensible default when switching modes the first time.
    if (m === "duration" && this._target < 5) this._target = MODE_DURATION_DEFAULT;
    if (m === "volume" && this._target > 1000) this._target = MODE_VOLUME_DEFAULT;
    this._mode = m;
  }

  private _fmtDate(d: Date): string {
    return d.toLocaleString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
      day: "2-digit",
      month: "short",
    });
  }

  static styles = css`
    :host {
      --ic-primary: var(--primary-color, #03a9f4);
      --ic-bg: var(--card-background-color, #fff);
      --ic-text: var(--primary-text-color, #212121);
      --ic-secondary: var(--secondary-text-color, #727272);
      --ic-divider: var(--divider-color, #e0e0e0);
      --ic-success: var(--success-color, #4caf50);
      --ic-warning: var(--warning-color, #ff9800);
    }

    .card-header {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 16px 16px 0;
      font-size: 1.1em;
      font-weight: 500;
      color: var(--ic-text);
    }

    .card-header ha-icon {
      color: var(--ic-primary);
    }

    .card-header span {
      flex: 1;
    }

    .pill {
      font-size: 0.75em;
      padding: 2px 8px;
      border-radius: 10px;
      font-weight: 500;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .pill.idle {
      background: var(--ic-divider);
      color: var(--ic-secondary);
    }
    .pill.running {
      background: var(--ic-primary);
      color: white;
    }
    .pill.manual {
      background: var(--ic-warning);
      color: white;
    }

    .card-content {
      padding: 16px;
    }

    /* Mode tabs */
    .mode-tabs {
      display: flex;
      gap: 8px;
      margin-bottom: 12px;
    }
    .tab {
      flex: 1;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      padding: 10px;
      border: 1px solid var(--ic-divider);
      border-radius: 8px;
      background: transparent;
      color: var(--ic-secondary);
      font-size: 0.95em;
      cursor: pointer;
    }
    .tab.active {
      background: var(--ic-primary);
      color: white;
      border-color: var(--ic-primary);
    }

    /* Target input */
    .target-row {
      display: flex;
      flex-direction: column;
      gap: 6px;
      margin-bottom: 16px;
    }
    .target-row label {
      font-size: 0.85em;
      font-weight: 500;
      color: var(--ic-secondary);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .target-input {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .target-input input {
      flex: 1;
      padding: 10px 12px;
      border: 1px solid var(--ic-divider);
      border-radius: 8px;
      background: var(--ic-bg);
      color: var(--ic-text);
      font-size: 1.1em;
      outline: none;
    }
    .target-input input:focus {
      border-color: var(--ic-primary);
    }
    .target-input .unit {
      color: var(--ic-secondary);
      font-size: 0.95em;
    }

    /* Primary actions */
    .primary-actions {
      display: flex;
      gap: 8px;
    }
    .start-btn,
    .manual-btn,
    .stop-btn {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      padding: 12px;
      border: none;
      border-radius: 8px;
      font-size: 0.95em;
      font-weight: 500;
      cursor: pointer;
    }
    .start-btn {
      flex: 2;
      background: var(--ic-primary);
      color: white;
    }
    .manual-btn {
      flex: 1;
      background: transparent;
      border: 1px solid var(--ic-divider);
      color: var(--ic-text);
    }
    .manual-btn.on {
      background: var(--ic-warning);
      color: white;
      border-color: var(--ic-warning);
    }
    .stop-btn {
      width: 100%;
      margin-top: 16px;
      background: transparent;
      border: 1px solid var(--ic-divider);
      color: var(--ic-text);
    }

    /* Last-cycle line */
    .last-cycle {
      margin-top: 16px;
      padding-top: 12px;
      border-top: 1px solid var(--ic-divider);
      font-size: 0.85em;
      color: var(--ic-text);
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .dim {
      color: var(--ic-secondary);
    }

    /* Progress view */
    .progress {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .progress-text {
      display: flex;
      align-items: baseline;
      gap: 4px;
      font-variant-numeric: tabular-nums;
    }
    .progress-text .big {
      font-size: 2em;
      font-weight: 600;
      color: var(--ic-text);
    }
    .progress-text .dim {
      font-size: 1em;
    }
    .bar {
      height: 8px;
      background: var(--ic-divider);
      border-radius: 4px;
      overflow: hidden;
    }
    .fill {
      height: 100%;
      background: var(--ic-primary);
      transition: width 0.5s linear;
    }
    .progress-sub {
      font-size: 0.85em;
      color: var(--ic-secondary);
    }
  `;
}

function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const total = Math.round(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) {
    return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }
  return `${m}:${String(s).padStart(2, "0")}`;
}

// Idempotent registration — guards against double-load.
if (!customElements.get("irrigation-control-card")) {
  customElements.define("irrigation-control-card", IrrigationControlCard);
  const w = window as unknown as { customCards?: unknown[] };
  w.customCards = w.customCards || [];
  if (
    !w.customCards.some(
      (c) => (c as { type?: string }).type === "irrigation-control-card"
    )
  ) {
    w.customCards.push({
      type: "irrigation-control-card",
      name: "Irrigation Control",
      description:
        "Toggle a valve, start a single watering cycle by duration or volume, and watch progress live.",
    });
  }
}
