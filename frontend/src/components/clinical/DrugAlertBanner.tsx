import React, { useState } from 'react';
import {
  Alert,
  AlertTitle,
  Box,
  Chip,
  Typography,
  Collapse,
  IconButton,
  Button,
} from '@mui/material';
import {
  Warning,
  Error as ErrorIcon,
  Info,
  Close,
  ExpandLess,
  ExpandMore,
  Visibility,
} from '@mui/icons-material';
import { DrugAlert } from '@/lib/types';
import { clinicalColors } from '@/theme/clinical';

type AlertSeverity = 'major' | 'moderate' | 'minor';

interface SeverityConfigType {
  icon: typeof ErrorIcon;
  color: string;
  bgColor: string;
  borderColor: string;
  shadow: string;
}

interface DrugAlertBannerProps {
  alerts: DrugAlert[];
  onViewDetails?: (alert: DrugAlert) => void;
  dismissible?: boolean;
  onDismiss?: (alertId: string) => void;
  defaultExpanded?: boolean;
}

const severityConfig: Record<AlertSeverity, SeverityConfigType> = {
  major: {
    icon: ErrorIcon,
    color: clinicalColors.severity.major.main,
    bgColor: clinicalColors.severity.major.light,
    borderColor: clinicalColors.severity.major.dark,
    shadow: '0 4px 16px rgba(198, 40, 40, 0.24)',
  },
  moderate: {
    icon: Warning,
    color: clinicalColors.severity.moderate.main,
    bgColor: clinicalColors.severity.moderate.light,
    borderColor: clinicalColors.severity.moderate.dark,
    shadow: '0 4px 16px rgba(239, 108, 0, 0.24)',
  },
  minor: {
    icon: Info,
    color: clinicalColors.severity.minor.main,
    bgColor: clinicalColors.severity.minor.light,
    borderColor: clinicalColors.severity.minor.dark,
    shadow: '0 4px 16px rgba(25, 118, 210, 0.24)',
  },
};

const getSeverityGroup = (alerts: DrugAlert[], severity: AlertSeverity): DrugAlert[] => {
  return alerts.filter((alert) => alert.severity === severity);
};

const buildAlertKey = (alert: DrugAlert, index: number): string =>
  alert.id ?? `${alert.severity}:${alert.source}:${alert.description}:${index}`;

export default function DrugAlertBanner({
  alerts,
  onViewDetails,
  dismissible = false,
  onDismiss,
  defaultExpanded = true,
}: DrugAlertBannerProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [dismissedIds, setDismissedIds] = useState<Set<string>>(new Set());

  if (alerts.length === 0) {
    return null;
  }

  const alertKeys = new Map<DrugAlert, string>(alerts.map((alert, index) => [alert, buildAlertKey(alert, index)]));
  const visibleAlerts = alerts.filter((alert) => !dismissedIds.has(alertKeys.get(alert) ?? ""));
  
  const majorAlerts = getSeverityGroup(visibleAlerts, 'major');
  const moderateAlerts = getSeverityGroup(visibleAlerts, 'moderate');
  const minorAlerts = getSeverityGroup(visibleAlerts, 'minor');

  const handleDismiss = (alertId: string) => {
    setDismissedIds((prev) => new Set([...prev, alertId]));
    onDismiss?.(alertId);
  };

  const renderAlertGroup = (severity: AlertSeverity, alertsInGroup: DrugAlert[]) => {
    if (alertsInGroup.length === 0) return null;

    const config = severityConfig[severity];
    const SeverityIcon = config.icon;

    return (
      <Alert
        key={`banner-${severity}`}
        severity={severity === 'major' ? 'error' : severity === 'moderate' ? 'warning' : 'info'}
        sx={{
          bgcolor: config.bgColor,
          borderLeft: `4px solid ${config.borderColor}`,
          boxShadow: config.shadow,
          mb: 2,
        }}
        icon={<SeverityIcon />}
      >
        <AlertTitle sx={{ display: 'flex', alignItems: 'center', gap: 1, fontWeight: 600 }}>
          {severity === 'major' && 'Critical Drug Alerts'}
          {severity === 'moderate' && 'Moderate Drug Interactions'}
          {severity === 'minor' && 'Minor Drug Notices'}
          <Chip
            label={`${alertsInGroup.length} alert${alertsInGroup.length > 1 ? 's' : ''}`}
            size="small"
            sx={{ height: 20, fontSize: 10 }}
          />
        </AlertTitle>
        
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
          {alertsInGroup.map((alert, index) => {
            const alertKey = alertKeys.get(alert) ?? `${severity}:${index}`;

            return (
            <Box
              key={alertKey}
              sx={{
                display: 'flex',
                flexDirection: 'column',
                gap: 0.5,
                p: 1.5,
                borderRadius: 1,
                bgcolor: 'rgba(255, 255, 255, 0.6)',
              }}
            >
              <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
                <Typography variant="body2" fontWeight={500}>
                  {alert.description}
                </Typography>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                  {alert.evidence_level && (
                    <Chip
                      label={`Level ${alert.evidence_level}`}
                      size="small"
                      variant="outlined"
                      sx={{ height: 20, fontSize: 10 }}
                    />
                  )}
                  {dismissible && (
                    <IconButton
                      size="small"
                      onClick={() => handleDismiss(alertKey)}
                      aria-label="Dismiss alert"
                    >
                      <Close fontSize="small" />
                    </IconButton>
                  )}
                </Box>
              </Box>

              {alert.alternatives && alert.alternatives.length > 0 && (
                <Typography variant="caption" color="text.secondary">
                  <strong>Alternatives:</strong> {alert.alternatives.join(', ')}
                </Typography>
              )}

              {alert.clinical_significance && (
                <Box
                  sx={{
                    mt: 0.5,
                    p: 1,
                    borderRadius: 1,
                    bgcolor: 'rgba(0, 0, 0, 0.04)',
                  }}
                >
                  <Typography variant="caption" fontWeight={600} color="text.secondary">
                    Clinical Significance
                  </Typography>
                  <Typography variant="caption" display="block">
                    {alert.clinical_significance}
                  </Typography>
                </Box>
              )}

              {onViewDetails && (
                <Button
                  size="small"
                  startIcon={<Visibility />}
                  onClick={() => onViewDetails(alert)}
                  sx={{ alignSelf: 'flex-start', mt: 0.5 }}
                >
                  View Details
                </Button>
              )}
            </Box>
          );
          })}
        </Box>
      </Alert>
    );
  };

  return (
    <Box sx={{ mb: 2 }}>
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          mb: 1,
        }}
      >
        <Typography variant="subtitle2" color="text.secondary">
          Drug Safety Alerts ({visibleAlerts.length})
        </Typography>
        <IconButton
          size="small"
          onClick={() => setExpanded(!expanded)}
          aria-label={expanded ? 'Collapse alerts' : 'Expand alerts'}
        >
          {expanded ? <ExpandLess /> : <ExpandMore />}
        </IconButton>
      </Box>

      <Collapse in={expanded}>
        {renderAlertGroup('major', majorAlerts)}
        {renderAlertGroup('moderate', moderateAlerts)}
        {renderAlertGroup('minor', minorAlerts)}
      </Collapse>
    </Box>
  );
}

export { DrugAlertBanner };
export type { DrugAlertBannerProps, AlertSeverity };
