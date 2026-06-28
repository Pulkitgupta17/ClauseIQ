import { type AnalysisRequest, analysisRequestSchema } from "@/lib/schemas";
import { useAnalysisStore } from "@/stores/analysis";
import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

/** Generate a short, URL-friendly session id. */
function newSessionId(): string {
  return crypto.randomUUID().slice(0, 8);
}

/**
 * Mutation that starts an analysis: validates the request, stashes it for the
 * streaming view, and navigates to `/analysis/:id`. The actual SSE run happens
 * there (see {@link useStreamingAgents}).
 */
export function useAnalyzeContract() {
  const setInput = useAnalysisStore((state) => state.setInput);
  const navigate = useNavigate();

  return useMutation({
    mutationFn: async (request: AnalysisRequest): Promise<string> => {
      const validated = analysisRequestSchema.parse(request);
      const id = newSessionId();
      setInput(id, validated);
      return id;
    },
    onSuccess: (id) => navigate(`/analysis/${id}`),
    onError: (error) =>
      toast.error(error instanceof Error ? error.message : "Could not start the analysis."),
  });
}
