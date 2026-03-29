import { useState } from 'react';
import {
  AppBar,
  Toolbar,
  Typography,
  Button,
  IconButton,
  Menu,
  MenuItem,
  Divider,
  Box,
  Tooltip,
  Avatar,
  Chip,
  useTheme,
  alpha,
} from '@mui/material';
import {
  Brightness4,
  Brightness7,
  Menu as MenuIcon,
  Logout,
  Settings,
  Wifi,
  WifiOff,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';

import { useThemeStore, useUserStore } from '@/stores/userStore';
import { login, logout, getActiveAccount } from '@/lib/auth';
import { NAVBAR_HEIGHT, SIDEBAR_WIDTH } from './AppShell';
import { spacing, transitions, primary } from '@/theme';

export interface NavbarProps {
  onMenuClick?: () => void;
  showMenuButton?: boolean;
  sidebarWidth?: number;
  systemStatus?: 'online' | 'offline' | 'degraded';
}

export default function Navbar({
  onMenuClick,
  showMenuButton = false,
  sidebarWidth = 0,
  systemStatus = 'online',
}: NavbarProps) {
  const theme = useTheme();
  const navigate = useNavigate();
  const user = useUserStore((state) => state.user);
  const themeMode = useThemeStore((state) => state.theme);
  const toggleTheme = useThemeStore((state) => state.toggleTheme);
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);

  const account = getActiveAccount();
  const displayName = account?.name || user?.name || 'User';
  const email = account?.username || user?.email || '';
  const initials = displayName
    .split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);

  const handleMenu = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget);
  };

  const handleClose = () => {
    setAnchorEl(null);
  };

  const handleLogout = async () => {
    handleClose();
    await logout();
  };

  const handleLogin = async () => {
    await login();
  };

  const statusConfig = {
    online: { color: theme.palette.success.main, label: 'Online' },
    offline: { color: theme.palette.error.main, label: 'Offline' },
    degraded: { color: theme.palette.warning.main, label: 'Degraded' },
  };

  return (
    <AppBar
      position="fixed"
      elevation={0}
      sx={{
        height: NAVBAR_HEIGHT,
        backgroundColor: theme.palette.background.paper,
        borderBottom: `1px solid ${theme.palette.divider}`,
        marginLeft: sidebarWidth,
        width: sidebarWidth > 0 ? `calc(100% - ${sidebarWidth}px)` : '100%',
        transition: transitions.common,
        zIndex: theme.zIndex.appBar,
      }}
    >
      <Toolbar
        sx={{
          height: '100%',
          px: spacing[3],
          gap: spacing[2],
        }}
      >
        {showMenuButton && (
          <IconButton
            edge="start"
            color="inherit"
            onClick={onMenuClick}
            sx={{
              mr: spacing[1],
              color: theme.palette.text.primary,
            }}
          >
            <MenuIcon />
          </IconButton>
        )}

        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: spacing[1],
            flexGrow: 1,
          }}
        >
          <Typography
            variant="h6"
            component="div"
            sx={{
              color: theme.palette.primary.main,
              fontWeight: 700,
              letterSpacing: '-0.02em',
              fontSize: '1.25rem',
            }}
          >
            CDSS
          </Typography>
          <Typography
            variant="body2"
            sx={{
              color: theme.palette.text.secondary,
              fontWeight: 400,
              display: { xs: 'none', sm: 'inline' },
            }}
          >
            Clinical Decision Support System
          </Typography>
        </Box>

        <Box sx={{ display: 'flex', alignItems: 'center', gap: spacing[1] }}>
          <Chip
            icon={
              systemStatus === 'online' ? (
                <Wifi fontSize="small" />
              ) : (
                <WifiOff fontSize="small" />
              )
            }
            label={statusConfig[systemStatus].label}
            size="small"
            sx={{
              backgroundColor: alpha(statusConfig[systemStatus].color, 0.1),
              color: statusConfig[systemStatus].color,
              fontWeight: 500,
              display: { xs: 'none', md: 'flex' },
              '& .MuiChip-icon': {
                color: statusConfig[systemStatus].color,
              },
            }}
          />

          <Tooltip title={themeMode === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}>
            <IconButton
              onClick={toggleTheme}
              sx={{
                color: theme.palette.text.secondary,
                '&:hover': {
                  backgroundColor: alpha(theme.palette.primary.main, 0.08),
                  color: theme.palette.primary.main,
                },
              }}
            >
              {themeMode === 'dark' ? <Brightness7 /> : <Brightness4 />}
            </IconButton>
          </Tooltip>

          {account ? (
            <Tooltip title="Account">
              <IconButton
                onClick={handleMenu}
                sx={{
                  ml: spacing[1],
                  p: 0.5,
                  border: `2px solid ${theme.palette.divider}`,
                  '&:hover': {
                    borderColor: theme.palette.primary.main,
                  },
                }}
              >
                <Avatar
                  sx={{
                    width: 32,
                    height: 32,
                    backgroundColor: theme.palette.primary.main,
                    fontSize: '0.875rem',
                    fontWeight: 600,
                  }}
                >
                  {initials}
                </Avatar>
              </IconButton>
            </Tooltip>
          ) : (
            <Button variant="outlined" size="small" onClick={handleLogin}>
              Sign in
            </Button>
          )}

          {account && (
            <Menu
              anchorEl={anchorEl}
              open={Boolean(anchorEl)}
              onClose={handleClose}
              transformOrigin={{ horizontal: 'right', vertical: 'top' }}
              anchorOrigin={{ horizontal: 'right', vertical: 'bottom' }}
              PaperProps={{
                sx: {
                  mt: 1,
                  minWidth: 200,
                  boxShadow: theme.shadows[3],
                },
              }}
            >
              <Box sx={{ px: 2, py: 1.5 }}>
                <Typography variant="subtitle2" fontWeight={600}>
                  {displayName}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {email}
                </Typography>
              </Box>
              <Divider />
              <MenuItem
                onClick={() => {
                  handleClose();
                  navigate('/settings');
                }}
                sx={{ py: 1.5 }}
              >
                <Settings sx={{ mr: 1.5, fontSize: 20 }} />
                Settings
              </MenuItem>
              <MenuItem onClick={handleLogout} sx={{ py: 1.5 }}>
                <Logout sx={{ mr: 1.5, fontSize: 20 }} />
                Logout
              </MenuItem>
            </Menu>
          )}
        </Box>
      </Toolbar>
    </AppBar>
  );
}
