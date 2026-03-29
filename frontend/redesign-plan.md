# CDSS Frontend Redesign Plan

## Overview

This document outlines the comprehensive redesign plan for the Clinical Decision Support System (CDSS) frontend to The goal is to create a modern, premium, trustworthy clinical interface while preserving clinical clarity and patient safety.

## Current State Analysis

### Existing Issues
- Generic MUI blue theme (#1976d2) lacks clinical gravitas
- No centralized design token system
- Inconsistent severity color usage across components
- Limited motion/interaction design
- Weak visual hierarchy for complex medical data

### Tech Stack
- React 18 + TypeScript 5.3
- Vite 5.1
- MUI v5.15
- React Query v5.24
- Zustand v4.5
- Recharts 2.12

## Phase 1: Design System Foundation ✅ COMPLETE

### Files Created
```
frontend/src/theme/
├── designTokens.ts    # Comprehensive token definitions
├── palette.ts          # Color palette with semantic severity colors
├── typography.ts       # Typography scale configuration
├── shadows.ts           # Elevation/shadow system
├── motion.ts            # Animation/motion constants
├── clinical.ts          # Clinical-specific colors
└── index.ts            # Main export with MUI theme creation
```

### Key Design Decisions

| Token | Value | Rationale |
|-------|-------|----------|
| **Primary Color** | `#0D7377` | Deep, trustworthy clinical teal |
| **Drug Severity Major** | `#DC2626` | Critical - demands immediate clinical attention |
| **Drug Severity Moderate** | `#D97706` | Warning - requires monitoring |
| **Drug Severity Minor** | `#2563EB` | Informational - low priority |
| **Drug Severity None** | `#16A34A` | Safe - no interaction |
| **Font Family** | Inter | Modern, highly legible |
| **Border Radius** | 8px default | Professional, clinical feel |
| **Motion Duration** | 150-400ms | Quick, non-distracting |

### Semantic Severity Colors (CRITICAL)

All severity colors are **SEMANTICALLY STABLE** and WCAG AA compliant:

```typescript
severity: {
  major: {
    main: '#DC2626', light: '#EF4444', dark: '#991B1B',
    description: 'Critical drug interaction requiring immediate clinical attention'
  },
  moderate: {
    main: '#D97706', light: '#FEF3C7', dark: '#92400E',
    description: 'Drug interaction requiring monitoring and dose adjustment'
  },
  minor: {
    main: '#2563EB', light: '#DBEAFE', dark: '#1E40AF',
    description: 'Low severity drug interaction - informational only'
  },
  none: {
    main: '#16A34A', light: '#DCFCE7', dark: '#15803d',
    description: 'No drug interaction - safe status'
  }
}
```

### Theme Integration

```typescript
// In main.tsx, replace:
const lightTheme = createTheme({ palette: { mode: 'light', primary: { main: '#1976d2' } } });
const darkTheme = createTheme({ palette: { mode: 'dark', primary: { main: '#90caf9' } } });

// With:
import { lightTheme, darkTheme, getTheme } from '@/theme';
import { useThemeStore } from '@/stores/userStore';

const ThemedApp: React.FC = () => {
  const themeMode = useThemeStore((state) => state.theme);
  const theme = getTheme(themeMode);
  
  return (
    <ThemeProvider theme={theme}>
      {/* app content */}
    </ThemeProvider>
  );
};
```

## Phase 2: Core UI Primitives (IN PROGRESS)

### Components to Create

| Component | Variants | Purpose |
|-----------|----------|---------|
| `Button` | primary, secondary, ghost, danger, clinical | Action buttons |
| `Card` | default, elevated, outlined, clinical | Content containers |
| `Input` | text, search, textarea, clinical | Form inputs |
| `Alert` | success, warning, error, info, clinical | Notifications |
| `Badge` | severity, status, dot | Status indicators |
| `Chip` | default, filter, clinical | Tags and filters |
| `Skeleton` | text, card, table, clinical | Loading states |
| `Progress` | linear, circular, confidence | Progress indicators |

### Directory Structure
```
frontend/src/components/ui/
├── Button.tsx
├── Card.tsx
├── Input.tsx
├── Alert.tsx
├── Badge.tsx
├── Chip.tsx
├── Skeleton.tsx
├── Progress.tsx
└── index.ts
```

## Phase 3: Clinical Components (IN PROGRESS)

### Components to Create/Update

| Component | Status | Description |
|-----------|--------|-------------|
| `ConfidenceIndicator` | NEW | Visual confidence score with color-coded progress bar |
| `Citation` | NEW | Expandable citation with source type icons |
| `AgentStatusCard` | NEW | Multi-agent status display with progress |
| `EvidenceSummary` | NEW | Evidence breakdown with grade badges |
| `DrugAlertBanner` | UPDATE | Enhanced styling with new severity colors |
| `ResponseViewer` | UPDATE | Improved visual hierarchy and styling |

### Clinical Design Requirements
- **Drug severity MUST be visually obvious**
- **Confidence scores MUST be clearly visible**
- **Citations MUST be prominent and verifiable**
- **Guardrails/safety MUST be explicit and non-ambiguous**
- **NO playful visual metaphors**

## Phase 4: Layout Components (IN PROGRESS)

### Components to Create/Update

| Component | Status | Description |
|-----------|--------|-------------|
| `AppShell` | NEW | Main layout container with responsive design |
| `Navbar` | UPDATE | Modern top navigation with theme toggle |
| `Sidebar` | UPDATE | Enhanced navigation with active route indication |
| `StatusBar` | NEW | Bottom status strip for system health |
| `MobileNav` | NEW | Mobile navigation for small screens |
| `Layout` | UPDATE | Update to use new AppShell |

### Layout Specifications
- **Sidebar width**: 240px desktop, drawer on mobile
- **Navbar height**: 64px
- **Status bar height**: 32px
- **Responsive breakpoint**: 960px (MUI md)

- **Mobile-first approach**

## Phase 5: Page Components (PENDING)

### Pages to Update

| Page | Priority | Key Changes |
|------|----------|-------------|
| `Dashboard` | HIGH | New stat cards, activity feed, system status |
| `QueryPage` | HIGH | Improved query input, streaming UI, response viewer |
| `PatientPage` | HIGH | Enhanced patient profile, medication list, lab charts |
| `DrugCheckerPage` | HIGH | Updated interaction matrix, severity indicators |
| `LiteraturePage` | MEDIUM | Improved search UI, citation display |
| `DocumentUploadPage` | MEDIUM | Drag-drop upload, processing status |
| `AdminPage` | LOW | Updated audit trail, system status |
| `SettingsPage` | LOW | Theme controls, preferences |

## Phase 6: Accessibility & Performance (PENDING)

### Accessibility Checklist
- [ ] All interactive elements have visible focus indicators
- [ ] Color contrast ratios meet WCAG AA (4.5:1 minimum)
- [ ] Touch targets minimum 44px
- [ ] Screen reader accessible
- [ ] Keyboard navigation fully functional
- [ ] Error messages are announced clearly
- [ ] Form labels properly associated with inputs
- [ ] Skip links provided for main content
- [ ] ARIA landmarks used where appropriate

### Performance Checklist
- [ ] Design tokens pre-computed at build time
- [ ] Tree-shaking for production builds
- [ ] Critical rendering path optimized
- [ ] Bundle size analyzed (< 200KB gzipped)
- [ ] React.memo for expensive components
- [ ] Virtual scrolling for long lists
- [ ] Lazy loading with skeletons
- [ ] Image optimization (WebP, lazy loading)

## Phase 7: Documentation (PENDING)

### Documentation to Create
- `frontend/docs/DESIGN_SYSTEM.md` - Comprehensive design system documentation
- Component usage examples
- Migration guide
- Accessibility guidelines

## Migration Strategy

### Low-Risk Migration Order
1. **Phase 1** - Add design system (additive, no breaking changes)
2. **Phase 2** - Add UI primitives (additive, can be used incrementally)
3. **Phase 3** - Update clinical components (update existing, maintain API)
4. **Phase 4** - Update layout (update existing, maintain structure)
5. **Phase 5** - Update pages (can be done one at a time)
6. **Phase 6** - Add accessibility features (additive)
7. **Phase 7** - Add documentation (additive)

### Testing Strategy
- Unit tests for new UI primitives
- Integration tests for clinical components
- Visual regression tests for layout changes
- Accessibility audits for all pages

## Timeline Estimate
- **Week 1**: Phase 1 (Design System) ✅ COMPLETE
- **Week 2**: Phase 2-4 (Components) - In Progress
- **Week 3-4**: Phase 5 (Pages)
- **Week 5**: Phase 6-7 (Accessibility & Documentation)

## Files Changed Summary

### Created (15 files)
- `frontend/src/theme/` (7 files)
- `frontend/src/components/ui/` (9 files)
- `frontend/src/components/layout/` (6 files)

### Updated (10 files)
- `frontend/src/main.tsx` - Theme integration
- `frontend/src/components/common/Layout.tsx`
- `frontend/src/components/common/Navbar.tsx`
- `frontend/src/components/common/Sidebar.tsx`
- `frontend/src/components/clinical/DrugAlertBanner.tsx`
- `frontend/src/components/clinical/ResponseViewer.tsx`
- `frontend/src/pages/Dashboard.tsx`
- `frontend/src/pages/QueryPage.tsx`
- `frontend/src/pages/PatientPage.tsx`
- `frontend/src/pages/DrugCheckerPage.tsx`

## Risk Assessment
- **Low Risk**: Additive changes (design system, primitives)
- **Medium Risk**: Component updates (clinical, layout)
- **High Risk**: Page updates (requires thorough testing)

## Dependencies
- **No new dependencies required**
- Using existing: MUI v5, React Query, Zustand, Recharts

## Next Steps
1. Wait for background agents to complete UI primitives and clinical components, and layout components
2. Verify created components
3. Update `main.tsx` to use new theme system
4. Update page components incrementally
5. Run accessibility audit
6. Create documentation

---

*This is a living document and will be updated as implementation progresses.*
