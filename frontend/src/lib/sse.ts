import { API_BASE_URL, ApiError } from "@/lib/api";
import { type AnalysisRequest, type StreamEvent, streamEventSchema } from "@/lib/schemas";

export interface StreamHandlers {
  onEvent: (event: StreamEvent) => void;
  signal?: AbortSignal;
}

/** Parse a single SSE frame ("event: x\ndata: {...}") into a StreamEvent. */
export function parseSseFrame(frame: string): StreamEvent | null {
  let eventName = "message";
  const dataLines: string[] = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) {
      eventName = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }
  if (dataLines.length === 0) {
    return null;
  }
  try {
    const data: unknown = JSON.parse(dataLines.join("\n"));
    return streamEventSchema.parse({ event: eventName, data });
  } catch {
    return null;
  }
}

/**
 * Stream a contract analysis via Server-Sent Events over a POST request.
 *
 * `EventSource` only supports GET, and our stream endpoint takes a JSON body,
 * so we POST and parse the SSE frames from the response body stream.
 */
export async function streamAnalysis(
  request: AnalysisRequest,
  { onEvent, signal }: StreamHandlers,
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/v1/analyze/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(request),
    signal,
  });
  if (!response.ok || !response.body) {
    throw new ApiError(`Stream failed (HTTP ${response.status})`, response.status);
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += value;
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const event = parseSseFrame(frame);
      if (event) {
        onEvent(event);
      }
      boundary = buffer.indexOf("\n\n");
    }
  }
}
