import { LitElement, html, css, nothing, PropertyValues } from "lit";
import { property, state } from "lit/decorators.js";
import {
  TimerSlot,
  TimerMode,
  DAYS,
  NUM_SLOTS,
  IrrigationTimerCardConfig,
} from "./models";

// HA types (minimal)
interface HomeAssistant {
  states: Record<string, HassEntity>;
  callService(
    domain: string,
    service: string,
    data?: Record<string, unknown>,
    target?: unknown,
    notifyOnError?: boolean,
    returnResponse?: boolean
  ): Promise<{ response?: ResyncResponse }>;
}

/** Return payload of xtend_tuya.fdm5kw_resync_timers. */
interface ResyncResponse {
  success?: boolean;
  error?: string;
  checked?: number;
  orphans_cleared?: number;
  orphans_deferred?: number;
}

interface HassEntity {
  state: string;
  attributes: Record<string, unknown>;
}

/** Shape of each entry in the registry sensor's `slots` attribute. */
interface SlotAttribute {
  slot: number;
  hour: number;
  minute: number;
  mode: "duration" | "volume";
  value: number;
  value_unit: "s" | "L";
  days: string[];
  days_mask: number;
  enabled: boolean;
  cloud_timer_id?: string;
}

export class IrrigationTimerCard extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @state() private _config!: IrrigationTimerCardConfig;

  /** Cached timer slots from state updates */
  @state() private _timers: Map<number, TimerSlot> = new Map();

  /** Currently editing timer (null = list view) */
  @state() private _editing: TimerSlot | null = null;

  /** Are we creating a new timer? */
  @state() private _isNew = false;

  /** Cloud-resync in flight + last-result banner (auto-clears). */
  @state() private _resyncing = false;
  @state() private _resyncStatus: string | null = null;

  setConfig(config: IrrigationTimerCardConfig): void {
    if (!config.entity) {
      throw new Error("Please define an entity (timer registry sensor)");
    }
    if (!config.device_id) {
      throw new Error("Please define a device_id");
    }
    this._config = config;
  }

  getCardSize(): number {
    return 4;
  }

  protected updated(changedProps: PropertyValues): void {
    if (changedProps.has("hass") && this.hass) {
      this._updateTimersFromState();
    }
  }

  private _updateTimersFromState(): void {
    const entity = this.hass.states[this._config.entity];
    if (!entity) return;

    const slots = entity.attributes?.slots as
      | Record<string, SlotAttribute | null>
      | undefined;
    if (!slots) return;

    const next = new Map<number, TimerSlot>();
    for (let i = 0; i < NUM_SLOTS; i++) {
      const raw = slots[String(i)];
      if (!raw) continue;
      next.set(i, {
        slot: i,
        mode: raw.mode === "volume" ? TimerMode.Volume : TimerMode.Duration,
        value: raw.value,
        hour: raw.hour,
        minute: raw.minute,
        daysMask: raw.days_mask,
        enabled: raw.enabled,
      });
    }
    this._timers = next;
  }

  private _newTimer(): TimerSlot {
    for (let i = 0; i < NUM_SLOTS; i++) {
      if (!this._timers.has(i)) {
        return {
          slot: i,
          mode: TimerMode.Duration,
          value: 900, // 15 min default
          hour: 6,
          minute: 0,
          daysMask: 0b1111111,
          enabled: true,
        };
      }
    }
    return {
      slot: 0,
      mode: TimerMode.Duration,
      value: 900,
      hour: 6,
      minute: 0,
      daysMask: 0b1111111,
      enabled: true,
    };
  }

  private async _sendSetTimer(timer: TimerSlot): Promise<void> {
    await this.hass.callService("xtend_tuya", "fdm5kw_set_timer", {
      device_id: this._config.device_id,
      slot: timer.slot,
      hour: timer.hour,
      minute: timer.minute,
      mode: timer.mode === TimerMode.Volume ? "volume" : "duration",
      value: timer.value,
      days: timer.daysMask,
      enabled: timer.enabled,
    });
  }

  private async _sendDeleteTimer(slot: number): Promise<void> {
    await this.hass.callService("xtend_tuya", "fdm5kw_delete_timer", {
      device_id: this._config.device_id,
      slot,
    });
  }

  private async _saveTimer(): Promise<void> {
    if (!this._editing) return;
    await this._sendSetTimer(this._editing);

    this._timers = new Map(this._timers);
    this._timers.set(this._editing.slot, { ...this._editing });
    this._editing = null;
    this._isNew = false;
  }

  private async _deleteTimer(slot: number): Promise<void> {
    await this._sendDeleteTimer(slot);

    this._timers = new Map(this._timers);
    this._timers.delete(slot);
  }

  /** Reconcile this valve's timers against the Tuya cloud, dropping ghosts.
   * Read-first server-side: only a live orphan (would water offline) costs a
   * device write. The registry entity refreshes itself, so the ghost rows
   * just vanish; the banner covers the "nothing changed / all clean" case. */
  private async _resync(): Promise<void> {
    if (this._resyncing) return;
    this._resyncing = true;
    this._resyncStatus = null;
    try {
      const res = await this.hass.callService(
        "xtend_tuya",
        "fdm5kw_resync_timers",
        { device_id: this._config.device_id },
        undefined,
        undefined,
        true
      );
      const r = res?.response ?? {};
      if (r.success === false) {
        this._resyncStatus = `Resync failed: ${r.error ?? "unknown"}`;
      } else {
        const cleared = r.orphans_cleared ?? 0;
        const parts: string[] = [];
        if (cleared === 0) parts.push("All in sync");
        else parts.push(`Cleared ${cleared} zombie${cleared === 1 ? "" : "s"}`);
        if (r.orphans_deferred) parts.push(`${r.orphans_deferred} deferred (quota)`);
        this._resyncStatus = parts.join(" · ");
      }
    } catch (err) {
      this._resyncStatus = `Resync failed: ${err}`;
    } finally {
      this._resyncing = false;
      window.setTimeout(() => {
        this._resyncStatus = null;
      }, 5000);
    }
  }

  private _startEdit(timer: TimerSlot): void {
    this._editing = { ...timer };
    this._isNew = false;
  }

  private _startNew(): void {
    this._editing = this._newTimer();
    this._isNew = true;
  }

  private _cancelEdit(): void {
    this._editing = null;
    this._isNew = false;
  }

  // --- Rendering ---

  protected render() {
    if (!this._config || !this.hass) return nothing;

    const stateAttrs = this.hass.states[this._config.entity]?.attributes;
    const valveName = stateAttrs?.valve_name as string | undefined;
    const name =
      this._config.name ??
      valveName ??
      (stateAttrs?.friendly_name as string | undefined) ??
      "Irrigation Timer";

    // "Home · Room" sub-line, same source/registry attributes as the control
    // card, so the timer card on the detail view also helps locate the valve
    // in the SmartLife app (Simon's request). Renders nothing until known.
    const home = stateAttrs?.valve_home as string | undefined;
    const room = stateAttrs?.valve_room as string | undefined;
    const location = [home, room]
      .filter((p) => p && String(p).trim())
      .join(" · ");

    return html`
      <ha-card>
        <div class="card-header">
          <ha-icon icon="mdi:timer-cog-outline"></ha-icon>
          <div class="title">
            <span class="name">${name}</span>
            ${location
              ? html`<span class="location">${location}</span>`
              : nothing}
          </div>
          <button
            class="resync-btn ${this._resyncing ? "spinning" : ""}"
            title="Resync timers from cloud (clears ghost/zombie timers)"
            ?disabled=${this._resyncing}
            @click=${this._resync}
          >
            <ha-icon icon="mdi:cloud-sync-outline"></ha-icon>
          </button>
        </div>
        ${this._resyncStatus
          ? html`<div class="resync-status">${this._resyncStatus}</div>`
          : nothing}
        <div class="card-content">
          ${this._editing ? this._renderEditor() : this._renderList()}
        </div>
      </ha-card>
    `;
  }

  private _renderList() {
    // Sort by time of day, not slot index — slot numbers are an internal
    // device detail and read as random ordering (Trello ExgyBKSb).
    const timers = Array.from(this._timers.values()).sort(
      (a, b) => a.hour * 60 + a.minute - (b.hour * 60 + b.minute)
    );

    return html`
      ${timers.length === 0
        ? html`<div class="empty">No timers configured</div>`
        : timers.map((t) => this._renderTimerRow(t))}
      <button class="add-btn" @click=${this._startNew}>
        <ha-icon icon="mdi:plus"></ha-icon>
        Add Timer
      </button>
    `;
  }

  private _renderTimerRow(timer: TimerSlot) {
    const timeStr = `${timer.hour.toString().padStart(2, "0")}:${timer.minute.toString().padStart(2, "0")}`;
    const valueStr =
      timer.mode === TimerMode.Duration
        ? timer.value < 60
          ? `${timer.value}s`
          : timer.value % 60 === 0
            ? `${timer.value / 60}min`
            : `${Math.floor(timer.value / 60)}min ${timer.value % 60}s`
        : `${timer.value}L`;
    const daysStr = DAYS.filter((_, i) => timer.daysMask & (1 << i)).join(", ");

    return html`
      <div class="timer-row ${timer.enabled ? "" : "disabled"}">
        <div class="timer-info" @click=${() => this._startEdit(timer)}>
          <div class="timer-time">${timeStr}</div>
          <div class="timer-details">
            <span class="timer-value">${valueStr}</span>
            <span class="timer-days">${daysStr}</span>
          </div>
        </div>
        <div class="timer-actions">
          <ha-switch
            .checked=${timer.enabled}
            @change=${(e: Event) => this._toggleEnabled(timer, e)}
          ></ha-switch>
        </div>
      </div>
    `;
  }

  private async _toggleEnabled(
    timer: TimerSlot,
    e: Event
  ): Promise<void> {
    const checked = (e.target as HTMLInputElement).checked;
    const updated = { ...timer, enabled: checked };
    await this._sendSetTimer(updated);

    this._timers = new Map(this._timers);
    this._timers.set(timer.slot, updated);
  }

  private _renderEditor() {
    const t = this._editing!;
    return html`
      <div class="editor">
        <div class="editor-row">
          <label>Time</label>
          <input
            type="time"
            .value=${`${t.hour.toString().padStart(2, "0")}:${t.minute.toString().padStart(2, "0")}`}
            @change=${(e: Event) => {
              const [h, m] = (e.target as HTMLInputElement).value.split(":");
              this._editing = {
                ...t,
                hour: parseInt(h, 10),
                minute: parseInt(m, 10),
              };
            }}
          />
        </div>

        <div class="editor-row">
          <label>Mode</label>
          <div class="mode-toggle">
            <button
              class=${t.mode === TimerMode.Duration ? "active" : ""}
              @click=${() => {
                this._editing = {
                  ...t,
                  mode: TimerMode.Duration,
                  value: t.mode === TimerMode.Volume ? 900 : t.value,
                };
              }}
            >
              <ha-icon icon="mdi:timer-outline"></ha-icon>
              Duration
            </button>
            <button
              class=${t.mode === TimerMode.Volume ? "active" : ""}
              @click=${() => {
                this._editing = {
                  ...t,
                  mode: TimerMode.Volume,
                  value: t.mode === TimerMode.Duration ? 50 : t.value,
                };
              }}
            >
              <ha-icon icon="mdi:water"></ha-icon>
              Volume
            </button>
          </div>
        </div>

        <div class="editor-row">
          <label>${t.mode === TimerMode.Duration ? "Duration (min)" : "Volume (L)"}</label>
          <input
            type="number"
            min="1"
            max=${t.mode === TimerMode.Duration ? 1440 : 9999}
            .value=${t.mode === TimerMode.Duration ? Math.floor(t.value / 60) : t.value}
            @change=${(e: Event) => {
              const raw = parseInt((e.target as HTMLInputElement).value, 10);
              this._editing = {
                ...t,
                value:
                  t.mode === TimerMode.Duration ? raw * 60 : raw,
              };
            }}
          />
        </div>

        <div class="editor-row">
          <label>Days</label>
          <div class="day-picker">
            ${DAYS.map(
              (day, i) => html`
                <button
                  class="day-btn ${t.daysMask & (1 << i) ? "active" : ""}"
                  @click=${() => {
                    this._editing = {
                      ...t,
                      daysMask: t.daysMask ^ (1 << i),
                    };
                  }}
                >
                  ${day.charAt(0)}${day.charAt(1)}
                </button>
              `
            )}
          </div>
        </div>

        <div class="editor-actions">
          ${!this._isNew
            ? html`<button
                class="delete-btn"
                @click=${() => {
                  this._deleteTimer(t.slot);
                  this._editing = null;
                  this._isNew = false;
                }}
              >
                Delete
              </button>`
            : nothing}
          <button class="cancel-btn" @click=${this._cancelEdit}>
            Cancel
          </button>
          <button class="save-btn" @click=${this._saveTimer}>Save</button>
        </div>
      </div>
    `;
  }

  static styles = css`
    :host {
      --timer-card-primary: var(--primary-color, #03a9f4);
      --timer-card-bg: var(--card-background-color, #fff);
      --timer-card-text: var(--primary-text-color, #212121);
      --timer-card-secondary: var(--secondary-text-color, #727272);
      --timer-card-disabled: var(--disabled-text-color, #bdbdbd);
      --timer-card-divider: var(--divider-color, #e0e0e0);
    }

    .card-header {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 16px 16px 0;
      font-size: 1.1em;
      font-weight: 500;
      color: var(--timer-card-text);
    }

    .card-header ha-icon {
      color: var(--timer-card-primary);
    }

    .card-header .title {
      flex: 1;
      display: flex;
      flex-direction: column;
      min-width: 0;
    }
    .card-header .title .name {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .card-header .title .location {
      font-size: 0.7em;
      font-weight: 400;
      opacity: 0.6;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .resync-btn {
      flex: 0 0 auto;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 4px;
      border: none;
      background: transparent;
      color: var(--timer-card-secondary);
      cursor: pointer;
      border-radius: 50%;
      transition: color 0.2s;
    }
    .resync-btn:hover:not([disabled]) {
      color: var(--timer-card-primary);
    }
    .resync-btn[disabled] {
      cursor: default;
    }
    .resync-btn.spinning ha-icon {
      animation: resync-spin 1s linear infinite;
    }
    @keyframes resync-spin {
      to {
        transform: rotate(360deg);
      }
    }
    .resync-status {
      margin: 4px 16px 0;
      font-size: 0.8em;
      color: var(--timer-card-secondary);
      text-align: right;
    }

    .card-content {
      padding: 16px;
    }

    .empty {
      text-align: center;
      color: var(--timer-card-secondary);
      padding: 24px 0;
    }

    /* Timer list */
    .timer-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 0;
      border-bottom: 1px solid var(--timer-card-divider);
      cursor: pointer;
    }

    .timer-row:last-of-type {
      border-bottom: none;
    }

    .timer-row.disabled {
      opacity: 0.5;
    }

    .timer-info {
      flex: 1;
    }

    .timer-time {
      font-size: 1.5em;
      font-weight: 500;
      color: var(--timer-card-text);
      font-variant-numeric: tabular-nums;
    }

    .timer-details {
      display: flex;
      gap: 8px;
      color: var(--timer-card-secondary);
      font-size: 0.9em;
      margin-top: 2px;
    }

    .timer-value {
      font-weight: 500;
      color: var(--timer-card-primary);
    }

    .add-btn {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      width: 100%;
      padding: 12px;
      margin-top: 8px;
      border: 2px dashed var(--timer-card-divider);
      border-radius: 8px;
      background: transparent;
      color: var(--timer-card-primary);
      font-size: 0.95em;
      cursor: pointer;
      transition: border-color 0.2s;
    }

    .add-btn:hover {
      border-color: var(--timer-card-primary);
    }

    /* Editor */
    .editor {
      display: flex;
      flex-direction: column;
      gap: 16px;
    }

    .editor-row {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }

    .editor-row label {
      font-size: 0.85em;
      font-weight: 500;
      color: var(--timer-card-secondary);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }

    .editor-row input[type="time"],
    .editor-row input[type="number"] {
      padding: 10px 12px;
      border: 1px solid var(--timer-card-divider);
      border-radius: 8px;
      background: var(--timer-card-bg);
      color: var(--timer-card-text);
      font-size: 1.1em;
      outline: none;
    }

    .editor-row input:focus {
      border-color: var(--timer-card-primary);
    }

    /* Mode toggle */
    .mode-toggle {
      display: flex;
      gap: 8px;
    }

    .mode-toggle button {
      flex: 1;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      padding: 10px;
      border: 1px solid var(--timer-card-divider);
      border-radius: 8px;
      background: transparent;
      color: var(--timer-card-secondary);
      font-size: 0.9em;
      cursor: pointer;
      transition: all 0.2s;
    }

    .mode-toggle button.active {
      background: var(--timer-card-primary);
      color: white;
      border-color: var(--timer-card-primary);
    }

    /* Day picker */
    .day-picker {
      display: flex;
      gap: 4px;
    }

    .day-btn {
      flex: 1;
      padding: 8px 0;
      border: 1px solid var(--timer-card-divider);
      border-radius: 8px;
      background: transparent;
      color: var(--timer-card-secondary);
      font-size: 0.8em;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s;
    }

    .day-btn.active {
      background: var(--timer-card-primary);
      color: white;
      border-color: var(--timer-card-primary);
    }

    /* Editor actions */
    .editor-actions {
      display: flex;
      gap: 8px;
      margin-top: 8px;
    }

    .editor-actions button {
      flex: 1;
      padding: 10px;
      border: none;
      border-radius: 8px;
      font-size: 0.95em;
      font-weight: 500;
      cursor: pointer;
      transition: opacity 0.2s;
    }

    .save-btn {
      background: var(--timer-card-primary);
      color: white;
    }

    .cancel-btn {
      background: var(--timer-card-divider);
      color: var(--timer-card-text);
    }

    .delete-btn {
      background: var(--error-color, #db4437);
      color: white;
    }

    .editor-actions button:hover {
      opacity: 0.85;
    }
  `;
}

// Idempotent registration — guards against double-load (e.g. an old
// /local/ resource still hanging around). Without this, the second
// load throws DOMException("name already used") which aborts the whole
// module and leaves any later cards unregistered too.
if (!customElements.get("irrigation-timer-card")) {
  customElements.define("irrigation-timer-card", IrrigationTimerCard);
  // Card picker entry — only add once per page load.
  const w = window as unknown as { customCards?: unknown[] };
  w.customCards = w.customCards || [];
  if (
    !w.customCards.some(
      (c) => (c as { type?: string }).type === "irrigation-timer-card"
    )
  ) {
    w.customCards.push({
      type: "irrigation-timer-card",
      name: "Irrigation Timer",
      description: "Manage Tuya irrigation valve timer schedules",
    });
  }
}
