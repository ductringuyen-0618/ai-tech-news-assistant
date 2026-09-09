import { Loader2, CheckCircle2, Circle, AlertTriangle } from 'lucide-react';

/**
 * ResearchProgressTimeline — M3.M2 vertical timeline.
 *
 * Replaces the single-chip phase indicator with a 5-row vertical timeline
 * that shows the live state of every agent phase. Each row has:
 *   - status dot (pending → in-progress → done)
 *   - label (e.g. "Decomposing", "Reading articles (3 in flight, 8 done)")
 *   - elapsed time when done
 *
 * Preserves the `data-testid="research-phase-chip"` selector by wrapping
 * the currently-active row's status text with that testid. Existing
 * tests query this testid for the current phase and still work.
 */

export type TimelineStatus = 'pending' | 'in-progress' | 'done' | 'error';

export interface TimelineStep {
  id: string;
  label: string;
  status: TimelineStatus;
  /** Elapsed ms once the step is done. Optional. */
  durationMs?: number;
  /** Optional sub-label rendered in muted text below the main label. */
  detail?: string;
}

interface ResearchProgressTimelineProps {
  steps: TimelineStep[];
  /**
   * The currently-active step ID — its status label gets the
   * `research-phase-chip` testid for backward compat with the existing
   * tests. When a run reaches done, set this to "done" so the testid
   * lands on the last "Done" row.
   */
  activeStepId: string;
  /**
   * Backward-compat: a plain text phase string. Some existing tests
   * still query `research-phase-chip` text contents (e.g. "Done",
   * "Decomposing"). When provided, this overrides the active step's
   * label inside the testid wrapper.
   */
  phaseChipText?: string;
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function StatusIcon({ status }: { status: TimelineStatus }): JSX.Element {
  if (status === 'done') {
    return (
      <CheckCircle2 className="w-4 h-4 text-green-600 dark:text-green-400" />
    );
  }
  if (status === 'in-progress') {
    return (
      <Loader2 className="w-4 h-4 text-blue-600 dark:text-blue-400 animate-spin" />
    );
  }
  if (status === 'error') {
    return <AlertTriangle className="w-4 h-4 text-red-600 dark:text-red-400" />;
  }
  return <Circle className="w-4 h-4 text-muted-foreground/40" />;
}

export function ResearchProgressTimeline({
  steps,
  activeStepId,
  phaseChipText,
}: ResearchProgressTimelineProps): JSX.Element {
  return (
    <div
      data-testid="research-progress-timeline"
      className="border border-gray-200 dark:border-gray-800 rounded-lg overflow-hidden bg-white dark:bg-gray-900"
    >
      <ol className="divide-y divide-gray-100 dark:divide-gray-800">
        {steps.map(step => {
          const isActive = step.id === activeStepId;
          const labelForChip = phaseChipText ?? step.label;
          return (
            <li
              key={step.id}
              data-testid="research-timeline-row"
              data-step-id={step.id}
              data-status={step.status}
              className={`flex items-start gap-3 px-3 py-2 text-sm ${
                isActive ? 'bg-blue-50/40 dark:bg-blue-950/30' : ''
              }`}
            >
              <span className="mt-0.5 flex-shrink-0">
                <StatusIcon status={step.status} />
              </span>
              <span className="flex-1 min-w-0">
                {/* The currently-active row carries the legacy phase-chip
                    testid so existing tests that look for the active phase
                    text still find it. */}
                {isActive ? (
                  <span
                    data-testid="research-phase-chip"
                    className={`font-medium ${
                      step.status === 'error'
                        ? 'text-red-600 dark:text-red-400'
                        : step.status === 'done'
                          ? 'text-green-700 dark:text-green-400'
                          : 'text-foreground'
                    }`}
                  >
                    {labelForChip}
                  </span>
                ) : (
                  <span
                    className={`font-medium ${
                      step.status === 'done'
                        ? 'text-foreground'
                        : step.status === 'error'
                          ? 'text-red-600 dark:text-red-400'
                          : 'text-muted-foreground'
                    }`}
                  >
                    {step.label}
                  </span>
                )}
                {step.detail && (
                  <span className="block text-xs text-muted-foreground mt-0.5">
                    {step.detail}
                  </span>
                )}
              </span>
              {step.status === 'done' &&
                typeof step.durationMs === 'number' && (
                  <span className="flex-shrink-0 text-xs text-muted-foreground">
                    {formatDuration(step.durationMs)}
                  </span>
                )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export default ResearchProgressTimeline;
