import { expect, test } from "@playwright/test";

const ROUTES = [
  { path: "/", name: "dashboard" },
  { path: "/query", name: "query" },
  { path: "/patients", name: "patients" },
  { path: "/drugs", name: "drug-checker" },
  { path: "/literature", name: "literature" },
  { path: "/documents", name: "documents" },
  { path: "/admin", name: "admin" },
] as const;

const VIEWPORTS = [
  { width: 1440, height: 1024, label: "desktop-1440" },
  { width: 1024, height: 768, label: "laptop-1024" },
  { width: 768, height: 1024, label: "tablet-768" },
  { width: 390, height: 844, label: "mobile-390" },
] as const;

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    const fixed = new Date("2026-03-13T09:00:00.000Z").valueOf();
    const RealDate = Date;
    // Keep timestamps deterministic for visual snapshots.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any).Date = class extends RealDate {
      constructor(...args: ConstructorParameters<typeof Date>) {
        if (args.length === 0) {
          super(fixed);
        } else {
          super(...args);
        }
      }
      static now() {
        return fixed;
      }
    };
  });
});

for (const viewport of VIEWPORTS) {
  test.describe(`viewport:${viewport.label}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    for (const route of ROUTES) {
      test(`snapshot ${route.name}`, async ({ page }) => {
        await page.goto(route.path, { waitUntil: "domcontentloaded" });
        await page.addStyleTag({
          content: `
            *, *::before, *::after {
              transition: none !important;
              animation: none !important;
              caret-color: transparent !important;
            }
          `,
        });
        await page.waitForLoadState("networkidle");
        await page.waitForTimeout(500);

        await expect(page).toHaveScreenshot(`${route.name}-${viewport.label}.png`, {
          fullPage: true,
          animations: "disabled",
          maxDiffPixelRatio: 0.02,
        });
      });
    }
  });
}
