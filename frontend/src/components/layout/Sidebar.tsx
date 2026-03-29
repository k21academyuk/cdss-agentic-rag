/**
 * Sidebar - Navigation sidebar component
 *
 * A responsive navigation sidebar that provides access to main application sections.
 * Uses a permanent drawer on desktop and a temporary drawer on mobile.
 *
 * @module components/layout/Sidebar
 */

import { useCallback } from 'react';
import {
  Drawer,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Box,
  Toolbar,
  Divider,
  Typography,
  useTheme,
  useMediaQuery,
  alpha,
} from '@mui/material';
import {
  Dashboard,
  Search,
  Person,
  Medication,
  UploadFile,
  MenuBook,
  Settings,
} from '@mui/icons-material';
import { useNavigate, useLocation } from 'react-router-dom';

import { SIDEBAR_WIDTH, NAVBAR_HEIGHT } from './AppShell';
import { spacing, transitions, primary } from '@/theme';
import { clinicalColors } from '@/theme/clinical';

// ============================================================================
// TYPES
// ============================================================================

export interface SidebarProps {
  /** Whether the mobile drawer is open */
  mobileOpen?: boolean;
  /** Callback when mobile drawer should close */
  onMobileClose?: () => void;
}

// ============================================================================
// NAVIGATION ITEMS
// ============================================================================

interface NavItem {
  text: string;
  icon: React.ReactNode;
  path: string;
}

const mainNavItems: NavItem[] = [
  { text: 'Dashboard', icon: <Dashboard />, path: '/' },
  { text: 'Query', icon: <Search />, path: '/query' },
  { text: 'Patients', icon: <Person />, path: '/patients' },
  { text: 'Drugs', icon: <Medication />, path: '/drugs' },
  { text: 'Documents', icon: <UploadFile />, path: '/documents' },
  { text: 'Literature', icon: <MenuBook />, path: '/literature' },
];

const adminNavItems: NavItem[] = [
  { text: 'Settings', icon: <Settings />, path: '/settings' },
];

// ============================================================================
// SIDEBAR COMPONENT
// ============================================================================

