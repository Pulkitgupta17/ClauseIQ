import { z } from "zod";

/**
 * Zod schemas mirroring the backend Pydantic models (single source of truth on
 * the backend; manually mirrored here). Dates arrive as ISO strings.
 */

export const citationSchema = z.object({
  law_code: z.string(),
  section_number: z.string(),
  section_title: z.string(),
  reference: z.string(),
  snippet: z.string(),
  source_url: z.string().nullable().optional(),
  effective_date: z.string().nullable().optional(),
  last_amended: z.string().nullable().optional(),
  source_fetched_at: z.string().nullable().optional(),
  relevance_score: z.number().nullable().optional(),
  amendment_note: z.string().nullable().optional(),
});
export type Citation = z.infer<typeof citationSchema>;

export const severityLabels = ["info", "low", "medium", "high", "critical"] as const;
export type SeverityLabel = (typeof severityLabels)[number];

export const riskFlagSchema = z.object({
  clause_id: z.string(),
  clause_heading: z.string().nullable().optional(),
  clause_excerpt: z.string(),
  clause_type: z.string(),
  severity_score: z.number().int().min(1).max(5),
  severity_label: z.enum(severityLabels),
  rationale: z.string(),
  confidence: z.number(),
  suggested_action: z.string().nullable().optional(),
  citations: z.array(citationSchema).default([]),
});
export type RiskFlag = z.infer<typeof riskFlagSchema>;

export const contractAnalysisSchema = z.object({
  contract_id: z.string(),
  jurisdiction: z.string(),
  flag_count: z.number().int(),
  highest_severity: z.string().nullable().optional(),
  flags: z.array(riskFlagSchema).default([]),
  corpus_version: z.string(),
  disclaimer: z.string(),
});
export type ContractAnalysis = z.infer<typeof contractAnalysisSchema>;

export const lawSectionSchema = z.object({
  law_code: z.string(),
  section_number: z.string(),
  section_title: z.string(),
  reference: z.string(),
  snippet: z.string(),
  relevance_score: z.number().nullable().optional(),
  source_url: z.string().nullable().optional(),
  effective_date: z.string().nullable().optional(),
  last_amended: z.string().nullable().optional(),
  amendment_note: z.string().nullable().optional(),
});
export type LawSection = z.infer<typeof lawSectionSchema>;

export const jurisdictions = ["IN-MH", "IN-DL", "IN-KA"] as const;
export type Jurisdiction = (typeof jurisdictions)[number];

export const analysisRequestSchema = z.object({
  contract_text: z.string().min(100, "Contract text must be at least 100 characters."),
  jurisdiction: z.enum(jurisdictions).default("IN-MH"),
});
export type AnalysisRequest = z.infer<typeof analysisRequestSchema>;

/** The ordered set of SSE event names the backend emits. */
export const streamEventNames = [
  "supervisor_start",
  "supervisor_complete",
  "retriever_complete",
  "risk_analyzer_complete",
  "citation_verifier_complete",
  "done",
  "error",
] as const;
export type StreamEventName = (typeof streamEventNames)[number];

export const streamEventSchema = z.object({
  event: z.string(),
  data: z.record(z.string(), z.unknown()).default({}),
});
export type StreamEvent = z.infer<typeof streamEventSchema>;

/** Payload of the terminal `done` event. */
export const doneEventDataSchema = z.object({
  analysis: contractAnalysisSchema,
  usage: z.object({ total_tokens: z.number(), cost_usd: z.number() }).partial().optional(),
});
export type DoneEventData = z.infer<typeof doneEventDataSchema>;
