/**
 * CDSS Design Token System
 *
 * A comprehensive, clinical-grade design token system for the Clinical Decision
 * Support System. All tokens are designed for accessibility (WCAG AA compliance)
 * and semantic clarity for medical applications.
 *
 * @module designTokens
 */

// ============================================================================
// SPACING SCALE
// ============================================================================

/**
 * Spacing scale based on 4px base unit.
 * Follows an 8-point grid system with additional 4px increments for fine control.
 */
export const spacing = {
  /** 0px - No spacing */
  0: 0,
  /** 4px - Extra small spacing (tight gaps) */
  1: 4,
  /** 8px - Small spacing (compact gaps) */
  2: 8,
  /** 12px - Medium-small spacing */
  3: 12,
  /** 16px - Medium spacing (standard gap) */
  4: 16,
  /** 24px - Large spacing (section gaps) */
  6: 24,
  /** 32px - Extra large spacing */
  8: 32,
  /** 48px - Section spacing */
  12: 48,
  /** 64px - Major section spacing */
  16: 64,
  /** 96px - Page-level spacing */
  24: 96,
  /** 128px - Large page sections */
  32: 128,
} as const;

/** Type for spacing values */
export type Spacing = (typeof spacing)[keyof typeof spacing];

// ============================================================================
// BORDER RADIUS SCALE
// ============================================================================

/**
 * Border radius scale for consistent corner rounding.
 * Uses subtle curves appropriate for clinical interfaces.
 */
export const borderRadius = {
  /** No rounding */
  none: 0,
  /** 4px - Extra small (buttons, tags) */
  xs: 4,
  /** 6px - Small (inputs, small cards) */
  sm: 6,
  /** 8px - Medium (standard cards, containers) */
  md: 8,
  /** 12px - Large (feature cards, modals) */
  lg: 12,
  /** 16px - Extra large (hero sections) */
  xl: 16,
  /** 9999px - Fully rounded (pills, avatars) */
  full: 9999,
} as const;

/** Type for border radius values */
export type BorderRadius = (typeof borderRadius)[keyof typeof borderRadius];

// ============================================================================
// TYPOGRAPHY SCALE
// ============================================================================

/**
 * Typography scale using a modular approach.
 * Font sizes range from 12px to 48px for comprehensive coverage.
 */
export const fontSize = {
  /** 12px - Caption, legal text */
  xs: '12px',
  /** 14px - Small body text, labels */
  sm: '14px',
  /** 16px - Body text (base) */
  base: '16px',
  /** 18px - Large body text */
  lg: '18px',
  /** 20px - Small headings */
  xl: '20px',
  /** 24px - H4 headings */
  '2xl': '24px',
  /** 28px - H3 headings */
  '3xl': '28px',
  /** 32px - H2 headings */
  '4xl': '32px',
  /** 36px - H1 headings */
  '5xl': '36px',
  /** 40px - Display headings */
  '6xl': '40px',
  /** 44px - Large display */
  '7xl': '44px',
  /** 48px - Hero headings */
  '8xl': '48px',
} as const;

/**
 * Font weight scale for typographic hierarchy.
 */
export const fontWeight = {
  /** 300 - Light weight for subtle text */
  light: 300,
  /** 400 - Regular weight for body text */
  regular: 400,
  /** 500 - Medium weight for emphasis */
  medium: 500,
  /** 600 - Semibold for subheadings */
  semibold: 600,
  /** 700 - Bold for headings and emphasis */
  bold: 700,
} as const;

/**
 * Line height scale for optimal readability.
 */
export const lineHeight = {
  /** 1 - Tight line height for headings */
  tight: 1,
  /** 1.25 - Snug line height for subheadings */
  snug: 1.25,
  /** 1.5 - Normal line height for body text */
  normal: 1.5,
  /** 1.625 - Relaxed line height for long-form text */
  relaxed: 1.625,
  /** 2 - Loose line height for captions */
  loose: 2,
} as const;

/**
 * Letter spacing scale for typographic refinement.
 */
export const letterSpacing = {
  /** -0.025em - Tighter tracking for headings */
  tighter: '-0.025em',
  /** -0.015em - Tight tracking */
  tight: '-0.015em',
  /** 0 - Normal tracking */
  normal: '0',
  /** 0.025em - Wide tracking for labels */
  wide: '0.025em',
  /** 0.05em - Wider tracking for uppercase */
  wider: '0.05em',
  /** 0.1em - Widest tracking for small caps */
  widest: '0.1em',
} as const;

/**
 * Complete typography configuration.
 */
export const typography = {
  fontFamily: "\"IBM Plex Sans\", \"Segoe UI\", \"Helvetica Neue\", Arial, sans-serif",
  fontSize,
  fontWeight,
  lineHeight,
  letterSpacing,
} as const;

