import { SEVERITY_META, severityMeta } from "@/lib/severity";
import { describe, expect, it } from "vitest";

describe("severityMeta", () => {
  it("maps a known label to its metadata", () => {
    expect(severityMeta("critical")).toBe(SEVERITY_META.critical);
    expect(severityMeta("critical")?.score).toBe(5);
  });

  it("returns null for an unknown label", () => {
    expect(severityMeta("extreme")).toBeNull();
  });

  it("returns null for nullish input", () => {
    expect(severityMeta(null)).toBeNull();
    expect(severityMeta(undefined)).toBeNull();
  });
});
