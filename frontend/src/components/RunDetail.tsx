import type { Live, TestCase, VerificationResult } from "../types";
import { formatDuration, shortId, shortRevision } from "../format";
import { BugCard } from "./BugCard";
import { StatusTimeline } from "./StatusTimeline";
import { statusTone } from "./RunList";

interface Props {
  live: Live;
  verifying: string | null;
  verifications: Record<string, VerificationResult>;
  onVerify: (patchId: string) => void;
}

function TestRow({ test }: { test: TestCase }) {
  return (
    <li className={`test-row test-${test.status}`}>
      <span className="test-status">{test.status}</span>
      <span className="test-name">
        {test.name}
        <span className="muted mono test-key">{test.test_key}</span>
      </span>
      <span className="test-duration">{formatDuration(test.duration_ms)}</span>
      {test.failure_message && (
        <details className="test-failure">
          <summary>Failure detail</summary>
          <pre>{test.failure_message}</pre>
        </details>
      )}
    </li>
  );
}

export function RunDetail({ live, verifying, verifications, onVerify }: Props) {
  const { run, tests, bugs, active } = live;
  const summary = run.summary;
  const attempts = Array.from(new Set(tests.map((test) => test.attempt))).sort();

  return (
    <div className="detail">
      <header className="detail-head">
        <div>
          <div className="eyebrow">
            {run.project_name ?? "Project"} · run <span className="mono">{shortId(run.id)}</span>
          </div>
          <h1>
            {run.scope.join(" + ") || "Investigation"}{" "}
            <span className={`status status-${statusTone(run.status)}`}>
              {run.status.replace("_", " ")}
            </span>
          </h1>
          <p className="hint">
            mode {run.mode} · provider {summary?.provider ?? "—"} · revision{" "}
            <span className="mono">{shortRevision(run.target_revision)}</span>
            {summary ? ` · ${formatDuration(summary.duration_ms)}` : ""}
          </p>
        </div>
        {active && <div className="pulse" aria-label="run in progress" />}
      </header>

      <StatusTimeline status={run.status} />

      {run.error_message && (
        <div className="callout callout-err">
          <strong>{run.error_kind ?? "error"}</strong>
          <pre>{run.error_message}</pre>
        </div>
      )}

      {summary && (
        <div className="stats">
          <div className="stat">
            <span className="stat-value">{summary.tests_total}</span>
            <span className="stat-label">tests</span>
          </div>
          <div className="stat">
            <span className="stat-value ok">{summary.passed}</span>
            <span className="stat-label">passed</span>
          </div>
          <div className="stat">
            <span className="stat-value err">{summary.failed}</span>
            <span className="stat-label">failed</span>
          </div>
          <div className="stat">
            <span className="stat-value">{summary.confirmed_bugs}</span>
            <span className="stat-label">confirmed bugs</span>
          </div>
          <div className="stat">
            <span className="stat-value">{summary.patch_ids.length}</span>
            <span className="stat-label">patches</span>
          </div>
        </div>
      )}

      <section className="panel">
        <h2>Test outcomes</h2>
        {tests.length === 0 && (
          <p className="hint">
            {active ? "Waiting for the browser runner to report…" : "No tests recorded."}
          </p>
        )}
        {attempts.map((attempt) => (
          <div key={attempt} className="attempt">
            <h3 className="attempt-title">
              Attempt {attempt} — {attempt === 1 ? "initial execution" : "reproduction"}
            </h3>
            <ul className="tests">
              {tests
                .filter((test) => test.attempt === attempt)
                .map((test) => (
                  <TestRow key={test.id} test={test} />
                ))}
            </ul>
          </div>
        ))}
      </section>

      <section className="panel">
        <h2>Bugs ({bugs.length})</h2>
        {bugs.length === 0 && (
          <p className="hint">
            {active
              ? "No bug can be reported until a failure reproduces twice."
              : run.status === "inconclusive"
                ? "Failures did not reproduce on the second execution, so no bug was reported."
                : "No confirmed bugs in this run."}
          </p>
        )}
        <div className="bugs">
          {bugs.map((bug) => (
            <BugCard
              key={bug.id}
              bug={bug}
              verifying={verifying}
              verifications={verifications}
              onVerify={onVerify}
            />
          ))}
        </div>
      </section>

      {run.plan && (
        <details className="panel plan">
          <summary>Bounded test plan</summary>
          <pre>{JSON.stringify(run.plan, null, 2)}</pre>
        </details>
      )}
    </div>
  );
}