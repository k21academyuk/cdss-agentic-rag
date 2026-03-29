# Clinical AI Frontend Design System (MUI + CSS Variables)

## 1) Token Table

| Category | Token Group | Key Tokens | Notes |
| --- | --- | --- | --- |
| Typography | `fontFamily` | `heading = Manrope`, `clinical = IBM Plex Sans`, `monospace` | Headings/UI chrome use Manrope, dense clinical text uses IBM Plex Sans |
| Semantic Roles | `semanticRoles.light` / `semanticRoles.dark` | `surface`, `border`, `text`, `accent`, `success`, `warning`, `critical`, `info`, `muted` | Mode-aware role tokens injected as CSS vars (`--cdss-role-*`) |
| Medical Status | `medicalStatusTokens.light` / `medicalStatusTokens.dark` | `critical`, `warning`, `info`, `success` | Maps clinical risk levels to foreground/surface/border tokens (`--cdss-status-*`) |
| Layout Scale | `spacing` | `0,1,2,3,4,6,8,12,16,24,32` | 4px base scale for consistent spacing rhythm |
| Radius Scale | `borderRadius` | `none, xs, sm, md, lg, xl, full` | Uniform corners across cards/inputs/dialogs |
| Elevation | `shadows`, `darkShadows`, `componentShadows` | Levels 0-4 + component contracts | Light/dark parity with tuned depth |
| Focus Ring | `focusRing` | `width`, `offset`, `lightColor`, `darkColor`, `lightShadow`, `darkShadow` | Keyboard visibility + accessibility-first focus treatment |
| Motion | `duration`, `easing`, `transitions` | `fast`, `micro`, `standard`, `slow`, `interactive`, `shadow`, `background` | Clinical-safe motion: clear but non-distracting |
| Density Modes | `density` | `compact`, `comfortable` | Compact for high-density clinical tables; comfortable for general pages |

## 2) MUI Theme Object Structure

```ts
// src/theme/index.ts
export interface CreateCDSSThemeOptions {
  mode?: "light" | "dark";
  densityMode?: "compact" | "comfortable";
}

export const theme = createCDSSTheme({
  mode: "light",
  densityMode: "comfortable",
});

// Theme metadata contract
theme.cdss = {
  roles: semanticRoles[mode],          // semantic role tokens
  medicalStatus: medicalStatusTokens[mode],
  densityMode,
  density: density[densityMode],
  focusRing,
  motion: { duration, easing, transitions },
  severity,
  clinical,
  shadows: { clinical: clinicalShadows, components: componentShadows },
};

// Component style contracts implemented in MUI `components`:
// MuiButton, MuiCard, MuiDataGrid, MuiChip, MuiTabs/MuiTab, MuiAlert,
// MuiTooltip, MuiDialog, MuiDrawer, MuiAppBar, and Form control components.
```

## 3) Usage Examples (React TSX)

### A. Select mode + density and inject CSS variables

```tsx
import React from "react";
import { CssBaseline, ThemeProvider } from "@mui/material";
import { createCDSSTheme, injectCssCustomProperties } from "@/theme";

export function AppThemeShell({ children }: { children: React.ReactNode }) {
  const mode: "light" | "dark" = "dark";
  const densityMode: "compact" | "comfortable" = "compact";
  const theme = React.useMemo(
    () => createCDSSTheme({ mode, densityMode }),
    [mode, densityMode]
  );

  React.useEffect(() => {
    injectCssCustomProperties(theme, densityMode);
  }, [theme, densityMode]);

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      {children}
    </ThemeProvider>
  );
}
```

### B. Medical status semantics in UI

```tsx
import { Alert, Box, Chip } from "@mui/material";

export function DrugRiskBanner() {
  return (
    <Box sx={{ display: "grid", gap: 1 }}>
      <Alert severity="error">Major contraindication detected.</Alert>
      <Chip
        label="Validated"
        sx={{
          color: "var(--cdss-status-success-foreground)",
          backgroundColor: "var(--cdss-status-success-surface)",
          border: "1px solid var(--cdss-status-success-border)",
        }}
      />
    </Box>
  );
}
```

### C. Dense DataGrid in compact mode

```tsx
import { DataGrid, GridColDef } from "@mui/x-data-grid";

const columns: GridColDef[] = [
  { field: "patient", headerName: "Patient", flex: 1 },
  { field: "risk", headerName: "Risk", width: 140 },
];

const rows = [
  { id: 1, patient: "P001", risk: "critical" },
  { id: 2, patient: "P002", risk: "warning" },
];

export function PatientRiskGrid() {
  return <DataGrid rows={rows} columns={columns} autoHeight />;
}
```

## 4) Do / Don't Guidance

### Do
- Use semantic role tokens (`surface`, `border`, `text`, `accent`) instead of hardcoded hex values.
- Use medical status tokens (`critical`, `warning`, `info`, `success`) for risk communication.
- Use `compact` density for high-information clinical tables and monitoring views.
- Keep headings in Manrope and dense content in IBM Plex Sans.
- Preserve focus ring visibility for keyboard navigation and accessibility.

### Don’t
- Don’t remap clinical status colors arbitrarily between screens.
- Don’t use decorative motion for critical alerts or decision surfaces.
- Don’t bypass theme contracts with ad-hoc component overrides unless unavoidable.
- Don’t mix inconsistent spacing/radius scales outside token definitions.
- Don’t ship light-mode-only styling; always verify dark parity.
