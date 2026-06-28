import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import type { Citation } from "@/lib/schemas";
import { BookOpen, ExternalLink } from "lucide-react";

interface CitationLinkProps {
  citation: Citation;
}

/** A citation chip that opens a dialog with the full section text. */
export function CitationLink({ citation }: CitationLinkProps) {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className="h-7 gap-1.5 text-xs">
          <BookOpen className="h-3.5 w-3.5" />
          {citation.reference}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{citation.reference}</DialogTitle>
          <DialogDescription>{citation.section_title}</DialogDescription>
        </DialogHeader>
        <p className="max-h-72 overflow-y-auto whitespace-pre-wrap text-sm leading-relaxed">
          {citation.snippet}
        </p>
        {citation.amendment_note ? (
          <p className="rounded-md bg-muted px-3 py-2 text-muted-foreground text-xs">
            {citation.amendment_note}
          </p>
        ) : null}
        {citation.source_url ? (
          <a
            href={citation.source_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 text-muted-foreground text-xs hover:text-foreground"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            View official source
          </a>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
