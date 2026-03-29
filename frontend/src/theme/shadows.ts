/**
 * CDSS Shadow/Elevation System
 *
 * Uses a 5-level design vocabulary, expanded to the 25-level MUI shadow scale.
 * Includes specialized shadows for clinical alerts and notifications.
 *
 * @module shadows
 */

// ============================================================================
// BASE SHADOWS (5 DESIGN LEVELS -> 25 MUI LEVELS)
// ============================================================================

/**
 * Base shadow definitions for elevation hierarchy.
 * Designed for clinical interfaces - subtle but functional.
 */
const lightShadowBase = [
  // Level 0: No shadow (flat)
  'none',
  
  // Level 1: Subtle elevation
  // Use for: hover states, raised buttons, focused inputs
  '0px 1px 2px rgba(0, 0, 0, 0.05), 0px 1px 3px rgba(0, 0, 0, 0.1)',
  
  // Level 2: Low elevation
  // Use for: cards, list items, dropdown triggers
  '0px 2px 4px rgba(0, 0, 0, 0.05), 0px 2px 6px rgba(0, 0, 0, 0.08)',
  
  // Level 3: Medium elevation
  // Use for: dropdowns, popovers, sticky headers
  '0px 4px 6px rgba(0, 0, 0, 0.05), 0px 4px 12px rgba(0, 0, 0, 0.1)',
  
  // Level 4: High elevation
  // Use for: modals, dialogs, floating action buttons
  '0px 8px 16px rgba(0, 0, 0, 0.08), 0px 8px 24px rgba(0, 0, 0, 0.12)',
] as const;

function expandMuiShadows(base: readonly string[]): string[] {
  // MUI components can request elevations up to 24 (e.g., Drawer uses 16).
  // Repeat the highest designed level for any remaining slots.
  return Array.from({ length: 25 }, (_, index) => base[Math.min(index, base.length - 1)]);
}

export const shadows = expandMuiShadows(lightShadowBase);

// ============================================================================
// CLINICAL ALERT SHADOWS
// ============================================================================

/**
 * Specialized shadows for clinical alerts and notifications.
 * Color-tinted to match severity levels.
 */
export const clinicalShadows = {
  /** Critical/major alert shadow - red tinted */
  critical: '0px 4px 12px rgba(220, 38, 38, 0.2), 0px 2px 6px rgba(220, 38, 38, 0.15)',
  
  /** Warning/moderate alert shadow - amber tinted */
  warning: '0px 4px 12px rgba(217, 119, 6, 0.2), 0px 2px 6px rgba(217, 119, 6, 0.15)',
  
  /** Info/minor alert shadow - blue tinted */
  info: '0px 4px 12px rgba(37, 99, 235, 0.2), 0px 2px 6px rgba(37, 99, 235, 0.15)',
  
  /** Success/safe status shadow - green tinted */
  success: '0px 4px 12px rgba(22, 163, 74, 0.2), 0px 2px 6px rgba(22, 163, 74, 0.15)',
} as const;

// ============================================================================
// DARK MODE SHADOWS
// ============================================================================

/**
 * Shadow definitions optimized for dark mode.
 * Uses lighter, more subtle shadows on dark backgrounds.
 */
const darkShadowBase = [
  // Level 0: No shadow
  'none',
  
  // Level 1: Subtle elevation
  '0px 1px 2px rgba(0, 0, 0, 0.2), 0px 1px 3px rgba(0, 0, 0, 0.3)',
  
  // Level 2: Low elevation
  '0px 2px 4px rgba(0, 0, 0, 0.2), 0px 2px 6px rgba(0, 0, 0, 0.25)',
  
  // Level 3: Medium elevation
  '0px 4px 6px rgba(0, 0, 0, 0.2), 0px 4px 12px rgba(0, 0, 0, 0.3)',
  
  // Level 4: High elevation
  '0px 8px 16px rgba(0, 0, 0, 0.25), 0px 8px 24px rgba(0, 0, 0, 0.35)',
] as const;

export const darkShadows = expandMuiShadows(darkShadowBase);

// ============================================================================
// INTERACTIVE STATE SHADOWS
// ============================================================================

/**
 * Shadows for interactive component states.
 * Used for hover, focus, and active states.
 */
export const interactiveShadows = {
  /** Default resting state */
  resting: shadows[1],
  
  /** Hover state - slightly elevated */
  hover: '0px 2px 4px rgba(0, 0, 0, 0.08), 0px 4px 8px rgba(0, 0, 0, 0.12)',
  
  /** Focus state - with ring effect */
  focus: '0px 0px 0px 3px rgba(13, 115, 119, 0.2), 0px 2px 4px rgba(0, 0, 0, 0.1)',
  
  /** Active/pressed state - reduced elevation */
  active: '0px 1px 2px rgba(0, 0, 0, 0.1)',
  
  /** Disabled state - no shadow */
  disabled: 'none',
} as const;

// ============================================================================
// COMPONENT-SPECIFIC SHADOWS
// ============================================================================

/**
 * Shadows for specific UI components.
 */
export const componentShadows = {
  /** App bar / header shadow */
  appBar: '0px 1px 3px rgba(0, 0, 0, 0.08), 0px 1px 2px rgba(0, 0, 0, 0.06)',
  
  /** Navigation drawer shadow */
  drawer: '0px 8px 24px rgba(0, 0, 0, 0.12), 0px 4px 12px rgba(0, 0, 0, 0.08)',
  
  /** Card shadow */
  card: shadows[2],
  
  /** Card hover shadow */
  cardHover: shadows[3],
  
  /** Menu/tooltip shadow */
  menu: shadows[3],
  
  /** Dialog/modal shadow */
  dialog: shadows[4],
  
  /** Snackbar/toast shadow */
  snackbar: '0px 6px 16px rgba(0, 0, 0, 0.15), 0px 3px 6px rgba(0, 0, 0, 0.1)',
  
  /** Floating action button shadow */
  fab: shadows[3],
  
  /** FAB hover shadow */
  fabHover: shadows[4],
} as const;

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/**
 * Creates a colored shadow for custom alert components.
 * @param color - The base color (hex format)
 * @param opacity - The opacity multiplier (0-1)
 * @returns CSS box-shadow string
 */
export function createColoredShadow(color: string, opacity = 0.2): string {
  return `0px 4px 12px rgba(${hexToRgb(color)}, ${opacity}), 0px 2px 6px rgba(${hexToRgb(color)}, ${opacity * 0.75})`;
}

/**
 * Converts a hex color to RGB values string.
 * @param hex - Hex color string (with or without #)
 * @returns RGB values as "r, g, b"
 */
function hexToRgb(hex: string): string {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  if (!result) {
    return '0, 0, 0';
  }
  return `${parseInt(result[1], 16)}, ${parseInt(result[2], 16)}, ${parseInt(result[3], 16)}`;
}

// ============================================================================
// TYPE EXPORTS
// ============================================================================

export type Shadow = typeof shadows[number];
export type ClinicalShadow = typeof clinicalShadows[keyof typeof clinicalShadows];
export type InteractiveShadow = typeof interactiveShadows[keyof typeof interactiveShadows];
export type ComponentShadow = typeof componentShadows[keyof typeof componentShadows];
