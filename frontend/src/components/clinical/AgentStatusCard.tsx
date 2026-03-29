import React, { useState } from 'react';
import {
  Box,
  Typography,
  LinearProgress,
  Paper,
  Collapse,
  IconButton,
  useTheme,
} from '@mui/material';
import {
  CheckCircle,
  Error as ErrorIcon,
  Schedule,
  TrendingUp,
  ExpandMore,
  ExpandLess,
} from '@mui/icons-material';
import { clinicalColors } from '@/theme/clinical';

type AgentStatus = 'pending' | 'running' | 'completed' | 'error';

interface AgentStatusCardProps {
  name: string;
  status: AgentStatus;
  progress?: number;
  latency?: number;
  startTime?: number;
  details?: React.ReactNode;
  defaultExpanded?: boolean;
}

const statusConfig: Record<AgentStatus, { 
  icon: typeof Schedule; 
  color: string; 
  bgColor: string; 
  label: string; 
}> = {
  pending: {
    icon: Schedule,
    color: clinicalColors.agent.pending.main,
    bgColor: clinicalColors.agent.pending.light,
    label: 'Pending',
  },
  running: {
    icon: TrendingUp,
    color: clinicalColors.agent.running.main,
    bgColor: clinicalColors.agent.running.light,
    label: 'Running',
  },
  completed: {
    icon: CheckCircle,
    color: clinicalColors.agent.completed.main,
    bgColor: clinicalColors.agent.completed.light,
    label: 'Completed',
  },
  error: {
    icon: ErrorIcon,
    color: clinicalColors.agent.error.main,
    bgColor: clinicalColors.agent.error.light,
    label: 'Error',
  },
};

export default function AgentStatusCard({
  name,
  status,
  progress = 0,
  latency,
  startTime,
  details,
  defaultExpanded = false,
}: AgentStatusCardProps) {
  const theme = useTheme();
  const [expanded, setExpanded] = useState(defaultExpanded);
  const isDark = theme.palette.mode === 'dark';
  
  const config = statusConfig[status];
  const StatusIcon = config.icon;
  const statusColor = config.color;
  const statusBgColor = config.bgColor;

  const getStatusLabel = () => {
    switch (status) {
      case 'pending':
        return 'Initializing...';
      case 'running':
        return `Processing (${progress}%)...`;
      case 'completed':
        return 'Completed';
      case 'error':
        return 'Failed';
      default:
        return status;
    }
  };

  const progressValue = status === 'running' ? progress : status === 'completed' ? 100 : 0;

  return (
    <Paper
      sx={{
        p: 2,
        mb: 1,
        borderLeft: `3px solid ${statusColor}`,
        backgroundColor: statusBgColor,
        transition: 'all 0.2s ease-in-out',
        '&:hover': {
          boxShadow: theme.shadows[2],
        },
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flex: 1 }}>
          <StatusIcon
            sx={{
              color: statusColor,
              fontSize: 24,
              ...(status === 'running' && {
                animation: 'pulse 1.5s ease-in-out infinite',
                '@keyframes pulse': {
                  '0%, 100%': { opacity: 1 },
                  '50%': { opacity: 0.5 },
                },
              }),
            }}
          />
          <Box sx={{ flex: 1 }}>
            <Typography variant="subtitle2" fontWeight={600}>
              {name}
            </Typography>
            {status === 'completed' && latency !== undefined && (
              <Typography variant="caption" color="text.secondary" sx={{ fontSize: 11 }}>
                {latency}ms
              </Typography>
            )}
          </Box>
        </Box>

        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          {status === 'running' && (
            <Box sx={{ width: 100, mr: 1 }}>
              <LinearProgress
                variant="determinate"
                value={progressValue}
                sx={{
                  height: 6,
                  borderRadius: 3,
                  bgcolor: isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)',
                  '& .MuiLinearProgress-bar': {
                    borderRadius: 3,
                    backgroundColor: statusColor,
                  },
                }}
              />
            </Box>
          )}
          <Typography
            variant="caption"
            sx={{
              fontWeight: 500,
              color: statusColor,
              textTransform: 'uppercase',
              fontSize: 10,
              letterSpacing: 0.5,
            }}
          >
            {config.label}
          </Typography>
          {details && (
            <IconButton
              size="small"
              onClick={() => setExpanded(!expanded)}
              aria-label={expanded ? 'Collapse details' : 'Expand details'}
            >
              {expanded ? <ExpandLess fontSize="small" /> : <ExpandMore fontSize="small" />}
            </IconButton>
          )}
        </Box>
      </Box>

      {details && (
        <Collapse in={expanded}>
          <Box
            sx={{
              mt: 2,
              pt: 2,
              borderTop: `1px solid ${theme.palette.divider}`,
              maxHeight: 200,
              overflow: 'auto',
            }}
          >
            <Typography variant="caption" color="text.secondary" sx={{ mb: 1, display: 'block' }}>
              Details
            </Typography>
            {details}
          </Box>
        </Collapse>
      )}
    </Paper>
  );
}

export { AgentStatusCard };
export type { AgentStatusCardProps, AgentStatus };
