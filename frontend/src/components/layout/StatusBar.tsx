/**
 * StatusBar - Bottom Status Bar Component
 *
 * A fixed status bar at the bottom of the application viewport that displays
 * connection status, connection info, and version information.
 *
 * @module components/layout/StatusBar
 */

import React from 'react';
import {
  Box,
  Typography,
  Chip,
  useTheme,
  alpha,
} from '@mui/material';
import {
  FiberManualRecord,
  Wifi,
  WifiOff,
  Cloud,
  Warning,
  CheckCircle,
} from '@mui/icons-material';

import { STATUS_BAR_HEIGHT, SIDEBAR_WIDTH } from './AppShell';
import { spacing, transitions, semantic } from '@/theme';

// ============================================================================
// TYPES
// ============================================================================

export interface StatusBarProps {
  /** System connection status */
  systemStatus?: 'online' | 'offline' | 'degraded';
  /** Optional message to display */
  message?: string;
  /** Width of sidebar for offset calculation */
  sidebarWidth?: number;
  /** Application version to display */
  version?: string;
}

// ============================================================================
// STATUS CONFIGURATION
// ============================================================================

const statusConfig = {
  online: {
    color: semantic.success.main,
    bgColor: alpha(semantic.success.main, 0.08),
    icon: CheckCircle,
    label: 'Connected',
  },
  offline: {
    color: semantic.error.main,
    bgColor: alpha(semantic.error.main, 0.08),
    icon: WifiOff,
    label: 'Disconnected',
  },
  degraded: {
    color: semantic.warning.main,
    bgColor: alpha(semantic.warning.main, 0.08),
    icon: Warning,
    label: 'Degraded',
  },
};

// ============================================================================
// STATUS BAR COMPONENT
// ============================================================================

export default function StatusBar({
  systemStatus = 'online',
  message,
  sidebarWidth = 0,
  version = '1.0.0',
}: StatusBarProps) {
  const theme = useTheme();
  const currentStatus = statusConfig[systemStatus];
  const StatusIcon = currentStatus.icon;

  return (
    <Box
      sx={{
        position: 'fixed',
        bottom: 0,
        left: sidebarWidth,
        width: sidebarWidth > 0 ? `calc(100% - ${sidebarWidth}px)` : '100%',
        height: STATUS_BAR_HEIGHT,
        backgroundColor: theme.palette.background.paper,
        borderTop: `1px solid ${theme.palette.divider}`,
        zIndex: theme.zIndex.appBar - 1,
        transition: transitions.common,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        px: spacing[3],
      }}
    >
      {/* Connection Status */}
      <Chip
        size="small"
        icon={<StatusIcon sx={{ fontSize: 14 }} />}
        label={currentStatus.label}
        sx={{
          backgroundColor: currentStatus.bgColor,
          color: currentStatus.color,
          fontWeight: 500,
          '& .MuiChip-icon': {
            color: currentStatus.color,
            fontSize: 14,
          },
        }}
      />

      {/* Message */}
      {message && (
        <Typography
          variant="caption"
          sx={{
            color: theme.palette.text.secondary,
            fontSize: '0.625rem',
            ml: spacing[2],
          }}
        >
          {message}
        </Typography>
      )}

      {/* Spacer */}
      <Box sx={{ flex: 1 }} />

      {/* Version */}
      <Typography
        variant="caption"
        sx={{
          color: theme.palette.text.disabled,
          fontSize: '0.625rem',
        }}
      >
        v{version}
      </Typography>
    </Box>
  );
}
