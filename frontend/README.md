# Frontend assets for xtend_tuya

Source for the Lovelace cards bundled with the xtend_tuya integration.
Build output lands directly under `custom_components/xtend_tuya/cards/`,
where the integration registers it as a frontend resource on setup, so
HACS users get the card without any separate deployment.

## Layout

```
frontend/
├── src/                irrigation-timer-card source (TypeScript / lit)
├── dashboards/         starter dashboard YAML(s)
├── ha-scripts/         legacy helper scripts (kept for reference)
├── package.json
├── rollup.config.js
└── tsconfig.json
```

## Build

```sh
cd frontend
npm install
npm run build         # → ../custom_components/xtend_tuya/cards/irrigation-timer-card.js
```

Commit the rebuilt JS alongside source changes. Bumping
`custom_components/xtend_tuya/manifest.json:version` triggers HACS
to push the update; the registered card URL is mtime-cache-busted
so browsers refresh on upgrade.

## Dashboards

`dashboards/valve-dashboard.yaml` is a starter Lovelace YAML for the
fdm5kw irrigation valves. Copy it into HA → Settings → Dashboards →
Raw Config Editor on a fresh dashboard. Each timer card auto-shows
the SmartLife `custom_name` via the registry sensor's `valve_name`
attribute when no `name:` is set.
