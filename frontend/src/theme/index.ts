/**
 * CDSS Theme System - Main Entry Point
 *
 * Production-ready design system for clinical AI workflows using MUI theming
 * + CSS variables with light/dark parity and compact/comfortable density modes.
 *
 * @module theme
 */

import { createTheme } from "@mui/material/styles";
import type { Theme, ThemeOptions } from "@mui/material/styles";
import type {} from "@mui/x-data-grid/themeAugmentation";

// ============================================================================
// RE-EXPORT DESIGN TOKENS
// ============================================================================

export {
  spacing,
  type Spacing,
  borderRadius,
  type BorderRadius,
  typography,
  fontSize,
  fontWeight,
  lineHeight,
  letterSpacing,
  type FontSize,
  type FontWeight,
  type LineHeight,
  type LetterSpacing,
  elevation,
  type Elevation,
  motion,
  zIndex,
  type ZIndex,
  breakpoints,
  type Breakpoint,
  opacity,
  type Opacity,
  componentSize,
  focusRing,
  density,
  type DensityMode,
  type DensityTokens,
  designTokens,
  type DesignTokens,
} from "./designTokens";

// ============================================================================
// RE-EXPORT PALETTE TOKENS
// ============================================================================

export {
  primary,
  secondary,
  severity,
  type SeverityLevel,
  semantic,
  semanticRoles,
  medicalStatusTokens,
  type MedicalStatus,
  neutral,
  lightPalette,
  darkPalette,
  clinical,
  alpha,
  generateCssCustomProperties,
  type PaletteMode,
} from "./palette";

// ============================================================================
// RE-EXPORT TYPOGRAPHY / SHADOW / MOTION
// ============================================================================

export {
  fontFamily,
  fontSize as typographyFontSize,
  fontWeight as typographyFontWeight,
  lineHeight as typographyLineHeight,
  letterSpacing as typographyLetterSpacing,
  typographyOptions,
  clinicalTypography,
  type FontFamily,
  type FontSize as TypographyFontSize,
  type FontWeight as TypographyFontWeight,
  type LineHeight as TypographyLineHeight,
  type LetterSpacing as TypographyLetterSpacing,
  type ClinicalTypography,
} from "./typography";

export {
  shadows,
  darkShadows,
  clinicalShadows,
  interactiveShadows,
  componentShadows,
  createColoredShadow,
  type Shadow,
  type ClinicalShadow,
  type InteractiveShadow,
  type ComponentShadow,
} from "./shadows";

export {
  duration,
  easing,
  transitions,
  keyframes,
  animations,
  reducedMotion,
  type Duration as MotionDuration,
  type Easing as MotionEasing,
  type Transitions,
  type Keyframes,
  type Animations,
} from "./motion";

// ============================================================================
// INTERNAL IMPORTS
// ============================================================================

import { borderRadius, density, focusRing, zIndex } from "./designTokens";
import { duration, easing, transitions } from "./motion";
import {
  clinical,
  darkPalette,
  lightPalette,
  medicalStatusTokens,
  semantic,
  semanticRoles,
  severity,
} from "./palette";
import { clinicalShadows, componentShadows, darkShadows, shadows } from "./shadows";
import { fontFamily, typographyOptions } from "./typography";

type SupportedMode = "light" | "dark";

export interface CreateCDSSThemeOptions {
  mode?: SupportedMode;
  densityMode?: keyof typeof density;
}

const getDensityDataGridMode = (densityMode: keyof typeof density): "compact" | "standard" =>
  densityMode === "compact" ? "compact" : "standard";

