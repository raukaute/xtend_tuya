import { LitElement, html, css, nothing, PropertyValues } from "lit";
import { property, state } from "lit/decorators.js";
import { IrrigationValveMatrixConfig, ValveMatrixRow } from "./models";

// HA types (minimal — mirrors the other cards in this bundle).
interface HomeAssistant {
  states: Record<string, HassEntity>;
  callWS<T>(msg: Record<string, unknown>): Promise<T>;
}

interface HassEntity {
  state: string;
  attributes: Record<string, unknown>;
}

/** One compressed state point from history/history_during_period. */
interface HistoryPoint {
  /** state */
  s: string;
  /** last_updated, epoch seconds (float) */
  lu: number;
}

/** A rendered timeline segment: [leftFraction, widthFraction, on?]. */
interface Segment {
  left: number;
  width: number;
  on: boolean;
}

const HISTORY_REFRESH_MS = 60_000;

export class IrrigationValveMatrix extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @state() private _config!: IrrigationValveMatrixConfig;
  /** entity_id -> rendered segments over the window. */
  @state() private _segments: Record<string, Segment[]> = {};

  private _refreshHandle: number | null = null;
  private _fetching = false;

  setConfig(config: IrrigationValveMatrixConfig): void {
    if (!config.valves || !Array.isArray(config.valves)) {
      throw new Error("irrigation-valve-matrix: `valves` list is required");
    }
    this._config = config;
  }

  getCardSize(): number {
    return Math.max(3, Math.ceil((this._config?.valves?.length ?? 0) / 2));
  }

  connectedCallback(): void {
    super.connectedCallback();
    this._refreshHandle = window.setInterval(
      () => void this._fetchHistory(),
      HISTORY_REFRESH_MS
    );
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    if (this._refreshHandle !== null) {
      window.clearInterval(this._refreshHandle);
      this._refreshHandle = null;
    }
  }

  protected updated(changedProps: PropertyValues): void {
    // First time we get hass (or config), pull the history once.
    if (
      (changedProps.has("hass") || changedProps.has("_config")) &&
      this.hass &&
      this._config &&
      Object.keys(this._segments).length === 0
    ) {
      void this._fetchHistory();
    }
  }

  private _hours(): number {
    return this._config.hours ?? 24;
  }

  private async _fetchHistory(): Promise<void> {
    if (!this.hass || !this._config || this._fetching) return;
    const entities = this._config.valves
      .map((v) => v.switch)
      .filter((e): e is string => !!e);
    if (entities.length === 0) return;

    this._fetching = true;
    const now = Date.now();
    const start = now - this._hours() * 3_600_000;
    try {
      const raw = await this.hass.callWS<Record<string, HistoryPoint[]>>({
        type: "history/history_during_period",
        start_time: new Date(start).toISOString(),
        end_time: new Date(now).toISOString(),
        entity_ids: entities,
        minimal_response: true,
        no_attributes: true,
      });
      const next: Record<string, Segment[]> = {};
      for (const entity of entities) {
        next[entity] = this._buildSegments(raw[entity] ?? [], start, now);
      }
      this._segments = next;
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("irrigation-valve-matrix: history fetch failed", err);
    } finally {
      this._fetching = false;
    }
  }

  /** Convert compressed history points into on/off fractional segments. */
  private _buildSegments(
    points: HistoryPoint[],
    startMs: number,
    endMs: number
  ): Segment[] {
    const span = endMs - startMs;
    if (span <= 0 || points.length === 0) return [];
    const segs: Segment[] = [];
    for (let i = 0; i < points.length; i++) {
      const p = points[i];
      const tStart = Math.max(p.lu * 1000, startMs);
      const tEnd =
        i + 1 < points.length ? Math.min(points[i + 1].lu * 1000, endMs) : endMs;
      if (tEnd <= tStart) continue;
      segs.push({
        left: (tStart - startMs) / span,
        width: (tEnd - tStart) / span,
        on: p.s === "on",
      });
    }
    return segs;
  }

  private _batteryText(entity?: string): string {
    if (!entity) return "—";
    const e = this.hass.states[entity];
    if (!e || e.state === "unavailable" || e.state === "unknown") {
      return "Unavailable";
    }
    const n = parseFloat(e.state);
    if (!Number.isFinite(n)) return e.state;
    const unit = (e.attributes.unit_of_measurement as string) ?? "%";
    return `${Math.round(n)}${unit}`;
  }

  private _batteryClass(entity?: string): string {
    if (!entity) return "muted";
    const e = this.hass.states[entity];
    if (!e || e.state === "unavailable" || e.state === "unknown") return "muted";
    const n = parseFloat(e.state);
    if (Number.isFinite(n) && n <= 20) return "low";
    return "";
  }

  private _navigate(path?: string): void {
    if (!path) return;
    // view_path is relative to this dashboard; build /<dashboard>/<path>.
    const base = window.location.pathname.split("/")[1] || "lovelace";
    const url = path.startsWith("/") ? path : `/${base}/${path}`;
    window.history.pushState(null, "", url);
    this.dispatchEvent(
      new Event("location-changed", { bubbles: true, composed: true })
    );
  }

  private _renderRow(v: ValveMatrixRow) {
    const segs = v.switch ? this._segments[v.switch] ?? [] : [];
    return html`
      <div
        class="row ${v.path ? "clickable" : ""}"
        @click=${() => this._navigate(v.path)}
      >
        <div class="name" title=${v.name}>${v.name}</div>
        <div class="bar">
          ${segs.map(
            (s) => html`<span
              class="seg ${s.on ? "on" : "off"}"
              style="left:${(s.left * 100).toFixed(3)}%;width:${(
                s.width * 100
              ).toFixed(3)}%"
            ></span>`
          )}
        </div>
        <div class="battery ${this._batteryClass(v.battery)}">
          ${this._batteryText(v.battery)}
        </div>
      </div>
    `;
  }

  protected render() {
    if (!this._config) return nothing;
    return html`
      <ha-card>
        ${this._config.title
          ? html`<h1 class="card-header">${this._config.title}</h1>`
          : nothing}
        <div class="grid">
          ${this._config.valves.map((v) => this._renderRow(v))}
        </div>
      </ha-card>
    `;
  }

  static styles = css`
    ha-card {
      padding-bottom: 8px;
    }
    .card-header {
      font-size: 1.4rem;
      font-weight: 400;
      padding: 16px 16px 8px;
      margin: 0;
    }
    .grid {
      display: flex;
      flex-direction: column;
    }
    .row {
      display: grid;
      grid-template-columns: 150px 1fr 64px;
      align-items: center;
      gap: 12px;
      height: 32px;
      padding: 0 16px;
    }
    .row.clickable {
      cursor: pointer;
    }
    .row.clickable:hover {
      background: var(--secondary-background-color);
    }
    .name {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 0.9rem;
    }
    .bar {
      position: relative;
      height: 18px;
      border-radius: 3px;
      background: var(--disabled-color, #bdbdbd);
      opacity: 0.55;
      overflow: hidden;
    }
    .seg {
      position: absolute;
      top: 0;
      bottom: 0;
    }
    .seg.off {
      background: transparent;
    }
    .seg.on {
      background: var(--state-switch-active-color, #f9a825);
    }
    .battery {
      text-align: right;
      font-variant-numeric: tabular-nums;
      font-size: 0.9rem;
    }
    .battery.muted {
      color: var(--secondary-text-color);
    }
    .battery.low {
      color: var(--error-color, #db4437);
      font-weight: 600;
    }
  `;
}

// Idempotent registration — guards against double-load.
if (!customElements.get("irrigation-valve-matrix")) {
  customElements.define("irrigation-valve-matrix", IrrigationValveMatrix);
  const w = window as unknown as { customCards?: unknown[] };
  w.customCards = w.customCards || [];
  if (
    !w.customCards.some(
      (c) => (c as { type?: string }).type === "irrigation-valve-matrix"
    )
  ) {
    w.customCards.push({
      type: "irrigation-valve-matrix",
      name: "Irrigation Valve Matrix",
      description:
        "One aligned row per valve: name, watering on/off timeline, battery %.",
    });
  }
}
