import React, { useState } from 'react';
import {
  Dialog, DialogContent, DialogActions,
  TextField, Button, Box, Typography, Alert, InputAdornment,
  IconButton, Chip
} from '@mui/material';
import { useTheme } from '@mui/material/styles';
import Visibility from '@mui/icons-material/Visibility';
import VisibilityOff from '@mui/icons-material/VisibilityOff';
import ShieldIcon from '@mui/icons-material/Shield';
import LockOutlinedIcon from '@mui/icons-material/LockOutlined';

export default function LoginModal({ open, onLogin, error, loading }) {
  const theme = useTheme();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  const isDemoMode = import.meta.env.VITE_DEMO_MODE === 'true';

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!username || !password) return;
    onLogin(username, password);
  };

  const handleQuickSelect = (u, p) => {
    setUsername(u);
    setPassword(p);
    onLogin(u, p);
  };

  return (
    <Dialog
      open={open}
      fullWidth
      maxWidth="xs"
      slotProps={{
        paper: {
          sx: {
            bgcolor: 'background.paper',
            color: 'text.primary',
            border: '1px solid',
            borderColor: 'divider',
            borderRadius: 2,
            boxShadow: 8
          }
        }
      }}
    >
      <Box sx={{ p: 3, textAlign: 'center' }}>
        <Box
          sx={{
            width: 48,
            height: 48,
            borderRadius: '50%',
            bgcolor: 'rgba(0, 230, 118, 0.1)',
            color: 'primary.main',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            mb: 1.5
          }}
        >
          <ShieldIcon fontSize="medium" />
        </Box>
        <Typography variant="h5" sx={{ fontWeight: 700, letterSpacing: 1 }}>
          SYBAU VMS
        </Typography>
        <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.5 }}>
          Secure Video Analytics & Forensic Intelligence
        </Typography>
        {isDemoMode && (
          <Box sx={{ display: 'flex', gap: 1, justifyContent: 'center', mt: 1.5 }}>
            <Chip label="Admin" size="small" onClick={() => handleQuickSelect('admin', 'Admin@123456')} sx={{ bgcolor: 'action.hover', color: 'primary.main', cursor: 'pointer' }} />
            <Chip label="Operator" size="small" onClick={() => handleQuickSelect('operator', 'Operator@123456')} sx={{ bgcolor: 'action.hover', color: 'info.main', cursor: 'pointer' }} />
            <Chip label="Viewer" size="small" onClick={() => handleQuickSelect('viewer', 'Viewer@123456')} sx={{ bgcolor: 'action.hover', color: 'secondary.main', cursor: 'pointer' }} />
          </Box>
        )}
      </Box>

      <form onSubmit={handleSubmit}>
        <DialogContent sx={{ pt: 0, pb: 2 }}>
          {error && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {error}
            </Alert>
          )}

          <TextField
            autoFocus
            fullWidth
            label="Username"
            variant="outlined"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            disabled={loading}
            sx={{ mb: 2 }}
          />

          <TextField
            fullWidth
            label="Password"
            type={showPassword ? 'text' : 'password'}
            variant="outlined"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={loading}
            slotProps={{
              input: {
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton
                      onClick={() => setShowPassword(!showPassword)}
                      edge="end"
                      aria-label={showPassword ? "Hide password" : "Show password"}
                    >
                      {showPassword ? <VisibilityOff /> : <Visibility />}
                    </IconButton>
                  </InputAdornment>
                )
              }
            }}
            sx={{ mb: 2 }}
          />
        </DialogContent>

        <DialogActions sx={{ p: 3, pt: 1 }}>
          <Button
            type="submit"
            fullWidth
            variant="contained"
            disabled={loading || !username || !password}
            startIcon={<LockOutlinedIcon />}
            sx={{
              py: 1.2,
              fontWeight: 700
            }}
          >
            {loading ? 'Authenticating...' : 'Sign In'}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}

