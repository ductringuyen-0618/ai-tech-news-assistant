/**
 * DropCap -- editorial drop-cap paragraph (design-review #17).
 *
 * Extracted from the original inline usage in
 * :module:`WelcomeScreen` so the same broadsheet drop-cap can be
 * re-used as the lead device on Digest's daily-brief paragraph and
 * inside research reports. Pairs ``font-display`` (Fraunces) at
 * 16px body with the global ``.editorial-drop::first-letter`` rule
 * (defined in ``index.css``) that floats a 4.6em Fraunces capital
 * in the signal accent.
 *
 * Usage::
 *
 *     <DropCap>
 *       Reading the news is now a research problem...
 *     </DropCap>
 *
 * The component is presentational only -- no state, no effects, no
 * test-id (callers can attach their own via ``data-testid`` through
 * the spread of native ``<p>`` attributes which would be a v2 add).
 */
import type { ReactNode } from "react";

export interface DropCapProps {
  children: ReactNode;
  /** Extra classes appended to the default editorial typography. */
  className?: string;
  /** Optional test-id for Playwright hooks. */
  "data-testid"?: string;
}

export function DropCap({
  children,
  className = "",
  ...rest
}: DropCapProps) {
  return (
    <p
      {...rest}
      className={
        "editorial-drop font-display text-[16px] leading-[1.65] text-foreground " +
        className
      }
    >
      {children}
    </p>
  );
}
