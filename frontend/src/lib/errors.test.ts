import { describeError } from "@/lib/errors";
import { describe, expect, it } from "vitest";

describe("describeError", () => {
  it("maps the not_a_contract code to friendly copy (no raw code shown)", () => {
    const msg = describeError("not_a_contract");
    expect(msg).toMatch(/doesn't look like a contract/i);
    expect(msg).not.toContain("not_a_contract");
  });

  it("maps prompt-injection to friendly copy", () => {
    expect(describeError("prompt_injection_detected")).toMatch(/instructions to the AI/i);
  });

  it("maps service/quota failures to a retry message", () => {
    expect(describeError("generation_failed")).toMatch(/temporarily unavailable/i);
  });

  it("passes through an already-human message", () => {
    const human = "Could not reach the analysis service: network down";
    expect(describeError(human)).toBe(human);
  });

  it("has a safe fallback for unknown bare codes and empty input", () => {
    expect(describeError("some_weird_code")).toMatch(/couldn't analyse/i);
    expect(describeError(null)).toMatch(/couldn't analyse/i);
  });
});
