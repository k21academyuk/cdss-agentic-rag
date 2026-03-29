// src/hooks/useConfidenceLevel.ts
// Maps confidence score to token color and label.

import { useMemo } from "react";
import { tokens } from "@/styles/design-tokens";
import type { ConfidenceLevel } from "@/styles/design-tokens";

export interface ConfidenceInfo {
  level: ConfidenceLevel;
  color: string;
  label: string;
  isBelowThreshold: boolean;
}

export function useConfidenceLevel(score: number | null): ConfidenceInfo {
  return useMemo(() => {
    let level: ConfidenceLevel;
    let color: string;

    if (score === null) {
      level = "insufficient";
      color = tokens.color.confidence.insufficient;
    } else if (score >= 0.8) {
      level = "high";
      color = tokens.color.confidence.high;
    } else if (score >= 0.6) {
      level = "moderate";
      color = tokens.color.confidence.moderate;
    } else {
      level = "low";
      color = tokens.color.confidence.low;
    }

    const labels: Record<ConfidenceLevel, string> = {
      high: "High",
      moderate: "Moderate",
      low: "Low",
      insufficient: "Insufficient",
    };

    return {
      level,
      color,
      label: labels[level],
      isBelowThreshold: level === "low",
    };
  }, [score]);
}