/** Type for font size values */
export type FontSize = (typeof fontSize)[keyof typeof fontSize];
/** Type for font weight values */
export type FontWeight = (typeof fontWeight)[keyof typeof fontWeight];
/** Type for line height values */
export type LineHeight = (typeof lineHeight)[keyof typeof lineHeight];
/** Type for letter spacing values */
export type LetterSpacing = (typeof letterSpacing)[keyof typeof letterSpacing];

// ============================================================================
// ELEVATION SCALE (SHADOWS)
// ============================================================================

/**
 * Elevation levels for depth hierarchy.
 * Corresponds to shadow definitions in shadows.ts.
 */
export const elevation = {
  /** No elevation (flat) */
  0: 0,
  /** Subtle elevation (hover states, raised buttons) */
  1: 1,
  /** Low elevation (cards, list items) */
  2: 2,
  /** Medium elevation (dropdowns, popovers) */
  3: 3,
  /** High elevation (modals, dialogs) */
  4: 4,
} as const;

/** Type for elevation values */
export type Elevation = (typeof elevation)[keyof typeof elevation];

// ============================================================================
// MOTION / ANIMATION TOKENS
// ============================================================================

/**
 * Duration tokens for animations and transitions.
 * Designed for clinical interfaces - responsive but not distracting.
 */
export const duration = {
  /** 0ms - Instant (no animation) */
  instant: 0,
  /** 100ms - Fast micro-interactions */
  fast: 100,
  /** 150ms - Micro-interactions (button hover, checkbox) */
  micro: 150,
  /** 250ms - Standard transitions (dropdown, modal enter) */
  standard: 250,
  /** 400ms - Slow transitions (page transitions, complex animations) */
  slow: 400,
  /** 500ms - Slower transitions (skeleton loading) */
  slower: 500,
  /** 600ms - Complex multi-step animations */
  complex: 600,
} as const;

/**
 * Easing functions for smooth, natural animations.
 * Uses ease-out for entrances and ease-in-out for state changes.
 */
export const easing = {
  /** Linear easing - constant speed */
  linear: 'linear',
  /** Ease-in - slow start, fast end */
  easeIn: 'cubic-bezier(0.4, 0, 1, 1)',
  /** Ease-out - fast start, slow end (preferred for most UI) */
  easeOut: 'cubic-bezier(0, 0, 0.2, 1)',
  /** Ease-in-out - slow start and end */
  easeInOut: 'cubic-bezier(0.4, 0, 0.2, 1)',
  /** Bounce - playful bounce effect (use sparingly) */
  bounce: 'cubic-bezier(0.68, -0.55, 0.265, 1.55)',
  /** Smooth deceleration for clinical precision */
  clinicalEase: 'cubic-bezier(0.25, 0.1, 0.25, 1)',
} as const;

/**
 * Complete motion configuration.
 */
export const motion = {
  duration,
  easing,
} as const;

/** Type for duration values */
export type Duration = (typeof duration)[keyof typeof duration];
/** Type for easing values */
export type Easing = (typeof easing)[keyof typeof easing];

// ============================================================================
// Z-INDEX SCALE
// ============================================================================

/**
 * Z-index scale for consistent layering across the application.
 * Uses increments of 100 to allow room for intermediate values.
 */
export const zIndex = {
  /** Base layer (default) */
  base: 0,
  /** Dropdown menus, selects */
  dropdown: 100,
  /** Sticky headers, navigation */
  sticky: 200,
  /** Fixed elements (app bars) */
  fixed: 300,
  /** Modal backdrops */
  modalBackdrop: 400,
  /** Modal content */
  modal: 500,
  /** Popovers, tooltips */
  popover: 600,
  /** Toast notifications */
  toast: 700,
  /** Tooltip layer */
  tooltip: 800,
  /** Maximum layer (should rarely be used) */
  max: 9999,
} as const;

/** Type for z-index values */
export type ZIndex = (typeof zIndex)[keyof typeof zIndex];

// ============================================================================
// BREAKPOINTS
// ============================================================================

/**
 * Breakpoint definitions for responsive design.
 * Matches Material-UI default breakpoints.
 */
export const breakpoints = {
  /** 0px - Extra small screens (mobile portrait) */
  xs: 0,
  /** 600px - Small screens (mobile landscape, tablet portrait) */
  sm: 600,
  /** 900px - Medium screens (tablet landscape) */
  md: 900,
  /** 1200px - Large screens (desktop) */
  lg: 1200,
  /** 1536px - Extra large screens (large desktop) */
  xl: 1536,
} as const;