const getThemeOptions = (mode: SupportedMode, densityMode: keyof typeof density): ThemeOptions => {
  const isDark = mode === "dark";
  const palette = isDark ? darkPalette : lightPalette;
  const roleSet = semanticRoles[mode];
  const statusSet = medicalStatusTokens[mode];
  const densitySet = density[densityMode];
  const themeShadows = isDark ? darkShadows : shadows;
  const focusShadow = isDark ? focusRing.darkShadow : focusRing.lightShadow;

  return {
    palette,
    typography: typographyOptions,
    shadows: themeShadows as unknown as Theme["shadows"],
    shape: {
      borderRadius: borderRadius.md,
    },
    spacing: (factor: number) => `${factor * 4}px`,
    zIndex: {
      mobileStepper: zIndex.dropdown,
      speedDial: zIndex.dropdown,
      appBar: zIndex.fixed,
      drawer: zIndex.sticky,
      modal: zIndex.modal,
      snackbar: zIndex.toast,
      tooltip: zIndex.tooltip,
    },
    transitions: {
      duration: {
        shortest: duration.fast,
        shorter: duration.micro,
        short: duration.standard,
        standard: duration.standard,
        complex: duration.slow,
        enteringScreen: duration.slow,
        leavingScreen: duration.standard,
      },
      easing: {
        easeInOut: easing.easeInOut,
        easeOut: easing.easeOut,
        easeIn: easing.easeIn,
        sharp: easing.sharp,
      },
    },
    components: {
      MuiCssBaseline: {
        styleOverrides: {
          body: {
            backgroundColor: roleSet.surface.canvas,
            color: roleSet.text.primary,
          },
          "h1, h2, h3, h4, h5, h6": {
            fontFamily: fontFamily.heading,
          },
          ".clinical-text, .MuiDataGrid-root, .MuiTableCell-root": {
            fontFamily: fontFamily.clinical,
          },
        },
      },

      // Button contract
      MuiButton: {
        defaultProps: {
          disableElevation: true,
        },
        styleOverrides: {
          root: {
            minHeight: densitySet.buttonHeight,
            borderRadius: borderRadius.sm,
            textTransform: "none",
            fontWeight: 600,
            transition: transitions.interactive,
            "&:focus-visible": {
              outline: `${focusRing.width}px solid transparent`,
              boxShadow: focusShadow,
            },
          },
          contained: {
            backgroundColor: roleSet.accent.main,
            color: roleSet.text.inverse,
            "&:hover": {
              backgroundColor: roleSet.accent.strong,
              boxShadow: componentShadows.cardHover,
            },
          },
        },
      },

      // Card contract
      MuiCard: {
        styleOverrides: {
          root: {
            borderRadius: borderRadius.md,
            border: `1px solid ${roleSet.border.subtle}`,
            boxShadow: componentShadows.card,
            transition: transitions.shadow.standard,
            "&:hover": {
              boxShadow: componentShadows.cardHover,
            },
          },
        },
      },

      // DataGrid contract
      MuiDataGrid: {
        defaultProps: {
          density: getDensityDataGridMode(densityMode),
          rowHeight: densitySet.tableRowHeight,
          columnHeaderHeight: densitySet.tableHeaderHeight,
        },
        styleOverrides: {
          root: {
            borderRadius: borderRadius.md,
            borderColor: roleSet.border.default,
            backgroundColor: roleSet.surface.panel,
            color: roleSet.text.primary,
            fontFamily: fontFamily.clinical,
          },
          columnHeaders: {
            borderBottom: `1px solid ${roleSet.border.default}`,
            backgroundColor: roleSet.surface.subdued,
            fontFamily: fontFamily.heading,
            fontWeight: 700,
          },
          cell: {
            borderBottom: `1px solid ${roleSet.border.subtle}`,
            fontFamily: fontFamily.clinical,
          },
          row: {
            "&:hover": {
              backgroundColor: roleSet.muted.surface,
            },
            "&.Mui-selected": {
              backgroundColor: roleSet.accent.subtle,
            },
          },
        },
      },

      // Chip contract
      MuiChip: {
        styleOverrides: {
          root: {
            height: densitySet.chipHeight,
            borderRadius: borderRadius.full,
            fontWeight: 600,
            borderColor: roleSet.border.default,
          },
        },
      },

      // Tabs contract
      MuiTabs: {
        styleOverrides: {
          root: {
            minHeight: densitySet.tabMinHeight,
          },
          indicator: {
            height: 3,
            borderRadius: borderRadius.full,
            backgroundColor: roleSet.accent.main,
          },
        },
      },
      MuiTab: {
        styleOverrides: {
          root: {
            minHeight: densitySet.tabMinHeight,
            fontFamily: fontFamily.heading,
            textTransform: "none",
            fontWeight: 600,
            color: roleSet.text.secondary,
            "&.Mui-selected": {
              color: roleSet.text.primary,
            },
          },
        },
      },

      // Alert contract
      MuiAlert: {
        styleOverrides: {
          root: {
            borderRadius: borderRadius.sm,
            border: `1px solid ${roleSet.border.subtle}`,
            fontFamily: fontFamily.clinical,
            fontWeight: 500,
          },
          standardError: {
            backgroundColor: statusSet.critical.surface,
            color: statusSet.critical.foreground,
            boxShadow: clinicalShadows.critical,
          },
          standardWarning: {
            backgroundColor: statusSet.warning.surface,
            color: statusSet.warning.foreground,
            boxShadow: clinicalShadows.warning,
          },
          standardInfo: {
            backgroundColor: statusSet.info.surface,
            color: statusSet.info.foreground,
            boxShadow: clinicalShadows.info,
          },
          standardSuccess: {
            backgroundColor: statusSet.success.surface,
            color: statusSet.success.foreground,
            boxShadow: clinicalShadows.success,
          },
        },
      },

      // Tooltip contract
      MuiTooltip: {
        styleOverrides: {
          tooltip: {
            borderRadius: borderRadius.xs,
            fontSize: "0.75rem",
            backgroundColor: roleSet.text.primary,
            color: roleSet.text.inverse,
            fontFamily: fontFamily.clinical,
          },
        },
      },

      // Dialog contract
      MuiDialog: {
        styleOverrides: {
          paper: {
            borderRadius: borderRadius.lg,
            boxShadow: componentShadows.dialog,
            padding: densitySet.dialogPadding,
            border: `1px solid ${roleSet.border.subtle}`,
          },
        },
      },

      // Drawer contract
      MuiDrawer: {
        styleOverrides: {
          paper: {
            borderRight: `1px solid ${roleSet.border.subtle}`,
            boxShadow: componentShadows.drawer,
            backgroundColor: roleSet.surface.panel,
          },
        },
      },

      // AppBar contract
      MuiAppBar: {
        styleOverrides: {
          root: {
            backgroundColor: roleSet.surface.panel,
            color: roleSet.text.primary,
            borderBottom: `1px solid ${roleSet.border.subtle}`,
            boxShadow: componentShadows.appBar,
          },
        },
      },

      // Form control contract
      MuiTextField: {
        styleOverrides: {
          root: {
            "& .MuiOutlinedInput-root": {
              minHeight: densitySet.inputHeight,
            },
          },
        },
      },
      MuiFormControl: {
        styleOverrides: {
          root: {
            "& .MuiOutlinedInput-root": {
              borderRadius: borderRadius.sm,
              backgroundColor: roleSet.surface.panel,
              transition: transitions.interactive,
              "&:hover .MuiOutlinedInput-notchedOutline": {
                borderColor: roleSet.border.strong,
              },
              "&.Mui-focused .MuiOutlinedInput-notchedOutline": {
                borderColor: roleSet.border.focus,
                borderWidth: "2px",
              },
              "&.Mui-focused": {
                boxShadow: focusShadow,
              },
            },
          },
        },
      },
      MuiOutlinedInput: {
        styleOverrides: {
          root: {
            minHeight: densitySet.inputHeight,
            "& .MuiOutlinedInput-notchedOutline": {
              borderColor: roleSet.border.default,
            },
          },
          input: {
            fontFamily: fontFamily.clinical,
          },
        },
      },
      MuiFormLabel: {
        styleOverrides: {
          root: {
            fontFamily: fontFamily.heading,
            fontWeight: 600,
          },
        },
      },
      MuiInputLabel: {
        styleOverrides: {
          root: {
            fontFamily: fontFamily.heading,
            fontWeight: 600,
          },
        },
      },
      MuiFormHelperText: {
        styleOverrides: {
          root: {
            fontFamily: fontFamily.clinical,
          },
        },
      },
      MuiSelect: {
        styleOverrides: {
          select: {
            fontFamily: fontFamily.clinical,
          },
        },
      },
      MuiCheckbox: {
        styleOverrides: {
          root: {
            color: roleSet.border.strong,
            "&.Mui-checked": {
              color: roleSet.accent.main,
            },
          },
        },
      },
      MuiRadio: {
        styleOverrides: {
          root: {
            color: roleSet.border.strong,
            "&.Mui-checked": {
              color: roleSet.accent.main,
            },
          },
        },
      },

      MuiSnackbar: {
        styleOverrides: {
          root: {
            "& .MuiSnackbarContent-root": {
              borderRadius: borderRadius.md,
              boxShadow: componentShadows.snackbar,
            },
          },
        },
      },
    },
  };
};

