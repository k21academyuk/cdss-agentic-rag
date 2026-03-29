/**
 * CDSS Motion/Animation System
 *
 * Animation constants for clinical interfaces.
 * Designed for responsive but non-distracting interactions.
 *
 * @module motion
 */

// ============================================================================
// DURATION TOKENS
// ============================================================================

/**
 * Duration values for animations and transitions.
 * Clinical interfaces require quick, responsive feedback without being distracting.
 */
export const duration = {
  /** 0ms - Instant (no animation, immediate state change) */
  instant: 0,
  
  /** 100ms - Fast micro-interactions (checkbox toggle, switch) */
  fast: 100,
  
  /** 150ms - Micro-interactions (button hover, input focus) */
  micro: 150,
  
  /** 250ms - Standard transitions (dropdown, collapse, expand) */
  standard: 250,
  
  /** 400ms - Slow transitions (modal enter/exit, page transitions) */
  slow: 400,
  
  /** 500ms - Slower transitions (skeleton loading, complex reveals) */
  slower: 500,
  
  /** 600ms - Complex multi-step animations */
  complex: 600,
  
  /** 1000ms - Long-form animations (progress indicators) */
  long: 1000,
} as const;

// ============================================================================
// EASING FUNCTIONS
// ============================================================================

/**
 * Cubic-bezier easing functions for smooth, natural animations.
 * Ease-out is preferred for most UI transitions.
 */
export const easing = {
  /** Linear - constant speed throughout */
  linear: 'linear',
  
  /** Ease-in - slow start, fast end (use for exits) */
  easeIn: 'cubic-bezier(0.4, 0, 1, 1)',
  
  /** Ease-out - fast start, slow end (preferred for most UI) */
  easeOut: 'cubic-bezier(0, 0, 0.2, 1)',
  
  /** Ease-in-out - slow start and end (use for state changes) */
  easeInOut: 'cubic-bezier(0.4, 0, 0.2, 1)',
  
  /** Sharp - quick start, slow end */
  sharp: 'cubic-bezier(0.4, 0, 0.6, 1)',
  
  /** Smooth - gentle deceleration for clinical precision */
  clinical: 'cubic-bezier(0.25, 0.1, 0.25, 1)',
  
  /** Emphasized - more pronounced deceleration */
  emphasized: 'cubic-bezier(0.2, 0, 0, 1)',
  
  /** Bounce - playful effect (use very sparingly in clinical context) */
  bounce: 'cubic-bezier(0.68, -0.55, 0.265, 1.55)',
} as const;

// ============================================================================
// TRANSITION VARIANTS
// ============================================================================

/**
 * Pre-built transition strings for common use cases.
 */
export const transitions = {
  // Fade transitions
  fade: {
    fast: `opacity ${duration.fast}ms ${easing.easeOut}`,
    standard: `opacity ${duration.standard}ms ${easing.easeOut}`,
    slow: `opacity ${duration.slow}ms ${easing.easeOut}`,
  },
  
  // Color transitions
  color: {
    fast: `color ${duration.fast}ms ${easing.easeOut}`,
    standard: `color ${duration.standard}ms ${easing.easeOut}`,
  },
  
  // Background transitions
  background: {
    fast: `background-color ${duration.fast}ms ${easing.easeOut}`,
    standard: `background-color ${duration.standard}ms ${easing.easeOut}`,
    slow: `background-color ${duration.slow}ms ${easing.easeOut}`,
  },
  
  // Border transitions
  border: {
    fast: `border-color ${duration.fast}ms ${easing.easeOut}`,
    standard: `border-color ${duration.standard}ms ${easing.easeOut}`,
  },
  
  // Transform transitions
  transform: {
    fast: `transform ${duration.fast}ms ${easing.easeOut}`,
    standard: `transform ${duration.standard}ms ${easing.easeOut}`,
    slow: `transform ${duration.slow}ms ${easing.easeOut}`,
  },
  
  // Box shadow transitions
  shadow: {
    standard: `box-shadow ${duration.standard}ms ${easing.easeOut}`,
    slow: `box-shadow ${duration.slow}ms ${easing.easeOut}`,
  },
  
  // Combined transitions
  all: {
    fast: `all ${duration.fast}ms ${easing.easeOut}`,
    standard: `all ${duration.standard}ms ${easing.easeOut}`,
    slow: `all ${duration.slow}ms ${easing.easeOut}`,
  },
  
  // Common combined transitions
  common: `background-color ${duration.micro}ms ${easing.easeOut}, border-color ${duration.micro}ms ${easing.easeOut}, color ${duration.micro}ms ${easing.easeOut}`,
  
  interactive: `background-color ${duration.micro}ms ${easing.easeOut}, border-color ${duration.micro}ms ${easing.easeOut}, color ${duration.micro}ms ${easing.easeOut}, box-shadow ${duration.standard}ms ${easing.easeOut}`,
} as const;

// ============================================================================
// ANIMATION KEYFRAMES
// ============================================================================

/**
 * CSS keyframe animation definitions.
 * These should be registered with the theme's augmentGlobalCss feature.
 */
