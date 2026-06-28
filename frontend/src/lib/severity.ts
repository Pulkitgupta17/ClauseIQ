import type { SeverityLabel } from "@/lib/schemas";

export interface SeverityMeta {
  label: string;
  score: number;
  text: string;
  bg: string;
  bar: string;
  stroke: string;
}

/** Tailwind classes per severity (driven by the --color-severity-* tokens). */
export const SEVERITY_META: Record<SeverityLabel, SeverityMeta> = {
  info: {
    label: "Info",
    score: 1,
    text: "text-severity-info",
    bg: "bg-severity-info/10",
    bar: "bg-severity-info",
    stroke: "stroke-severity-info",
  },
  low: {
    label: "Low",
    score: 2,
    text: "text-severity-low",
    bg: "bg-severity-low/10",
    bar: "bg-severity-low",
    stroke: "stroke-severity-low",
  },
  medium: {
    label: "Medium",
    score: 3,
    text: "text-severity-medium",
    bg: "bg-severity-medium/10",
    bar: "bg-severity-medium",
    stroke: "stroke-severity-medium",
  },
  high: {
    label: "High",
    score: 4,
    text: "text-severity-high",
    bg: "bg-severity-high/10",
    bar: "bg-severity-high",
    stroke: "stroke-severity-high",
  },
  critical: {
    label: "Critical",
    score: 5,
    text: "text-severity-critical",
    bg: "bg-severity-critical/10",
    bar: "bg-severity-critical",
    stroke: "stroke-severity-critical",
  },
};

export function severityMeta(label: string | null | undefined): SeverityMeta | null {
  if (label && label in SEVERITY_META) {
    return SEVERITY_META[label as SeverityLabel];
  }
  return null;
}