const attachCDSSMetadata = (theme: Theme, mode: SupportedMode, densityMode: keyof typeof density): CDSSTheme => {
  const themeWithMeta = theme as CDSSTheme;
  themeWithMeta.cdss = {
    severity,
    clinical,
    roles: semanticRoles[mode],
    medicalStatus: medicalStatusTokens[mode],
    densityMode,
    density: density[densityMode],
    focusRing: {
      ...focusRing,
      activeShadow: mode === "dark" ? focusRing.darkShadow : focusRing.lightShadow,
      activeColor: mode === "dark" ? focusRing.darkColor : focusRing.lightColor,
    },
    motion: {
      duration,
      easing,
      transitions,
    },
    shadows: {
      clinical: clinicalShadows,
      components: componentShadows,
    },
  };
  return themeWithMeta;
};

export function createCDSSTheme(options: CreateCDSSThemeOptions = {}): CDSSTheme {
  const mode = options.mode ?? "light";
  const densityMode = options.densityMode ?? "comfortable";
  const baseTheme = createTheme(getThemeOptions(mode, densityMode));
  return attachCDSSMetadata(baseTheme, mode, densityMode);
}

/**
 * Default comfortable themes used by the application shell.
 */
export const lightTheme = createCDSSTheme({ mode: "light", densityMode: "comfortable" });
export const darkTheme = createCDSSTheme({ mode: "dark", densityMode: "comfortable" });

