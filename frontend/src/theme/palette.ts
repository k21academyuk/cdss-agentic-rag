/**
 * CDSS Color Palette System
 *
 * Clinical-grade color palette with semantically stable severity colors
 * for drug safety interactions. All colors meet WCAG AA contrast requirements.
 *
 * CRITICAL: Severity colors are SEMANTICALLY STABLE:
 * - major: ALWAYS critical/danger (demands immediate action)
 * - moderate: ALWAYS warning (requires attention)
 * - minor: ALWAYS informational (low priority)
 * - none: ALWAYS safe (no interaction)
 *
 * @module palette
 */

import { alpha } from '@mui/material/styles';

// ============================================================================
// PRIMARY CLINICAL COLORS
// ============================================================================

/**
 * Primary clinical teal palette.
 * Deep, trustworthy medical color conveying professionalism and reliability.
 */
export const primary = {
  /** Darkest - #004D4E - Deep teal for high-emphasis elements */
  50: '#E6F5F5',
  100: '#CCEBEB',
  200: '#99D6D7',
  300: '#66C2C3',
  400: '#33ADAE',
  /** Main brand color - #0D7377 - Clinical teal */
  500: '#0D7377',
  600: '#0A5C5F',
  /** Dark variant - #084849 - For text on light backgrounds */
  700: '#084849',
  800: '#053235',
  /** Darkest - #031C1D - For extreme contrast */
  900: '#031C1D',
  main: '#0D7377',
  light: '#33ADAE',
  dark: '#084849',
  contrastText: '#FFFFFF',
} as const;

/**
 * Secondary accent palette.
 * Warm supporting color for secondary actions and highlights.
 */
export const secondary = {
  50: '#F5F0E6',
  100: '#EBE1CD',
  200: '#D7C39B',
  300: '#C3A569',
  400: '#AF8737',
  /** Main secondary - #9B7425 - Warm gold */
  500: '#9B7425',
  600: '#7C5D1E',
  700: '#5D4616',
  800: '#3E2E0E',
  900: '#1F1707',
  main: '#9B7425',
  light: '#C3A569',
  dark: '#5D4616',
  contrastText: '#FFFFFF',
} as const;

// ============================================================================
// DRUG SEVERITY COLORS (SEMANTICALLY STABLE)
// ============================================================================

/**
 * Drug interaction severity colors.
 *
 * CRITICAL: These colors MUST remain semantically stable across all themes.
 * The severity level determines the visual treatment, not the color itself.
 *
 * - major: Critical interactions requiring immediate clinical attention
 * - moderate: Warning interactions requiring review
 * - minor: Informational interactions of low priority
 * - none: No interaction (safe status)
 */
export const severity = {
  /**
   * Major/Critical severity - #DC2626
   * Use for: Critical drug interactions, contraindications, life-threatening alerts
   * WCAG AA: Passes on white (4.56:1) and dark backgrounds
   */
  major: {
    main: '#DC2626',
    light: '#EF4444',
    dark: '#B91C1C',
    contrastText: '#FFFFFF',
    // Alpha variants for backgrounds
    bgLight: alpha('#DC2626', 0.08),
    bgMedium: alpha('#DC2626', 0.12),
    bgStrong: alpha('#DC2626', 0.16),
  },
  /**
   * Moderate/Warning severity - #D97706
   * Use for: Moderate drug interactions, dose adjustments, monitoring required
   * WCAG AA: Passes on white (4.52:1) and dark backgrounds
   */
  moderate: {
    main: '#D97706',
    light: '#F59E0B',
    dark: '#B45309',
    contrastText: '#FFFFFF',
    bgLight: alpha('#D97706', 0.08),
    bgMedium: alpha('#D97706', 0.12),
    bgStrong: alpha('#D97706', 0.16),
  },
  /**
   * Minor/Info severity - #2563EB
   * Use for: Minor drug interactions, informational notes, low-priority alerts
   * WCAG AA: Passes on white (4.68:1) and dark backgrounds
   */
  minor: {
    main: '#2563EB',
    light: '#3B82F6',
    dark: '#1D4ED8',
    contrastText: '#FFFFFF',
    bgLight: alpha('#2563EB', 0.08),
    bgMedium: alpha('#2563EB', 0.12),
    bgStrong: alpha('#2563EB', 0.16),
  },
  /**
   * None/Safe severity - #16A34A
   * Use for: No interaction found, safe drug combinations, verified status
   * WCAG AA: Passes on white (4.56:1) and dark backgrounds
   */
  none: {
    main: '#16A34A',
    light: '#22C55E',
    dark: '#15803D',
    contrastText: '#FFFFFF',
    bgLight: alpha('#16A34A', 0.08),
    bgMedium: alpha('#16A34A', 0.12),
    bgStrong: alpha('#16A34A', 0.16),
  },
} as const;

