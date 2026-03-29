/**
 * MobileNav - Mobile Bottom Navigation Component
 *
 * A bottom navigation bar for mobile devices that provides quick access
 * to the main sections of the application.
 *
 * @module components/layout/MobileNav
 */

import React from 'react';
import {
  Paper,
  BottomNavigation,
  BottomNavigationAction,
  useTheme,
  alpha,
} from '@mui/material';
import {
  Home,
  Search,
  Person,
  Medication,
  MoreHoriz,
} from '@mui/icons-material';
import { useNavigate, useLocation } from 'react-router-dom';

import { MOBILE_NAV_HEIGHT } from './AppShell';
import { spacing, transitions, primary } from '@/theme';

export interface MobileNavProps {
  /** Callback when navigation occurs */
  onNavigate?: () => void;
}

interface NavItem {
  text: string;
  icon: React.ReactNode;
  path: string;
}

const mobileNavItems: NavItem[] = [
  {
    text: 'Home',
    icon: <Home />,
    path: '/',
  },
  {
    text: 'Query',
    icon: <Search />,
    path: '/query',
  },
  {
    text: 'Patients',
    icon: <Person />,
    path: '/patients',
  },
  {
    text: 'Drugs',
    icon: <Medication />,
    path: '/drugs',
  },
  {
    text: 'More',
    icon: <MoreHoriz />,
    path: '/settings',
  },
];

export default function MobileNav({ onNavigate }: MobileNavProps) {
  const theme = useTheme();
  const navigate = useNavigate();
  const location = useLocation();

  const handleNavigate = (path: string) => {
    navigate(path);
    onNavigate?.();
  };

  const getCurrentValue = (): number => {
    const currentPath = location.pathname;
    const index = mobileNavItems.findIndex((item) => item.path === currentPath);
    return index >= 0 ? index : 0;
  };

  return (
    <Paper
      elevation={0}
      sx={{
        position: 'fixed',
        bottom: 0,
        left: 0,
        right: 0,
        height: MOBILE_NAV_HEIGHT,
        backgroundColor: theme.palette.background.paper,
        borderTop: `1px solid ${theme.palette.divider}`,
        zIndex: theme.zIndex.appBar,
      }}
    >
      <BottomNavigation
        showLabels
        value={getCurrentValue()}
        onChange={(_, newValue) => {
          handleNavigate(mobileNavItems[newValue].path);
        }}
        sx={{
          height: '100%',
          backgroundColor: 'transparent',
          '& .MuiBottomNavigationAction-root': {
            minWidth: 'auto',
            padding: `${spacing[1]}px ${spacing[2]}px`,
            color: theme.palette.text.secondary,
            transition: transitions.common,
            '&.Mui-selected': {
              color: primary.main,
            },
          },
          '& .MuiBottomNavigationAction-label': {
            fontSize: '0.625rem',
            fontWeight: 500,
            marginTop: spacing[0.5],
            '&.Mui-selected': {
              fontSize: '0.625rem',
            },
          },
        }}
      >
        {mobileNavItems.map((item, index) => (
          <BottomNavigationAction
            key={item.text}
            label={item.text}
            icon={item.icon}
            value={index}
            sx={{
              '& .MuiSvgIcon-root': {
                fontSize: 20,
              },
              '&.Mui-selected': {
                '& .MuiSvgIcon-root': {
                  color: primary.main,
                },
              },
            }}
          />
        ))}
      </BottomNavigation>
    </Paper>
  );
}
