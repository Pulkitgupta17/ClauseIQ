import { ContractUploader } from "@/components/ContractUploader";
import { Card, CardContent } from "@/components/ui/card";
import { motion } from "framer-motion";
import { Gavel, ScrollText, ShieldCheck } from "lucide-react";

const FEATURES = [
  {
    icon: ScrollText,
    title: "Clause-by-clause",
    body: "Every clause read and scored 1–5 for unfairness.",
  },
  {
    icon: Gavel,
    title: "Cited to the law",
    body: "Each flag backed by the exact section of Indian law.",
  },
  {
    icon: ShieldCheck,
    title: "Verified citations",
    body: "Citations checked against the statute — no hallucinations.",
  },
];

export default function Landing() {
  return (
    <div className="space-y-10">
      <motion.section
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="space-y-3 pt-6 text-center"
      >
        <h1 className="text-balance font-bold text-4xl tracking-tight sm:text-5xl">
          Know what you're signing.
        </h1>
        <p className="mx-auto max-w-xl text-balance text-muted-foreground">
          ClauseIQ reads an Indian contract, flags clauses that are unfair to you with a severity
          score, and cites the exact section of Indian law behind each flag.
        </p>
      </motion.section>

      <Card>
        <CardContent className="pt-6">
          <ContractUploader />
        </CardContent>
      </Card>

      <section className="grid gap-4 sm:grid-cols-3">
        {FEATURES.map((feature) => (
          <div key={feature.title} className="rounded-xl border bg-card p-5">
            <feature.icon className="mb-3 h-5 w-5 text-muted-foreground" />
            <h3 className="font-medium text-sm">{feature.title}</h3>
            <p className="mt-1 text-muted-foreground text-sm">{feature.body}</p>
          </div>
        ))}
      </section>
    </div>
  );
}
