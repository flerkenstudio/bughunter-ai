import { useEffect, useState } from "react";
import type { Catalog, Project } from "../types";

interface Props {
  projects: Project[];
  catalog: Catalog | null;
  starting: boolean;
  onStart: (
    projectId: string,
    scope: string[],
    mode: string,
    maxSeconds: number
  ) => Promise<void>;
}

const FALLBACK_SCOPES = ["probe", "login", "checkout", "cart"];
const DEMO_SCOPES = ["login", "checkout", "cart"];

export function RunForm({ projects, catalog, starting, onStart }: Props) {
  const [projectId, setProjectId] = useState("");
  const [scope, setScope] = useState<string[]>(["login", "checkout"]);
  const [mode, setMode] = useState("reproduce");
  const [seconds, setSeconds] = useState(120);

  const scopes = catalog?.scopes?.length ? catalog.scopes : FALLBACK_SCOPES;
  const project = projects.find((item) => item.id === projectId);
  const isExternal = project?.target_kind === "external";

  useEffect(() => {
    if (!projectId && projects.length > 0) setProjectId(projects[0].id);
  }, [projects, projectId]);

  useEffect(() => {
    // The demo scopes assert Nimbus Supply behaviour, so an external URL gets the
    // generic site probe pack instead.
    setScope(isExternal ? ["probe"] : ["login", "checkout"]);
  }, [projectId, isExternal]);

  const toggleScope = (area: string) => {
    if (isExternal && area !== "probe") return;
    setScope((current) =>
      current.includes(area) ? current.filter((item) => item !== area) : [...current, area]
    );
  };

  return (
    <section className="panel">
      <h2>New investigation</h2>
      <div className="field">
        <label htmlFor="project">Target</label>
        <select
          id="project"
          value={projectId}
          onChange={(event) => setProjectId(event.target.value)}
        >
          {projects.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
              {item.target_kind === "external" ? " (external URL)" : ""}
            </option>
          ))}
        </select>
        {project && <span className="hint mono">{project.base_url}</span>}
      </div>

      <div className="field">
        <label>Scope</label>
        <div className="chips">
          {scopes.map((area) => {
            const disabled = isExternal && DEMO_SCOPES.includes(area);
            return (
              <button
                type="button"
                key={area}
                className={`chip ${scope.includes(area) ? "chip-on" : ""}`}
                onClick={() => toggleScope(area)}
                aria-pressed={scope.includes(area)}
                disabled={disabled}
                title={
                  disabled
                    ? "Demo-only checks: they assert Nimbus Supply behaviour"
                    : undefined
                }
              >
                {area}
              </button>
            );
          })}
        </div>
        <span className="hint">
          {isExternal
            ? "Generic site probe: loads, console errors, failed requests, metadata, images, links, labels, mobile layout."
            : "Demo journeys for the bundled Nimbus Supply storefront."}
        </span>
      </div>

      <div className="field-row">
        <div className="field">
          <label htmlFor="mode">Mode</label>
          <select id="mode" value={mode} onChange={(event) => setMode(event.target.value)}>
            <option value="reproduce">Reproduce &amp; report</option>
            <option value="fix">Reproduce &amp; propose fix</option>
          </select>
        </div>
        <div className="field narrow">
          <label htmlFor="seconds">Limit (s)</label>
          <input
            id="seconds"
            type="number"
            min={10}
            max={600}
            value={seconds}
            onChange={(event) => setSeconds(Number(event.target.value))}
          />
        </div>
      </div>

      <button
        className="primary"
        disabled={starting || !projectId || scope.length === 0}
        onClick={() => onStart(projectId, scope, mode, seconds)}
      >
        {starting ? "Starting…" : "Start investigation"}
      </button>
      <p className="hint">
        Targets are validated before any browser starts. Private, loopback and metadata
        addresses stay blocked unless explicitly allowed.
      </p>
    </section>
  );
}