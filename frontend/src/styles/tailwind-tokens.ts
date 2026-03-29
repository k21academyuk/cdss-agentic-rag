// src/styles/tailwind-tokens.ts
import { tokens } from "./design-tokens";

export const tailwindExtend = {
  colors: {
    clinical: {
      alert: tokens.color.alert,
      confidence: tokens.color.confidence,
      agent: tokens.color.agent,
      surface: tokens.color.surface,
      text: tokens.color.text,
      border: tokens.color.border,
    },
  },
  fontFamily: {
    clinical: [tokens.typography.fontFamily.clinical],
    mono: [tokens.typography.fontFamily.mono],
  },
  fontSize: tokens.typography.fontSize,
  borderRadius: tokens.radius,
  boxShadow: tokens.shadow,
  spacing: tokens.spacing,
  zIndex: tokens.zIndex,
};