/**
 * Optional compact variants for dense clinical tables/workflows.
 */
export const compactLightTheme = createCDSSTheme({ mode: "light", densityMode: "compact" });
export const compactDarkTheme = createCDSSTheme({ mode: "dark", densityMode: "compact" });

export function getTheme(mode: SupportedMode, densityMode: keyof typeof density = "comfortable"): CDSSTheme {
  if (mode === "dark" && densityMode === "compact") return compactDarkTheme;
  if (mode === "dark") return darkTheme;
  if (densityMode === "compact") return compactLightTheme;
  return lightTheme;
}

export function getSeverityColor(level: keyof typeof severity) {
  return severity[level];
}

export function getClinicalColor<K extends keyof typeof clinical>(category: K, status: keyof typeof clinical[K]): string {
  return clinical[category][status] as string;
}

// ============================================================================
// CSS CUSTOM PROPERTIES
// ============================================================================

const setCssVars = (root: HTMLElement, object: Record<string, unknown>, path: string[] = []): void => {
  Object.entries(object).forEach(([key, value]) => {
    const nextPath = [...path, key];
    if (typeof value === "string" || typeof value === "number") {
      root.style.setProperty(`--${nextPath.join("-")}`, String(value));
    } else if (value && typeof value === "object") {
      setCssVars(root, value as Record<string, unknown>, nextPath);
    }
  });
};