export const keyframes = {
  /** Fade in animation */
  fadeIn: {
    '0%': { opacity: 0 },
    '100%': { opacity: 1 },
  },
  
  /** Fade out animation */
  fadeOut: {
    '0%': { opacity: 1 },
    '100%': { opacity: 0 },
  },
  
  /** Slide in from top */
  slideInTop: {
    '0%': { transform: 'translateY(-100%)', opacity: 0 },
    '100%': { transform: 'translateY(0)', opacity: 1 },
  },
  
  /** Slide in from bottom */
  slideInBottom: {
    '0%': { transform: 'translateY(100%)', opacity: 0 },
    '100%': { transform: 'translateY(0)', opacity: 1 },
  },
  
  /** Slide in from left */
  slideInLeft: {
    '0%': { transform: 'translateX(-100%)', opacity: 0 },
    '100%': { transform: 'translateX(0)', opacity: 1 },
  },
  
  /** Slide in from right */
  slideInRight: {
    '0%': { transform: 'translateX(100%)', opacity: 0 },
    '100%': { transform: 'translateX(0)', opacity: 1 },
  },
  
  /** Scale in (pop in) */
  scaleIn: {
    '0%': { transform: 'scale(0.9)', opacity: 0 },
    '100%': { transform: 'scale(1)', opacity: 1 },
  },
  
  /** Scale out (pop out) */
  scaleOut: {
    '0%': { transform: 'scale(1)', opacity: 1 },
    '100%': { transform: 'scale(0.9)', opacity: 0 },
  },
  
  /** Pulse animation (for loading states) */
  pulse: {
    '0%, 100%': { opacity: 1 },
    '50%': { opacity: 0.5 },
  },
  
  /** Spin animation */
  spin: {
    '0%': { transform: 'rotate(0deg)' },
    '100%': { transform: 'rotate(360deg)' },
  },
  
  /** Shake animation (for errors) */
  shake: {
    '0%, 100%': { transform: 'translateX(0)' },
    '10%, 30%, 50%, 70%, 90%': { transform: 'translateX(-4px)' },
    '20%, 40%, 60%, 80%': { transform: 'translateX(4px)' },
  },
  
  /** Bounce animation */
  bounce: {
    '0%, 100%': { transform: 'translateY(0)' },
    '50%': { transform: 'translateY(-10px)' },
  },
} as const;

// ============================================================================
// ANIMATION VARIANTS
// ============================================================================

/**
 * Complete animation configurations combining duration, easing, and keyframes.
 */
export const animations = {
  /** Quick fade in */
  fadeIn: {
    animation: 'fadeIn',
    duration: duration.fast,
    easing: easing.easeOut,
  },
  
  /** Standard fade in */
  fadeInStandard: {
    animation: 'fadeIn',
    duration: duration.standard,
    easing: easing.easeOut,
  },
  
  /** Modal enter animation */
  modalEnter: {
    animation: 'scaleIn',
    duration: duration.standard,
    easing: easing.emphasized,
  },
  
  /** Modal exit animation */
  modalExit: {
    animation: 'scaleOut',
    duration: duration.fast,
    easing: easing.easeIn,
  },
  
  /** Drawer enter animation */
  drawerEnter: {
    animation: 'slideInLeft',
    duration: duration.standard,
    easing: easing.easeOut,
  },
  
  /** Snackbar enter animation */
  snackbarEnter: {
    animation: 'slideInBottom',
    duration: duration.standard,
    easing: easing.easeOut,
  },
  
  /** Loading spinner */
  spinner: {
    animation: 'spin',
    duration: 1000,
    easing: easing.linear,
    iterationCount: 'infinite',
  },
  
  /** Skeleton loading pulse */
  skeletonPulse: {
    animation: 'pulse',
    duration: duration.slower * 2,
    easing: easing.easeInOut,
    iterationCount: 'infinite',
  },
  
  /** Error shake */
  errorShake: {
    animation: 'shake',
    duration: duration.standard * 2,
    easing: easing.easeOut,
  },
} as const;

// ============================================================================
// REDUCED MOTION SUPPORT
// ============================================================================

/**
 * Motion preferences for accessibility.
 * These values should be used when `prefers-reduced-motion` is enabled.
 */
export const reducedMotion = {
  duration: {
    instant: 0,
    fast: 0,
    micro: 0,
    standard: 0,
    slow: 0,
    slower: 0,
    complex: 0,
    long: 0,
  },
  easing: easing.linear,
  transitions: {
    fade: 'opacity 0ms',
    color: 'color 0ms',
    background: 'background-color 0ms',
    border: 'border-color 0ms',
    transform: 'transform 0ms',
    shadow: 'box-shadow 0ms',
    all: 'all 0ms',
    common: 'none',
    interactive: 'none',
  },
} as const;

// ============================================================================
// TYPE EXPORTS
// ============================================================================

export type Duration = typeof duration;
export type Easing = typeof easing;
export type Transitions = typeof transitions;
export type Keyframes = typeof keyframes;
export type Animations = typeof animations;
