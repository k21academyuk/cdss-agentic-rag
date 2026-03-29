# CDSS Redesigned UI Test & QA Checklist

## Scope
This checklist is the release QA baseline for redesigned CDSS frontend routes and shared UI systems.

- Routes in scope: `/`, `/query`, `/patients`, `/drugs`, `/literature`, `/documents`, `/admin`
- Viewports in scope: `1440x1024`, `1024x768`, `768x1024`, `390x844`
- Core UX in scope: app shell, streaming lifecycle, clinical safety indicators, accessibility, and performance.

---

## 1) Visual Regression Checkpoints

### Commands
```bash
# Refresh baseline snapshots intentionally
npm run test:visual:update

# Verify no unexpected diffs
npm run test:visual
```

### Route x Viewport Matrix
- [ ] Dashboard (`/`) snapshots pass at desktop/laptop/tablet/mobile
- [ ] Query (`/query`) snapshots pass at desktop/laptop/tablet/mobile
- [ ] Patients (`/patients`) snapshots pass at desktop/laptop/tablet/mobile
- [ ] Drug Checker (`/drugs`) snapshots pass at desktop/laptop/tablet/mobile
- [ ] Literature (`/literature`) snapshots pass at desktop/laptop/tablet/mobile
- [ ] Documents (`/documents`) snapshots pass at desktop/laptop/tablet/mobile
- [ ] Admin (`/admin`) snapshots pass at desktop/laptop/tablet/mobile

### Review Rules
- [ ] Any snapshot change has a linked UI change reason in PR notes
- [ ] No unreviewed snapshot churn from transient content (timestamps/animations)
- [ ] Baselines updated only when UX/layout change is intentional

---

## 2) Functional Checks: Query Streaming Lifecycle

### Entry + Start
- [ ] Query page loads without console/runtime errors
- [ ] Submit enabled only when query input is valid
- [ ] Stream start transitions state `idle -> streaming`
- [ ] Timeline logs `stream_start` event

### In-flight Behavior
- [ ] Agent cards/timeline show start/progress/complete events in expected order
- [ ] Progress values update continuously without layout jank
- [ ] Guardrail validation phase appears (`validation_start`, `validation_complete`)
- [ ] Partial data renders progressively without blocking final response sections

### Completion + Error Paths
- [ ] Success path transitions to `completed` with response sections visible
- [ ] Agent failure path transitions to `partial_failure` with failed agent visibility
- [ ] Transport/runtime error path transitions to `error` with actionable message
- [ ] User cancellation transitions to `cancelled` and halts further updates
- [ ] Reset returns state to `idle` and clears timeline/response/error

### Retry + Recovery
- [ ] Retry from failed/cancelled path starts a clean new stream
- [ ] Previous stream artifacts do not leak into new run

---

## 3) Accessibility Checks

### Contrast + Semantics
- [ ] Text and non-text contrast meets WCAG AA in light mode
- [ ] Major/moderate/minor/safe indicators are not color-only (icon/text/label also present)
- [ ] Alerts and key statuses have accessible names

### Focus and Keyboard-Only Flows
- [ ] Focus order is logical in app shell and all redesigned routes
- [ ] All primary flows complete with keyboard only (Tab/Shift+Tab/Enter/Space/Escape)
- [ ] Focus indicator is always visible on interactive components
- [ ] No keyboard traps in menus/drawers/dialogs
- [ ] Drawer and menu close behavior works with keyboard (`Escape`)

### Forms, Labels, and Announcements
- [ ] Inputs, selectors, and tokenized controls have explicit labels
- [ ] Required fields expose validation message accessibly
- [ ] Loading/streaming/error updates are announced where appropriate
- [ ] Table/list controls are navigable and announce headers/labels correctly

---

## 4) Performance Budgets

### Budgets (Production Build, representative network/device)
- [ ] LCP <= 2.5s for critical routes (`/`, `/query`, `/drugs`)
- [ ] CLS <= 0.10 on all redesigned routes
- [ ] Interaction latency (INP or p95 interaction delay) <= 200ms for primary actions
- [ ] No long task > 200ms during initial route render on critical routes

### Measurement Workflow
- [ ] Run Lighthouse for in-scope routes and archive report links/artifacts
- [ ] Validate Web Vitals in browser performance tooling for at least desktop + mobile viewport
- [ ] Confirm bundle/profile changes are expected after shell and motion updates

---

## 5) Clinical Safety UX Checks

### Major Alert Prominence
- [ ] Major drug alerts are visually dominant over moderate/minor alerts
- [ ] Major alerts remain visible without deep scrolling when relevant
- [ ] Alert severity text is explicit and clinically unambiguous

### Guardrail Result Visibility
- [ ] Guardrail status is visible in final response area without hidden dependency on logs
- [ ] Guardrail failures/warnings are persistent until explicit reset/new query
- [ ] Partial-failure guardrail states remain obvious after stream completion

### Citation Traceability
- [ ] Each recommendation has traceable citations with source identifiers
- [ ] Citation actions (open/copy/drill-down) are discoverable and keyboard accessible
- [ ] Citation metadata (source, relevance/evidence cues) is scannable

### Disclaimer Persistence
- [ ] Clinical disclaimers remain visible in final response state
- [ ] Disclaimers are not dropped on viewport changes or route-level reflow
- [ ] Disclaimers persist through partial failure and retry flows

---

## 6) Final Release Gate (Pass/Fail)

Release can proceed only if all gate conditions are **PASS**.

| Gate | Criteria | Status |
|---|---|---|
| Visual Regression | All route/viewport snapshot checks pass with approved diffs only | [ ] PASS / [ ] FAIL |
| Streaming Functional | All lifecycle scenarios (`completed`, `partial_failure`, `cancelled`, `error`) validated | [ ] PASS / [ ] FAIL |
| Accessibility | Keyboard-only flow + contrast + labeling checks pass | [ ] PASS / [ ] FAIL |
| Performance | LCP/CLS/interaction budgets met for critical routes | [ ] PASS / [ ] FAIL |
| Clinical Safety UX | Major alert prominence, guardrails, citations, disclaimers verified | [ ] PASS / [ ] FAIL |
| Regression Risk | No blocker/high severity defects open | [ ] PASS / [ ] FAIL |

### Sign-off
- QA Owner: ____________________
- Clinical Reviewer: ____________________
- Engineering Owner: ____________________
- Date (UTC): ____________________

If any gate is **FAIL**, release is blocked until remediation and re-validation are complete.
