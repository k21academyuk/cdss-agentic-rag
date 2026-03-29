import React, { useState } from 'react';
import {
  Box,
  Typography,
  Paper,
  List,
  ListItem,
  ListItemText,
  ListItemButton,
  Chip,
  IconButton,
  Collapse,
  Divider,
  Alert,
  useTheme,
  alpha,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import MedicationIcon from '@mui/icons-material/Medication';
import { Medication, DrugInteraction } from '@/lib/types';

interface MedicationListProps {
  medications: Medication[];
  interactions?: DrugInteraction[];
  title?: string;
}

interface MedicationWithInteractions extends Medication {
  interactions: DrugInteraction[];
}

export default function MedicationList({
  medications,
  interactions = [],
  title = 'Active Medications',
}: MedicationListProps) {
  const theme = useTheme();
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const medicationsWithInteractions: MedicationWithInteractions[] = medications.map(
    (med) => ({
      ...med,
      interactions: interactions.filter(
        (int) => int.drug_a === med.name || int.drug_b === med.name
      ),
    })
  );

  const getSeverityColor = (severity: 'minor' | 'moderate' | 'major') => {
    switch (severity) {
      case 'major':
        return theme.palette.error.main;
      case 'moderate':
        return theme.palette.warning.main;
      case 'minor':
        return theme.palette.info.main;
      default:
        return theme.palette.grey[500];
    }
  };

  const handleToggle = (rxcui: string) => {
    setExpandedId(expandedId === rxcui ? null : rxcui);
  };

  if (!medications || medications.length === 0) {
    return (
      <Paper sx={{ p: 3 }}>
        <Typography variant="h6" gutterBottom fontWeight={600}>
          {title}
        </Typography>
        <Alert severity="info">No active medications on file.</Alert>
      </Paper>
    );
  }

  return (
    <Paper sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
        <MedicationIcon sx={{ mr: 1, color: theme.palette.primary.main }} />
        <Typography variant="h6" fontWeight={600}>
          {title}
        </Typography>
        <Chip
          label={`${medications.length} total`}
          size="small"
          sx={{ ml: 2 }}
        />
      </Box>

      <List disablePadding>
        {medicationsWithInteractions.map((med, index) => {
          const isExpanded = expandedId === med.rxcui;
          const hasInteractions = med.interactions.length > 0;
          const hasMajorInteraction = med.interactions.some(
            (i) => i.severity === 'major'
          );
          const hasModerateInteraction = med.interactions.some(
            (i) => i.severity === 'moderate'
          );

          return (
            <Box key={med.rxcui}>
              {index > 0 && <Divider />}
              <ListItem
                disablePadding
                secondaryAction={
                  <IconButton
                    edge="end"
                    aria-label={isExpanded ? 'collapse' : 'expand'}
                    onClick={() => handleToggle(med.rxcui)}
                  >
                    {isExpanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                  </IconButton>
                }
              >
                <ListItemButton onClick={() => handleToggle(med.rxcui)}>
                  <ListItemText
                    primary={
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Typography variant="subtitle1" fontWeight={600}>
                          {med.name}
                        </Typography>
                        {hasMajorInteraction && (
                          <Chip
                            label="Major Interaction"
                            size="small"
                            color="error"
                          />
                        )}
                        {!hasMajorInteraction && hasModerateInteraction && (
                          <Chip
                            label="Moderate Interaction"
                            size="small"
                            color="warning"
                          />
                        )}
                        {hasInteractions &&
                          !hasMajorInteraction &&
                          !hasModerateInteraction && (
                            <Chip
                              label="Minor Interaction"
                              size="small"
                              color="info"
                            />
                          )}
                      </Box>
                    }
                    secondary={
                      <Typography variant="body2" color="text.secondary">
                        {med.dose} • {med.frequency}
                      </Typography>
                    }
                  />
                </ListItemButton>
              </ListItem>

              <Collapse in={isExpanded} timeout="auto" unmountOnExit>
                <Box sx={{ px: 2, pb: 2 }}>
                  {med.start_date && (
                    <Box sx={{ mb: 1 }}>
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        fontWeight={600}
                      >
                        Started:{' '}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {new Date(med.start_date).toLocaleDateString()}
                      </Typography>
                    </Box>
                  )}

                  {med.prescriber && (
                    <Box sx={{ mb: 1 }}>
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        fontWeight={600}
                      >
                        Prescriber:{' '}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {med.prescriber}
                      </Typography>
                    </Box>
                  )}

                  <Box sx={{ mb: 1 }}>
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      fontWeight={600}
                    >
                      RxCUI:{' '}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {med.rxcui}
                    </Typography>
                  </Box>

                  {hasInteractions && (
                    <Box sx={{ mt: 2 }}>
                      <Typography
                        variant="subtitle2"
                        color="text.secondary"
                        gutterBottom
                      >
                        Drug Interactions
                      </Typography>
                      {med.interactions.map((interaction, i) => (
                        <Box
                          key={i}
                          sx={{
                            p: 1.5,
                            mb: 1,
                            borderRadius: 1,
                            backgroundColor: alpha(
                              getSeverityColor(interaction.severity),
                              0.1
                            ),
                            borderLeft: `3px solid ${getSeverityColor(
                              interaction.severity
                            )}`,
                          }}
                        >
                          <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
                            <Chip
                              label={interaction.severity.toUpperCase()}
                              size="small"
                              sx={{
                                backgroundColor: getSeverityColor(
                                  interaction.severity
                                ),
                                color: theme.palette.getContrastText(
                                  getSeverityColor(interaction.severity)
                                ),
                                fontWeight: 600,
                                mr: 1,
                              }}
                            />
                            <Typography variant="body2" fontWeight={600}>
                              {interaction.drug_a === med.name
                                ? interaction.drug_b
                                : interaction.drug_a}
                            </Typography>
                          </Box>
                          <Typography variant="body2" color="text.secondary">
                            {interaction.description}
                          </Typography>
                          {interaction.clinical_significance && (
                            <Typography
                              variant="caption"
                              display="block"
                              sx={{ mt: 0.5, fontStyle: 'italic' }}
                            >
                              {interaction.clinical_significance}
                            </Typography>
                          )}
                        </Box>
                      ))}
                    </Box>
                  )}

                  {!hasInteractions && (
                    <Alert severity="success" sx={{ mt: 1 }}>
                      No known interactions detected
                    </Alert>
                  )}
                </Box>
              </Collapse>
            </Box>
          );
        })}
      </List>
    </Paper>
  );
}
