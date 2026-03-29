// src/components/clinical/DrugAlertCard.tsx
import { AlertTriangle, AlertCircle, Info, CheckCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  CardFooter,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { tokens } from "@/styles/design-tokens";
import type { DrugAlert, DrugAlertSeverity } from "@/types/cdss";

export interface DrugAlertCardProps {
  alert: DrugAlert;
  onDismissAcknowledge?: () => void;
  isStreaming?: boolean;
  className?: string;
}

function getSeverityStyles(severity: DrugAlertSeverity): {
  borderColor: string;
  bgColor: string;
  textColor: string;
  badgeVariant: "destructive" | "default" | "secondary" | "outline";
  icon: React.ReactNode;
  ariaLive: "assertive" | "polite";
} {
  switch (severity) {
    case "major":
      return {
        borderColor: tokens.color.alert.critical,
        bgColor: "rgba(207, 102, 121, 0.1)",
        textColor: tokens.color.alert.critical,
        badgeVariant: "destructive",
        icon: <AlertTriangle className="w-4 h-4" aria-hidden="true" />,
        ariaLive: "assertive",
      };
    case "moderate":
      return {
        borderColor: tokens.color.alert.high,
        bgColor: "rgba(239, 108, 0, 0.1)",
        textColor: tokens.color.alert.high,
        badgeVariant: "default",
        icon: <AlertCircle className="w-4 h-4" aria-hidden="true" />,
        ariaLive: "polite",
      };
    case "minor":
    default:
      return {
        borderColor: tokens.color.alert.low,
        bgColor: "rgba(34, 139, 34, 0.1)",
        textColor: tokens.color.alert.low,
        badgeVariant: "secondary",
        icon: <Info className="w-4 h-4" aria-hidden="true" />,
        ariaLive: "polite",
      };
  }
}

function getSeverityLabel(severity: DrugAlertSeverity): string {
  switch (severity) {
    case "major":
      return "Major";
    case "moderate":
      return "Moderate";
    case "minor":
      return "Minor";
    default:
      return "Unknown";
  }
}

export function DrugAlertCard({
  alert,
  onDismissAcknowledge,
  isStreaming = false,
  className = "",
}: DrugAlertCardProps): JSX.Element {
  const styles = getSeverityStyles(alert.severity);
  const severityLabel = getSeverityLabel(alert.severity);

  return (
    <Card
      className={cn(
        "border-l-4 shadow-md relative overflow-hidden",
        className
      )}
      style={{
        borderLeftColor: styles.borderColor,
        backgroundColor: styles.bgColor,
        zIndex: parseInt(tokens.zIndex.alert, 10),
      }}
      role="alert"
      aria-live={styles.ariaLive}
      aria-label={`${severityLabel} drug alert: ${alert.description}`}
    >
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-sm">
            <span style={{ color: styles.textColor }}>{styles.icon}</span>
            <span className="text-clinical-text-primary">
              {severityLabel} Interaction
            </span>
          </CardTitle>
          <div className="flex items-center gap-2">
            <Badge variant={styles.badgeVariant} className="text-xs">
              {alert.source}
            </Badge>
            {onDismissAcknowledge && (
              <button
                type="button"
                onClick={onDismissAcknowledge}
                className="text-clinical-text-muted hover:text-clinical-text-primary transition-colors"
                aria-label="Acknowledge alert"
              >
                <CheckCircle className="w-4 h-4" aria-hidden="true" />
              </button>
            )}
          </div>
        </div>
      </CardHeader>

      <CardContent className="py-2">
        {isStreaming ? (
          <div className="space-y-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-3/4" />
          </div>
        ) : (
          <p
            className="text-sm leading-normal"
            style={{ color: tokens.color.text.clinical }}
          >
            {alert.description}
          </p>
        )}
      </CardContent>

      <CardFooter className="pt-2 border-t border-clinical-border-default">
        <div className="flex items-center justify-between w-full">
          <Badge variant="outline" className="text-xs">
            Level {alert.evidence_level} Evidence
          </Badge>
        </div>
      </CardFooter>
    </Card>
  );
}
