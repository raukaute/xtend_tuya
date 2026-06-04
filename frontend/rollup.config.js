import resolve from "@rollup/plugin-node-resolve";
import typescript from "@rollup/plugin-typescript";
import terser from "@rollup/plugin-terser";

const cardsOutDir = "../custom_components/xtend_tuya/cards";

const card = (name, format = "es") => ({
  input: `src/${name}.ts`,
  output: {
    // Build straight into the integration's served cards dir so HACS
    // distributes the bundled card alongside the integration code.
    file: `${cardsOutDir}/${name}.js`,
    format,
    name: format === "iife" ? name.replace(/-/g, "_") : undefined,
  },
  plugins: [resolve(), typescript(), terser()],
});

export default [
  card("irrigation-timer-card"),
  card("irrigation-control-card"),
  // Strategy bundle has zero deps (no Lit imports) and is tiny; ship it
  // as a classic IIFE so it can load via a blocking `<script>` tag and
  // register its custom element synchronously during page parse — the
  // ES-module path leaves Simon's first navigation racing HA's hard 5 s
  // strategy-element timeout on Nabu Casa cold loads.
  card("irrigation-valves-strategy", "iife"),
];
