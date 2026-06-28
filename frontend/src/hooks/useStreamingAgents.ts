import { ApiError } from "@/lib/api";
import { streamAnalysis } from "@/lib/sse";
import { useAnalysisStore } from "@/stores/analysis";
import { useEffect } from "react";

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.status === 422
      ? "That doesn't look like a contract (or contains a prompt-injection attempt)."
      : error.status === 503
        ? "The analysis service isn't configured (missing API key)."
        : error.message;
  }
  if (error instanceof Error) {
    return `Could not reach the analysis service: ${error.message}`;
  }
  return "Unknown error during analysis.";
}

/**
 * Drives the live SSE analysis for a session: reads the stashed request, opens
 * the stream, and feeds events into the analysis store. Returns the live state.
 */
export function useStreamingAgents(sessionId: string) {
  const request = useAnalysisStore((state) => state.inputs[sessionId]);
  const status = useAnalysisStore((state) => state.status);
  const steps = useAnalysisStore((state) => state.steps);
  const analysis = useAnalysisStore((state) => state.analysis);
  const error = useAnalysisStore((state) => state.error);
  const usage = useAnalysisStore((state) => state.usage);
  const startSession = useAnalysisStore((state) => state.startSession);
  const handleEvent = useAnalysisStore((state) => state.handleEvent);
  const fail = useAnalysisStore((state) => state.fail);

  useEffect(() => {
    if (!request) {
      return;
    }
    const controller = new AbortController();
    startSession();
    streamAnalysis(request, {
      onEvent: handleEvent,
      signal: controller.signal,
    }).catch((streamError: unknown) => {
      if (!controller.signal.aborted) {
        fail(errorMessage(streamError));
      }
    });
    return () => controller.abort();
  }, [request, startSession, handleEvent, fail]);

  return { request, status, steps, analysis, error, usage, missingInput: !request };
}
