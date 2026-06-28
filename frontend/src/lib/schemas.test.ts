import { analysisRequestSchema, contractAnalysisSchema, riskFlagSchema } from "@/lib/schemas";
import { describe, expect, it } from "vitest";

const validFlag = {
  clause_id: "cl1",
  clause_excerpt: "the deposit is forfeited",
  clause_type: "deposit_forfeiture",
  severity_score: 4,
  severity_label: "high",
  rationale: "Forfeiture operates as a penalty.",
  confidence: 0.82,
  citations: [],
};

const validAnalysis = {
  contract_id: "c1",
  jurisdiction: "IN-MH",
  flag_count: 1,
  highest_severity: "high",
  corpus_version: "golden-v2",
  disclaimer: "Not legal advice.",
  flags: [validFlag],
};

describe("schemas", () => {
  it("parses a valid analysis", () => {
    const parsed = contractAnalysisSchema.parse(validAnalysis);
    expect(parsed.flags).toHaveLength(1);
    expect(parsed.flags[0]?.severity_label).toBe("high");
  });

  it("rejects an out-of-range severity score", () => {
    expect(() => riskFlagSchema.parse({ ...validFlag, severity_score: 9 })).toThrow();
  });

  it("rejects an unknown severity label", () => {
    expect(() => riskFlagSchema.parse({ ...validFlag, severity_label: "extreme" })).toThrow();
  });

  it("enforces the minimum contract length", () => {
    expect(() => analysisRequestSchema.parse({ contract_text: "too short" })).toThrow();
  });

  it("defaults the jurisdiction", () => {
    const parsed = analysisRequestSchema.parse({ contract_text: "x".repeat(120) });
    expect(parsed.jurisdiction).toBe("IN-MH");
  });
});