export default function Sidebar({
  mobileOpen = false,
  onMobileClose,
}: SidebarProps) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const navigate = useNavigate();
  const location = useLocation();

  const handleNavigate = useCallback(
    (path: string) => {
      navigate(path);
      if (isMobile) {
        onMobileClose?.();
      }
    },
    [navigate, isMobile, onMobileClose]
  );

  const isActive = (path: string) => {
    if (path === '/') {
      return location.pathname === '/';
    }
    return location.pathname.startsWith(path);
  };

  // ============================================================================
  // DRAWER CONTENT
  // ============================================================================

  const drawerContent = (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        backgroundColor: theme.palette.background.paper,
      }}
    >
      {/* Header / Logo */}
      <Toolbar
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'flex-start',
          height: NAVBAR_HEIGHT,
          minHeight: NAVBAR_HEIGHT,
          px: spacing[3],
          backgroundColor: clinicalColors.agent.completed.main,
          color: '#ffffff',
        }}
      >
        <Medication sx={{ fontSize: 28, mr: 1.5 }} />
        <Box sx={{ display: 'flex', flexDirection: 'column' }}>
          <Typography
            variant="h6"
            sx={{
              fontWeight: 700,
              fontSize: '1.25rem',
              letterSpacing: '-0.02em',
              lineHeight: 1,
            }}
          >
            CDSS
          </Typography>
          <Typography
            variant="caption"
            sx={{ fontSize: '0.7rem', opacity: 0.85, fontWeight: 400 }}
          >
            Clinical Decision Support
          </Typography>
        </Box>
      </Toolbar>

      {/* Main Navigation Items */}
      <List sx={{ pt: spacing[1], flex: 1 }}>
        {mainNavItems.map((item) => (
          <ListItem key={item.text} disablePadding>
            <ListItemButton
              selected={isActive(item.path)}
              onClick={() => handleNavigate(item.path)}
              sx={{
                borderRadius: spacing[1],
                mx: spacing[1],
                py: spacing[0.5],
                minHeight: 48,
                transition: transitions.background.standard,
                '&.Mui-selected': {
                  backgroundColor: alpha(primary.main, 0.12),
                  color: primary.main,
                  '&:hover': {
                    backgroundColor: alpha(primary.main, 0.16),
                  },
                },
                '&:hover': {
                  backgroundColor: alpha(theme.palette.action.hover, 0.08),
                },
              }}
            >
              <ListItemIcon
                sx={{
                  minWidth: spacing[6],
                  color: isActive(item.path)
                    ? primary.main
                    : theme.palette.text.secondary,
                  transition: transitions.color,
                }}
              >
                {item.icon}
              </ListItemIcon>
              <ListItemText
                primary={item.text}
                sx={{
                  '& .MuiListItemText-primary': {
                    fontWeight: isActive(item.path) ? 600 : 500,
                    color: isActive(item.path)
                      ? primary.main
                      : theme.palette.text.secondary,
                  },
                }}
              />
            </ListItemButton>
          </ListItem>
        ))}
      </List>

      {/* Divider */}
      <Divider sx={{ mx: spacing[2], my: spacing[1] }} />

      {/* Admin Section */}
      <List sx={{ pt: spacing[0], pb: spacing[2] }}>
        {adminNavItems.map((item) => (
          <ListItem key={item.text} disablePadding>
            <ListItemButton
              selected={isActive(item.path)}
              onClick={() => handleNavigate(item.path)}
              sx={{
                borderRadius: spacing[1],
                mx: spacing[1],
                py: spacing[0.5],
                minHeight: 48,
                transition: transitions.background.standard,
                '&.Mui-selected': {
                  backgroundColor: alpha(primary.main, 0.12),
                  color: primary.main,
                  '&:hover': {
                    backgroundColor: alpha(primary.main, 0.16),
                  },
                },
                '&:hover': {
                  backgroundColor: alpha(theme.palette.action.hover, 0.08),
                },
              }}
            >
              <ListItemIcon
                sx={{
                  minWidth: spacing[6],
                  color: isActive(item.path)
                    ? primary.main
                    : theme.palette.text.secondary,
                  transition: transitions.color,
                }}
              >
                {item.icon}
              </ListItemIcon>
              <ListItemText
                primary={item.text}
                sx={{
                  '& .MuiListItemText-primary': {
                    fontWeight: isActive(item.path) ? 600 : 500,
                    color: isActive(item.path)
                      ? primary.main
                      : theme.palette.text.secondary,
                  },
                }}
              />
            </ListItemButton>
          </ListItem>
        ))}
      </List>
    </Box>
  );

  // ============================================================================
  // RENDER
  // ============================================================================

  if (isMobile) {
    // Mobile: Temporary drawer
    return (
      <Drawer
        variant="temporary"
        open={mobileOpen}
        onClose={onMobileClose}
        ModalProps={{ keepMounted: true }}
        sx={{
          display: { xs: 'block', md: 'none' },
          '& .MuiDrawer-paper': {
            boxSizing: 'border-box',
            width: SIDEBAR_WIDTH,
            borderRight: `1px solid ${theme.palette.divider}`,
          },
        }}
      >
        {drawerContent}
      </Drawer>
    );
  }

  // Desktop: Permanent drawer
  return (
    <Drawer
      variant="permanent"
      sx={{
        display: { xs: 'none', md: 'block' },
        '& .MuiDrawer-paper': {
          boxSizing: 'border-box',
          width: SIDEBAR_WIDTH,
          borderRight: `1px solid ${theme.palette.divider}`,
          backgroundColor: theme.palette.background.paper,
        },
      }}
      open
    >
      {drawerContent}
    </Drawer>
  );
}
