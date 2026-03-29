/**
 * AppShell - Main Layout Container
 *
 * The primary layout wrapper for the CDSS application. Provides responsive
 * sidebar navigation, fixed navbar, and mobile navigation support.
 *
 * @module components/layout/AppShell
 */

import { ReactNode, useState } from 'react';
import { Box, useTheme, useMediaQuery } from '@mui/material';
import { Outlet, useLocation } from 'react-router-dom';

import Navbar from './Navbar';
import Sidebar from './Sidebar';
import MobileNav from './MobileNav';
import StatusBar from './StatusBar';
import PageTransition from '@/components/common/PageTransition';
import { spacing } from '@/theme';

// ============================================================================
// LAYOUT CONSTANTS
// ============================================================================

/** Height of the top navigation bar in pixels */
export const NAVBAR_HEIGHT = 64;

/** Width of the sidebar in pixels (desktop) */
export const SIDEBAR_WIDTH = 240;

/** Height of the bottom status bar in pixels */
export const STATUS_BAR_HEIGHT = 32;

/** Height of mobile bottom navigation in pixels */
export const MOBILE_NAV_HEIGHT = 56;

// ============================================================================
// TYPES
// ============================================================================

export interface AppShellProps {
  /** Optional children to render instead of Outlet */
  children?: ReactNode;
  /** Show status bar at bottom */
  showStatusBar?: boolean;
  /** System status for status bar */
  systemStatus?: 'online' | 'offline' | 'degraded';
  /** Connection status message */
  connectionMessage?: string;
}

// ============================================================================
// APP SHELL COMPONENT
// ============================================================================

export function AppShell({
  children,
  showStatusBar = true,
  systemStatus = 'online',
  connectionMessage,
}: AppShellProps) {
  const theme = useTheme();
  const location = useLocation();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const [mobileOpen, setMobileOpen] = useState(false);

  const handleDrawerToggle = () => {
    setMobileOpen(!mobileOpen);
  };

  // Calculate content area dimensions
  const contentTop = NAVBAR_HEIGHT;
  const contentBottom = isMobile ? MOBILE_NAV_HEIGHT : showStatusBar ? STATUS_BAR_HEIGHT : 0;
  const sidebarWidth = isMobile ? 0 : SIDEBAR_WIDTH;

  return (
    <Box
      sx={{
        display: 'flex',
        minHeight: '100vh',
        backgroundColor: theme.palette.background.default,
      }}
    >
      {/* Top Navigation Bar */}
      <Navbar
        showMenuButton={isMobile}
        onMenuClick={handleDrawerToggle}
        sidebarWidth={sidebarWidth}
        systemStatus={systemStatus}
      />

      {/* Sidebar Navigation */}
      <Sidebar
        mobileOpen={mobileOpen}
        onMobileClose={() => setMobileOpen(false)}
      />

      {/* Main Content Area */}
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          width: { xs: '100%', md: `calc(100% - ${SIDEBAR_WIDTH}px)` },
          marginLeft: { xs: 0, md: `${SIDEBAR_WIDTH}px` },
          marginTop: `${contentTop}px`,
          marginBottom: `${contentBottom}px`,
          minHeight: `calc(100vh - ${contentTop}px - ${contentBottom}px)`,
          transition: theme.transitions.create(['margin', 'width'], {
            easing: theme.transitions.easing.sharp,
            duration: theme.transitions.duration.standard,
          }),
        }}
      >
        {/* Content Container with proper padding */}
        <Box
          sx={{
            flexGrow: 1,
            p: { xs: spacing[2], sm: spacing[3], md: spacing[4] },
            maxWidth: '100%',
            overflowX: 'hidden',
          }}
        >
          <PageTransition transitionKey={location.pathname}>{children || <Outlet />}</PageTransition>
        </Box>
      </Box>

      {/* Mobile Bottom Navigation */}
      {isMobile && <MobileNav />}

      {/* Bottom Status Bar (desktop only) */}
      {!isMobile && showStatusBar && (
        <StatusBar
          sidebarWidth={SIDEBAR_WIDTH}
          systemStatus={systemStatus}
          message={connectionMessage}
        />
      )}
    </Box>
  );
}

export default AppShell;
