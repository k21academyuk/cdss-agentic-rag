import React from 'react';
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  Grid,
  LinearProgress,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Skeleton,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import {
  AutoAwesome,
  Cancel,
  CheckCircle,
  ContentPasteSearch,
  Description,
  ErrorOutline,
  FactCheck,
  LocalHospital,
  Medication,
  PendingActions,
  PlayArrow,
  Psychology,
  Refresh,
  Search,
  Science,
  Send,
  WarningAmber,
} from '@mui/icons-material';
import { usePatientSearch, useSelectedPatient, useSetSelectedPatient } from '@/hooks/usePatientData';
import { StreamingTimelineEvent, useStreamingQuery } from '@/hooks/useStreamingQuery';
import { Citation, PatientProfile } from '@/lib/types';
import CitationCard from '@/components/clinical/Citation';
import ConfidenceIndicator from '@/components/clinical/ConfidenceIndicator';
import DrugAlertBanner from '@/components/clinical/DrugAlertBanner';
import { alpha as alphaUtil, borderRadius, componentShadows, semantic, severity, spacing, transitions } from '@/theme';

interface QueryPreset {
  label: string;
  text: string;
}

const QUERY_PRESETS: QueryPreset[] = [
  {
    label: 'T2DM + CKD Treatment',
    text: 'What are the recommended treatment options for type 2 diabetes with CKD in this patient?',
  },
  {
    label: 'Drug Interaction Review',
    text: 'Check for potential interactions and contraindications in this medication regimen.',
  },
  {
    label: 'Differential Diagnosis',
    text: 'What are likely differential diagnoses based on current symptoms and latest labs?',
  },
  {
    label: 'Guideline Conformance',
    text: 'Does the current care plan align with current guidelines and what should be updated?',
  },
];

function eventTypeLabel(event: StreamingTimelineEvent): string {
  switch (event.type) {
    case 'stream_start':
      return 'Stream started';
    case 'agent_start':
      return `${event.agent ?? 'Agent'} started`;
    case 'agent_progress':
      return `${event.agent ?? 'Agent'} progress`;
    case 'agent_complete':
      return `${event.agent ?? 'Agent'} completed`;
    case 'synthesis_start':
      return 'Synthesis started';
    case 'synthesis_complete':
      return 'Synthesis complete';
    case 'validation_start':
      return 'Guardrails validation started';
    case 'validation_complete':
      return 'Guardrails validation complete';
    case 'cancelled':
      return 'Cancelled';
    case 'stream_error':
      return 'Stream error';
    case 'error':
      return 'Agent error';
    default:
      return event.type;
  }
}

function eventIcon(event: StreamingTimelineEvent) {
  switch (event.type) {
    case 'agent_start':
      return <PlayArrow fontSize="small" />;
    case 'agent_progress':
      return <PendingActions fontSize="small" />;
    case 'agent_complete':
    case 'synthesis_complete':
    case 'validation_complete':
      return <CheckCircle fontSize="small" />;
    case 'error':
    case 'stream_error':
      return <ErrorOutline fontSize="small" />;
    case 'cancelled':
      return <Cancel fontSize="small" />;
    case 'validation_start':
      return <FactCheck fontSize="small" />;
    case 'synthesis_start':
      return <AutoAwesome fontSize="small" />;
    default:
      return <Psychology fontSize="small" />;
  }
}

function eventColor(event: StreamingTimelineEvent): string {
  if (event.level === 'error') return semantic.error.main;
  if (event.level === 'warning') return semantic.warning.main;
  if (event.level === 'success') return semantic.success.main;
  return semantic.info.main;
}

function confidenceRationale(
  confidenceScore: number,
  citationsCount: number,
  evidenceCount: number,
  drugAlertsCount: number
): string {
  const level = confidenceScore >= 0.8 ? 'high' : confidenceScore >= 0.6 ? 'moderate' : 'low';
  if (level === 'high') {
    return `${citationsCount} citations and ${evidenceCount} evidence items support this recommendation.`;
  }
  if (level === 'moderate') {
    return `Evidence is usable but mixed. Review ${drugAlertsCount} active alert(s) before final action.`;
  }
  return `Low confidence due to limited evidence support and/or conflicting safety signals.`;
}

