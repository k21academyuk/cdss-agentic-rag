import React from 'react';
import {
  Card,
  CardContent,
  Typography,
  Box,
  Chip,
  Divider,
  Paper,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Link,
  useTheme,
} from '@mui/material';
import {
  ExpandMore,
  OpenInNew,
  Science,
  CheckCircle,
  LocalHospital,
  Person,
  Medication,
  Description,
} from '@mui/icons-material';
import { ClinicalResponse } from '@/lib/types';
import { clinicalColors } from '@/theme/clinical';
import ConfidenceIndicator from './ConfidenceIndicator';
import DrugAlertBanner from './DrugAlertBanner';

interface ResponseViewerProps {
  response: ClinicalResponse;
}

export default function ResponseViewer({ response }: ResponseViewerProps) {
  const theme = useTheme();
  const isDark = theme.palette.mode === 'dark';
  const evidenceItems =
    response.evidence_summary?.length > 0
      ? response.evidence_summary
      : (response.evidence?.sources ?? []);

  const getSourceIcon = (sourceType: string) => {
    switch (sourceType) {
      case 'pubmed':
        return <Science fontSize="small" />;
      case 'guideline':
        return <LocalHospital fontSize="small" />;
      case 'drug_database':
        return <Medication fontSize="small" />;
      default:
        return <Description fontSize="small" />;
    }
  };

  return (
    <Card sx={{ mt: 3 }}>
      <CardContent>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography variant="h6" fontWeight={600}>
            Clinical Response
          </Typography>
          <ConfidenceIndicator
            score={response.confidence_score}
            showLabel
            size="medium"
          />
        </Box>

        <Paper
          variant="outlined"
          sx={{
            p: 2,
            mb: 2,
            bgcolor: isDark ? 'rgba(40,40,40,0.15)' : 'rgba(250,250,250,0.8)',
            borderRadius: 2,
          }}
        >
          <Typography variant="subtitle2" color="text.secondary" gutterBottom fontWeight={600}>
            Assessment
          </Typography>
          <Typography variant="body1">{response.assessment}</Typography>
        </Paper>

        <Paper
          variant="outlined"
          sx={{
            p: 2,
            mb: 2,
            borderLeft: `4px solid ${theme.palette.primary.main}`,
            borderRadius: 2,
          }}
        >
          <Typography variant="subtitle2" sx={{ opacity: 0.9, fontWeight: 600 }} gutterBottom>
            Recommendation
          </Typography>
          <Typography variant="body1" fontWeight={500}>
            {response.recommendation}
          </Typography>
        </Paper>

        {evidenceItems.length > 0 && (
          <Box sx={{ mb: 2 }}>
            <Typography variant="subtitle2" gutterBottom fontWeight={600}>
              Evidence Summary
            </Typography>
            <Box component="ul" sx={{ pl: 2, m: 0 }}>
              {evidenceItems.map((item, i) => (
                <Typography component="li" key={i} variant="body2" sx={{ mb: 0.5 }}>
                  {item}
                </Typography>
              ))}
            </Box>
          </Box>
        )}

        {response.citations && response.citations.length > 0 && (
          <Box sx={{ mb: 2 }}>
            <Typography variant="subtitle2" gutterBottom fontWeight={600}>
              Citations ({response.citations.length})
            </Typography>
            {response.citations.map((citation, i) => (
              <Accordion key={i} sx={{ mb: 1, borderRadius: 2, '&:before': { display: 'none' } }}>
                <AccordionSummary expandIcon={<ExpandMore />}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    {getSourceIcon(citation.source_type)}
                    <Typography variant="body2">{citation.title}</Typography>
                    <Chip label={citation.source_type} size="small" variant="outlined" />
                  </Box>
                </AccordionSummary>
                <AccordionDetails>
                  <Typography variant="body2" color="text.secondary">
                    Identifier: {citation.identifier}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Relevance: {Math.round(citation.relevance_score * 100)}%
                  </Typography>
                  {citation.url && (
                    <Link href={citation.url} target="_blank" rel="noopener" sx={{ mt: 1, display: 'block' }}>
                      View Source
                    </Link>
                  )}
                </AccordionDetails>
              </Accordion>
            ))}
          </Box>
        )}

        {response.drug_alerts && response.drug_alerts.length > 0 && (
          <Box sx={{ mb: 2 }}>
            <DrugAlertBanner alerts={response.drug_alerts} />
          </Box>
        )}

        {response.disclaimers && response.disclaimers.length > 0 && (
          <Box
            sx={{
              mt: 2,
              p: 2,
              bgcolor: isDark ? 'rgba(255,193,7,0.08)' : 'rgba(255,193,7,0.08)',
              borderRadius: 2,
              borderLeft: `3px solid ${theme.palette.warning.main}`,
            }}
          >
            <Typography variant="subtitle2" color="warning.main" gutterBottom fontWeight={600}>
              Disclaimers
            </Typography>
            {response.disclaimers.map((disclaimer, i) => (
              <Typography key={i} variant="caption" display="block" sx={{ lineHeight: 1.5, mb: 0.5 }}>
                {disclaimer}
              </Typography>
            ))}
          </Box>
        )}

        <Divider sx={{ my: 2 }} />

        <Box>
          <Typography variant="subtitle2" gutterBottom fontWeight={600}>
            Agent Outputs
          </Typography>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
            {Object.entries(response.agent_outputs || {}).map(([agent, output]) => (
              <Chip
                key={agent}
                label={`${agent.replace(/_/g, ' ').toUpperCase()}: ${(output as any)?.latency_ms || 0}ms`}
                size="small"
                variant="outlined"
                icon={<CheckCircle sx={{ width: 16, height: 16, color: clinicalColors.agent.completed.main }} />}
                sx={{ mb: 0.5 }}
              />
            ))}
          </Box>
        </Box>
      </CardContent>
    </Card>
  );
}

export { ResponseViewer };
export type { ResponseViewerProps };