/**
 * Injects CSS custom properties for the active mode and density.
 */
export function injectCssCustomProperties(theme: Theme, densityMode: keyof typeof density = "comfortable"): void {
  const root = document.documentElement;
  const mode: SupportedMode = theme.palette.mode === "dark" ? "dark" : "light";
  const roleSet = semanticRoles[mode];
  const statusSet = medicalStatusTokens[mode];
  const densitySet = density[densityMode];

  root.dataset.themeMode = mode;
  root.dataset.densityMode = densityMode;

  // Typography
  root.style.setProperty("--cdss-font-heading", fontFamily.heading);
  root.style.setProperty("--cdss-font-clinical", fontFamily.clinical);

  // Core palette compatibility variables
  root.style.setProperty("--cdss-primary-main", theme.palette.primary.main);
  root.style.setProperty("--cdss-primary-light", theme.palette.primary.light ?? "");
  root.style.setProperty("--cdss-primary-dark", theme.palette.primary.dark ?? "");
  root.style.setProperty("--cdss-background-default", theme.palette.background.default);
  root.style.setProperty("--cdss-background-paper", theme.palette.background.paper);
  root.style.setProperty("--cdss-text-primary", theme.palette.text.primary);
  root.style.setProperty("--cdss-text-secondary", theme.palette.text.secondary);
  root.style.setProperty("--cdss-severity-major", severity.major.main);
  root.style.setProperty("--cdss-severity-moderate", severity.moderate.main);
  root.style.setProperty("--cdss-severity-minor", severity.minor.main);
  root.style.setProperty("--cdss-severity-none", severity.none.main);
  root.style.setProperty("--cdss-success", semantic.success.main);
  root.style.setProperty("--cdss-info", semantic.info.main);
  root.style.setProperty("--cdss-warning", semantic.warning.main);
  root.style.setProperty("--cdss-error", semantic.error.main);

  // Semantic roles and medical statuses
  setCssVars(root, roleSet as unknown as Record<string, unknown>, ["cdss", "role"]);
  setCssVars(root, statusSet as unknown as Record<string, unknown>, ["cdss", "status"]);
  setCssVars(root, densitySet as unknown as Record<string, unknown>, ["cdss", "density"]);

  // Focus + motion
  root.style.setProperty("--cdss-focus-ring-width", String(focusRing.width));
  root.style.setProperty("--cdss-focus-ring-offset", String(focusRing.offset));
  root.style.setProperty("--cdss-focus-ring-color", mode === "dark" ? focusRing.darkColor : focusRing.lightColor);
  root.style.setProperty("--cdss-focus-ring-shadow", mode === "dark" ? focusRing.darkShadow : focusRing.lightShadow);
  root.style.setProperty("--cdss-motion-fast", `${duration.fast}ms`);
  root.style.setProperty("--cdss-motion-micro", `${duration.micro}ms`);
  root.style.setProperty("--cdss-motion-standard", `${duration.standard}ms`);
  root.style.setProperty("--cdss-motion-slow", `${duration.slow}ms`);
}

// ============================================================================
// TYPE EXPORTS
// ============================================================================

export type { Theme, ThemeOptions };

export interface CDSSTheme extends Theme {
  cdss: {
    severity: typeof severity;
    clinical: typeof clinical;
    roles: (typeof semanticRoles)[SupportedMode];
    medicalStatus: (typeof medicalStatusTokens)[SupportedMode];
    densityMode: keyof typeof density;
    density: (typeof density)[keyof typeof density];
    focusRing: typeof focusRing & { activeShadow: string; activeColor: string };
    motion: {
      duration: typeof duration;
      easing: typeof easing;
      transitions: typeof transitions;
    };
    shadows: {
      clinical: typeof clinicalShadows;
      components: typeof componentShadows;
    };
  };
}

export default lightTheme;
