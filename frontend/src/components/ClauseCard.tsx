import { CitationLink } from "@/components/CitationLink";
import { Badge } from "@/components/ui/badge";
import type { RiskFlag } from "@/lib/schemas";
import { SEVERITY_META } from "@/lib/severity";
import { cn } from "@/lib/utils";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown, Lightbulb } from "lucide-react";
import { useState } from "react";

interface ClauseCardProps {
  flag: RiskFlag;
}

/** Variants for staggered reveal; consumed by a parent `motion` list. */
export const clauseCardVariants = {
  hidden: { opacity: 0, y: 12 },
  visible: { opacity: 1, y: 0 },
};

function humaniseType(value: string): string {
  return value.replace(/_/g, " ");
}

export function ClauseCard({ flag }: ClauseCardProps) {
  const [open, setOpen] = useState(false);
  const meta = SEVERITY_META[flag.severity_label];

  return (
    <motion.div variants={clauseCardVariants} className="overflow-hidden rounded-xl border bg-card">
      <div className="flex">
        <div className={cn("w-1.5 shrink-0", meta.bar)} aria-hidden />
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          className="flex flex-1 items-start gap-3 p-4 text-left"
        >
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <Badge className={cn("border-transparent", meta.bg, meta.text)}>
                {meta.label} · {flag.severity_score}/5
              </Badge>
              <span className="font-medium text-sm capitalize">
                {humaniseType(flag.clause_type)}
              </span>
              {flag.clause_heading ? (
                <span className="text-muted-foreground text-xs">{flag.clause_heading}</span>
              ) : null}
            </div>
            <p className="mt-2 line-clamp-2 text-muted-foreground text-sm">{flag.clause_excerpt}</p>
          </div>
          <ChevronDown
            className={cn(
              "mt-1 h-4 w-4 shrink-0 text-muted-foreground transition-transform",
              open && "rotate-180",
            )}
          />
        </button>
      </div>

      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            key="content"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="space-y-4 border-t px-4 py-4 pl-5.5">
              <div>
                <p className="font-medium text-xs text-muted-foreground uppercase tracking-wide">
                  Why this is risky
                </p>
                <p className="mt-1 text-sm leading-relaxed">{flag.rationale}</p>
              </div>
              {flag.suggested_action ? (
                <div className="flex gap-2 rounded-lg bg-muted/60 p-3">
                  <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-severity-medium" />
                  <p className="text-sm">{flag.suggested_action}</p>
                </div>
              ) : null}
              {flag.citations.length > 0 ? (
                <div>
                  <p className="mb-2 font-medium text-muted-foreground text-xs uppercase tracking-wide">
                    Backed by
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {flag.citations.map((citation) => (
                      <CitationLink
                        key={`${citation.law_code}:${citation.section_number}`}
                        citation={citation}
                      />
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </motion.div>
  );
}
