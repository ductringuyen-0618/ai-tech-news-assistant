/**
 * Global Vitest setup — runs once per worker before any test file.
 *
 * - Brings in @testing-library/jest-dom matchers (toBeInTheDocument,
 *   toHaveClass, toBeVisible, ...).
 * - Shims a few browser APIs that jsdom does not implement but are
 *   referenced by code paths a unit test might transitively touch
 *   (matchMedia for theme detection, IntersectionObserver for
 *   scroll-anchored reveals, ResizeObserver for Radix primitives).
 * - Provides a default `global.fetch` stub so a test that forgets to
 *   mock it doesn't silently make a real network call.
 *
 * Individual tests can override any of these (`vi.spyOn(global, "fetch")`
 * etc.) — these are only safe defaults so an unmocked code path fails
 * loudly with a recognisable error instead of hanging or hitting the
 * real internet.
 */
import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

// Unmount any React tree left over from the previous test so DOM-state
// leakage cannot cause cross-test pollution.
afterEach(() => {
  cleanup();
});

// jsdom does not implement matchMedia. next-themes and a few internal
// hooks call it; without this stub they throw on import.
if (typeof window !== "undefined" && !window.matchMedia) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {}, // legacy API still consulted by some libs
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}

// jsdom does not implement IntersectionObserver. Welcome-screen panel
// reveals and any framer-motion scroll triggers rely on it.
if (typeof globalThis.IntersectionObserver === "undefined") {
  class IO {
    root = null;
    rootMargin = "";
    thresholds = [];
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords() {
      return [];
    }
  }
  // @ts-expect-error -- assigning a partial stub is intentional for tests.
  globalThis.IntersectionObserver = IO;
}

// jsdom does not implement ResizeObserver — Radix primitives need it.
if (typeof globalThis.ResizeObserver === "undefined") {
  class RO {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  // @ts-expect-error -- assigning a partial stub is intentional for tests.
  globalThis.ResizeObserver = RO;
}

// A default fetch stub that screams. Any test that hits the network
// without explicitly opting in to a mock will fail fast with a clear
// message instead of attempting a real request from CI.
if (!("fetch" in globalThis) || typeof globalThis.fetch !== "function") {
  globalThis.fetch = vi.fn(async (input: any) => {
    throw new Error(
      `Unmocked fetch() call in test for: ${
        typeof input === "string" ? input : input?.url ?? "<unknown>"
      }`
    );
  }) as any;
}
