import React, { useState } from 'react';
import {
  Dialog, DialogContent, DialogActions,
  TextField, Button, Box, Typography, Alert, InputAdornment,
  IconButton, Chip
} from '@mui/material';
import Visibility from '@mui/icons-material/Visibility';
import VisibilityOff from '@mui/icons-material/VisibilityOff';
import ShieldIcon from '@mui/icons-material/Shield';
import LockOutlinedIcon from '@mui/icons-material/LockOutlined';

export default function LoginModal({ open, onLogin, error, loading }) {
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
      PaperProps={{
        sx: {
          bgcolor: '#0d0d0d',
          color: '#f2f2f2',
          border: '1px solid #232323',
          borderRadius: 2,
          boxShadow: '0 8px 32px rgba(0,0,0,0.8)'
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
            color: '#00e676',
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
        <Typography variant="body2" sx={{ color: '#8a8a8a', mt: 0.5 }}>
          Secure Video Analytics & Forensic Intelligence
        </Typography>
      </Box>

      <form onSubmit={handleSubmit}>
        <DialogContent sx={{ pt: 0, pb: 2 }}>
          {error && (
            <Alert severity="error" sx={{ mb: 2, bgcolor: 'rgba(255, 23, 68, 0.15)', color: '#ff1744' }}>
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
            sx={{
              mb: 2,
              '& .MuiOutlinedInput-root': { color: '#fff', '& fieldset': { borderColor: '#333' } },
              '& .MuiInputLabel-root': { color: '#888' }
            }}
          />

          <TextField
            fullWidth
            label="Password"
            type={showPassword ? 'text' : 'password'}
            variant="outlined"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={loading}
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton
                    onClick={() => setShowPassword(!showPassword)}
                    edge="end"
                    sx={{ color: '#888' }}
                  >
                    {showPassword ? <VisibilityOff /> : <Visibility />}
                  </IconButton>
                </InputAdornment>
              )
            }}
            sx={{
              mb: 2,
              '& .MuiOutlinedInput-root': { color: '#fff', '& fieldset': { borderColor: '#333' } },
              '& .MuiInputLabel-root': { color: '#888' }
            }}
          />

          {isDemoMode && (
            <Box sx={{ mt: 2, pt: 2, borderTop: '1px dashed #333' }}>
              <Typography variant="caption" sx={{ color: '#00e676', display: 'block', mb: 1, fontWeight: 600 }}>
                DEMO MODE — Quick Login Presets
              </Typography>
              <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                <Chip
                  label="Admin"
                  size="small"
                  onClick={() => handleQuickSelect('admin', 'Admin@123456')}
                  sx={{ bgcolor: '#1e293b', color: '#38bdf8', cursor: 'pointer', '&:hover': { bgcolor: '#334155' } }}
                />
                <Chip
                  label="Operator"
                  size="small"
                  onClick={() => handleQuickSelect('operator', 'Operator@123456')}
                  sx={{ bgcolor: '#1e293b', color: '#4ade80', cursor: 'pointer', '&:hover': { bgcolor: '#334155' } }}
                />
                <Chip
                  label="Viewer"
                  size="small"
                  onClick={() => handleQuickSelect('viewer', 'Viewer@123456')}
                  sx={{ bgcolor: '#1e293b', color: '#facc15', cursor: 'pointer', '&:hover': { bgcolor: '#334155' } }}
                />
              </Box>
            </Box>
          )}
        </DialogContent>

        <DialogActions sx={{ p: 3, pt: 1 }}>
          <Button
            type="submit"
            fullWidth
            variant="contained"
            disabled={loading || !username || !password}
            startIcon={<LockOutlinedIcon />}
            sx={{
              bgcolor: '#00e676',
              color: '#000',
              fontWeight: 700,
              py: 1.2,
              '&:hover': { bgcolor: '#00c853' }
            }}
          >
            {loading ? 'Authenticating...' : 'Sign In'}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
