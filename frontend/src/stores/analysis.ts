import { describeError } from "@/lib/errors";
import {
  type AnalysisRequest,
  type ContractAnalysis,
  type StreamEvent,
  contractAnalysisSchema,
  doneEventDataSchema,
} from "@/lib/schemas";
import { create } from "zustand";

/** Mark the step that was running as failed; leave completed/pending steps as-is. */
function markActiveStepError(steps: StepState[]): StepState[] {
  return steps.map((step) => (step.status === "active" ? { ...step, status: "error" } : step));
}

/** The four agent steps shown in the live trace, in order. */
export const AGENT_STEPS = [
  { key: "supervisor", label: "Reading & segmenting clauses", completeOn: "supervisor_complete" },
  { key: "retriever", label: "Retrieving relevant Indian law", completeOn: "retriever_complete" },
  {
    key: "risk_analyzer",
    label: "Analysing clauses for risk",
    completeOn: "risk_analyzer_complete",
  },
  {
    key: "citation_verifier",
    label: "Verifying citations",
    completeOn: "citation_verifier_complete",
  },
] as const;

export type StepStatus = "pending" | "active" | "complete" | "error";
export type SessionStatus = "idle" | "streaming" | "done" | "error";

export interface StepState {
  key: string;
  label: string;
  status: StepStatus;
  detail?: string;
}

export interface Usage {
  total_tokens?: number;
  cost_usd?: number;
}

interface AnalysisStore {
  inputs: Record<string, AnalysisRequest>;
  status: SessionStatus;
  steps: StepState[];
  analysis: ContractAnalysis | null;
  error: string | null;
  usage: Usage | null;

  setInput: (id: string, request: AnalysisRequest) => void;
  startSession: () => void;
  handleEvent: (event: StreamEvent) => void;
  fail: (message: string) => void;
  reset: () => void;
}

function initialSteps(activeIndex: number): StepState[] {
  return AGENT_STEPS.map((step, index) => ({
    key: step.key,
    label: step.label,
    status: index < activeIndex ? "complete" : index === activeIndex ? "active" : "pending",
  }));
}

function advance(steps: StepState[], completedKey: string): StepState[] {
  const completedIndex = AGENT_STEPS.findIndex((step) => step.completeOn === completedKey);
  if (completedIndex === -1) {
    return steps;
  }
  return steps.map((step, index) => {
    if (index <= completedIndex) {
      return { ...step, status: "complete" };
    }
    if (index === completedIndex + 1) {
      return { ...step, status: "active" };
    }
    return step;
  });
}

export const useAnalysisStore = create<AnalysisStore>((set) => ({
  inputs: {},
  status: "idle",
  steps: initialSteps(-1),
  analysis: null,
  error: null,
  usage: null,

  setInput: (id, request) => set((state) => ({ inputs: { ...state.inputs, [id]: request } })),

  startSession: () =>
    set({ status: "streaming", steps: initialSteps(0), analysis: null, error: null, usage: null }),

  handleEvent: (event) =>
    set((state) => {
      if (event.event === "done") {
        const parsed = doneEventDataSchema.safeParse(event.data);
        const analysis = parsed.success
          ? parsed.data.analysis
          : (contractAnalysisSchema.safeParse(event.data.analysis).data ?? null);
        return {
          status: "done",
          analysis,
          usage: parsed.success ? (parsed.data.usage ?? null) : null,
          steps: state.steps.map((step) => ({ ...step, status: "complete" })),
        };
      }
      if (event.event === "error") {
        const raw =
          typeof event.data.error === "string"
            ? event.data.error
            : typeof event.data.message === "string"
              ? event.data.message
              : null;
        return {
          status: "error",
          error: describeError(raw),
          steps: markActiveStepError(state.steps),
        };
      }
      return { steps: advance(state.steps, event.event) };
    }),

  fail: (message) =>
    set((state) => ({
      status: "error",
      error: message,
      steps: markActiveStepError(state.steps),
    })),

  reset: () =>
    set({ status: "idle", steps: initialSteps(-1), analysis: null, error: null, usage: null }),
}));
