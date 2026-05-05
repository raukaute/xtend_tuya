import resolve from "@rollup/plugin-node-resolve";
import typescript from "@rollup/plugin-typescript";
import terser from "@rollup/plugin-terser";

const cardsOutDir = "../custom_components/xtend_tuya/cards";

const card = (name) => ({
  input: `src/${name}.ts`,
  output: {
    // Build straight into the integration's served cards dir so HACS
    // distributes the bundled card alongside the integration code.
    file: `${cardsOutDir}/${name}.js`,
    format: "es",
  },
  plugins: [resolve(), typescript(), terser()],
});

export default [
  card("irrigation-timer-card"),
  card("irrigation-control-card"),
  card("irrigation-valves-strategy"),
];
