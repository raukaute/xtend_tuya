import { LitElement, html, css, nothing, PropertyValues } from "lit";
import { property, state } from "lit/decorators.js";

interface HassEntity {
  state: string;
  attributes: Record<string, unknown>;
  last_changed?: string;
}
interface HomeAssistant {
  states: Record<string, HassEntity>;
  entities?: Record<string, { device_id?: string | null }>;
  callService?: (domain: string, service: string, data: unknown) => void;
  callWS?: <T = unknown>(msg: Record<string, unknown>) => Promise<T>;
  callApi?: <T = unknown>(method: string, path: string) => Promise<T>;
}

type LocationMap = Record<string, { home?: string | null; room?: string | null }>;

interface LovelaceView {
  path?: string;
  cards?: unknown[];
  sections?: { cards?: unknown[] }[];
}
interface LovelaceConfig {
  views?: LovelaceView[];
}

interface RoomGroupsConfig {
  type: string;
  title?: string;
}

interface ValveRow {
  name: string;
  state: string; // open | closed | unavailable | unknown
  entity: string | null; // valve entity for tap
  path: string | null; // detail-view path for the link (null = no view)
}

// HA derives each per-valve detail view's path by slugifying its title (the
// valve name): lowercase, every run of non-alphanumerics -> single hyphen,
// trimmed. e.g. "FG Green Carpet 01 (809)" -> "fg-green-carpet-01-809".
function slugify(s: string): string {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

const REGISTRY_SUFFIX = "_irrigation_timer_registry";
const UNASSIGNED = "Unassigned";

// The detail/tile entity is the official valve.* entity; derive it from the
// fdm5kw timer-registry sensor's entity_id (sensor.<slug>_irrigation_timer_
// registry -> valve.<slug>_valve). Falls back to a name match if the slug
// doesn't line up (a few valves carry a legacy slug).
function deriveValveEntity(
  registryId: string,
  hass: HomeAssistant,
  valveName: string
): string | null {
  const slug = registryId
    .replace(/^sensor\./, "")
    .replace(new RegExp(`${REGISTRY_SUFFIX}$`), "");
  const guess = `valve.${slug}_valve`;
  if (hass.states[guess]) return guess;
  // name fallback: official valve entity friendly_name is "<name> Valve"
  const target = `${valveName} Valve`;
  for (const id of Object.keys(hass.states)) {
    if (!id.startsWith("valve.")) continue;
    if (hass.states[id].attributes?.friendly_name === target) return id;
  }
  return null;
}

export class IrrigationRoomGroups extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @state() private _config!: RoomGroupsConfig;
  // registry_entity -> detail view path, learned from the lovelace config so
  // links survive valve renames (the per-valve view paths are slugs of OLD
  // titles and don't always match the live valve_name).
  @state() private _pathMap: Record<string, string> | null = null;
  private _pathLoadStarted = false;
  // Cloud-backed device -> home/room map from the backend. Authoritative over
  // live sensor attrs: an unavailable registry sensor loses its attrs, which
  // used to dump every offline valve into "Unassigned" (ticket c802BqOn).
  @state() private _locMap: LocationMap | null = null;
  private _locLoadStarted = false;

  setConfig(config: RoomGroupsConfig): void {
    this._config = config;
  }

  // Build registry_entity -> view-path once, from this dashboard's config. Each
  // per-valve detail view holds an irrigation-control-card whose registry_entity
  // is the same sensor this card groups on — an exact, rename-proof key.
  private async _loadPaths(): Promise<void> {
    if (this._pathLoadStarted || !this.hass?.callWS) return;
    this._pathLoadStarted = true;
    const urlPath =
      window.location.pathname.split("/").filter(Boolean)[0] ?? "lovelace";
    let cfg: LovelaceConfig;
    try {
      cfg = await this.hass.callWS<LovelaceConfig>({
        type: "lovelace/config",
        url_path: urlPath,
      });
    } catch {
      return; // leave _pathMap null -> chips fall back to slug links
    }
    const map: Record<string, string> = {};
    const scan = (node: unknown, path: string | undefined): void => {
      if (Array.isArray(node)) {
        for (const n of node) scan(n, path);
        return;
      }
      if (node && typeof node === "object") {
        const o = node as Record<string, unknown>;
        if (
          typeof o.type === "string" &&
          o.type.includes("irrigation-control-card") &&
          typeof o.registry_entity === "string" &&
          path
        ) {
          map[o.registry_entity] = path;
        }
        for (const k of Object.keys(o)) scan(o[k], path);
      }
    };
    for (const v of cfg.views ?? []) {
      scan(v.cards, v.path);
      scan(v.sections, v.path);
    }
    this._pathMap = map;
  }

  private async _loadLocations(): Promise<void> {
    if (this._locLoadStarted || !this.hass?.callApi) return;
    this._locLoadStarted = true;
    try {
      const r = await this.hass.callApi<{ locations?: LocationMap }>(
        "GET",
        "xtend_tuya/valve_locations"
      );
      this._locMap = r?.locations ?? {};
    } catch {
      // leave null -> grouping falls back to live sensor attrs
    }
  }

  getCardSize(): number {
    return 6;
  }

  protected shouldUpdate(changed: PropertyValues): boolean {
    return (
      changed.has("_config") ||
      changed.has("hass") ||
      changed.has("_pathMap") ||
      changed.has("_locMap")
    );
  }

  // home -> room -> valves, built fresh from the timer-registry sensors that
  // carry valve_home / valve_room (filled by the backend location service).
  private _groups(): Map<string, Map<string, ValveRow[]>> {
    const homes = new Map<string, Map<string, ValveRow[]>>();
    for (const id of Object.keys(this.hass.states)) {
      if (!id.endsWith(REGISTRY_SUFFIX)) continue;
      const e = this.hass.states[id];
      const a = e.attributes;
      // Offline valves have no valve_name attr; fall back to friendly_name but
      // strip the " Irrigation timer registry" suffix so the chip reads clean.
      const raw = (a.valve_name as string) || (a.friendly_name as string) || id;
      const name =
        raw.replace(/\s*Irrigation timer registry$/i, "").trim() || raw;
      // Location: backend map first (keyed by Tuya id from attrs, or by HA
      // device id when the sensor is unavailable and attrs are stripped),
      // then live attrs for old backends without the view.
      const tuyaId = (a.device_id as string) || null;
      const haDevId = this.hass.entities?.[id]?.device_id ?? null;
      const loc =
        (tuyaId ? this._locMap?.[tuyaId] : undefined) ??
        (haDevId ? this._locMap?.[haDevId] : undefined);
      const home =
        (loc?.home || (a.valve_home as string) || "").trim() || UNASSIGNED;
      const room =
        (loc?.room || (a.valve_room as string) || "").trim() || UNASSIGNED;
      const valveEntity = deriveValveEntity(id, this.hass, name);
      const state = valveEntity
        ? this.hass.states[valveEntity]?.state ?? "unknown"
        : "unknown";
      if (!homes.has(home)) homes.set(home, new Map());
      const rooms = homes.get(home)!;
      if (!rooms.has(room)) rooms.set(room, []);
      rooms.get(room)!.push({
        name,
        state,
        entity: valveEntity,
        path: this._detailPath(id, name),
      });
    }
    // sort valves by name within each room
    for (const rooms of homes.values())
      for (const list of rooms.values())
        list.sort((x, y) => x.name.localeCompare(y.name, undefined, { numeric: true }));
    return homes;
  }

  private _dotClass(state: string): string {
    if (state === "open" || state === "on") return "on";
    if (state === "closed" || state === "off") return "off";
    return "na";
  }

  // The dashboard root, derived from the current URL (e.g. the overview at
  // /dashboard-valves/overview -> /dashboard-valves), so the chip links point
  // at this dashboard's per-valve detail views regardless of its url_path.
  private _dashboardBase(): string {
    const seg = window.location.pathname.split("/").filter(Boolean);
    return seg.length ? `/${seg[0]}` : "";
  }

  // Detail-view path for a valve. Prefer the learned registry_entity -> path
  // map (authoritative: if loaded and missing, the valve has no detail view, so
  // no link). Until the map loads, fall back to a name slug as a best effort.
  private _detailPath(registryId: string, name: string): string | null {
    const base = this._dashboardBase();
    if (this._pathMap) {
      const p = this._pathMap[registryId];
      return p ? `${base}/${p}` : null;
    }
    const slug = slugify(name);
    return slug ? `${base}/${slug}` : null;
  }

  // SPA navigation to a detail view (no full reload) — the standard custom-card
  // pattern: push history + fire location-changed so HA's router picks it up.
  private _navigate(e: Event, path: string): void {
    e.preventDefault();
    window.history.pushState(null, "", path);
    this.dispatchEvent(
      new Event("location-changed", { bubbles: true, composed: true })
    );
  }

  protected render() {
    if (!this._config || !this.hass) return nothing;
    void this._loadPaths(); // one-shot, guarded
    void this._loadLocations(); // one-shot, guarded
    const homes = this._groups();
    if (homes.size === 0) {
      return html`<ha-card
        ><div class="empty">No valve home/room data yet.</div></ha-card
      >`;
    }

    const multiHome = homes.size > 1;
    const homeNames = [...homes.keys()].sort((a, b) => a.localeCompare(b));

    return html`
      <ha-card>
        <div class="card-header">
          <ha-icon icon="mdi:home-map-marker"></ha-icon>
          <span>${this._config.title ?? "Valves by room"}</span>
        </div>
        <div class="card-content">
          ${homeNames.map((home) => {
            const rooms = homes.get(home)!;
            const roomNames = [...rooms.keys()].sort((a, b) => {
              if (a === UNASSIGNED) return 1;
              if (b === UNASSIGNED) return -1;
              return a.localeCompare(b);
            });
            return html`
              ${multiHome
                ? html`<div class="home">${home}</div>`
                : nothing}
              ${roomNames.map((room) => {
                const list = rooms.get(room)!;
                const on = list.filter(
                  (v) => v.state === "open" || v.state === "on"
                ).length;
                return html`
                  <div class="room">
                    <div class="room-head">
                      <span class="room-name">${room}</span>
                      <span class="room-count"
                        >${on > 0 ? html`<span class="on-count">${on} on</span> · ` : nothing}${list.length}</span
                      >
                    </div>
                    <div class="chips">
                      ${list.map((v) =>
                        v.path
                          ? html`
                              <a
                                class="chip ${this._dotClass(v.state)}"
                                href=${v.path}
                                title=${v.state}
                                @click=${(e: Event) =>
                                  this._navigate(e, v.path as string)}
                              >
                                <span class="dot"></span>${v.name}
                              </a>
                            `
                          : html`
                              <span
                                class="chip nolink ${this._dotClass(v.state)}"
                                title=${v.state}
                              >
                                <span class="dot"></span>${v.name}
                              </span>
                            `
                      )}
                    </div>
                  </div>
                `;
              })}
            `;
          })}
        </div>
      </ha-card>
    `;
  }

  static styles = css`
    :host {
      --rg-text: var(--primary-text-color, #212121);
      --rg-dim: var(--secondary-text-color, #727272);
      --rg-divider: var(--divider-color, #e0e0e0);
      --rg-on: var(--success-color, #4caf50);
      --rg-off: var(--secondary-text-color, #9e9e9e);
      --rg-na: var(--warning-color, #ff9800);
    }
    .card-header {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 16px 16px 4px;
      font-size: 1.1em;
      font-weight: 500;
      color: var(--rg-text);
    }
    .card-header ha-icon {
      color: var(--rg-dim);
    }
    .card-content {
      padding: 8px 16px 16px;
    }
    .home {
      font-size: 0.95em;
      font-weight: 600;
      color: var(--rg-text);
      margin: 12px 0 4px;
    }
    .room {
      margin: 10px 0;
    }
    .room-head {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      border-bottom: 1px solid var(--rg-divider);
      padding-bottom: 4px;
      margin-bottom: 6px;
    }
    .room-name {
      font-size: 0.9em;
      font-weight: 500;
      color: var(--rg-text);
      text-transform: uppercase;
      letter-spacing: 0.4px;
    }
    .room-count {
      font-size: 0.8em;
      color: var(--rg-dim);
      font-variant-numeric: tabular-nums;
    }
    .on-count {
      color: var(--rg-on);
      font-weight: 600;
    }
    .chips {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .chip {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      border: 1px solid var(--rg-divider);
      border-radius: 14px;
      background: transparent;
      color: var(--rg-text);
      font-size: 0.82em;
      cursor: pointer;
      text-decoration: none;
    }
    .chip:hover {
      border-color: var(--rg-text);
    }
    .chip.nolink {
      cursor: default;
      opacity: 0.85;
    }
    .chip .dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--rg-off);
      flex: 0 0 auto;
    }
    .chip.on .dot {
      background: var(--rg-on);
    }
    .chip.on {
      border-color: var(--rg-on);
    }
    .chip.na .dot {
      background: var(--rg-na);
    }
    .empty {
      padding: 16px;
      color: var(--rg-dim);
    }
  `;
}

if (!customElements.get("irrigation-room-groups")) {
  customElements.define("irrigation-room-groups", IrrigationRoomGroups);
  const w = window as unknown as { customCards?: unknown[] };
  w.customCards = w.customCards || [];
  if (
    !w.customCards.some(
      (c) => (c as { type?: string }).type === "irrigation-room-groups"
    )
  ) {
    w.customCards.push({
      type: "irrigation-room-groups",
      name: "Irrigation Valves by Room",
      description:
        "Groups irrigation valves by home and room (from valve_home/valve_room) for quick location.",
    });
  }
}
