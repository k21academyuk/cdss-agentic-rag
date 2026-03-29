// src/components/panels/SynthesisPanel.tsx
// Complete working example demonstrating JSON → UI rendering pipeline.

import { useState, useEffect, useRef } from "react";
import { AlertTriangle, ShieldAlert, ShieldCheck, Info } from "lucide-react";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  CardFooter,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import { DrugAlertCard } from "@/components/clinical/DrugAlertCard";
import { ConfidenceScoreBadge } from "@/components/clinical/ConfidenceScoreBadge";
import { CitationAccordion } from "@/components/clinical/CitationAccordion";
import { useSessionStore } from "@/stores/sessionStore";
import { tokens } from "@/styles/design-tokens";
import { cn } from "@/lib/utils";
import type { ConversationTurn, DrugAlert, GuardrailsResult } from "@/types/cdss";

export interface SynthesisPanelProps {
  turn: ConversationTurn | null;
  isLoading?: boolean;
  onFeedback?: (rating: number, correction?: string) => void;
  className?: string;
}

function GuardrailsIndicator({
  guardrails,
}: {
  guardrails: GuardrailsResult | null;
}): JSX.Element {
  if (!guardrails) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Info className="w-3.5 h-3.5" aria-hidden="true" />
        <span>Guardrails pending...</span>
      </div>
    );
  }

  const items = [
    {
      key: "hallucination_check",
      label: "Hallucination",
      status: guardrails.hallucination_check,
    },
    { key: "safety_check", label: "Safety", status: guardrails.safety_check },
    { key: "scope_check", label: "Scope", status: guardrails.scope_check },
  ] as const;

  return (
    <div className="flex items-center gap-3">
      {items.map((item) => {
        const passed = item.status === "passed";
        const warning = item.status === "warning";
        const Icon = ShieldAlert;
        const color = passed
          ? tokens.color.confidence.high
          : warning
          ? tokens.color.confidence.moderate
          : tokens.color.alert.critical;

        return (
          <div
            key={item.key}
            className="flex items-center gap-1"
            title={`${item.label}: ${item.status}`}
          >
            {passed ? (
              <ShieldCheck
                className="w-3.5 h-3.5"
                style={{ color }}
                aria-hidden="true"
              />
            ) : (
              <ShieldAlert
                className="w-3.5 h-3.5"
                style={{ color }}
                aria-hidden="true"
              />
            )}
            <span
              className="text-xs font-medium"
              style={{ color }}
            >
              {item.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function sortAlertsBySeverity(alerts: DrugAlert[]): DrugAlert[] {
  const severityOrder: Record<DrugAlert["severity"], number> = {
    major: 0,
    moderate: 1,
    minor: 2,
  };
  return [...alerts].sort(
    (a, b) => severityOrder[a.severity] - severityOrder[b.severity]
  );
}

export function SynthesisPanel({
  turn,
  isLoading = false,
  onFeedback,
  className = "",
}: SynthesisPanelProps): JSX.Element {
  const [showCorrection, setShowCorrection] = useState(false);
  const [correction, setCorrection] = useState("");
  const synthesisStatus = useSessionStore((state) => state.synthesisStatus);
  const synthesisChunks = useSessionStore((state) => state.synthesisChunks);
  const prevChunksLengthRef = useRef(0);

  // Progressive text rendering
  const [displayText, setDisplayText] = useState("");

  useEffect(() => {
    if (synthesisStatus === "streaming" && synthesisChunks.length > 0) {
      const newChunks = synthesisChunks.slice(prevChunksLengthRef.current);
      if (newChunks.length > 0) {
        setDisplayText((prev) => prev + newChunks.join(""));
      }
      prevChunksLengthRef.current = synthesisChunks.length;
    } else if (turn?.response?.recommendation) {
      setDisplayText(turn.response.recommendation);
      prevChunksLengthRef.current = 0;
    } else if (synthesisStatus !== "streaming") {
      setDisplayText("");
      prevChunksLengthRef.current = 0;
    }
  }, [synthesisChunks, synthesisStatus, turn?.response?.recommendation]);

  // Loading state
  if (isLoading && !turn) {
    return (
      <Card className={cn("p-6", className)}>
        <div className="space-y-4">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-32 w-full" />
        </div>
      </Card>
    );
  }

  // Empty state
  if (!turn && synthesisStatus === "idle") {
    return (
      <Card className={cn("p-6", className)}>
        <div className="text-center text-muted-foreground">
          <Info className="w-8 h-8 mx-auto mb-3 opacity-50" aria-hidden="true" />
          <p className="text-sm">Submit a clinical query to receive synthesized recommendations.</p>
        </div>
      </Card>
    );
  }

  const response = turn?.response;
  const confidenceScore = response?.confidence_score ?? null;
  const citations = response?.citations ?? [];
  const drugAlerts = response?.drug_alerts ?? [];
  const disclaimers = response?.disclaimers ?? [];
  const guardrails = turn?.guardrails ?? null;
  const sortedAlerts = sortAlertsBySeverity(drugAlerts);

  return (
    <Card className={cn("flex flex-col", className)}>
      {/* Header: Confidence + Guardrails */}
      <CardHeader className="pb-3 border-b border-clinical-border-default">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <CardTitle className="text-base">Clinical Recommendation</CardTitle>
            {confidenceScore !== null && (
              <ConfidenceScoreBadge score={confidenceScore} />
            )}
          </div>
          <GuardrailsIndicator guardrails={guardrails} />
        </div>
      </CardHeader>

      {/* Main Content */}
      <CardContent className="flex-1 py-4">
        {/* Recommendation Text */}
        <div className="mb-4">
          <p
            className="text-body leading-relaxed whitespace-pre-wrap"
            style={{ color: tokens.color.text.clinical }}
          >
            {displayText || (
              <span className="text-muted-foreground italic">
                Waiting for synthesis...
              </span>
            )}
          </p>
        </div>

        {/* Drug Alerts */}
        {sortedAlerts.length > 0 && (
          <div className="mb-4">
            <h4 className="text-sm font-semibold text-clinical-text-primary mb-2 flex items-center gap-2">
              <AlertTriangle
                className="w-4 h-4"
                style={{ color: tokens.color.alert.critical }}
                aria-hidden="true"
              />
              Drug Alerts ({sortedAlerts.length})
            </h4>
            <div className="space-y-2">
              {sortedAlerts.map((alert, index) => (
                <DrugAlertCard
                  key={`alert-${index}`}
                  alert={alert}
                />
              ))}
            </div>
          </div>
        )}

        {/* Citations */}
        {citations.length > 0 && (
          <div className="mb-4">
            <h4 className="text-sm font-semibold text-clinical-text-primary mb-2">
              Citations ({citations.length})
            </h4>
            <CitationAccordion citations={citations} maxVisible={3} />
          </div>
        )}
      </CardContent>

      {/* Footer: Disclaimers + Feedback */}
      <CardFooter className="flex-col items-start gap-3 bg-clinical-surface-secondary">
        {/* Disclaimers */}
        {disclaimers.length > 0 && (
          <div className="text-xs text-muted-foreground">
            <p className="font-medium mb-1">Disclaimers:</p>
            <ul className="list-disc list-inside space-y-0.5">
              {disclaimers.map((disclaimer, index) => (
                <li key={`disclaimer-${index}`}>{disclaimer}</li>
              ))}
            </ul>
          </div>
        )}

        <Separator className="my-2" />

        {/* Feedback Section */}
        {onFeedback && (
          <div className="w-full">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-clinical-text-secondary">
                Rate this response:
              </span>
              <div className="flex gap-1">
                {[1, 2, 3, 4, 5].map((rating) => (
                  <button
                    key={rating}
                    type="button"
                    className="w-7 h-7 rounded text-xs font-medium hover:bg-muted transition-colors"
                    onClick={() => onFeedback(rating)}
                    aria-label={`Rate ${rating} stars`}
                  >
                    {rating}
                  </button>
                ))}
              </div>
            </div>

            {showCorrection && (
              <div className="mt-2">
                <Textarea
                  placeholder="Enter your correction or feedback..."
                  value={correction}
                  onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setCorrection(e.target.value)}
                  className="h-20 text-xs"
                />
                <div className="flex justify-end gap-2 mt-2">
                  <button
                    type="button"
                    className="px-3 py-1.5 text-xs rounded hover:bg-muted transition-colors"
                    onClick={() => {
                      setShowCorrection(false);
                      setCorrection("");
                    }}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    className="px-3 py-1.5 text-xs rounded bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
                    onClick={() => {
                      onFeedback(0, correction);
                      setShowCorrection(false);
                      setCorrection("");
                    }}
                  >
                    Submit Correction
                  </button>
                </div>
              </div>
            )}

            {!showCorrection && (
              <button
                type="button"
                className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                onClick={() => setShowCorrection(true)}
              >
                Provide Correction
              </button>
            )}
          </div>
        )}
      </CardFooter>
    </Card>
  );
}
