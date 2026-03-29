// src/components/shell/ClinicalSidebar.tsx
import { ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";
import type { PatientProfile } from "@/types/cdss";

export interface ClinicalSidebarProps {
  patient: PatientProfile | null;
  isLoading?: boolean;
  className?: string;
}

interface SectionProps {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  defaultOpen?: boolean;
}

function Section({ title, icon, children, defaultOpen = true }: SectionProps): JSX.Element {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <div className="border-b border-clinical-border-default last:border-b-0">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-clinical-surface-secondary transition-colors"
        aria-expanded={isOpen}
      >
        <div className="flex items-center gap-2">
          <span className="text-clinical-text-muted" aria-hidden="true">{icon}</span>
          <span className="text-sm font-medium text-clinical-text-primary">{title}</span>
        </div>
        {isOpen ? (
          <ChevronDown className="w-4 h-4 text-clinical-text-muted" aria-hidden="true" />
        ) : (
          <ChevronRight className="w-4 h-4 text-clinical-text-muted" aria-hidden="true" />
        )}
      </button>
      {isOpen && <div className="px-4 pb-3">{children}</div>}
    </div>
  );
}

function formatBloodType(bt: string): string {
  return bt.toUpperCase();
}

function calculateBMI(weightKg: number, heightCm: number): string {
  const heightM = heightCm / 100;
  const bmi = weightKg / (heightM * heightM);
  return bmi.toFixed(1);
}

