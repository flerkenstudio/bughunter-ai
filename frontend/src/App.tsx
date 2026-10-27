import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { Catalog, Health, Live, Project, Run, VerificationResult } from "./types";
import { RunForm } from "./components/RunForm";
import { RunList } from "./components/RunList";
import { RunDetail } from "./components/RunDetail";
import { shortRevision } from "./format";

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [live, setLive] = useState<Live | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [verifying, setVerifying] = useState<string | null>(null);
  const [verifications, setVerifications] = useState<Record<string, VerificationResult>>({});
  const [showTargetForm, setShowTargetForm] = useState(false);
  const pollRef = useRef<number | null>(null);

  const refreshRuns = useCallback(async () => {
    try {
      const next = await api.runs();
      setRuns(next);
      return next;
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      return [];
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function bootstrap() {
      try {
        const [healthResult, projectsResult, catalogResult, runsResult] = await Promise.all([
          api.health(),
          api.projects(),
          api.catalog(),
          api.runs()
        ]);
        if (cancelled) return;
        setHealth(healthResult);
        setProjects(projectsResult);
        setCatalog(catalogResult);
        setRuns(runsResult);
        if (runsResult.length > 0) setSelectedId(runsResult[0].id);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      }
    }
    bootstrap();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const stop = () => {
      if (pollRef.current !== null) {
        window.clearTimeout(pollRef.current);
        pollRef.current = null;
      }
    };

    async function tick() {
      if (!selectedId) {
        setLive(null);
        return;
      }
      try {
        const next = await api.live(selectedId);
        if (cancelled) return;
        setLive(next);
        if (next.active) {
          pollRef.current = window.setTimeout(tick, 1500);
        } else {
          void refreshRuns();
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      }
    }

    stop();
    setLive(null);
    void tick();
    return () => {
      cancelled = true;
      stop();
    };
  }, [selectedId, refreshRuns]);

  const handleStart = async (
    projectId: string,
    scope: string[],
    mode: string,
    maxSeconds: number
  ) => {
    setStarting(true);
    setError(null);
    setNotice(null);
    try {
      const run = await api.startRun(projectId, scope, mode, maxSeconds);
      setSelectedId(run.id);
      await refreshRuns();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setStarting(false);
    }
  };

  const handleVerify = async (patchId: string) => {
    setVerifying(patchId);
    setError(null);
    setNotice(null);
    try {
      const result = await api.verifyPatch(patchId);
      setVerifications((current) => ({ ...current, [patchId]: result }));
      setNotice(
        result.all_passed
          ? `${result.message}. Revision ${shortRevision(result.revision)}.`
          : result.message
      );
      if (selectedId) setLive(await api.live(selectedId));
      await refreshRuns();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setVerifying(null);
    }
  };

  const addTarget = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const name = String(form.get("name") ?? "").trim();
    const baseUrl = String(form.get("baseUrl") ?? "").trim();
    try {
      const project = await api.createProject(name, baseUrl);
      setProjects((current) => [project, ...current]);
      setShowTargetForm(false);
      setNotice(`Target registered: ${project.name}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const selectedProject = projects.find(
    (project) => project.id === (live?.run.project_id ?? runs[0]?.project_id)
  );

  return (
    <div className="app">
      <header className="topbar">
        <div className="logo">
          BugHunter<span>AI</span>
          <em>autonomous QA</em>
        </div>
        <div className="topbar-right">
          <a className="ghost-link" href={selectedProject?.base_url ?? "http://127.0.0.1:8090"} target="_blank" rel="noreferrer">
            Open demo store ↗
          </a>
          <span className={`status status-${health ? "ok" : "busy"}`}>
            {health ? `api ok · ${health.ai_provider}` : "connecting…"}
          </span>
        </div>
      </header>

      {(error || notice) && (
        <div className={`banner ${error ? "banner-err" : "banner-ok"}`}>
          <span>{error ?? notice}</span>
          <button
            className="link"
            onClick={() => {
              setError(null);
              setNotice(null);
            }}
          >
            dismiss
          </button>
        </div>
      )}

      <main className="layout">
        <aside className="sidebar">
          <section className="panel">
            <div className="panel-head">
              <h2>Targets</h2>
              <button className="link" onClick={() => setShowTargetForm((value) => !value)}>
                {showTargetForm ? "cancel" : "+ add"}
              </button>
            </div>
            <ul className="target-list">
              {projects.map((project) => (
                <li key={project.id}>
                  <span className="target-name">{project.name}</span>
                  <span className="hint mono">{project.base_url}</span>
                </li>
              ))}
            </ul>
            {showTargetForm && (
              <form className="target-form" onSubmit={addTarget}>
                <input name="name" placeholder="Name" required />
                <input name="baseUrl" placeholder="http://127.0.0.1:8090" required />
                <button className="small" type="submit">
                  Register target
                </button>
              </form>
            )}
          </section>

          <RunForm
            projects={projects}
            catalog={catalog}
            starting={starting}
            onStart={handleStart}
          />

          <RunList runs={runs} selectedId={selectedId} onSelect={setSelectedId} />
        </aside>

        <section className="content">
          {live ? (
            <RunDetail
              live={live}
              verifying={verifying}
              verifications={verifications}
              onVerify={handleVerify}
            />
          ) : (
            <div className="empty">
              <h1>Evidence, not explanations.</h1>
              <p>
                BugHunter AI runs a bounded browser test plan, reproduces any failure before
                reporting it, and proves a patch by re-running the failing test plus the
                regression suite in an isolated checkout.
              </p>
              <p className="hint">
                Choose a target on the left and start an investigation. The seeded checkout bug
                is detected, reproduced twice, and reported with screenshots, console logs and a
                Playwright trace.
              </p>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}