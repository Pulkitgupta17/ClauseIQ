import { cn } from "@/lib/utils";
import type { StepState } from "@/stores/analysis";
import { motion } from "framer-motion";
import { Check, Loader2, X } from "lucide-react";

interface AgentTraceProps {
  steps: StepState[];
}

/** Live agent timeline; the active step pulses, completed steps get a check. */
export function AgentTrace({ steps }: AgentTraceProps) {
  return (
    <ol className="space-y-1">
      {steps.map((step) => (
        <li key={step.key} className="flex items-center gap-3 py-2">
          <span
            className={cn(
              "flex h-7 w-7 shrink-0 items-center justify-center rounded-full border text-xs",
              step.status === "complete" &&
                "border-severity-low/40 bg-severity-low/15 text-severity-low",
              step.status === "active" && "border-primary/40 bg-primary/10 text-foreground",
              step.status === "error" && "border-destructive/40 bg-destructive/15 text-destructive",
              step.status === "pending" && "border-border bg-muted text-muted-foreground",
            )}
          >
            {step.status === "complete" ? (
              <Check className="h-4 w-4" />
            ) : step.status === "error" ? (
              <X className="h-4 w-4" />
            ) : step.status === "active" ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <span className="h-1.5 w-1.5 rounded-full bg-current" />
            )}
          </span>
          <span
            className={cn(
              "text-sm",
              step.status === "error" && "text-destructive",
              step.status === "pending" ? "text-muted-foreground" : "text-foreground",
            )}
          >
            {step.label}
          </span>
          {step.status === "active" ? (
            <motion.span
              aria-hidden
              className="ml-auto h-2 w-2 rounded-full bg-primary"
              animate={{ opacity: [1, 0.3, 1], scale: [1, 0.8, 1] }}
              transition={{ duration: 1.2, repeat: Number.POSITIVE_INFINITY }}
            />
          ) : null}
        </li>
      ))}
    </ol>
  );
}