function SectionCard({ title, children, stickyTop }: { title: string; children: React.ReactNode; stickyTop?: number }) {
  return (
    <Card
      sx={{
        borderRadius: borderRadius.md,
        boxShadow: componentShadows.card,
        ...(stickyTop !== undefined && {
          position: 'sticky',
          top: stickyTop,
          zIndex: 2,
        }),
      }}
    >
      <CardContent sx={{ p: spacing[4] }}>
        <Typography variant="h6" sx={{ mb: 1.5 }}>
          {title}
        </Typography>
        {children}
      </CardContent>
    </Card>
  );
}

function ProgressiveResultSkeleton() {
  return (
    <Stack spacing={2}>
      {['Assessment', 'Recommendation', 'Evidence Summary', 'Citations', 'Drug Alerts', 'Guardrails', 'Disclaimers'].map(
        (section) => (
          <Card key={section}>
            <CardContent>
              <Skeleton width={220} height={30} />
              <Skeleton width="100%" height={22} />
              <Skeleton width="90%" height={22} />
              <Skeleton width="75%" height={22} />
            </CardContent>
          </Card>
        )
      )}
    </Stack>
  );
}

function EmptyResultState() {
  return (
    <Card>
      <CardContent sx={{ textAlign: 'center', py: spacing[8] }}>
        <ContentPasteSearch sx={{ fontSize: 42, color: 'text.disabled', mb: 1 }} />
        <Typography variant="h6" sx={{ mb: 0.5 }}>
          No clinical result yet
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Select a patient context, compose a query, and start streaming orchestration.
        </Typography>
      </CardContent>
    </Card>
  );
}

function CitationProvenanceSummary({ citations }: { citations: Citation[] }) {
  const counts = citations.reduce<Record<string, number>>((acc, citation) => {
    acc[citation.source_type] = (acc[citation.source_type] || 0) + 1;
    return acc;
  }, {});

  return (
    <Stack direction="row" spacing={1} sx={{ mb: 1.5, flexWrap: 'wrap', rowGap: 1 }}>
      {Object.entries(counts).map(([sourceType, count]) => (
        <Chip
          key={sourceType}
          size="small"
          label={`${sourceType.replace(/_/g, ' ')}: ${count}`}
          sx={{
            textTransform: 'capitalize',
            bgcolor: alphaUtil(semantic.info.main, 0.1),
            color: semantic.info.dark,
            fontWeight: 600,
          }}
        />
      ))}
    </Stack>
  );
}

