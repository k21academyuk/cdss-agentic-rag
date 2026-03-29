import React, { useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Switch,
  FormControlLabel,
  Divider,
  TextField,
  Button,
  Grid,
  Paper,
  Alert,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Chip,
} from '@mui/material';
import { Save, Refresh } from '@mui/icons-material';
import { useThemeStore, useUserStore, useQueryHistoryStore } from '@/stores/userStore';

export default function SettingsPage() {
  const themeMode = useThemeStore((state) => state.theme);
  const toggleTheme = useThemeStore((state) => state.toggleTheme);
  const sessionTimeout = useUserStore((state) => state.sessionTimeout);
  const resetSession = useUserStore((state) => state.resetSession);
  const { queries, clearHistory } = useQueryHistoryStore();

  const [timeoutMinutes, setTimeoutMinutes] = useState(sessionTimeout / 60000);
  const [saved, setSaved] = useState(false);

  const handleSaveTimeout = () => {
    resetSession();
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  };

  const handleClearHistory = () => {
    clearHistory();
  };

  return (
    <Box>
      <Typography variant="h4" gutterBottom fontWeight={600}>
        Settings
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 4 }}>
        Configure your application preferences
      </Typography>

      <Grid container spacing={3}>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom fontWeight={600}>
                Appearance
              </Typography>
              <Divider sx={{ mb: 2 }} />

              <FormControlLabel
                control={
                  <Switch
                    checked={themeMode === 'dark'}
                    onChange={toggleTheme}
                    color="primary"
                  />
                }
                label={
                  <Box>
                    <Typography variant="body1">Dark Mode</Typography>
                    <Typography variant="caption" color="text.secondary">
                      Toggle between light and dark themes
                    </Typography>
                  </Box>
                }
              />
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom fontWeight={600}>
                Session
              </Typography>
              <Divider sx={{ mb: 2 }} />

              <FormControl fullWidth sx={{ mb: 2 }}>
                <InputLabel>Session Timeout</InputLabel>
                <Select
                  value={timeoutMinutes}
                  label="Session Timeout"
                  onChange={(e) => setTimeoutMinutes(Number(e.target.value))}
                >
                  <MenuItem value={15}>15 minutes</MenuItem>
                  <MenuItem value={30}>30 minutes</MenuItem>
                  <MenuItem value={60}>1 hour</MenuItem>
                  <MenuItem value={120}>2 hours</MenuItem>
                </Select>
              </FormControl>

              <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 2 }}>
                Automatically log out after period of inactivity
              </Typography>

              <Button
                variant="outlined"
                startIcon={<Save />}
                onClick={handleSaveTimeout}
              >
                Save
              </Button>

              {saved && (
                <Alert severity="success" sx={{ mt: 2 }}>
                  Settings saved successfully
                </Alert>
              )}
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom fontWeight={600}>
                Query History
              </Typography>
              <Divider sx={{ mb: 2 }} />

              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                <Typography variant="body2" color="text.secondary">
                  Stored queries:
                </Typography>
                <Chip label={queries.length} size="small" color="primary" />
              </Box>

              <Button
                variant="outlined"
                color="error"
                startIcon={<Refresh />}
                onClick={handleClearHistory}
                disabled={queries.length === 0}
              >
                Clear History
              </Button>

              {queries.length === 0 && (
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
                  No queries in history
                </Typography>
              )}
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom fontWeight={600}>
                About
              </Typography>
              <Divider sx={{ mb: 2 }} />

              <Typography variant="body2" gutterBottom>
                <strong>CDSS Clinical Decision Support System</strong>
              </Typography>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                Version: 0.1.0
              </Typography>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                Powered by Azure OpenAI (GPT-4o)
              </Typography>

              <Divider sx={{ my: 2 }} />

              <Typography variant="caption" color="text.secondary">
                This system provides clinical decision support only. It is not a substitute for professional medical judgment.
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
}
