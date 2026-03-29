import type { Config } from "tailwindcss";
import { tailwindExtend } from "./src/styles/tailwind-tokens";

const config: Config = {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  important: '#root',
  theme: {
    extend: tailwindExtend,
  },
  plugins: [],
  // Enable preflight for consistent base styles
  corePlugins: {
    preflight: true,
  },
};

export default config;
