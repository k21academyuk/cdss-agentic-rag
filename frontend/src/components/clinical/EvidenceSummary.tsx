import React, { useState } from 'react';
import {
  Box,
  Typography,
  Chip,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Paper,
  useTheme,
} from '@mui/material';
import {
  ExpandMore,
  Science,
  LocalHospital,
  Person,
  Medication,
  Description,
} from '@mui/icons-material';
import { clinicalColors } from '@/theme/clinical';

type EvidenceGrade = 'A' | 'B' | 'C' | 'D' | 'expert_opinion';
type SourceType = 'pubmed' | 'guideline' | 'patient_record' | 'drug_database';

interface EvidenceItem {
  title: string;
  source_type: SourceType;
  grade: EvidenceGrade;
  summary: string;
  relevance_score: number;
  source_count?: number;
  url?: string;
}

interface EvidenceSummaryProps {
  evidence: EvidenceItem[];
  className?: string;
}

const gradeConfig: Record<EvidenceGrade, { label: string; color: string; description: string }> = {
  A: {
    label: 'A',
    color: clinicalColors.evidence.gradeA.main,
    description: 'High-quality evidence from systematic reviews',
  },
  B: {
    label: 'B',
    color: clinicalColors.evidence.gradeB.main,
    description: 'Moderate-quality evidence from RCTs or cohort studies',
  },
  C: {
    label: 'C',
    color: clinicalColors.evidence.gradeC.main,
    description: 'Low-quality evidence from case series or retrospective',
  },
  D: {
    label: 'D',
    color: clinicalColors.evidence.gradeD.main,
    description: 'Very low-quality evidence from case series or expert opinion',
  },
  expert_opinion: {
    label: 'Expert Opinion',
    color: clinicalColors.evidence.expert.main,
    description: 'Expert consensus without RCTs',
  },
};

const getGradeInfo = (grade: EvidenceGrade) => {
  return gradeConfig[grade];
};

const GradeChip: React.FC<{ grade: EvidenceGrade }> = ({ grade }) => {
  const theme = useTheme();
  const config = getGradeInfo(grade);
  const isDark = theme.palette.mode === 'dark';

  return (
    <Chip
      label={config.label}
      size="small"
      sx={{
        height: 24,
        fontSize: 11,
        fontWeight: 600,
        backgroundColor: isDark ? 'rgba(255,255,255,0.15)' : config.color,
        color: isDark ? config.color : 'white',
      }}
    />
  );
};

const SourceTypeIcon: React.FC<{ sourceType: SourceType }> = ({ sourceType }) => {
  switch (sourceType) {
    case 'pubmed':
      return <Science fontSize="small" sx={{ color: clinicalColors.sourceType.pubmed }} />;
    case 'guideline':
      return <LocalHospital fontSize="small" sx={{ color: clinicalColors.sourceType.guideline }} />;
    case 'patient_record':
      return <Person fontSize="small" sx={{ color: clinicalColors.sourceType.patient_record }} />;
    case 'drug_database':
      return <Medication fontSize="small" sx={{ color: clinicalColors.sourceType.drug_database }} />;
    default:
      return <Description fontSize="small" />;
  }
};

export default function EvidenceSummary({
  evidence,
  className,
}: EvidenceSummaryProps) {
  const theme = useTheme();
  const isDark = theme.palette.mode === 'dark';

  if (evidence.length === 0) {
    return (
      <Paper sx={{ p: 2, mb: 2 }} className={className}>
        <Typography variant="subtitle2" color="text.secondary" sx={{ textAlign: 'center', py: 2 }}>
          No evidence available
        </Typography>
      </Paper>
    );
  }

  return (
    <Paper sx={{ mb: 2 }} className={className}>
      {evidence.map((item, index) => (
        <Accordion
          key={index}
          sx={{
            backgroundColor: 'background.paper',
            '&:before': {
              display: 'none',
            },
            '&.Mui-expanded': {
              backgroundColor: 'action.selected',
            },
            borderBottom: '1px solid',
            borderColor: 'divider',
          }}
        >
          <AccordionSummary
            expandIcon={<ExpandMore />}
            sx={{
              display: 'flex',
              alignItems: 'center',
              gap: 1,
              py: 0.5,
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <SourceTypeIcon sourceType={item.source_type} />
              <Typography
                variant="body2"
                sx={{
                  fontWeight: 500,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {item.title}
              </Typography>
              <GradeChip grade={item.grade} />
              {item.source_count !== undefined && (
                <Chip
                  label={`${item.source_count} sources`}
                  size="small"
                  sx={{ height: 20 }}
                />
              )}
            </Box>
          </AccordionSummary>
          <AccordionDetails sx={{ pt: 1.5, pb: 2 }}>
            <Typography variant="body2" color="text.secondary" gutterBottom>
              Summary
            </Typography>
            <Typography variant="body2">{item.summary}</Typography>

            {item.relevance_score !== undefined && (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 1 }}>
                <Typography variant="caption" color="text.secondary">
                  Relevance:
                </Typography>
                <Box
                  sx={{
                    width: 80,
                    height: 6,
                    borderRadius: 0.5,
                    backgroundColor: isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)',
                    overflow: 'hidden',
                  }}
                >
                  <Box
                    sx={{
                      width: `${item.relevance_score * 100}%`,
                      height: 6,
                      borderRadius: 0.5,
                      backgroundColor: isDark ? '#4caf50' : '#2e7d32',
                      transition: 'width 0.3s ease-out',
                    }}
                  />
                </Box>
                <Typography variant="caption" fontWeight={500}>
                  {Math.round(item.relevance_score * 100)}%
                </Typography>
              </Box>
            )}
          </AccordionDetails>
        </Accordion>
      ))}
    </Paper>
  );
}

export { EvidenceSummary };
export type { EvidenceSummaryProps, EvidenceItem, EvidenceGrade, SourceType };
