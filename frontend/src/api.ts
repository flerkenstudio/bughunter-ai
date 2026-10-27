import type {
  Bug,
  Catalog,
  Health,
  Live,
  Project,
  Run,
  TestCase,
  VerificationResult
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // keep the status text
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<Health>("/api/health"),

  projects: () => request<Project[]>("/api/projects"),

  createProject: (name: string, baseUrl: string) =>
    request<Project>("/api/projects", {
      method: "POST",
      body: JSON.stringify({ name, base_url: baseUrl, description: "" })
    }),

  catalog: () => request<Catalog>("/api/catalog"),

  runs: () => request<Run[]>("/api/runs"),

  run: (id: string) => request<Run>(`/api/runs/${id}`),

  live: (id: string) => request<Live>(`/api/runs/${id}/live`),

  tests: (id: string) => request<TestCase[]>(`/api/runs/${id}/tests`),

  bugs: (id: string) => request<Bug[]>(`/api/runs/${id}/bugs`),

  startRun: (projectId: string, scope: string[], mode: string, maxSeconds: number) =>
    request<Run>("/api/runs", {
      method: "POST",
      body: JSON.stringify({
        project_id: projectId,
        scope,
        mode,
        max_duration_seconds: maxSeconds
      })
    }),

  verifyPatch: (patchId: string) =>
    request<VerificationResult>(`/api/patches/${patchId}/verify`, { method: "POST" })
};