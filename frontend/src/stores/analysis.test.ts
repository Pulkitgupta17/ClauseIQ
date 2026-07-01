import { useAnalysisStore } from "@/stores/analysis";
import { beforeEach, describe, expect, it } from "vitest";

const store = () => useAnalysisStore.getState();

const analysis = {
  contract_id: "c1",
  jurisdiction: "IN-MH",
  flag_count: 0,
  highest_severity: null,
  corpus_version: "v2",
  disclaimer: "Not legal advice.",
  flags: [],
};

beforeEach(() => store().reset());

describe("analysis store", () => {
  it("activates the first step on start", () => {
    store().startSession();
    expect(store().status).toBe("streaming");
    expect(store().steps[0]?.status).toBe("active");
    expect(store().steps[1]?.status).toBe("pending");
  });

  it("advances steps as completion events arrive", () => {
    store().startSession();
    store().handleEvent({ event: "supervisor_complete", data: {} });
    expect(store().steps[0]?.status).toBe("complete");
    expect(store().steps[1]?.status).toBe("active");

    store().handleEvent({ event: "retriever_complete", data: {} });
    expect(store().steps[1]?.status).toBe("complete");
    expect(store().steps[2]?.status).toBe("active");
  });

  it("captures the analysis and completes all steps on done", () => {
    store().startSession();
    store().handleEvent({ event: "done", data: { analysis } });
    expect(store().status).toBe("done");
    expect(store().analysis?.contract_id).toBe("c1");
    expect(store().steps.every((step) => step.status === "complete")).toBe(true);
  });

  it("maps an error event to friendly copy and marks the running step failed", () => {
    store().startSession();
    store().handleEvent({ event: "error", data: { error: "not_a_contract" } });
    expect(store().status).toBe("error");
    // Friendly message, never the raw code.
    expect(store().error).toMatch(/doesn't look like a contract/i);
    expect(store().error).not.toContain("not_a_contract");
    // The step that was running (the first) is marked failed, not left spinning.
    expect(store().steps[0]?.status).toBe("error");
    expect(store().steps.some((step) => step.status === "active")).toBe(false);
  });
});
