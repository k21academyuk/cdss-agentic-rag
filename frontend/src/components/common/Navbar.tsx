import React, { useState } from 'react';
import {
  AppBar,
  Toolbar,
  Typography,
  IconButton,
  Menu,
  MenuItem,
  Divider,
  Box,
  Tooltip,
  useTheme,
} from '@mui/material';
import {
  Brightness4,
  Brightness7,
  AccountCircle,
  Logout,
  Settings,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { useThemeStore, useUserStore } from '@/stores/userStore';
import { logout, getActiveAccount } from '@/lib/auth';

export default function Navbar() {
  const theme = useTheme();
  const navigate = useNavigate();
  const user = useUserStore((state) => state.user);
  const themeMode = useThemeStore((state) => state.theme);
  const toggleTheme = useThemeStore((state) => state.toggleTheme);
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);

  const account = getActiveAccount();
  const displayName = account?.name || user?.name || 'User';
  const email = account?.username || user?.email || '';

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

  return (
    <AppBar
      position="fixed"
      sx={{
        zIndex: theme.zIndex.drawer + 1,
        backgroundColor: theme.palette.background.paper,
        borderBottom: `1px solid ${theme.palette.divider}`,
      }}
    >
      <Toolbar>
        <Typography
          variant="h6"
          component="div"
          sx={{ flexGrow: 1, color: theme.palette.text.primary, fontWeight: 600 }}
        >
          CDSS - Clinical Decision Support System
        </Typography>

        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Tooltip title="Toggle theme">
            <IconButton onClick={toggleTheme} color="inherit">
              {themeMode === 'dark' ? <Brightness7 /> : <Brightness4 />}
            </IconButton>
          </Tooltip>

          <IconButton onClick={handleMenu} color="inherit">
            <AccountCircle />
          </IconButton>
          <Menu
            anchorEl={anchorEl}
            open={Boolean(anchorEl)}
            onClose={handleClose}
          >
            <Box sx={{ px: 2, py: 1 }}>
              <Typography variant="subtitle2" fontWeight={600}>
                {displayName}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {email}
              </Typography>
            </Box>
            <Divider />
            <MenuItem onClick={() => { handleClose(); navigate('/settings'); }}>
              <Settings sx={{ mr: 1.5 }} fontSize="small" />
              Settings
            </MenuItem>
            <MenuItem onClick={handleLogout}>
              <Logout sx={{ mr: 1.5 }} fontSize="small" />
              Logout
            </MenuItem>
          </Menu>
        </Box>
      </Toolbar>
    </AppBar>
  );
}
