# Vendored Components

This directory contains cherry-picked components from external sources (e.g., 21st.dev) that have been vendored into the project.

## Rules

1. Maximum 5 vendored components total
2. Each component must have an entry below with:
   - `source_url`: Original source URL
   - `vendor_date`: Date of vendoring
   - `modifications`: List of changes made to the original
   - `a11y_audit_status`: WCAG compliance status

## Components

_No components vendored yet._

---

## Usage

When adding a vendored component:

1. Copy the component source into this directory
2. Strip all external imports (replace with local implementations)
3. Add an entry to this file
4. Ensure WCAG AA compliance before use in production
