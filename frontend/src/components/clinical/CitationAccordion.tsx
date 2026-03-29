// src/components/clinical/CitationAccordion.tsx
import { ExternalLink, FileText, BookOpen, ChevronDown } from "lucide-react";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { tokens } from "@/styles/design-tokens";
import type { Citation, PubMedCitation, GuidelineCitation } from "@/types/cdss";
import { isPubMedCitation, isGuidelineCitation } from "@/types/cdss";

export interface CitationAccordionProps {
  citations: Citation[];
  maxVisible?: number;
  className?: string;
}

function CitationItem({
  citation,
  index,
}: {
  citation: Citation;
  index: number;
}): JSX.Element {
  if (isPubMedCitation(citation)) {
    return <PubMedCitationItem citation={citation} index={index} />;
  }

  if (isGuidelineCitation(citation)) {
    return <GuidelineCitationItem citation={citation} index={index} />;
  }

  return (
    <div className="text-sm text-muted-foreground">
      Unknown citation type
    </div>
  );
}

function PubMedCitationItem({
  citation,
  index,
}: {
  citation: PubMedCitation;
  index: number;
}): JSX.Element {
  const pmid = citation.pmid;
  const relevancePercent = Math.round(citation.relevance * 100);

  return (
    <AccordionItem
      value={`citation-${index}`}
      className="border-b border-clinical-border-default last:border-b-0"
      data-trace-id={`pmid-${pmid}`}
    >
      <AccordionTrigger
        className="hover:no-underline px-4 py-3 hover:bg-clinical-surface-secondary transition-colors"
        aria-label={`Citation from PubMed, relevance ${relevancePercent}%`}
      >
        <div className="flex items-center gap-3 text-left w-full">
          <BookOpen
            className="w-4 h-4 flex-shrink-0"
            style={{ color: tokens.color.agent.literature }}
            aria-hidden="true"
          />
          <div className="flex-1 min-w-0">
            <span className="text-sm font-medium text-clinical-text-primary truncate block">
              [PMID:{pmid}] {citation.title}
            </span>
          </div>
        </div>
      </AccordionTrigger>
      <AccordionContent className="px-4 pb-3">
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <span className="text-xs text-clinical-text-muted">Relevance:</span>
            <Progress
              value={relevancePercent}
              className="h-1.5 flex-1"
              style={{
                ["--progress-background" as string]: tokens.color.agent.literature,
              }}
            />
            <span className="text-xs font-medium text-clinical-text-secondary">
              {relevancePercent}%
            </span>
          </div>
          <a
            href={`https://pubmed.ncbi.nlm.nih.gov/${pmid}/`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:underline"
            data-trace-id={`pmid-${pmid}-link`}
          >
            <ExternalLink className="w-3 h-3" aria-hidden="true" />
            View on PubMed
          </a>
        </div>
      </AccordionContent>
    </AccordionItem>
  );
}

function GuidelineCitationItem({
  citation,
  index,
}: {
  citation: GuidelineCitation;
  index: number;
}): JSX.Element {
  const relevancePercent = Math.round(citation.relevance * 100);

  return (
    <AccordionItem
      value={`citation-${index}`}
      className="border-b border-clinical-border-default last:border-b-0"
      data-trace-id={`guideline-${citation.guideline}-${citation.section}`}
    >
      <AccordionTrigger
        className="hover:no-underline px-4 py-3 hover:bg-clinical-surface-secondary transition-colors"
        aria-label={`Citation from ${citation.guideline}, Section ${citation.section}, relevance ${relevancePercent}%`}
      >
        <div className="flex items-center gap-3 text-left w-full">
          <FileText
            className="w-4 h-4 flex-shrink-0"
            style={{ color: tokens.color.agent.protocol }}
            aria-hidden="true"
          />
          <div className="flex-1 min-w-0">
            <span className="text-sm font-medium text-clinical-text-primary truncate block">
              [{citation.guideline} §{citation.section}]
            </span>
          </div>
        </div>
      </AccordionTrigger>
      <AccordionContent className="px-4 pb-3">
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <span className="text-xs text-clinical-text-muted">Relevance:</span>
            <Progress
              value={relevancePercent}
              className="h-1.5 flex-1"
              style={{
                ["--progress-background" as string]: tokens.color.agent.protocol,
              }}
            />
            <span className="text-xs font-medium text-clinical-text-secondary">
              {relevancePercent}%
            </span>
          </div>
          <p className="text-xs text-clinical-text-muted italic">
            Internal protocol reference
          </p>
        </div>
      </AccordionContent>
    </AccordionItem>
  );
}

export function CitationAccordion({
  citations,
  maxVisible = 3,
  className = "",
}: CitationAccordionProps): JSX.Element {
  const visibleCitations = citations.slice(0, maxVisible);
  const remainingCount = citations.length - maxVisible;

  if (citations.length === 0) {
    return (
      <div
        className={cn(
          "px-4 py-3 text-sm text-clinical-text-muted",
          className
        )}
        role="status"
        aria-label="No citations available"
      >
        No citations available
      </div>
    );
  }

  return (
    <div className={cn("w-full", className)}>
      <Accordion
        className="w-full border border-clinical-border-default rounded-lg overflow-hidden"
        role="list"
        aria-label="Citation list"
      >
        {visibleCitations.map((citation, index) => (
          <CitationItem
            key={`citation-${index}`}
            citation={citation}
            index={index}
          />
        ))}
      </Accordion>

      {remainingCount > 0 && (
        <details className="w-full mt-2">
          <summary className="cursor-pointer text-xs text-clinical-text-muted hover:text-clinical-text-secondary px-4 py-2 bg-clinical-surface-secondary rounded-lg list-none flex items-center gap-1">
            <ChevronDown className="w-3 h-3" aria-hidden="true" />
            Show {remainingCount} more citation{remainingCount !== 1 ? "s" : ""}
          </summary>
          <Accordion
            className="w-full border-t border-clinical-border-default mt-2"
            role="list"
            aria-label="Additional citations"
          >
            {citations.slice(maxVisible).map((citation, index) => (
              <CitationItem
                key={`citation-more-${index}`}
                citation={citation}
                index={maxVisible + index}
              />
            ))}
          </Accordion>
        </details>
      )}
    </div>
  );
}
