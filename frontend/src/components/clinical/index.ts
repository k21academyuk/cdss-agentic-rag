// New shadcn/ui-based clinical components
export { DrugAlertCard } from "./DrugAlertCard";
export type { DrugAlertCardProps } from "./DrugAlertCard";

export { ConfidenceScoreBadge } from "./ConfidenceScoreBadge";
export type { ConfidenceScoreBadgeProps } from "./ConfidenceScoreBadge";

export { CitationAccordion } from "./CitationAccordion";
export type { CitationAccordionProps } from "./CitationAccordion";

// Legacy components (to be migrated)
export { default as ConfidenceIndicator } from './ConfidenceIndicator';
export { default as CitationCard } from './Citation';
export { default as DrugAlertBanner } from './DrugAlertBanner';
export { default as ResponseViewer } from './ResponseViewer';
export { default as AgentStatusCard, type AgentStatusCardProps, type AgentStatus } from './AgentStatusCard';
export { default as EvidenceSummary } from './EvidenceSummary';
