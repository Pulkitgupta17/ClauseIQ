import { useAnalyzeContract } from "@/hooks/useAnalyzeContract";
import { useAnalysisStore } from "@/stores/analysis";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("useAnalyzeContract", () => {
  it("validates, stores the input, and returns a session id", async () => {
    const { result } = renderHook(() => useAnalyzeContract(), { wrapper });

    let id = "";
    await act(async () => {
      id = await result.current.mutateAsync({
        contract_text: "x".repeat(150),
        jurisdiction: "IN-MH",
      });
    });

    expect(id).toHaveLength(8);
    expect(useAnalysisStore.getState().inputs[id]?.contract_text).toHaveLength(150);
  });

  it("rejects a too-short contract", async () => {
    const { result } = renderHook(() => useAnalyzeContract(), { wrapper });

    await expect(
      act(async () => {
        await result.current.mutateAsync({ contract_text: "short", jurisdiction: "IN-MH" });
      }),
    ).rejects.toThrow();
  });
});
