export const clinicalColors = {
  confidence: {
    high: {
      main: '#2e7d32',
      light: '#e8f5e9',
      dark: '#1b5e20',
    },
    moderate: {
      main: '#f9a825',
      light: '#fff8e1',
      dark: '#f57f17',
    },
    low: {
      main: '#c62828',
      light: '#ffebee',
      dark: '#b71c1c',
    },
  },
  severity: {
    major: {
      main: '#c62828',
      light: '#ffebee',
      dark: '#b71c1c',
    },
    moderate: {
      main: '#ef6c00',
      light: '#fff3e0',
      dark: '#e65100',
    },
    minor: {
      main: '#1976d2',
      light: '#e3f2fd',
      dark: '#1565c0',
    },
  },
  evidence: {
    gradeA: {
      main: '#1b5e20',
      light: '#e8f5e9',
      label: 'A',
    },
    gradeB: {
      main: '#33691e',
      light: '#f1f8e9',
      label: 'B',
    },
    gradeC: {
      main: '#827717',
      light: '#f9fbe7',
      label: 'C',
    },
    gradeD: {
      main: '#f57f17',
      light: '#fff8e1',
      label: 'D',
    },
    expert: {
      main: '#616161',
      light: '#f5f5f5',
      label: 'Expert',
    },
  },
  agent: {
    pending: {
      main: '#757575',
      light: '#fafafa',
    },
    running: {
      main: '#1976d2',
      light: '#e3f2fd',
    },
    completed: {
      main: '#2e7d32',
      light: '#e8f5e9',
    },
    error: {
      main: '#c62828',
      light: '#ffebee',
    },
  },
  sourceType: {
    pubmed: '#1565c0',
    guideline: '#2e7d32',
    patient_record: '#616161',
    drug_database: '#7b1fa2',
  },
} as const;

export const confidenceThresholds = {
  high: 0.8,
  moderate: 0.6,
} as const;

export const getConfidenceLevel = (score: number): 'high' | 'moderate' | 'low' => {
  if (score >= confidenceThresholds.high) return 'high';
  if (score >= confidenceThresholds.moderate) return 'moderate';
  return 'low';
};

export const getConfidenceColor = (score: number): string => {
  const level = getConfidenceLevel(score);
  return clinicalColors.confidence[level].main;
};

export const getConfidenceBgColor = (score: number): string => {
  const level = getConfidenceLevel(score);
  return clinicalColors.confidence[level].light;
};

export const getSeverityColor = (severity: 'major' | 'moderate' | 'minor'): string => {
  return clinicalColors.severity[severity].main;
};

export const getSeverityBgColor = (severity: 'major' | 'moderate' | 'minor'): string => {
  return clinicalColors.severity[severity].light;
};

export const getAgentStatusColor = (status: 'pending' | 'running' | 'completed' | 'error'): string => {
  return clinicalColors.agent[status].main;
};

export const getEvidenceGradeConfig = (grade: 'A' | 'B' | 'C' | 'D' | 'expert_opinion') => {
  const gradeKey = grade === 'expert_opinion' ? 'expert' : `grade${grade}` as keyof typeof clinicalColors.evidence;
  return clinicalColors.evidence[gradeKey];
};

export const clinicalSpacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
} as const;

export const clinicalTransitions = {
  fast: '150ms ease-in-out',
  normal: '250ms ease-in-out',
  slow: '350ms ease-in-out',
} as const;

export const clinicalShadows = {
  card: '0 2px 8px rgba(0, 0, 0, 0.08)',
  cardHover: '0 4px 12px rgba(0, 0, 0, 0.12)',
  alert: {
    major: '0 4px 16px rgba(198, 40, 40, 0.24)',
    moderate: '0 4px 16px rgba(239, 108, 0, 0.24)',
    minor: '0 4px 16px rgba(25, 118, 210, 0.24)',
  },
} as const;
