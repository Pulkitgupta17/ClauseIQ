import { severityMeta } from "@/lib/severity";
import { cn } from "@/lib/utils";
import { motion } from "framer-motion";

interface RiskGaugeProps {
  highestSeverity: string | null | undefined;
  flagCount: number;
}

const RADIUS = 52;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

/** Circular SVG gauge; the arc fills to the highest severity, animated with Framer Motion. */
export function RiskGauge({ highestSeverity, flagCount }: RiskGaugeProps) {
  const meta = severityMeta(highestSeverity);
  const fraction = meta ? meta.score / 5 : 0;

  return (
    <div
      className="relative h-36 w-36"
      role="img"
      aria-label={`${flagCount} risk flags, highest severity ${meta?.label ?? "none"}`}
    >
      <svg viewBox="0 0 120 120" className="-rotate-90 h-full w-full" aria-hidden="true">
        <circle cx="60" cy="60" r={RADIUS} className="stroke-muted" strokeWidth="10" fill="none" />
        <motion.circle
          cx="60"
          cy="60"
          r={RADIUS}
          className={cn("fill-none", meta ? meta.stroke : "stroke-muted-foreground")}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={CIRCUMFERENCE}
          initial={{ strokeDashoffset: CIRCUMFERENCE }}
          animate={{ strokeDashoffset: CIRCUMFERENCE * (1 - fraction) }}
          transition={{ duration: 1, ease: "easeOut" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-bold text-3xl tabular-nums">{flagCount}</span>
        <span className="text-muted-foreground text-xs">{flagCount === 1 ? "flag" : "flags"}</span>
        {meta ? (
          <span className={cn("mt-0.5 font-medium text-xs", meta.text)}>{meta.label}</span>
        ) : null}
      </div>
    </div>
  );
}
