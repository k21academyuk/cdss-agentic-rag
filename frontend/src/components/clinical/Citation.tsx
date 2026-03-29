import React, { useState } from 'react';
import {
  Box,
  Typography,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Chip,
  Link,
  IconButton,
  Tooltip,
} from '@mui/material';
import {
  ExpandMore,
  OpenInNew,
  Science,
  LocalHospital,
  Description,
  Medication,
  Person,
} from '@mui/icons-material';
import { Citation } from '@/lib/types';
import { clinicalColors } from '@/theme/clinical';

interface CitationCardProps {
  citation: Citation;
  defaultExpanded?: boolean;
}

const sourceTypeConfig = {
  pubmed: {
    icon: Science,
    color: clinicalColors.sourceType.pubmed,
    label: 'PubMed',
  },
  guideline: {
    icon: LocalHospital,
    color: clinicalColors.sourceType.guideline,
    label: 'Guideline',
  },
  patient_record: {
    icon: Person,
    color: clinicalColors.sourceType.patient_record,
    label: 'Patient Record',
  },
  drug_database: {
    icon: Medication,
    color: clinicalColors.sourceType.drug_database,
    label: 'Drug Database',
  },
};

export default function CitationCard({
  citation,
  defaultExpanded = false,
}: CitationCardProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  
  const sourceConfig = sourceTypeConfig[citation.source_type] || {
    icon: Description,
    color: clinicalColors.sourceType.patient_record,
    label: citation.source_type.replace('_', ' ').toUpperCase(),
  };
  const SourceIcon = sourceConfig.icon;

  const formatIdentifier = () => {
    if (citation.identifier.startsWith('PMID:')) {
      return `PMID: ${citation.identifier}`;
    }
    if (citation.identifier.match(/^10\.\d{4,}/)) {
      return `DOI: ${citation.identifier}`;
    }
    return citation.identifier;
  };

  return (
    <Accordion
      expanded={expanded}
      onChange={(_, isExpanded) => setExpanded(isExpanded)}
      sx={{
        mb: 1,
        width: '100%',
        overflow: 'hidden',
        borderRadius: 2,
        border: '1px solid',
        borderColor: 'divider',
        '&:before': {
          display: 'none',
        },
        '&.Mui-expanded': {
          borderColor: 'primary.main',
        },
        boxShadow: '0 2px 8px rgba(0, 0, 0, 0.08)',
        transition: 'all 0.2s ease-in-out',
      }}
    >
      <AccordionSummary
        expandIcon={<ExpandMore />}
        aria-controls={`citation-${citation.identifier}-content`}
        id={`citation-${citation.identifier}-header`}
        sx={{
          px: 2,
          minHeight: 56,
          alignItems: 'flex-start',
          backgroundColor: 'background.paper',
          '& .MuiAccordionSummary-content': {
            my: 1,
            minWidth: 0,
            overflow: 'hidden',
          },
          '& .MuiAccordionSummary-content.Mui-expanded': {
            my: 1,
          },
          '&:hover': {
            backgroundColor: 'action.hover',
          },
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flex: 1, minWidth: 0 }}>
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 36,
              height: 36,
              borderRadius: 1,
              backgroundColor: sourceConfig.color,
              color: 'white',
            }}
          >
            <SourceIcon fontSize="small" />
          </Box>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography
              variant="body2"
              sx={{
                fontWeight: 500,
                lineHeight: 1.35,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                display: '-webkit-box',
                WebkitLineClamp: 2,
                WebkitBoxOrient: 'vertical',
                wordBreak: 'break-word',
              }}
            >
              {citation.title}
            </Typography>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 0.5, flexWrap: 'wrap' }}>
              <Chip
                label={sourceConfig.label}
                size="small"
                sx={{
                  height: 20,
                  fontSize: 10,
                  backgroundColor: 'transparent',
                  border: `1px solid ${sourceConfig.color}`,
                  color: sourceConfig.color,
                }}
              />
              <Chip
                label={`${Math.round(citation.relevance_score * 100)}% relevant`}
                size="small"
                color="primary"
                variant="outlined"
                sx={{ height: 20, fontSize: 10 }}
              />
            </Box>
            </Box>
          </Box>
        </AccordionSummary>
        <AccordionDetails
        id={`citation-${citation.identifier}-content`}
        sx={{
          px: 2,
          pb: 2,
          backgroundColor: 'grey.50',
        }}
      >
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
            <Typography variant="caption" color="text.secondary">
              Identifier:
            </Typography>
            <Typography variant="body2" sx={{ fontFamily: 'monospace', wordBreak: 'break-all' }}>
              {formatIdentifier()}
            </Typography>
          </Box>

          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Typography variant="caption" color="text.secondary">
              Relevance Score:
            </Typography>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
              <Box
                sx={{
                  width: 100,
                  height: 6,
                  borderRadius: 3,
                  backgroundColor: 'grey.300',
                  overflow: 'hidden',
                }}
              >
                <Box
                  sx={{
                    width: `${citation.relevance_score * 100}%`,
                    height: '100%',
                    backgroundColor: 'primary.main',
                    transition: 'width 0.3s ease-out',
                  }}
                />
              </Box>
              <Typography variant="caption" fontWeight={500}>
                {Math.round(citation.relevance_score * 100)}%
              </Typography>
            </Box>
          </Box>

          {citation.url && (
            <Box sx={{ mt: 1.5 }}>
              <Link
                href={citation.url}
                target="_blank"
                rel="noopener noreferrer"
                sx={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 0.5,
                  textDecoration: 'none',
                  color: 'primary.main',
                  '&:hover': {
                    textDecoration: 'underline',
                  },
                }}
              >
                View Source
                <OpenInNew fontSize="small" />
              </Link>
            </Box>
          )}
        </Box>
      </AccordionDetails>
    </Accordion>
  );
}

export { CitationCard };
export type { CitationCardProps };
