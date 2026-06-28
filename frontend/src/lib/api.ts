import {
  type AnalysisRequest,
  type ContractAnalysis,
  type LawSection,
  contractAnalysisSchema,
  lawSectionSchema,
} from "@/lib/schemas";

export const API_BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

/** An error from the API boundary, carrying the HTTP status and raw detail. */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function extractReason(body: unknown): string | undefined {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (detail && typeof detail === "object" && "reason" in detail) {
      return String((detail as { reason: unknown }).reason);
    }
    if (typeof detail === "string") {
      return detail;
    }
  }
  return undefined;
}

/** Analyze a contract (non-streaming) and validate the response. */
export async function analyzeContract(
  request: AnalysisRequest,
  signal?: AbortSignal,
): Promise<ContractAnalysis> {
  const response = await fetch(`${API_BASE_URL}/api/v1/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal,
  });
  const body = await readJson(response);
  if (!response.ok) {
    throw new ApiError(
      extractReason(body) ?? `Analysis failed (HTTP ${response.status})`,
      response.status,
      body,
    );
  }
  return contractAnalysisSchema.parse(body);
}

/** Fetch a single statutory section for citation drill-down. */
export async function fetchLawSection(
  sectionId: string,
  signal?: AbortSignal,
): Promise<LawSection> {
  const response = await fetch(`${API_BASE_URL}/api/v1/law/${encodeURIComponent(sectionId)}`, {
    signal,
  });
  const body = await readJson(response);
  if (!response.ok) {
    throw new ApiError(`Section not found (HTTP ${response.status})`, response.status, body);
  }
  return lawSectionSchema.parse(body);
}
