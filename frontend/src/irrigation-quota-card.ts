import { LitElement, html, css, nothing, PropertyValues } from "lit";
import { property, state } from "lit/decorators.js";

interface HassEntity {
  state: string;
  attributes: Record<string, unknown>;
}
interface HomeAssistant {
  states: Record<string, HassEntity>;
}

interface QuotaCardConfig {
  type: string;
  entity: string;
  name?: string;
  show_devices?: boolean;
}

export class IrrigationQuotaCard extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @state() private _config!: QuotaCardConfig;

  setConfig(config: QuotaCardConfig): void {
    if (!config.entity) {
      throw new Error("Please define the controllable-quota sensor entity");
    }
    this._config = config;
  }

  getCardSize(): number {
    return 2;
  }

  protected shouldUpdate(changed: PropertyValues): boolean {
    return changed.has("_config") || changed.has("hass");
  }

  private _num(v: unknown, fallback = 0): number {
    const n = typeof v === "number" ? v : parseFloat(String(v));
    return Number.isFinite(n) ? n : fallback;
  }

  protected render() {
    if (!this._config || !this.hass) return nothing;
    const e = this.hass.states[this._config.entity];
    if (!e) {
      return html`<ha-card>
        <div class="card-content unavailable">
          Quota sensor <code>${this._config.entity}</code> not found
        </div>
      </ha-card>`;
    }

    const used = this._num(e.state, 0);
    const limit = this._num(e.attributes.limit, 10);
    const remaining = this._num(e.attributes.remaining, Math.max(0, limit - used));
    const reset = (e.attributes.reset_date as string) ?? "";
    const devices = Array.isArray(e.attributes.devices)
      ? (e.attributes.devices as string[])
      : [];
    const name =
      this._config.name ??
      (e.attributes.friendly_name as string) ??
      "Controllable quota";

    const pct = limit > 0 ? Math.min(100, (used / limit) * 100) : 0;
    const level = remaining <= 0 ? "crit" : remaining <= 3 ? "warn" : "ok";

    return html`
      <ha-card>
        <div class="card-header">
          <ha-icon icon="mdi:cloud-lock-outline"></ha-icon>
          <span>${name}</span>
          <span class="pill ${level}">${remaining} left</span>
        </div>
        <div class="card-content">
          <div class="count">
            <span class="big">${used}</span><span class="dim"> / ${limit}</span>
            <span class="label"> controllable devices used this month</span>
          </div>
          <div class="bar">
            <div class="fill ${level}" style="width:${pct}%"></div>
          </div>
          <div class="sub">
            ${remaining <= 0
              ? html`<span class="crit-text"
                  >Cap reached — further new-device commands are blocked until
                  reset.</span
                >`
              : html`${remaining} command slot${remaining === 1 ? "" : "s"} left`}
            ${reset ? html` · resets ${reset}` : nothing}
          </div>
          ${this._config.show_devices && devices.length
            ? html`<div class="devices">
                ${devices.map((d) => html`<code>${d}</code>`)}
              </div>`
            : nothing}
        </div>
      </ha-card>
    `;
  }

  static styles = css`
    :host {
      --q-ok: var(--success-color, #4caf50);
      --q-warn: var(--warning-color, #ff9800);
      --q-crit: var(--error-color, #f44336);
      --q-text: var(--primary-text-color, #212121);
      --q-dim: var(--secondary-text-color, #727272);
      --q-divider: var(--divider-color, #e0e0e0);
    }
    .card-header {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 16px 16px 0;
      font-size: 1.1em;
      font-weight: 500;
      color: var(--q-text);
    }
    .card-header ha-icon {
      color: var(--q-dim);
    }
    .card-header span:nth-child(2) {
      flex: 1;
    }
    .pill {
      font-size: 0.75em;
      padding: 2px 8px;
      border-radius: 10px;
      font-weight: 600;
      color: white;
    }
    .pill.ok {
      background: var(--q-ok);
    }
    .pill.warn {
      background: var(--q-warn);
    }
    .pill.crit {
      background: var(--q-crit);
    }
    .card-content {
      padding: 12px 16px 16px;
    }
    .count {
      display: flex;
      align-items: baseline;
      flex-wrap: wrap;
      gap: 4px;
      font-variant-numeric: tabular-nums;
    }
    .count .big {
      font-size: 2em;
      font-weight: 600;
      color: var(--q-text);
    }
    .count .dim {
      font-size: 1.2em;
      color: var(--q-dim);
    }
    .count .label {
      font-size: 0.85em;
      color: var(--q-dim);
      margin-left: 6px;
    }
    .bar {
      height: 8px;
      background: var(--q-divider);
      border-radius: 4px;
      overflow: hidden;
      margin: 10px 0 6px;
    }
    .fill {
      height: 100%;
      transition: width 0.4s linear;
    }
    .fill.ok {
      background: var(--q-ok);
    }
    .fill.warn {
      background: var(--q-warn);
    }
    .fill.crit {
      background: var(--q-crit);
    }
    .sub {
      font-size: 0.85em;
      color: var(--q-dim);
    }
    .crit-text {
      color: var(--q-crit);
      font-weight: 500;
    }
    .devices {
      margin-top: 10px;
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
    }
    .devices code {
      font-size: 0.7em;
      background: var(--q-divider);
      padding: 1px 5px;
      border-radius: 4px;
      color: var(--q-dim);
    }
    .unavailable {
      color: var(--q-dim);
    }
  `;
}

if (!customElements.get("irrigation-quota-card")) {
  customElements.define("irrigation-quota-card", IrrigationQuotaCard);
  const w = window as unknown as { customCards?: unknown[] };
  w.customCards = w.customCards || [];
  if (
    !w.customCards.some(
      (c) => (c as { type?: string }).type === "irrigation-quota-card"
    )
  ) {
    w.customCards.push({
      type: "irrigation-quota-card",
      name: "Irrigation Quota",
      description:
        "Shows how many controllable-device units a Tuya OpenAPI hub has used this month.",
    });
  }
}
