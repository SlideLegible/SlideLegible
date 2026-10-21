// Typed client for the SlideLegible Web API (mirrors the core report schema 1.0).

export type PolicyName = "comfortable" | "projector" | "strict_aaa";

export interface Requirement {
  min_ratio: number;
  min_apca_lc: number | null;
}

export interface PolicyInfo {
  name: PolicyName;
  normal_text: Requirement;
  large_text: Requirement;
  allow_soften: boolean;
  soften_extremes: boolean;
  apca_version: string;
}

export interface RendererInfo {
  name: string;
  available: boolean;
  path: string | null;
  version: string | null;
  detail: string;
}

export interface Capabilities {
  version: string;
  renderer: RendererInfo | null;
  renderers: RendererInfo[];
  policies: PolicyInfo[];
  languages: string[];
}

export interface FillTarget {
  kind: string;
  part: string;
  label: string;
  color: string;
  shared: boolean;
}

export interface Background {
  kind: "solid" | "gradient" | "image" | "complex" | "unknown";
  certainty: "exact" | "derived" | "rendered_estimate" | "unknown";
  color: string | null;
  samples: string[];
  layers: string[];
  editable: FillTarget | null;
  has_image: boolean;
  note: string | null;
}

export interface Run {
  id: string;
  slide: number;
  shape: string;
  cell: [number, number] | null;
  excerpt: string;
  size_pt: number | null;
  bold: boolean;
  color: string;
  color_alpha: number;
  color_source: string;
  hyperlink: boolean;
  background: Background;
  unsupported: string | null;
}

export type Status =
  | "pass"
  | "fail"
  | "decorative"
  | "unsupported"
  | "unknown_background"
  | "uncertain_color";

export interface Finding {
  run: Run;
  large_text: boolean;
  requirement: Requirement;
  effective_color: string;
  ratio: number | null;
  apca_lc: number | null;
  worst_background: string | null;
  status: Status;
  reason: string | null;
}

export interface Suggestion {
  id: string;
  kind: "text_color" | "background_color" | "saturation" | "scrim" | "soften_text" | "soften_background";
  strategy: string;
  major: boolean;
  runs: string[];
  slides: number[];
  affected_slides: number[];
  original: string | null;
  proposed: string;
  alpha: number | null;
  target: FillTarget | null;
  depends_on: string[];
  before: { ratio: number | null; apca_lc: number | null };
  after: { ratio: number | null; apca_lc: number | null };
  delta_oklch: { lightness: number; chroma: number; hue: number } | null;
  estimate: boolean;
  rationale: string;
}

export interface Unfixed {
  run: string;
  slide: number;
  reason: string;
}

export interface Report {
  schema_version: string;
  source: { filename: string; fingerprint: string; slides: number; slide_size_emu: [number, number] };
  policy: PolicyInfo;
  renderer: RendererInfo | null;
  render_error: string | null;
  summary: Record<string, number>;
  findings: Finding[];
  unsupported: { slide: number; shape: string; kind: string; detail: string }[];
  warnings: string[];
  plan: { id: string; suggestions: Suggestion[]; unfixed: Unfixed[] };
}

export interface Correction {
  id: string;
  pptx_artifact: string;
  previews: Record<string, string>;
  render_error: string | null;
  applied: string[];
  skipped: Record<string, string>;
  verification: { suggestion: string; run: string; status: string; ratio?: number }[];
}

export interface Analysis {
  id: string;
  report: Report;
  original_previews: Record<string, string>;
  proposed: Correction | null;
}

export interface Job {
  id: string;
  kind: string;
  status: "queued" | "running" | "completed" | "failed";
  stage: string;
  progress: number;
  error: { category: string; code: string; message: string } | null;
  result: { analysis_id?: string; correction?: Correction } | null;
}

export class ApiError extends Error {
  code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    let code = `http_${response.status}`;
    let message = response.statusText;
    try {
      const body = await response.json();
      const err = body.error ?? body.detail;
      if (err) {
        code = err.code ?? code;
        message = err.message ?? message;
      }
    } catch {
      // keep defaults
    }
    throw new ApiError(code, message);
  }
  return (await response.json()) as T;
}

export const api = {
  capabilities: () => request<Capabilities>("/api/v1/capabilities"),
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{ id: string; filename: string; slides: number }>("/api/v1/presentations", {
      method: "POST",
      body: form,
    });
  },
  analyze: (uploadId: string, policy: PolicyName, soften: boolean) =>
    request<{ job_id: string }>(`/api/v1/presentations/${uploadId}/analysis`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ policy, soften }),
    }),
  job: (jobId: string) => request<Job>(`/api/v1/jobs/${jobId}`),
  analysis: (analysisId: string) => request<Analysis>(`/api/v1/analyses/${analysisId}`),
  correct: (analysisId: string, suggestionIds: string[]) =>
    request<{ job_id: string }>(`/api/v1/analyses/${analysisId}/corrections`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ suggestion_ids: suggestionIds }),
    }),
};

export const previewUrl = (artifactId: string) => `/api/v1/previews/${artifactId}`;
export const artifactUrl = (artifactId: string) => `/api/v1/artifacts/${artifactId}`;
export const reportUrl = (correctionId: string, lang: string) =>
  `/api/v1/corrections/${correctionId}/report?lang=${encodeURIComponent(lang)}`;

export async function waitForJob(
  jobId: string,
  onUpdate: (job: Job) => void,
  intervalMs = 400,
): Promise<Job> {
  for (;;) {
    const job = await api.job(jobId);
    onUpdate(job);
    if (job.status === "completed" || job.status === "failed") return job;
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}
