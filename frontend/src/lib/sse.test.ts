import { parseSseFrame } from "@/lib/sse";
import { describe, expect, it } from "vitest";

describe("parseSseFrame", () => {
  it("parses an event name and JSON data", () => {
    const event = parseSseFrame('event: supervisor_complete\ndata: {"clauses": 3}');
    expect(event?.event).toBe("supervisor_complete");
    expect(event?.data.clauses).toBe(3);
  });

  it("defaults the event name to 'message'", () => {
    expect(parseSseFrame('data: {"a": 1}')?.event).toBe("message");
  });

  it("returns null for a frame with no data line", () => {
    expect(parseSseFrame("event: ping")).toBeNull();
  });

  it("returns null for malformed JSON", () => {
    expect(parseSseFrame("data: {nope")).toBeNull();
  });
});
