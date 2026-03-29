// src/styles/design-tokens.ts
// CDSS Clinical Design Token System
// ALL visual values must originate from this file.
// Direct hex/rgb/hsl values in components are forbidden.

export const tokens = {
  color: {
    // --- Semantic Clinical Colors ---
    alert: {
      critical: "hsl(0, 72%, 51%)",      // Drug interactions: major severity
      high: "hsl(25, 95%, 53%)",          // Drug interactions: moderate severity
      moderate: "hsl(45, 93%, 47%)",      // Warnings, dose adjustments
      low: "hsl(142, 71%, 45%)",          // Informational, minor interactions
      info: "hsl(217, 91%, 60%)",         // Neutral clinical information
    },
    confidence: {
      high: "hsl(142, 71%, 45%)",         // score >= 0.8
      moderate: "hsl(45, 93%, 47%)",      // score >= 0.6 and < 0.8
      low: "hsl(0, 72%, 51%)",            // score < 0.6 (escalation threshold)
      insufficient: "hsl(0, 0%, 64%)",    // no score available
    },
    agent: {
      patientHistory: "hsl(217, 91%, 60%)",
      drugSafety: "hsl(0, 72%, 51%)",
      literature: "hsl(262, 83%, 58%)",
      protocol: "hsl(142, 71%, 45%)",
      synthesis: "hsl(199, 89%, 48%)",
    },
    // --- Surface Colors ---
    surface: {
      primary: "hsl(0, 0%, 100%)",
      secondary: "hsl(210, 40%, 98%)",
      elevated: "hsl(0, 0%, 100%)",
      overlay: "hsla(222, 47%, 11%, 0.6)",
      clinical: "hsl(210, 40%, 96%)",
    },
    // --- Text Colors ---
    text: {
      primary: "hsl(222, 47%, 11%)",
      secondary: "hsl(215, 16%, 47%)",
      muted: "hsl(215, 16%, 62%)",
      inverse: "hsl(0, 0%, 100%)",
      clinical: "hsl(222, 47%, 15%)",
    },
    // --- Border Colors ---
    border: {
      default: "hsl(214, 32%, 91%)",
      strong: "hsl(215, 20%, 65%)",
      clinical: "hsl(214, 32%, 83%)",
      focus: "hsl(217, 91%, 60%)",
    },
  },
  spacing: {
    xs: "0.25rem",
    sm: "0.5rem",
    md: "0.75rem",
    lg: "1rem",
    xl: "1.5rem",
    xxl: "2rem",
    xxxl: "3rem",
    panelGap: "0.375rem",
    cardPadding: "1rem",
    alertPadding: "0.75rem",
  },
  typography: {
    fontFamily: {
      clinical: "'Inter', 'SF Pro Text', -apple-system, BlinkMacSystemFont, sans-serif",
      mono: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
    },
    fontSize: {
      caption: "0.6875rem",
      small: "0.75rem",
      body2: "0.8125rem",
      body: "0.875rem",
      subheading: "1rem",
      heading3: "1.125rem",
      heading2: "1.25rem",
      heading1: "1.5rem",
    },
    fontWeight: {
      normal: "400",
      medium: "500",
      semibold: "600",
      bold: "700",
    },
    lineHeight: {
      tight: "1.25",
      normal: "1.5",
      relaxed: "1.625",
    },
  },
  radius: {
    sm: "0.25rem",
    md: "0.375rem",
    lg: "0.5rem",
    xl: "0.75rem",
    full: "9999px",
  },
  shadow: {
    card: "0 1px 3px 0 hsla(0, 0%, 0%, 0.1), 0 1px 2px -1px hsla(0, 0%, 0%, 0.1)",
    elevated: "0 4px 6px -1px hsla(0, 0%, 0%, 0.1), 0 2px 4px -2px hsla(0, 0%, 0%, 0.1)",
    alert: "0 0 0 3px hsla(0, 72%, 51%, 0.15)",
    focus: "0 0 0 3px hsla(217, 91%, 60%, 0.3)",
  },
  animation: {
    fast: "150ms ease-in-out",
    normal: "250ms ease-in-out",
    slow: "350ms ease-in-out",
    streaming: "1.5s ease-in-out infinite",
  },
  zIndex: {
    base: "0",
    card: "10",
    dropdown: "100",
    modal: "200",
    alert: "300",
    toast: "400",
  },
} as const;

// Type exports
export type DesignTokens = typeof tokens;
export type AlertSeverity = keyof typeof tokens.color.alert;
export type ConfidenceLevel = "high" | "moderate" | "low" | "insufficient";
export type AgentType = keyof typeof tokens.color.agent;