export default function QueryPage() {
  const [query, setQuery] = React.useState('');
  const [patientSearch, setPatientSearch] = React.useState('');
  const [revealed, setRevealed] = React.useState(false);

  React.useEffect(() => {
    const id = window.setTimeout(() => setRevealed(true), 40);
    return () => window.clearTimeout(id);
  }, []);

  const selectedPatient = useSelectedPatient();
  const setSelectedPatient = useSetSelectedPatient();
  const patientId = selectedPatient.selectedPatientId || undefined;
  const snapshotPatient = selectedPatient.selectedPatient;
  const snapshotDemographics = snapshotPatient?.demographics;
  const snapshotConditionsCount = Array.isArray(snapshotPatient?.active_conditions)
    ? snapshotPatient.active_conditions.length
    : 0;
  const snapshotMedicationsCount = Array.isArray(snapshotPatient?.active_medications)
    ? snapshotPatient.active_medications.length
    : 0;
  const snapshotAllergiesCount = Array.isArray(snapshotPatient?.allergies)
    ? snapshotPatient.allergies.length
    : 0;
  const snapshotLabsCount = Array.isArray(snapshotPatient?.recent_labs)
    ? snapshotPatient.recent_labs.length
    : 0;

  const { data: patientSearchResults, isLoading: searchingPatients } = usePatientSearch(patientSearch);
  const {
    response,
    isStreaming,
    progress,
    agentProgress,
    error,
    status,
    timeline,
    failedAgents,
    lastMessage,
    startStream,
    cancelStream,
    reset,
  } = useStreamingQuery(query, patientId);

  const handleSubmit = () => {
    if (!query.trim()) return;
    startStream();
  };

  const handleRetry = () => {
    if (!query.trim()) return;
    startStream();
  };

  const handlePreset = (preset: QueryPreset) => {
    setQuery(preset.text);
  };

  const evidenceItems = response?.evidence_summary || [];
  const citationItems = response?.citations || [];
  const drugAlerts = response?.drug_alerts || [];
  const guardrailSummary = response?.agent_outputs?.guardrails?.summary;
  const guardrailLatency = response?.agent_outputs?.guardrails?.latency_ms;
  const confidenceScore = response?.confidence_score || 0;

  const showPartialFailure = status === 'partial_failure' || (failedAgents.length > 0 && !!response);
  const showFatalError = status === 'error' && !response;
  const showCancelled = status === 'cancelled';
  const showStreaming = status === 'streaming' || isStreaming;
  const hasTimeline = timeline.length > 0;

  return (
    <Box
      sx={{
        opacity: revealed ? 1 : 0,
        transform: revealed ? 'translateY(0px)' : 'translateY(8px)',
        transition: `${transitions.fade.standard}, ${transitions.transform.standard}`,
      }}
    >
      <Box sx={{ mb: spacing[4] }}>
        <Typography variant="h4" sx={{ mb: 0.5 }}>
          Clinical Workspace
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Compose, orchestrate, and review a complete clinical decision support response.
        </Typography>
      </Box>

      <Grid container spacing={2}>
        {/* LEFT PANEL */}
        <Grid item xs={12} lg={3}>
          <SectionCard title="Patient + Query Composer">
            <Autocomplete
              options={patientSearchResults?.patients || []}
              getOptionLabel={(option: PatientProfile) => `Patient ${option.patient_id}`}
              loading={searchingPatients}
              onInputChange={(_, value) => setPatientSearch(value)}
              onChange={(_, value) => setSelectedPatient(value)}
              value={selectedPatient.selectedPatient}
              renderInput={(params) => (
                <TextField
                  {...params}
                  label="Patient Picker"
                  placeholder="Type patient id..."
                  InputProps={{
                    ...params.InputProps,
                    startAdornment: (
                      <>
                        <Search fontSize="small" style={{ marginRight: 6 }} />
                        {params.InputProps.startAdornment}
                      </>
                    ),
                  }}
                />
              )}
              sx={{ mb: 2 }}
            />

            {selectedPatient.selectedPatient && (
              <Chip
                size="small"
                label={`Selected: ${selectedPatient.selectedPatient.patient_id}`}
                sx={{
                  mb: 2,
                  bgcolor: alphaUtil(semantic.success.main, 0.12),
                  color: semantic.success.dark,
                  fontWeight: 600,
                }}
              />
            )}

            <TextField
              fullWidth
              multiline
              rows={7}
              label="Clinical Query"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Ask a focused clinical question..."
              disabled={isStreaming}
              sx={{ mb: 2 }}
            />

            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              Presets
            </Typography>
            <Stack spacing={1} sx={{ mb: 2 }}>
              {QUERY_PRESETS.map((preset) => (
                <Button
                  key={preset.label}
                  variant="outlined"
                  onClick={() => handlePreset(preset)}
                  disabled={isStreaming}
                  sx={{
                    justifyContent: 'flex-start',
                    textTransform: 'none',
                    borderRadius: borderRadius.sm,
                  }}
                >
                  {preset.label}
                </Button>
              ))}
            </Stack>

            <Stack direction={{ xs: 'column', sm: 'row', lg: 'column' }} spacing={1}>
              <Button
                variant="contained"
                startIcon={<Send />}
                onClick={handleSubmit}
                disabled={!query.trim() || isStreaming}
              >
                Run Orchestration
              </Button>
              <Button
                variant="outlined"
                startIcon={<Refresh />}
                onClick={handleRetry}
                disabled={!query.trim() || isStreaming}
              >
                Retry
              </Button>
              {isStreaming && (
                <Button variant="outlined" color="error" startIcon={<Cancel />} onClick={cancelStream}>
                  Cancel
                </Button>
              )}
              <Button variant="text" onClick={reset} disabled={isStreaming}>
                Clear Workspace
              </Button>
            </Stack>
          </SectionCard>
        </Grid>

        {/* CENTER PANEL */}
        <Grid item xs={12} lg={6}>
          <Stack spacing={2}>
            <SectionCard title="Streaming Orchestration Timeline">
              <Box sx={{ mb: 1 }}>
                <Typography variant="body2" color="text.secondary">
                  {lastMessage || 'Waiting to start orchestration...'}
                </Typography>
              </Box>

              {showStreaming && (
                <Box sx={{ mb: 2 }}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.6 }}>
                    <Typography variant="caption" color="text.secondary">
                      Progress
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {Math.round(progress)}%
                    </Typography>
                  </Box>
                  <LinearProgress value={progress} variant="determinate" />
                  <Stack direction="row" spacing={1} sx={{ mt: 1, flexWrap: 'wrap', rowGap: 1 }}>
                    {Object.entries(agentProgress).map(([agent, pct]) => (
                      <Chip
                        key={agent}
                        size="small"
                        label={`${agent.replace(/_/g, ' ')} ${Math.round(pct)}%`}
                        sx={{ textTransform: 'capitalize' }}
                      />
                    ))}
                  </Stack>
                </Box>
              )}

              {!hasTimeline ? (
                <Alert severity="info" variant="outlined">
                  Timeline will populate as agents start, progress, and complete.
                </Alert>
              ) : (
                <List disablePadding>
                  {timeline.map((event, index) => (
                    <ListItem
                      key={event.id}
                      disableGutters
                      sx={{
                        alignItems: 'flex-start',
                        py: 0.9,
                        borderBottom: index === timeline.length - 1 ? 'none' : '1px solid',
                        borderColor: 'divider',
                      }}
                    >
                      <ListItemIcon sx={{ minWidth: 32, mt: 0.2 }}>
                        <Box
                          sx={{
                            width: 22,
                            height: 22,
                            borderRadius: borderRadius.xs,
                            bgcolor: alphaUtil(eventColor(event), 0.14),
                            color: eventColor(event),
                            display: 'grid',
                            placeItems: 'center',
                          }}
                        >
                          {eventIcon(event)}
                        </Box>
                      </ListItemIcon>
                      <ListItemText
                        primary={
                          <Stack direction="row" spacing={1} alignItems="center" sx={{ flexWrap: 'wrap', rowGap: 0.5 }}>
                            <Typography variant="body2" sx={{ fontWeight: 600 }}>
                              {eventTypeLabel(event)}
                            </Typography>
                            {typeof event.progress === 'number' && (
                              <Chip size="small" label={`${Math.round(event.progress)}%`} sx={{ height: 20 }} />
                            )}
                            {event.agent && (
                              <Chip
                                size="small"
                                label={event.agent}
                                sx={{ textTransform: 'capitalize', height: 20 }}
                                variant="outlined"
                              />
                            )}
                          </Stack>
                        }
                        secondary={
                          event.message ? (
                            <Typography variant="caption" color="text.secondary">
                              {event.message}
                            </Typography>
                          ) : undefined
                        }
                      />
                    </ListItem>
                  ))}
                </List>
              )}
            </SectionCard>

            {showCancelled && (
              <Alert severity="warning">
                Stream cancelled. You can adjust the query and retry from the composer.
              </Alert>
            )}
            {showPartialFailure && (
              <Alert severity="warning">
                Partial failure detected{failedAgents.length > 0 ? ` in: ${failedAgents.join(', ')}` : ''}. Review
                sections below before finalizing clinical action.
              </Alert>
            )}
            {showFatalError && (
              <Alert severity="error">
                {error || 'Streaming failed before completion.'} Retry orchestration after adjusting query context.
              </Alert>
            )}

            {!response && showStreaming && <ProgressiveResultSkeleton />}
            {!response && !showStreaming && !showFatalError && <EmptyResultState />}

            {response && (
              <Stack spacing={2}>
                <Card sx={{ borderRadius: borderRadius.md, boxShadow: componentShadows.card }}>
                  <CardContent sx={{ p: spacing[4] }}>
                    <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} justifyContent="space-between">
                      <Box>
                        <Typography variant="h6" sx={{ mb: 0.6 }}>
                          Confidence
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          {confidenceRationale(
                            confidenceScore,
                            citationItems.length,
                            evidenceItems.length,
                            drugAlerts.length
                          )}
                        </Typography>
                      </Box>
                      <Box
                        sx={{
                          minWidth: 210,
                          p: 1.5,
                          borderRadius: borderRadius.sm,
                          bgcolor: alphaUtil(semantic.info.main, 0.08),
                        }}
                      >
                        <ConfidenceIndicator score={confidenceScore} size="large" showLabel />
                      </Box>
                    </Stack>
                  </CardContent>
                </Card>

                {drugAlerts.length > 0 && (
                  <Box sx={{ position: 'sticky', top: 72, zIndex: 4 }}>
                    <DrugAlertBanner alerts={drugAlerts} defaultExpanded />
                  </Box>
                )}

                <SectionCard title="Assessment">
                  <Typography variant="body1">{response.assessment}</Typography>
                </SectionCard>

                <SectionCard title="Recommendation">
                  <Typography variant="body1" sx={{ fontWeight: 500 }}>
                    {response.recommendation}
                  </Typography>
                </SectionCard>

                <SectionCard title="Evidence Summary">
                  {evidenceItems.length === 0 ? (
                    <Typography variant="body2" color="text.secondary">
                      No explicit evidence summary provided.
                    </Typography>
                  ) : (
                    <List dense disablePadding>
                      {evidenceItems.map((item, index) => (
                        <ListItem key={`${item}-${index}`} disableGutters>
                          <ListItemIcon sx={{ minWidth: 24 }}>
                            <Science sx={{ fontSize: 16, color: semantic.info.main }} />
                          </ListItemIcon>
                          <ListItemText primary={<Typography variant="body2">{item}</Typography>} />
                        </ListItem>
                      ))}
                    </List>
                  )}
                </SectionCard>

                <SectionCard title={`Citations (${citationItems.length})`}>
                  {citationItems.length === 0 ? (
                    <Typography variant="body2" color="text.secondary">
                      No citation provenance available.
                    </Typography>
                  ) : (
                    <>
                      <CitationProvenanceSummary citations={citationItems} />
                      <Stack spacing={1}>
                        {citationItems.map((citation, index) => (
                          <CitationCard key={`${citation.identifier}-${index}`} citation={citation} />
                        ))}
                      </Stack>
                    </>
                  )}
                </SectionCard>

                <SectionCard title={`Drug Alerts (${drugAlerts.length})`}>
                  {drugAlerts.length === 0 ? (
                    <Alert severity="success" variant="outlined">
                      No active drug alerts in this response.
                    </Alert>
                  ) : (
                    <DrugAlertBanner alerts={drugAlerts} defaultExpanded />
                  )}
                </SectionCard>

                <SectionCard title="Guardrails">
                  {guardrailSummary ? (
                    <Stack spacing={1}>
                      <Typography variant="body2">{guardrailSummary}</Typography>
                      <Stack direction="row" spacing={1}>
                        <Chip size="small" icon={<FactCheck />} label="Validation complete" />
                        {guardrailLatency !== undefined && (
                          <Chip size="small" label={`${guardrailLatency}ms`} variant="outlined" />
                        )}
                        {showPartialFailure && (
                          <Chip
                            size="small"
                            label="Partial failures detected"
                            sx={{
                              bgcolor: alphaUtil(semantic.warning.main, 0.12),
                              color: semantic.warning.dark,
                            }}
                          />
                        )}
                      </Stack>
                    </Stack>
                  ) : (
                    <Typography variant="body2" color="text.secondary">
                      Guardrail rationale not explicitly returned. Review timeline validation steps above.
                    </Typography>
                  )}
                </SectionCard>

                <SectionCard title="Disclaimers">
                  {response.disclaimers?.length ? (
                    <List dense disablePadding>
                      {response.disclaimers.map((disclaimer, index) => (
                        <ListItem key={`${disclaimer}-${index}`} disableGutters>
                          <ListItemIcon sx={{ minWidth: 24 }}>
                            <WarningAmber sx={{ fontSize: 16, color: severity.moderate.main }} />
                          </ListItemIcon>
                          <ListItemText
                            primary={<Typography variant="caption" sx={{ lineHeight: 1.6 }}>{disclaimer}</Typography>}
                          />
                        </ListItem>
                      ))}
                    </List>
                  ) : (
                    <Typography variant="body2" color="text.secondary">
                      No disclaimers returned.
                    </Typography>
                  )}
                </SectionCard>
              </Stack>
            )}
          </Stack>
        </Grid>

        {/* RIGHT PANEL */}
        <Grid item xs={12} lg={3}>
          <Stack spacing={2} sx={{ position: { lg: 'sticky' }, top: { lg: 76 }, alignSelf: 'flex-start' }}>
            <SectionCard title="Patient Snapshot">
              {snapshotPatient ? (
                <>
                  <Typography variant="subtitle2" sx={{ mb: 1 }}>
                    {snapshotPatient.patient_id}
                  </Typography>
                  <Stack spacing={0.6}>
                    <Typography variant="body2">
                      Age: {snapshotDemographics?.age ?? 'Unknown'}
                    </Typography>
                    <Typography variant="body2">
                      Sex: {snapshotDemographics?.sex ?? 'Unknown'}
                    </Typography>
                    <Typography variant="body2">
                      Conditions: {snapshotConditionsCount}
                    </Typography>
                    <Typography variant="body2">
                      Medications: {snapshotMedicationsCount}
                    </Typography>
                    <Typography variant="body2">
                      Allergies: {snapshotAllergiesCount}
                    </Typography>
                  </Stack>
                </>
              ) : (
                <Typography variant="body2" color="text.secondary">
                  Pick a patient to load context-aware risk and medication safety signals.
                </Typography>
              )}
            </SectionCard>

            <SectionCard title="Active Alerts + Safety Context">
              {drugAlerts.length > 0 ? (
                <DrugAlertBanner alerts={drugAlerts} defaultExpanded={false} />
              ) : (
                <Alert severity="success" variant="outlined">
                  No active medication alerts.
                </Alert>
              )}

              <Divider sx={{ my: 1.5 }} />

              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                Safety Context
              </Typography>
              <List dense disablePadding>
                <ListItem disableGutters>
                  <ListItemIcon sx={{ minWidth: 24 }}>
                    <LocalHospital sx={{ fontSize: 16 }} />
                  </ListItemIcon>
                  <ListItemText
                    primary={
                      <Typography variant="caption">
                        {selectedPatient.selectedPatient
                          ? `${snapshotLabsCount} recent lab result(s) in context`
                          : 'No patient labs loaded yet'}
                      </Typography>
                    }
                  />
                </ListItem>
                <ListItem disableGutters>
                  <ListItemIcon sx={{ minWidth: 24 }}>
                    <FactCheck sx={{ fontSize: 16 }} />
                  </ListItemIcon>
                  <ListItemText
                    primary={
                      <Typography variant="caption">
                        Guardrails: {guardrailSummary ? 'Validation summary available' : 'Pending explicit rationale'}
                      </Typography>
                    }
                  />
                </ListItem>
                <ListItem disableGutters>
                  <ListItemIcon sx={{ minWidth: 24 }}>
                    <Description sx={{ fontSize: 16 }} />
                  </ListItemIcon>
                  <ListItemText
                    primary={
                      <Typography variant="caption">
                        Citations: {citationItems.length} source(s) returned
                      </Typography>
                    }
                  />
                </ListItem>
              </List>
            </SectionCard>
          </Stack>
        </Grid>
      </Grid>

      {error && !showFatalError && (
        <Alert severity="error" sx={{ mt: 2 }}>
          {error}
        </Alert>
      )}
    </Box>
  );
}
