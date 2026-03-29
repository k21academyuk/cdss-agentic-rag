/**
 * CDSS Typography Configuration
 *
 * Typography system pairing Manrope for UI headings and IBM Plex Sans for
 * dense clinical text/content.
 *
 * @module typography
 */

import type { TypographyOptions } from "@mui/material/styles/createTypography";

// ============================================================================
// FONT FAMILY
// ============================================================================

/**
 * Font family stack definitions.
 */
export const fontFamily = {
  heading: "\"Manrope\", \"Segoe UI\", \"Helvetica Neue\", Arial, sans-serif",
  clinical: "\"IBM Plex Sans\", \"Segoe UI\", \"Helvetica Neue\", Arial, sans-serif",
  // Backward-compatible alias used across existing components.
  primary: "\"IBM Plex Sans\", \"Segoe UI\", \"Helvetica Neue\", Arial, sans-serif",
  monospace: "\"JetBrains Mono\", \"Fira Code\", \"Consolas\", monospace",
} as const;

// ============================================================================
// FONT SIZE SCALE
// ============================================================================

export const fontSize = {
  xs: "0.75rem", // 12px
  sm: "0.875rem", // 14px
  base: "1rem", // 16px
  lg: "1.125rem", // 18px
  xl: "1.25rem", // 20px
  "2xl": "1.5rem", // 24px
  "3xl": "1.75rem", // 28px
  "4xl": "2rem", // 32px
  "5xl": "2.25rem", // 36px
  "6xl": "2.5rem", // 40px
  "7xl": "2.75rem", // 44px
  "8xl": "3rem", // 48px
} as const;

// ============================================================================
// FONT WEIGHT SCALE
// ============================================================================

export const fontWeight = {
  light: 300,
  regular: 400,
  medium: 500,
  semibold: 600,
  bold: 700,
} as const;

// ============================================================================
// LINE HEIGHT SCALE
// ============================================================================

export const lineHeight = {
  tight: 1,
  snug: 1.25,
  normal: 1.5,
  relaxed: 1.625,
  loose: 2,
} as const;

// ============================================================================
// LETTER SPACING SCALE
// ============================================================================

export const letterSpacing = {
  tighter: "-0.025em",
  tight: "-0.015em",
  normal: "0",
  wide: "0.025em",
  wider: "0.05em",
  widest: "0.1em",
} as const;

// ============================================================================
// MUI TYPOGRAPHY OPTIONS
// ============================================================================

export const typographyOptions: TypographyOptions = {
  fontFamily: fontFamily.clinical,
  fontSize: 16,
  htmlFontSize: 16,
  fontWeightLight: fontWeight.light,
  fontWeightRegular: fontWeight.regular,
  fontWeightMedium: fontWeight.medium,
  fontWeightBold: fontWeight.bold,

  // Heading styles (Manrope)
  h1: {
    fontFamily: fontFamily.heading,
    fontSize: fontSize["7xl"],
    fontWeight: fontWeight.bold,
    lineHeight: lineHeight.tight,
    letterSpacing: letterSpacing.tighter,
  },
  h2: {
    fontFamily: fontFamily.heading,
    fontSize: fontSize["6xl"],
    fontWeight: fontWeight.bold,
    lineHeight: lineHeight.tight,
    letterSpacing: letterSpacing.tighter,
  },
  h3: {
    fontFamily: fontFamily.heading,
    fontSize: fontSize["5xl"],
    fontWeight: fontWeight.semibold,
    lineHeight: lineHeight.snug,
    letterSpacing: letterSpacing.tight,
  },
  h4: {
    fontFamily: fontFamily.heading,
    fontSize: fontSize["4xl"],
    fontWeight: fontWeight.semibold,
    lineHeight: lineHeight.snug,
    letterSpacing: letterSpacing.tight,
  },
  h5: {
    fontFamily: fontFamily.heading,
    fontSize: fontSize["3xl"],
    fontWeight: fontWeight.medium,
    lineHeight: lineHeight.snug,
    letterSpacing: letterSpacing.normal,
  },
  h6: {
    fontFamily: fontFamily.heading,
    fontSize: fontSize["2xl"],
    fontWeight: fontWeight.medium,
    lineHeight: lineHeight.normal,
    letterSpacing: letterSpacing.normal,
  },

  // Dense clinical text (IBM Plex Sans)
  body1: {
    fontFamily: fontFamily.clinical,
    fontSize: fontSize.base,
    fontWeight: fontWeight.regular,
    lineHeight: lineHeight.relaxed,
    letterSpacing: letterSpacing.normal,
  },
  body2: {
    fontFamily: fontFamily.clinical,
    fontSize: fontSize.sm,
    fontWeight: fontWeight.regular,
    lineHeight: lineHeight.normal,
    letterSpacing: letterSpacing.normal,
  },
  subtitle1: {
    fontFamily: fontFamily.heading,
    fontSize: fontSize.lg,
    fontWeight: fontWeight.medium,
    lineHeight: lineHeight.normal,
    letterSpacing: letterSpacing.tight,
  },
  subtitle2: {
    fontFamily: fontFamily.clinical,
    fontSize: fontSize.base,
    fontWeight: fontWeight.medium,
    lineHeight: lineHeight.normal,
    letterSpacing: letterSpacing.tight,
  },
  caption: {
    fontFamily: fontFamily.clinical,
    fontSize: fontSize.xs,
    fontWeight: fontWeight.regular,
    lineHeight: lineHeight.normal,
    letterSpacing: letterSpacing.wide,
  },
  overline: {
    fontFamily: fontFamily.heading,
    fontSize: fontSize.xs,
    fontWeight: fontWeight.semibold,
    lineHeight: lineHeight.normal,
    letterSpacing: letterSpacing.wider,
    textTransform: "uppercase",
  },
  button: {
    fontFamily: fontFamily.heading,
    fontSize: fontSize.sm,
    fontWeight: fontWeight.semibold,
    lineHeight: lineHeight.normal,
    letterSpacing: letterSpacing.wide,
    textTransform: "none",
  },
};