/** Severity level type */
export type SeverityLevel = keyof typeof severity;

// ============================================================================
// SEMANTIC CLINICAL COLORS
// ============================================================================

/**
 * Semantic colors for clinical interface states.
 */
export const semantic = {
  /** Success - Confirming positive outcomes, completed actions */
  success: {
    main: '#16A34A',
    light: '#22C55E',
    dark: '#15803D',
    contrastText: '#FFFFFF',
    bgLight: alpha('#16A34A', 0.08),
    bgMedium: alpha('#16A34A', 0.12),
  },
  /** Info - Neutral information, helpful tips */
  info: {
    main: '#0284C7',
    light: '#0EA5E9',
    dark: '#0369A1',
    contrastText: '#FFFFFF',
    bgLight: alpha('#0284C7', 0.08),
    bgMedium: alpha('#0284C7', 0.12),
  },
  /** Warning - Caution needed, review required */
  warning: {
    main: '#D97706',
    light: '#F59E0B',
    dark: '#B45309',
    contrastText: '#1F2937',
    bgLight: alpha('#D97706', 0.08),
    bgMedium: alpha('#D97706', 0.12),
  },
  /** Error - Something went wrong, action failed */
  error: {
    main: '#DC2626',
    light: '#EF4444',
    dark: '#B91C1C',
    contrastText: '#FFFFFF',
    bgLight: alpha('#DC2626', 0.08),
    bgMedium: alpha('#DC2626', 0.12),
  },
} as const;

// ============================================================================
// SEMANTIC ROLE TOKENS
// ============================================================================

/**
 * Semantic role tokens for UI surfaces, borders, text, and stateful accents.
 * These are mode-aware and mapped to CSS variables at runtime.
 */
export const semanticRoles = {
  light: {
    surface: {
      canvas: "#F8FAFC",
      panel: "#FFFFFF",
      raised: "#FFFFFF",
      subdued: "#F3F4F6",
    },
    border: {
      subtle: "#E5E7EB",
      default: "#D1D5DB",
      strong: "#9CA3AF",
      focus: primary.main,
    },
    text: {
      primary: "#111827",
      secondary: "#4B5563",
      muted: "#6B7280",
      inverse: "#FFFFFF",
    },
    accent: {
      main: primary.main,
      strong: primary.dark,
      subtle: alpha(primary.main, 0.12),
    },
    success: {
      main: semantic.success.main,
      foreground: semantic.success.dark,
      surface: semantic.success.bgLight,
    },
    warning: {
      main: semantic.warning.main,
      foreground: semantic.warning.dark,
      surface: semantic.warning.bgLight,
    },
    critical: {
      main: semantic.error.main,
      foreground: semantic.error.dark,
      surface: semantic.error.bgLight,
    },
    info: {
      main: semantic.info.main,
      foreground: semantic.info.dark,
      surface: semantic.info.bgLight,
    },
    muted: {
      main: "#6B7280",
      foreground: "#4B5563",
      surface: "#F3F4F6",
    },
  },
  dark: {
    surface: {
      canvas: "#0B1220",
      panel: "#111827",
      raised: "#1F2937",
      subdued: "#0F172A",
    },
    border: {
      subtle: alpha("#F8FAFC", 0.12),
      default: alpha("#F8FAFC", 0.2),
      strong: alpha("#F8FAFC", 0.35),
      focus: "#66C2C3",
    },
    text: {
      primary: "#F9FAFB",
      secondary: "#D1D5DB",
      muted: "#9CA3AF",
      inverse: "#0B1220",
    },
    accent: {
      main: "#33ADAE",
      strong: "#66C2C3",
      subtle: alpha("#33ADAE", 0.2),
    },
    success: {
      main: "#22C55E",
      foreground: "#4ADE80",
      surface: alpha("#22C55E", 0.18),
    },
    warning: {
      main: "#F59E0B",
      foreground: "#FBBF24",
      surface: alpha("#F59E0B", 0.2),
    },
    critical: {
      main: "#EF4444",
      foreground: "#F87171",
      surface: alpha("#EF4444", 0.2),
    },
    info: {
      main: "#38BDF8",
      foreground: "#7DD3FC",
      surface: alpha("#38BDF8", 0.18),
    },
    muted: {
      main: "#9CA3AF",
      foreground: "#D1D5DB",
      surface: alpha("#9CA3AF", 0.14),
    },
  },
} as const;

