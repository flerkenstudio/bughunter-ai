export type RunStatus =
  | "queued"
  | "planning"
  | "running"
  | "reproducing"
  | "analyzing"
  | "patching"
  | "verifying"
  | "completed"
  | "failed"
  | "cancelled"
  | "timed_out"
  | "inconclusive";

export type TestStatus = "passed" | "failed" | "error" | "skipped" | "not_run";
export type Severity = "critical" | "high" | "medium" | "low" | "info";

export interface Health {
  status: string;
  version: string;
  ai_provider: string;
  demo_target: string;
}

export interface Project {
  id: string;
  name: string;
  base_url: string;
  description: string;
  created_at: string;
  target_kind?: "demo" | "external";
}

export interface RunSummary {
  tests_total: number;
  passed: number;
  failed: number;
  not_run: number;
  confirmed_bugs: number;
  not_reproduced: string[];
  patch_ids: string[];
  duration_ms: number;
  provider: string;
}

export interface Run {
  id: string;
  project_id: string;
  project_name: string | null;
  status: RunStatus;
  mode: string;
  scope: string[];
  plan: Record<string, unknown> | null;
  summary: RunSummary | null;
  error_kind: string | null;
  error_message: string | null;
  target_revision: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface TestCase {
  id: string;
  run_id: string;
  test_key: string;
  name: string;
  status: TestStatus;
  duration_ms: number;
  failure_message: string | null;
  attempt: number;
  created_at: string;
}

export interface Artifact {
  id: string;
  run_id: string;
  test_case_id: string | null;
  bug_id: string | null;
  type: string;
  label: string;
  storage_path: string;
  sha256: string;
  size_bytes: number;
  created_at: string;
  download_url: string;
}

export interface Patch {
  id: string;
  bug_id: string;
  summary: string;
  diff: string;
  source: string;
  status: string;
  verification_status: "unverified" | "verified" | "failed" | "error";
  verification_output: string | null;
  verification_tests: VerificationTest[] | null;
  revision: string | null;
  created_at: string;
  verified_at: string | null;
}

export interface Bug {
  id: string;
  run_id: string;
  test_case_id: string | null;
  title: string;
  severity: Severity;
  description: string;
  root_cause: string;
  reproduction_steps: string[];
  status: string;
  created_at: string;
  evidence: Artifact[];
  patches: Patch[];
}

export interface Live {
  run: Run;
  active: boolean;
  tests: TestCase[];
  bugs: Bug[];
}

export interface VerificationTest {
  test_key: string;
  name: string;
  status: TestStatus;
  duration_ms: number;
  failure_message: string | null;
}

export interface VerificationResult {
  patch_id: string;
  verification_status: string;
  all_passed: boolean;
  tests: VerificationTest[];
  revision: string | null;
  output_tail: string;
  message: string;
}

export interface CatalogTest {
  key: string;
  function: string;
  name: string;
  scope: string;
  description: string;
  severity_hint: string;
}

export interface Catalog {
  scopes: string[];
  tests: CatalogTest[];
}