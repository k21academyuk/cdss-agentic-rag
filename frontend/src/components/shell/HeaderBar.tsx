// src/components/shell/HeaderBar.tsx
import { Clock, User, Activity } from "lucide-react";
import { DisclaimerBanner } from "./DisclaimerBanner";

export interface HeaderBarProps {
  sessionId: string | null;
  patientId: string | null;
  clinicianName: string;
  className?: string;
}

export function HeaderBar({
  sessionId,
  patientId,
  clinicianName,
  className = "",
}: HeaderBarProps): JSX.Element {
  const displaySessionId = sessionId ? `Session ${sessionId.slice(0, 8).toUpperCase()}` : "No Active Session";
  const displayPatientId = patientId ? `Patient ${patientId.slice(0, 8).toUpperCase()}` : "No Patient Selected";

  return (
    <header
      className={`
        sticky top-0 z-zindex-dropdown
        flex h-14 items-center justify-between
        border-b border-clinical-border-default
        bg-clinical-surface-primary px-6
        ${className}
      `}
      role="banner"
    >
      {/* Left Section: Session & Patient Info */}
      <div className="flex items-center gap-6">
        {/* Session Status */}
        <div className="flex items-center gap-2">
          <Activity
            className={`w-4 h-4 ${sessionId ? "text-clinical-agent-synthesis" : "text-clinical-text-muted"}`}
            aria-hidden="true"
          />
          <span className="text-sm font-medium text-clinical-text-primary">
            {displaySessionId}
          </span>
        </div>

        {/* Divider */}
        <div className="h-6 w-px bg-clinical-border-default" aria-hidden="true" />

        {/* Patient ID (de-identified) */}
        <span className="text-sm text-clinical-text-secondary">
          {displayPatientId}
        </span>
      </div>

      {/* Center Section: Disclaimer */}
      <div className="flex-1 flex justify-center">
        <DisclaimerBanner />
      </div>

      {/* Right Section: Clinician & Time */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <User className="w-4 h-4 text-clinical-text-muted" aria-hidden="true" />
          <span className="text-sm text-clinical-text-secondary">
            {clinicianName}
          </span>
        </div>
        <div className="flex items-center gap-1.5 text-xs text-clinical-text-muted">
          <Clock className="w-3.5 h-3.5" aria-hidden="true" />
          <span>{new Date().toLocaleTimeString()}</span>
        </div>
      </div>
    </header>
  );
}
