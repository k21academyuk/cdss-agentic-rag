// src/components/shell/AppShell.tsx
import type { ReactNode } from "react";
import { HeaderBar } from "./HeaderBar";
import { ClinicalSidebar } from "./ClinicalSidebar";
import type { PatientProfile } from "@/types/cdss";

export interface AppShellProps {
  children: ReactNode;
  sessionId: string | null;
  patientId: string | null;
  patient: PatientProfile | null;
  clinicianName: string;
  isPatientLoading?: boolean;
  synthesisPanel?: ReactNode;
  className?: string;
}

export function AppShell({
  children,
  sessionId,
  patientId,
  patient,
  clinicianName,
  isPatientLoading = false,
  synthesisPanel,
  className = "",
}: AppShellProps): JSX.Element {
  return (
    <div
      className={`
        flex flex-col h-screen w-screen overflow-hidden
        bg-clinical-surface-secondary
        ${className}
      `}
    >
      {/* Fixed Header */}
      <HeaderBar
        sessionId={sessionId}
        patientId={patientId}
        clinicianName={clinicianName}
      />

      {/* Main Layout: Sidebar + Content */}
      <div className="flex flex-1 overflow-hidden">
        {/* Collapsible Patient Sidebar */}
        <ClinicalSidebar
          patient={patient}
          isLoading={isPatientLoading}
        />

        {/* Main Content Area */}
        <main
          className="flex-1 flex flex-col overflow-hidden"
          role="main"
          aria-label="Clinical decision support content"
        >
          {/* Agent Panels Grid */}
          <div
            className={`
              flex-1 overflow-y-auto p-panelGap
              grid gap-panelGap
              grid-cols-1
              md:grid-cols-2
              lg:grid-cols-2
              xl:grid-cols-2
              2xl:grid-cols-2
            `}
            style={{
              gridAutoRows: "minmax(300px, 1fr)",
            }}
          >
            {children}
          </div>

          {/* Synthesis Panel - Full Width Below Grid */}
          {synthesisPanel && (
            <div
              className={`
                flex-shrink-0 border-t border-clinical-border-default
                bg-clinical-surface-primary
                max-h-[40vh] overflow-y-auto
              `}
            >
              {synthesisPanel}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