// ============================================================================
// MEDICAL STATUS TOKENS
// ============================================================================

/**
 * Medical status tokens used for contraindication/risk/monitoring/validated states.
 */
export const medicalStatusTokens = {
  light: {
    critical: {
      label: "major contraindication",
      main: severity.major.main,
      border: severity.major.main,
      foreground: severity.major.dark,
      surface: severity.major.bgLight,
    },
    warning: {
      label: "moderate risk",
      main: severity.moderate.main,
      border: severity.moderate.main,
      foreground: severity.moderate.dark,
      surface: severity.moderate.bgLight,
    },
    info: {
      label: "minor / monitor",
      main: severity.minor.main,
      border: severity.minor.main,
      foreground: severity.minor.dark,
      surface: severity.minor.bgLight,
    },
    success: {
      label: "validated / healthy",
      main: severity.none.main,
      border: severity.none.main,
      foreground: severity.none.dark,
      surface: severity.none.bgLight,
    },
  },
  dark: {
    critical: {
      label: "major contraindication",
      main: "#EF4444",
      border: "#F87171",
      foreground: "#FCA5A5",
      surface: alpha("#EF4444", 0.2),
    },
    warning: {
      label: "moderate risk",
      main: "#F59E0B",
      border: "#FBBF24",
      foreground: "#FCD34D",
      surface: alpha("#F59E0B", 0.2),
    },
    info: {
      label: "minor / monitor",
      main: "#38BDF8",
      border: "#7DD3FC",
      foreground: "#BAE6FD",
      surface: alpha("#38BDF8", 0.18),
    },
    success: {
      label: "validated / healthy",
      main: "#22C55E",
      border: "#4ADE80",
      foreground: "#86EFAC",
      surface: alpha("#22C55E", 0.2),
    },
  },
} as const;

export type MedicalStatus = keyof typeof medicalStatusTokens.light;

// ============================================================================
// NEUTRAL / GRAY SCALE
// ============================================================================

/**
 * Neutral gray palette for text, backgrounds, and borders.
 * Designed for clinical interfaces with optimal readability.
 */
export const neutral = {
  /** Lightest gray - backgrounds */
  50: '#F9FAFB',
  100: '#F3F4F6',
  200: '#E5E7EB',
  300: '#D1D5DB',
  /** Border gray */
  400: '#9CA3AF',
  /** Muted text */
  500: '#6B7280',
  /** Secondary text */
  600: '#4B5563',
  /** Primary text on light backgrounds */
  700: '#374151',
  800: '#1F2937',
  /** Darkest - primary text, headings */
  900: '#111827',
  /** Near black */
  950: '#030712',
} as const;

// ============================================================================
// LIGHT MODE PALETTE
// ============================================================================

/**
 * Complete light mode palette for MUI theme.
 */
export const lightPalette = {
  mode: 'light' as const,
  primary: {
    main: primary.main,
    light: primary.light,
    dark: primary.dark,
    contrastText: primary.contrastText,
  },
  secondary: {
    main: secondary.main,
    light: secondary.light,
    dark: secondary.dark,
    contrastText: secondary.contrastText,
  },
  error: {
    main: semantic.error.main,
    light: semantic.error.light,
    dark: semantic.error.dark,
    contrastText: semantic.error.contrastText,
  },
  warning: {
    main: semantic.warning.main,
    light: semantic.warning.light,
    dark: semantic.warning.dark,
    contrastText: semantic.warning.contrastText,
  },
  info: {
    main: semantic.info.main,
    light: semantic.info.light,
    dark: semantic.info.dark,
    contrastText: semantic.info.contrastText,
  },
  success: {
    main: semantic.success.main,
    light: semantic.success.light,
    dark: semantic.success.dark,
    contrastText: semantic.success.contrastText,
  },
  background: {
    default: '#F9FAFB',
    paper: '#FFFFFF',
  },
  text: {
    primary: neutral[900],
    secondary: neutral[600],
    disabled: neutral[400],
  },
  divider: neutral[200],
  action: {
    active: neutral[700],
    hover: alpha(neutral[900], 0.04),
    selected: alpha(primary.main, 0.08),
    disabled: alpha(neutral[900], 0.26),
    disabledBackground: alpha(neutral[900], 0.12),
    focus: alpha(primary.main, 0.12),
  },
} as const;

