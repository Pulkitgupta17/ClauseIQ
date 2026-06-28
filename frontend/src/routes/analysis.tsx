import { AgentTrace } from "@/components/AgentTrace";
import { ClauseCard } from "@/components/ClauseCard";
import { RiskGauge } from "@/components/RiskGauge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useStreamingAgents } from "@/hooks/useStreamingAgents";
import { motion } from "framer-motion";
import { AlertTriangle } from "lucide-react";
import { Link, Navigate, useParams } from "react-router-dom";

const listVariants = { visible: { transition: { staggerChildren: 0.06 } } };

export default function Analysis() {
  const { id } = useParams<{ id: string }>();
  const { status, steps, analysis, error, usage, missingInput } = useStreamingAgents(id ?? "");

  if (!id || missingInput) {
    return <Navigate to="/" replace />;
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[18rem_1fr]">
      <aside className="space-y-6 lg:sticky lg:top-20 lg:self-start">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Risk overview</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col items-center gap-4">
            <RiskGauge
              highestSeverity={analysis?.highest_severity}
              flagCount={analysis?.flag_count ?? 0}
            />
            {usage?.cost_usd !== undefined ? (
              <p className="text-muted-foreground text-xs">
                {usage.total_tokens?.toLocaleString()} tokens · ${usage.cost_usd.toFixed(4)}
              </p>
            ) : null}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Agents</CardTitle>
          </CardHeader>
          <CardContent>
            <AgentTrace steps={steps} />
          </CardContent>
        </Card>
      </aside>

      <section className="space-y-4">
        {error ? (
          <Card className="border-destructive/40">
            <CardContent className="flex flex-col items-start gap-3 pt-6">
              <div className="flex items-center gap-2 text-destructive">
                <AlertTriangle className="h-5 w-5" />
                <span className="font-medium">Analysis couldn't complete</span>
              </div>
              <p className="text-muted-foreground text-sm">{error}</p>
              <Button asChild variant="outline" size="sm">
                <Link to="/">Try another contract</Link>
              </Button>
            </CardContent>
          </Card>
        ) : status !== "done" || !analysis ? (
          <div className="space-y-3">
            {[0, 1, 2].map((index) => (
              <Skeleton key={index} className="h-24 w-full" />
            ))}
          </div>
        ) : analysis.flags.length === 0 ? (
          <Card>
            <CardContent className="pt-6 text-center text-muted-foreground text-sm">
              No unfair clauses were flagged in this contract.
            </CardContent>
          </Card>
        ) : (
          <motion.div
            initial="hidden"
            animate="visible"
            variants={listVariants}
            className="space-y-3"
          >
            {analysis.flags.map((flag) => (
              <ClauseCard key={flag.clause_id} flag={flag} />
            ))}
          </motion.div>
        )}

        {analysis ? (
          <p className="text-balance pt-2 text-muted-foreground text-xs">{analysis.disclaimer}</p>
        ) : null}
      </section>
    </div>
  );
}
