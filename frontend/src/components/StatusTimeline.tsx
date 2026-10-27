import type { RunStatus } from "../types";

const STEPS: { key: string; label: string }[] = [
  { key: "queued", label: "Queued" },
  { key: "planning", label: "Plan" },
  { key: "running", label: "Run tests" },
  { key: "reproducing", label: "Reproduce" },
  { key: "analyzing", label: "Analyze" },
  { key: "completed", label: "Report" }
];

const FAILURES: RunStatus[] = ["failed", "timed_out", "inconclusive", "cancelled"];

export function StatusTimeline({ status }: { status: RunStatus }) {
  const failed = FAILURES.includes(status);
  const currentIndex = STEPS.findIndex((step) => step.key === status);
  const completed = status === "completed";
  const activeIndex = completed ? STEPS.length : failed ? 4 : currentIndex;

  return (
    <ol className="timeline">
      {STEPS.map((step, index) => {
        const state =
          completed || index < activeIndex
            ? "done"
            : index === activeIndex
              ? failed
                ? "failed"
                : "current"
              : "pending";
        return (
          <li key={step.key} className={`timeline-step step-${state}`}>
            <span className="timeline-dot" />
            <span className="timeline-label">{step.label}</span>
          </li>
        );
      })}
      {failed && (
        <li className={`timeline-step step-failed`}>
          <span className="timeline-dot" />
          <span className="timeline-label">{status.replace("_", " ")}</span>
        </li>
      )}
    </ol>
  );
}