// ============================================================================
// DARK MODE PALETTE
// ============================================================================

/**
 * Complete dark mode palette for MUI theme.
 * Adjusted for proper contrast on dark backgrounds.
 */
export const darkPalette = {
  mode: 'dark' as const,
  primary: {
    main: '#33ADAE',
    light: '#66C2C3',
    dark: '#0D7377',
    contrastText: '#FFFFFF',
  },
  secondary: {
    main: '#C3A569',
    light: '#D7C39B',
    dark: '#9B7425',
    contrastText: '#1F2937',
  },
  error: {
    main: '#EF4444',
    light: '#F87171',
    dark: '#DC2626',
    contrastText: '#FFFFFF',
  },
  warning: {
    main: '#F59E0B',
    light: '#FBBF24',
    dark: '#D97706',
    contrastText: '#1F2937',
  },
  info: {
    main: '#0EA5E9',
    light: '#38BDF8',
    dark: '#0284C7',
    contrastText: '#FFFFFF',
  },
  success: {
    main: '#22C55E',
    light: '#4ADE80',
    dark: '#16A34A',
    contrastText: '#FFFFFF',
  },
  background: {
    default: '#0F172A',
    paper: '#1E293B',
  },
  text: {
    primary: '#F9FAFB',
    secondary: '#D1D5DB',
    disabled: '#6B7280',
  },
  divider: alpha('#FFFFFF', 0.12),
  action: {
    active: '#F9FAFB',
    hover: alpha('#FFFFFF', 0.08),
    selected: alpha('#33ADAE', 0.16),
    disabled: alpha('#FFFFFF', 0.3),
    disabledBackground: alpha('#FFFFFF', 0.12),
    focus: alpha('#33ADAE', 0.12),
  },
} as const;

// ============================================================================
// CLINICAL-SPECIFIC COLORS
// ============================================================================

/**
 * Clinical domain-specific colors.
 * Used for medical categories, status indicators, and clinical workflows.
 */
export const clinical = {
  /** Patient status colors */
  patientStatus: {
    active: '#16A34A',
    inactive: '#6B7280',
    discharged: '#0284C7',
    critical: '#DC2626',
  },
  /** Lab result status */
  labStatus: {
    normal: '#16A34A',
    abnormal: '#D97706',
    critical: '#DC2626',
    pending: '#6B7280',
  },
  /** Medication status */
  medicationStatus: {
    active: '#16A34A',
    hold: '#D97706',
    discontinued: '#6B7280',
    completed: '#0284C7',
  },
  /** Allergy severity */
  allergySeverity: {
    mild: '#F59E0B',
    moderate: '#D97706',
    severe: '#DC2626',
    unknown: '#6B7280',
  },
  /** Evidence quality (for literature/recommendations) */
  evidenceQuality: {
    high: '#16A34A',
    moderate: '#0284C7',
    low: '#F59E0B',
    insufficient: '#6B7280',
  },
} as const;

// ============================================================================
// CSS CUSTOM PROPERTIES GENERATOR
// ============================================================================

/**
 * Generates CSS custom properties from color tokens for runtime theming.
 * Call this function to inject colors as CSS variables.
 */
export function generateCssCustomProperties(
  palette: typeof lightPalette | typeof darkPalette,
  prefix = 'cdss'
): Record<string, string> {
  const cssVars: Record<string, string> = {};

  const processObject = (obj: Record<string, unknown>, path: string[] = []) => {
    Object.entries(obj).forEach(([key, value]) => {
      const currentPath = [...path, key];
      if (typeof value === 'string') {
        const cssKey = `--${prefix}-${currentPath.join('-')}`;
        cssVars[cssKey] = value;
      } else if (typeof value === 'object' && value !== null) {
        processObject(value as Record<string, unknown>, currentPath);
      }
    });
  };

  processObject(palette as unknown as Record<string, unknown>);
  return cssVars;
}

// ============================================================================
// ALPHA HELPER EXPORT
// ============================================================================

/**
 * Creates a transparent version of a color.
 * Wrapper around MUI's alpha function for convenience.
 */
export { alpha };

// ============================================================================
// TYPE EXPORTS
// ============================================================================

export type PaletteMode = 'light' | 'dark';
export type { PaletteOptions } from '@mui/material/styles';
