import path from "path";
import type { StorybookConfig } from "@storybook/react-vite";

const config: StorybookConfig = {
  framework: "@storybook/react-vite",
  stories: ["../stories/**/*.stories.@(ts|tsx)"],
  addons: ["@storybook/addon-essentials", "@storybook/addon-a11y"],
  docs: {
    autodocs: "tag",
  },
  async viteFinal(baseConfig) {
    baseConfig.resolve = baseConfig.resolve ?? {};
    baseConfig.resolve.alias = {
      ...(baseConfig.resolve.alias ?? {}),
      "@": path.resolve(__dirname, "../src"),
    };
    return baseConfig;
  },
};

export default config;
