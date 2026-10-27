import type { Run } from "../types";
import { formatClock, shortId } from "../format";

interface Props {
  runs: Run[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export function statusTone(status: string): string {
  if (status === "completed") return "ok";
  if (status === "failed" || status === "timed_out") return "err";
  if (status === "inconclusive" || status === "cancelled") return "warn";
  return "busy";
}

export function RunList({ runs, selectedId, onSelect }: Props) {
  return (
    <section className="panel">
      <h2>History</h2>
      {runs.length === 0 && <p className="hint">No runs yet.</p>}
      <ul className="run-list">
        {runs.map((run) => (
          <li key={run.id}>
            <button
              className={`run-item ${run.id === selectedId ? "run-item-on" : ""}`}
              onClick={() => onSelect(run.id)}
            >
              <span className={`dot dot-${statusTone(run.status)}`} />
              <span className="run-item-main">
                <span className="run-item-title">
                  {run.scope.join(" + ") || "run"}{" "}
                  <span className="muted mono">{shortId(run.id, 6)}</span>
                </span>
                <span className="run-item-meta">
                  {run.status.replace("_", " ")} · {formatClock(run.created_at)}
                </span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}