// src/components/clinical/ConfidenceScoreBadge.tsx
import { AlertTriangle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { tokens } from "@/styles/design-tokens";
import type { ConfidenceLevel } from "@/styles/design-tokens";

export interface ConfidenceScoreBadgeProps {
  score: number | null;
  showLabel?: boolean;
  className?: string;
}

function getConfidenceLevel(score: number | null): ConfidenceLevel {
  if (score === null) return "insufficient";
  if (score >= 0.8) return "high";
  if (score >= 0.6) return "moderate";
  return "low";
}

function getConfidenceStyles(level: ConfidenceLevel): {
  bgColor: string;
  textColor: string;
  label: string;
} {
  switch (level) {
    case "high":
      return {
        bgColor: tokens.color.confidence.high,
        textColor: tokens.color.text.inverse,
        label: "High",
      };
    case "moderate":
      return {
        bgColor: tokens.color.confidence.moderate,
        textColor: tokens.color.text.primary,
        label: "Moderate",
      };
    case "low":
      return {
        bgColor: tokens.color.confidence.low,
        textColor: tokens.color.text.inverse,
        label: "Low",
      };
    case "insufficient":
    default:
      return {
        bgColor: tokens.color.confidence.insufficient,
        textColor: tokens.color.text.inverse,
        label: "Insufficient",
      };
  }
}

export function ConfidenceScoreBadge({
  score,
  showLabel = true,
  className = "",
}: ConfidenceScoreBadgeProps): JSX.Element {
  const level = getConfidenceLevel(score);
  const styles = getConfidenceStyles(level);
  const isLow = level === "low";
  const displayScore = score !== null ? (score * 100).toFixed(0) : "N/A";
  const exactScore = score !== null ? score.toFixed(2) : "Not available";

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger>
          <Badge
            variant="default"
            className={cn(
              "inline-flex items-center gap-1.5 px-2 py-1 font-medium text-xs transition-all cursor-default",
              isLow && "animate-pulse ring-2 ring-offset-2",
              className
            )}
            style={{
              backgroundColor: styles.bgColor,
              color: styles.textColor,
              ["--tw-ring-color" as string]: isLow ? tokens.color.confidence.low : undefined,
            }}
            role="status"
            aria-label={`Confidence score: ${styles.label}, ${exactScore}`}
          >
            {isLow && (
              <AlertTriangle
                className="w-3.5 h-3.5"
                aria-hidden="true"
              />
            )}
            {showLabel ? (
              <span>
                {styles.label}
                {score !== null && (
                  <span className="ml-1 opacity-90">({displayScore}%)</span>
                )}
              </span>
            ) : (
              <span>{displayScore}%</span>
            )}
          </Badge>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-xs">
          <div className="text-center">
            <p className="font-medium">Confidence Score</p>
            <p className="text-xs text-muted-foreground">
              {exactScore}
            </p>
            {isLow && (
              <p
                className="text-xs mt-1"
                style={{ color: tokens.color.alert.critical }}
              >
                Below escalation threshold (0.6)
              </p>
            )}
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
