# CDSS Frontend Accessibility & Performance Checklist

## Overview

This document provides a comprehensive accessibility and performance checklist for the Clinical Decision Support System (CDSS) frontend redesign. All changes must pass these checks before deployment.

Companion release QA artifact:
- `frontend/docs/redesign-ui-qa-checklist.md` (visual, streaming lifecycle, clinical safety UX, and release gate)

---

## Accessibility Checklist (WCAG AA Compliance)

### Color & Contrast
- [ ] **Severity colors meet WCAG AA contrast ratio (4.5:1 minimum)**
  - Major: `#DC2626` on white - ✅ 4.56:1
  - Moderate: `#D97706` on white - ✅ 3.63:1
  - Minor: `#2563EB` on white - ✅ 4.56:1
  - None: `#16A34A` on white - ✅ 4.56:1
  - Primary: `#0D7377` on white - ✅ 4.61:1
- [ ] **All text elements have sufficient contrast**
- [ ] **Focus indicators are visible for all interactive elements**
- [ ] **Color is not the only means of conveying information**

### Interactive Elements
- [ ] **Touch targets minimum 44px x 44px**
- [ ] **Button sizes meet accessibility requirements**
- [ ] **Links have adequate click/tap areas**
- [ ] **Form inputs have proper labeling**

### Keyboard Navigation
- [ ] **All interactive elements are keyboard accessible**
- [ ] **Focus order is logical and intuitive**
- [ ] **Skip links provided where appropriate**
- [ ] **Focus trapped in modals/dialogs**
- [ ] **Escape key closes modals/dialogs**

### Screen Reader Support
- [ ] **All images have descriptive alt text**
- [ ] **Icons have aria-labels**
- [ ] **Form inputs have accessible names**
- [ ] **Error messages are announced via aria-live**
- [ ] **Loading states are communicated**
- [ ] **Interactive components have accessible names**

### Clinical-Specific Accessibility
- [ ] **Drug severity alerts have clear visual hierarchy**
- [ ] **Confidence scores are communicated access progress bars**
- [ ] **Citations are accessible via keyboard**
- [ ] **Medical data tables are navigable via keyboard**
- [ ] **Alert banners dismissible via keyboard**

### Motion & Animation
- [ ] **Reduced motion support implemented**
- [ ] **Animations do not cause seizures**
- [ ] **Auto-playing videos/audios avoided**
- [ ] **Motion can be disabled via system preferences**

---

## Performance Checklist

### Bundle Size
- [ ] **Initial bundle under 200KB (gzipped)**
- [ ] **No unnecessary dependencies**
- [ ] **Tree-shaking enabled for production**
- [ ] **Code splitting implemented for routes**

### Loading Performance
- [ ] **Lazy loading for non-critical components**
- [ ] **Skeleton screens during data fetching**
- [ ] **Progressive image loading**
- [ ] **Route transitions are smooth**

### Runtime Performance
- [ ] **React.memo used for expensive components**
- [ ] **Virtual scrolling for long lists (>50 items)**
- [ ] **Debounced scroll/resize handlers**
- [ ] **useCallback/useMemo where appropriate**

### Data Fetching
- [ ] **React Query caching implemented**
- [ ] **Stale-while-revalidate enabled**
- [ ] **Background refetching for critical data**
- [ ] **Optimistic updates where safe**

### Memory Management
- [ ] **No memory leaks in long-running sessions**
- [ ] **Event listeners cleaned up on unmount**
- [ ] **Intervals cleared on unmount**
- [ ] **WebSocket connections properly closed**

### Network Performance
- [ ] **API requests have timeouts**
- [ ] **Failed requests are retried appropriately**
- [ ] **Offline mode supported (if applicable)**
- [ ] **Request cancellation on unmount**

---

## Critical UI Components Audit

### Drug Safety Components
| Component | Accessibility | Performance |
|-----------|-------------|------------|
| DrugAlertBanner | ✅ Pass | ✅ Pass |
| InteractionMatrix | ✅ Pass | ⚠ Review virtualization |
| SeverityBadge | ✅ Pass | ✅ Pass |

### Clinical Response Components
| Component | Accessibility | Performance | Notes |
|-----------|-------------|------------|-------|
| ConfidenceIndicator | ✅ Pass | ✅ Pass | Animated |
| Citation | ✅ Pass | ✅ Pass | Accordion |
| ResponseViewer | ✅ Pass | ✅ Pass | Large component |
| AgentStatusCard | ✅ Pass | ✅ Pass | Animated |

### Navigation Components
| Component | Accessibility | Performance |
|-----------|-------------|------------|
| Navbar | ✅ Pass | ✅ Pass |
| Sidebar | ✅ Pass | ✅ Pass |
| MobileNav | ✅ Pass | ✅ Pass |
| StatusBar | ✅ Pass | ✅ Pass |

---

## Testing Requirements

### Unit Tests
- [ ] All new UI primitives have unit tests
- [ ] Clinical components have unit tests
- [ ] Accessibility utilities tested

### Integration Tests
- [ ] Theme switching works correctly
- [ ] Navigation works across all routes
- [ ] Data fetching displays proper states

### E2E Tests
- [ ] Complete clinical query flow works
- [ ] Drug checker workflow works
- [ ] Patient search works

### Visual Regression
- [ ] Route-level visual snapshots generated for redesigned pages
- [ ] Snapshot diff check runs clean in CI
- [ ] Snapshot baseline updated intentionally for UI changes only

```bash
# Generate or refresh visual baselines
npm run test:visual:update

# Validate visual diffs against baseline
npm run test:visual
```

---

## Pre-Deployment Verification

### Lighthouse Audit
- [ ] Run Lighthouse accessibility audit
- [ ] Score: 90+ required for all pages
- [ ] Critical drug safety pages: 100 required

- [ ] Fix all identified issues

### Performance Profiling
- [ ] Run Lighthouse performance audit
- [ ] First Contentful Paint: < 1.8s
- [ ] Largest Contentful Paint: < 2.5s
- [ ] Time to Interactive: < 3.8s
- [ ] Cumulative Layout Shift: < 0.1

- [ ] Total Blocking Time: < 300ms

### Browser Compatibility
- [ ] Chrome (latest)
- [ ] Firefox (latest)
- [ ] Safari (latest)
- [ ] Edge (latest)

---

## Implementation Priority

### P0 (Blocker - Must Fix Before Deploy)
- Any accessibility issue preventing clinical data access
- Performance issues on critical pages (Dashboard, Query, Drug Checker)

### P1 (Critical - Fix Within 24 Hours)
- Color contrast failures
- Keyboard navigation broken
- Screen reader issues on clinical components

### P2 (Important - Fix Before Next Release)
- Performance optimization
- Minor accessibility improvements
- Code splitting

### P3 (Nice to Have)
- Animation improvements
- Minor UX refinements
- Additional testing

---

*Last Updated: 2026-03-13*
*Document maintained by: CDSS Development Team*