export function ClinicalSidebar({
  patient,
  isLoading = false,
  className = "",
}: ClinicalSidebarProps): JSX.Element {
  if (isLoading) {
    return (
      <aside
        className={`
          w-[280px] flex-shrink-0
          border-r border-clinical-border-default
          bg-clinical-surface-primary
          overflow-y-auto
          ${className}
        `}
        aria-label="Patient context sidebar"
        aria-busy="true"
      >
        <div className="p-4 space-y-4">
          <div className="h-8 bg-clinical-surface-secondary animate-pulse rounded" />
          <div className="h-24 bg-clinical-surface-secondary animate-pulse rounded" />
          <div className="h-16 bg-clinical-surface-secondary animate-pulse rounded" />
        </div>
      </aside>
    );
  }

  if (!patient) {
    return (
      <aside
        className={`
          w-[280px] flex-shrink-0
          border-r border-clinical-border-default
          bg-clinical-surface-primary
          flex items-center justify-center
          ${className}
        `}
        aria-label="Patient context sidebar"
      >
        <p className="text-sm text-clinical-text-muted px-4 text-center">
          No patient selected. Search or select a patient to view their clinical context.
        </p>
      </aside>
    );
  }

  const { demographics, active_conditions, active_medications, allergies, recent_labs } = patient;

  return (
    <aside
      className={`
        w-[280px] flex-shrink-0
        border-r border-clinical-border-default
        bg-clinical-surface-primary
        overflow-y-auto
        ${className}
      `}
      aria-label="Patient context sidebar"
    >
      {/* Demographics Header */}
      <div className="p-4 border-b border-clinical-border-default bg-clinical-surface-secondary">
        <div className="flex items-center gap-3">
          <div
            className="w-10 h-10 rounded-full bg-clinical-agent-patientHistory/20 flex items-center justify-center"
            aria-hidden="true"
          >
            <span className="text-lg font-semibold text-clinical-agent-patientHistory">
              {demographics.sex === "M" ? "♂" : demographics.sex === "F" ? "♀" : "◯"}
            </span>
          </div>
          <div>
            <p className="text-sm font-semibold text-clinical-text-primary">
              {demographics.age} y/o {demographics.sex === "M" ? "Male" : demographics.sex === "F" ? "Female" : "Patient"}
            </p>
            <p className="text-caption text-clinical-text-muted">
              {calculateBMI(demographics.weight_kg, demographics.height_cm)} kg/m² • {formatBloodType(demographics.blood_type)}
            </p>
          </div>
        </div>
      </div>

      {/* Scrollable Sections */}
      <div className="flex-1 overflow-y-auto">
        {/* Active Conditions */}
        <Section
          title={`Conditions (${active_conditions.length})`}
          icon={<span className="text-clinical-alert-critical">●</span>}
          defaultOpen={true}
        >
          {active_conditions.length === 0 ? (
            <p className="text-caption text-clinical-text-muted">No active conditions</p>
          ) : (
            <ul className="space-y-1.5" role="list">
              {active_conditions.slice(0, 5).map((condition, index) => (
                <li
                  key={`${condition.code}-${index}`}
                  className="text-body2 text-clinical-text-clinical"
                >
                  <span className="font-medium">{condition.display}</span>
                  <span className="text-caption text-clinical-text-muted ml-1">
                    ({condition.code})
                  </span>
                </li>
              ))}
              {active_conditions.length > 5 && (
                <li className="text-caption text-clinical-text-muted">
                  +{active_conditions.length - 5} more
                </li>
              )}
            </ul>
          )}
        </Section>

        {/* Active Medications */}
        <Section
          title={`Medications (${active_medications.length})`}
          icon={<span className="text-clinical-agent-synthesis">●</span>}
          defaultOpen={true}
        >
          {active_medications.length === 0 ? (
            <p className="text-caption text-clinical-text-muted">No active medications</p>
          ) : (
            <ul className="space-y-1.5" role="list">
              {active_medications.slice(0, 5).map((med, index) => (
                <li
                  key={`${med.rxcui}-${index}`}
                  className="text-body2 text-clinical-text-clinical"
                >
                  <span className="font-medium">{med.name}</span>
                  <span className="text-caption text-clinical-text-secondary ml-1">
                    {med.dose} {med.frequency}
                  </span>
                </li>
              ))}
              {active_medications.length > 5 && (
                <li className="text-caption text-clinical-text-muted">
                  +{active_medications.length - 5} more
                </li>
              )}
            </ul>
          )}
        </Section>

        {/* Allergies */}
        <Section
          title={`Allergies (${allergies.length})`}
          icon={<span className="text-clinical-alert-high">●</span>}
          defaultOpen={true}
        >
          {allergies.length === 0 ? (
            <p className="text-caption text-clinical-text-muted">No known allergies</p>
          ) : (
            <ul className="space-y-1.5" role="list">
              {allergies.map((allergy, index) => (
                <li
                  key={`${allergy.code}-${index}`}
                  className="flex items-center gap-2"
                >
                  <span
                    className={`
                      text-caption px-1.5 py-0.5 rounded
                      ${allergy.severity === "severe"
                        ? "bg-clinical-alert-critical/20 text-clinical-alert-critical"
                        : allergy.severity === "moderate"
                        ? "bg-clinical-alert-high/20 text-clinical-alert-high"
                        : "bg-clinical-alert-moderate/20 text-clinical-alert-moderate"
                      }
                    `}
                  >
                    {allergy.severity}
                  </span>
                  <span className="text-body2 text-clinical-text-clinical">
                    {allergy.substance}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Section>

        {/* Recent Labs */}
        <Section
          title={`Recent Labs (${recent_labs.length})`}
          icon={<span className="text-clinical-agent-literature">●</span>}
          defaultOpen={false}
        >
          {recent_labs.length === 0 ? (
            <p className="text-caption text-clinical-text-muted">No recent lab results</p>
          ) : (
            <ul className="space-y-1.5" role="list">
              {recent_labs.slice(0, 4).map((lab, index) => (
                <li
                  key={`${lab.code}-${index}`}
                  className="text-body2 text-clinical-text-clinical flex justify-between"
                >
                  <span>{lab.display}</span>
                  <span className="text-clinical-text-secondary">
                    {lab.value} {lab.unit}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>
    </aside>
  );
}
