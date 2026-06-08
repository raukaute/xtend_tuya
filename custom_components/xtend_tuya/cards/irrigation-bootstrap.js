// Self-healing card loader for the xtend_tuya irrigation dashboard.
//
// Home Assistant injects every bundled card as a fire-and-forget inline
//   <script>import("/xtend_tuya_static/cards/<name>.js?v=<mtime>")</script>
// The promises are never awaited and their rejections are swallowed, so a
// single dropped import has no retry. Combined with the bundles' guarded
// registration (`customElements.get(x) || customElements.define(x, …)`),
// that means: if one boot import is served a stale or partial body from the
// HA workbox service worker (common right after a HACS update, where the SW
// still holds the 31-day-cached previous bundle), the element never
// registers for the whole page session and its card renders a permanent
// "Configuration error" until the user manually clears the service worker.
//
// This watchdog closes that gap. It polls for any custom element that should
// be defined but isn't, and re-imports its bundle with a unique cache-busting
// query (`?heal=<ts>`). The unique query bypasses BOTH the service worker and
// the browser's errored-module record, forcing a fresh, correct evaluation.
// Re-evaluation is safe because every bundle's define is idempotent. Once all
// elements are registered (HA's hui-card re-renders automatically when an
// element becomes defined), the poll stops.

const PREFIX = "/xtend_tuya_static/cards/";

// element name -> bundle file that defines it
const BUNDLES = {
  "irrigation-quota-card": "irrigation-quota-card.js",
  "irrigation-control-card": "irrigation-control-card.js",
  "irrigation-timer-card": "irrigation-timer-card.js",
  "irrigation-valve-matrix": "irrigation-valves-strategy.js",
  "irrigation-refresh-button": "irrigation-valves-strategy.js",
  "ll-strategy-irrigation-valves": "irrigation-valves-strategy.js",
  "ll-strategy-dashboard-irrigation-valves": "irrigation-valves-strategy.js",
};

const allDefined = () =>
  Object.keys(BUNDLES).every((el) => customElements.get(el));

async function heal() {
  // unique set of bundle files that own at least one missing element
  const files = [
    ...new Set(
      Object.entries(BUNDLES)
        .filter(([el]) => !customElements.get(el))
        .map(([, file]) => file),
    ),
  ];
  for (const file of files) {
    try {
      await import(`${PREFIX}${file}?heal=${Date.now()}`);
    } catch (e) {
      // transient (SW miss / relay hiccup); the next poll retries
    }
  }
}

if (!allDefined()) {
  let attempts = 0;
  const timer = setInterval(async () => {
    await heal();
    // give up after ~12 s — by then any real failure is a server-side issue
    // the watchdog can't fix, and we stop polling to avoid a busy loop.
    if (allDefined() || ++attempts > 24) clearInterval(timer);
  }, 500);
  // kick one immediate attempt so a fast heal doesn't wait for the first tick
  heal();
}
