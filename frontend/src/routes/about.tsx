import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ArrowRight } from "lucide-react";

const MCP_INSTALL_URL = "https://github.com/Pulkitgupta17/ClauseIQ/blob/main/docs/MCP_INSTALL.md";

export default function About() {
  return (
    <div className="mx-auto max-w-2xl space-y-8 py-4">
      <header className="space-y-2">
        <h1 className="font-bold text-3xl tracking-tight">About ClauseIQ</h1>
        <p className="text-muted-foreground">
          A multi-agent system that analyses Indian contracts and grounds every finding in the law.
        </p>
      </header>

      <section className="space-y-3 text-sm leading-relaxed">
        <p>
          A supervisor agent segments the contract into clauses, a retriever pulls the relevant
          sections of the Indian Contract Act, 1872 using hybrid search, a risk analyzer scores each
          clause from 1–5, and a citation verifier checks every cited section actually exists — so
          the analysis is grounded, not guessed. You watch each step happen live as it streams.
        </p>
        <p>
          The web app uses Google Gemini (free tier). The same tools are also exposed over MCP, so
          you can drive ClauseIQ directly from Claude Desktop.
        </p>
      </section>

      <Card>
        <CardContent className="flex flex-col items-start gap-3 pt-6">
          <h2 className="font-medium">Use it inside Claude Desktop</h2>
          <p className="text-muted-foreground text-sm">
            Install the MCP server and ask Claude to analyse contracts or look up Indian law.
          </p>
          <Button asChild variant="outline" size="sm">
            <a href={MCP_INSTALL_URL} target="_blank" rel="noreferrer">
              MCP install guide
              <ArrowRight className="h-4 w-4" />
            </a>
          </Button>
        </CardContent>
      </Card>

      <p className="text-muted-foreground text-xs">
        ClauseIQ is automated decision-support, not legal advice. Amendment history is not tracked;
        verify current law for time-sensitive matters.
      </p>
    </div>
  );
}
