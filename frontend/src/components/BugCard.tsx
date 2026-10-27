import type { Artifact, Bug, Patch, VerificationResult } from "../types";
import { formatBytes, shortRevision } from "../format";

interface Props {
  bug: Bug;
  verifying: string | null;
  verifications: Record<string, VerificationResult>;
  onVerify: (patchId: string) => void;
}

function EvidenceItem({ artifact }: { artifact: Artifact }) {
  if (artifact.type === "screenshot") {
    return (
      <a className="evidence-shot" href={artifact.download_url} target="_blank" rel="noreferrer">
        <img src={artifact.download_url} alt={artifact.label} loading="lazy" />
        <span>screenshot</span>
      </a>
    );
  }
  return (
    <a className="evidence-file" href={artifact.download_url} target="_blank" rel="noreferrer">
      <span className="evidence-kind">{artifact.type.replace("_", " ")}</span>
      <span className="evidence-name">{artifact.label.split(" / ").pop()}</span>
      <span className="muted small">{formatBytes(artifact.size_bytes)}</span>
    </a>
  );
}

function DiffView({ diff }: { diff: string }) {
  return (
    <pre className="diff">
      {diff.split("\n").map((line, index) => {
        let tone = "";
        if (line.startsWith("+++") || line.startsWith("---")) tone = "diff-meta";
        else if (line.startsWith("+")) tone = "diff-add";
        else if (line.startsWith("-")) tone = "diff-del";
        else if (line.startsWith("@@")) tone = "diff-hunk";
        return (
          <span key={index} className={tone}>
            {line || " "}
            {"\n"}
          </span>
        );
      })}
    </pre>
  );
}

function PatchBlock({
  patch,
  verifying,
  verification,
  onVerify
}: {
  patch: Patch;
  verifying: string | null;
  verification?: VerificationResult;
  onVerify: (patchId: string) => void;
}) {
  const busy = verifying === patch.id;
  // Live results from this session take precedence; persisted rows survive reloads.
  const rows = verification?.tests ?? patch.verification_tests ?? [];
  const revision = verification?.revision ?? patch.revision;
  return (
    <div className="patch">
      <div className="patch-head">
        <div>
          <span className="label">Proposed patch</span>
          <p className="patch-summary">{patch.summary || "No summary provided."}</p>
        </div>
        <span className={`badge badge-${patch.verification_status}`}>
          {patch.verification_status}
        </span>
      </div>

      <DiffView diff={patch.diff} />

      <div className="patch-actions">
        <button className="small" onClick={() => onVerify(patch.id)} disabled={busy}>
          {busy ? "Running isolated verification…" : "Verify in isolated checkout"}
        </button>
        <span className="hint">
          Source: {patch.source}. Verification re-runs the failing test plus the regression suite.
        </span>
      </div>

      {rows.length > 0 && (
        <div className="verify-results">
          <span className="label">
            Verification tests
            {revision ? ` · ${shortRevision(revision)}` : ""}
          </span>
          <ul className="verify-list">
            {rows.map((test) => (
              <li key={test.test_key} className={`verify-${test.status}`}>
                <span className="verify-status">{test.status}</span>
                <span className="verify-name">{test.name}</span>
                <span className="muted mono">{test.test_key}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {patch.verification_output && (
        <details className="patch-output">
          <summary>Verification output</summary>
          <pre>{patch.verification_output}</pre>
        </details>
      )}
    </div>
  );
}

export function BugCard({ bug, verifying, verifications, onVerify }: Props) {
  return (
    <article className="bug-card">
      <header className="bug-head">
        <span className={`severity sev-${bug.severity}`}>{bug.severity}</span>
        <div>
          <h3>{bug.title}</h3>
          <p className="bug-description">{bug.description}</p>
        </div>
        <span className="badge badge-verified">{bug.status}</span>
      </header>

      <div className="bug-grid">
        <section>
          <h4>Reproduction</h4>
          <ol className="steps">
            {bug.reproduction_steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        </section>
        <section>
          <h4>Root cause</h4>
          <p className="bug-rootcause">{bug.root_cause}</p>
        </section>
      </div>

      <section>
        <h4>Evidence ({bug.evidence.length})</h4>
        <div className="evidence">
          {bug.evidence.map((artifact) => (
            <EvidenceItem key={artifact.id} artifact={artifact} />
          ))}
        </div>
        <p className="hint">
          Artifacts are sha256-addressed; a test that never ran is never counted.
        </p>
      </section>

      {bug.patches.map((patch) => (
        <PatchBlock
          key={patch.id}
          patch={patch}
          verifying={verifying}
          verification={verifications[patch.id]}
          onVerify={onVerify}
        />
      ))}
    </article>
  );
}