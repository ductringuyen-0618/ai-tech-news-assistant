/// <reference types="vitest" />
import { defineConfig, mergeConfig } from "vitest/config";
import viteConfig from "./vite.config";

/**
 * Vitest config for the TechPulse AI frontend.
 *
 * Authored as the first unit-test setup for this codebase. Black-box
 * test scope only — contract-level checks against documented public
 * surfaces (API endpoint shape, exported config, masthead behavior).
 * NOT a substitute for the Playwright suite in `e2e/` which exercises
 * the rendered DOM end-to-end.
 *
 * Test environment notes:
 *   - `jsdom` so React Testing Library mounts and queries work.
 *   - `globals: true` so Vitest's `describe / it / expect` are
 *     available without per-file imports (mirrors @testing-library
 *     conventions; reduces boilerplate for hand-written component
 *     contract tests).
 *   - `setupFiles` wires up @testing-library/jest-dom matchers and a
 *     few global mocks (`fetch`, `matchMedia`, `IntersectionObserver`)
 *     that jsdom does NOT provide out of the box.
 *   - The Playwright `e2e/` tree is excluded — Vitest must not try to
 *     pick those up; they are run by `npm run test:e2e:ui` instead.
 */
export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/test/setup.ts"],
      include: ["src/**/*.{test,spec}.{ts,tsx}"],
      exclude: [
        "**/node_modules/**",
        "**/build/**",
        "**/dist/**",
        "e2e/**",
        "**/*.e2e.spec.ts",
      ],
      css: false,
      coverage: {
        provider: "v8",
        reporter: ["text", "html", "lcov"],
        reportsDirectory: "./coverage",
        include: ["src/**/*.{ts,tsx}"],
        exclude: [
          "src/**/*.d.ts",
          "src/**/*.test.{ts,tsx}",
          "src/**/*.spec.{ts,tsx}",
          "src/test/**",
          "src/main.tsx",
          "src/components/ui/**",
        ],
      },
    },
  })
);