// ============================================================================
// CLINICAL TYPOGRAPHY VARIANTS
// ============================================================================

export const clinicalTypography = {
  drugName: {
    fontFamily: fontFamily.heading,
    fontSize: fontSize.base,
    fontWeight: fontWeight.semibold,
    lineHeight: lineHeight.normal,
    letterSpacing: letterSpacing.normal,
  },
  dosage: {
    fontFamily: fontFamily.monospace,
    fontSize: fontSize.base,
    fontWeight: fontWeight.medium,
    lineHeight: lineHeight.normal,
    letterSpacing: letterSpacing.normal,
  },
  medicalCode: {
    fontFamily: fontFamily.monospace,
    fontSize: fontSize.sm,
    fontWeight: fontWeight.regular,
    lineHeight: lineHeight.normal,
    letterSpacing: letterSpacing.normal,
  },
  recommendation: {
    fontFamily: fontFamily.clinical,
    fontSize: fontSize.base,
    fontWeight: fontWeight.regular,
    lineHeight: lineHeight.relaxed,
    letterSpacing: letterSpacing.normal,
  },
  citation: {
    fontFamily: fontFamily.clinical,
    fontSize: fontSize.xs,
    fontWeight: fontWeight.regular,
    lineHeight: lineHeight.normal,
    letterSpacing: letterSpacing.normal,
    fontStyle: "italic",
  },
  alertText: {
    fontFamily: fontFamily.clinical,
    fontSize: fontSize.sm,
    fontWeight: fontWeight.medium,
    lineHeight: lineHeight.normal,
    letterSpacing: letterSpacing.normal,
  },
  patientId: {
    fontFamily: fontFamily.monospace,
    fontSize: fontSize.sm,
    fontWeight: fontWeight.medium,
    lineHeight: lineHeight.normal,
    letterSpacing: letterSpacing.normal,
  },
  timestamp: {
    fontFamily: fontFamily.monospace,
    fontSize: fontSize.xs,
    fontWeight: fontWeight.regular,
    lineHeight: lineHeight.normal,
    letterSpacing: letterSpacing.normal,
  },
} as const;

// ============================================================================
// TYPE EXPORTS
// ============================================================================

export type FontFamily = typeof fontFamily;
export type FontSize = typeof fontSize;
export type FontWeight = typeof fontWeight;
export type LineHeight = typeof lineHeight;
export type LetterSpacing = typeof letterSpacing;
export type ClinicalTypography = typeof clinicalTypography;