/** Type for breakpoint values */
export type Breakpoint = (typeof breakpoints)[keyof typeof breakpoints];

// ============================================================================
// TRANSITION VARIANTS
// ============================================================================

/**
 * Pre-defined transition variants for common use cases.
 */
export const transitions = {
  /** Fast fade transition */
  fadeFast: `opacity ${duration.fast}ms ${easing.easeOut}`,
  /** Standard fade transition */
  fadeStandard: `opacity ${duration.standard}ms ${easing.easeOut}`,
  /** Slow fade transition */
  fadeSlow: `opacity ${duration.slow}ms ${easing.easeOut}`,
  /** Color transition */
  color: `color ${duration.micro}ms ${easing.easeOut}`,
  /** Background color transition */
  backgroundColor: `background-color ${duration.standard}ms ${easing.easeOut}`,
  /** Border color transition */
  borderColor: `border-color ${duration.micro}ms ${easing.easeOut}`,
  /** Box shadow transition */
  boxShadow: `box-shadow ${duration.standard}ms ${easing.easeOut}`,
  /** Transform transition */
  transform: `transform ${duration.standard}ms ${easing.easeOut}`,
  /** All properties transition (use sparingly) */
  all: `all ${duration.standard}ms ${easing.easeOut}`,
  /** Combined common transitions */
  common: `background-color ${duration.micro}ms ${easing.easeOut}, 
           border-color ${duration.micro}ms ${easing.easeOut}, 
           color ${duration.micro}ms ${easing.easeOut}`,
} as const;

// ============================================================================
// COMPONENT SIZING
// ============================================================================

/**
 * Standard component sizes for consistent UI elements.
 */
export const componentSize = {
  /** Button heights */
  button: {
    small: 32,
    medium: 40,
    large: 48,
  },
  /** Input heights */
  input: {
    small: 32,
    medium: 40,
    large: 48,
  },
  /** Icon sizes */
  icon: {
    small: 16,
    medium: 20,
    large: 24,
    extraLarge: 32,
  },
  /** Avatar sizes */
  avatar: {
    small: 32,
    medium: 40,
    large: 48,
    extraLarge: 64,
  },
} as const;

// ============================================================================
// OPACITY SCALE
// ============================================================================

/**
 * Opacity values for overlays and disabled states.
 */
export const opacity = {
  /** Fully transparent */
  transparent: 0,
  /** Subtle overlay (hover states) */
  subtle: 0.04,
  /** Light overlay */
  light: 0.08,
  /** Medium overlay (disabled backgrounds) */
  medium: 0.12,
  /** Standard overlay (backdrops) */
  standard: 0.5,
  /** Dark overlay (modal backdrops) */
  dark: 0.6,
  /** Fully opaque */
  opaque: 1,
} as const;

/** Type for opacity values */
export type Opacity = (typeof opacity)[keyof typeof opacity];

// ============================================================================
// FOCUS RING TOKENS
// ============================================================================

/**
 * Focus ring tokens for keyboard accessibility and high-clarity focus states.
 */
export const focusRing = {
  width: 2,
  offset: 2,
  lightColor: "rgba(13, 115, 119, 0.32)",
  darkColor: "rgba(102, 194, 195, 0.4)",
  lightShadow: "0 0 0 3px rgba(13, 115, 119, 0.22)",
  darkShadow: "0 0 0 3px rgba(102, 194, 195, 0.32)",
} as const;

// ============================================================================
// DENSITY MODES
// ============================================================================

/**
 * Density modes for compact clinical data views vs. comfortable general pages.
 */
export const density = {
  compact: {
    buttonHeight: 32,
    inputHeight: 34,
    chipHeight: 22,
    tableRowHeight: 36,
    tableHeaderHeight: 40,
    tabMinHeight: 34,
    cardPadding: 12,
    dialogPadding: 16,
    drawerItemHeight: 40,
  },
  comfortable: {
    buttonHeight: 40,
    inputHeight: 40,
    chipHeight: 28,
    tableRowHeight: 48,
    tableHeaderHeight: 52,
    tabMinHeight: 40,
    cardPadding: 16,
    dialogPadding: 24,
    drawerItemHeight: 48,
  },
} as const;

export type DensityMode = keyof typeof density;
export type DensityTokens = (typeof density)[DensityMode];

// ============================================================================
// COMPLETE TOKEN EXPORT
// ============================================================================

/**
 * Complete design token collection for the CDSS.
 */
export const designTokens = {
  spacing,
  borderRadius,
  typography,
  elevation,
  motion,
  zIndex,
  breakpoints,
  transitions,
  componentSize,
  opacity,
  focusRing,
  density,
} as const;

export type DesignTokens = typeof designTokens;
