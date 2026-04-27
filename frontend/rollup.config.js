import resolve from "@rollup/plugin-node-resolve";
import typescript from "@rollup/plugin-typescript";
import terser from "@rollup/plugin-terser";

export default {
  input: "src/irrigation-timer-card.ts",
  output: {
    // Build straight into the integration's served cards dir so HACS
    // distributes the bundled card alongside the integration code.
    file: "../custom_components/xtend_tuya/cards/irrigation-timer-card.js",
    format: "es",
  },
  plugins: [resolve(), typescript(), terser()],
};
