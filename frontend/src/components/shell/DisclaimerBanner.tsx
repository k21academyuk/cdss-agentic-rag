// src/components/shell/DisclaimerBanner.tsx
import { AlertTriangle } from "lucide-react";

export interface DisclaimerBannerProps {
  className?: string;
}

export function DisclaimerBanner({ className = "" }: DisclaimerBannerProps): JSX.Element {
  return (
    <div
      className={`
        flex items-center gap-2 px-3 py-1.5
        bg-clinical-alert-moderate/10
        border-b border-clinical-border-default
        text-clinical-text-secondary text-small
        ${className}
      `}
      role="banner"
      aria-label="Clinical decision support disclaimer"
    >
      <AlertTriangle
        className="w-3.5 h-3.5 text-clinical-alert-moderate flex-shrink-0"
        aria-hidden="true"
      />
      <span>
        <strong className="font-medium text-clinical-text-primary">Clinical decision support tool</strong>
        {" — verify with attending physician"}
      </span>
    </div>
  );
}
