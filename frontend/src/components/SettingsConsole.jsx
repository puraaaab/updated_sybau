import React, { useState } from 'react';
import {
  Box, Typography, Grid, Paper, FormControl, InputLabel, Select, MenuItem,
  FormControlLabel, Switch, Slider, Button, TextField, Divider, Table, TableBody,
  TableCell, TableContainer, TableHead, TableRow, IconButton, Alert, Chip,
  List, ListItem, ListItemButton, ListItemText, ListItemIcon,
  Dialog, DialogTitle, DialogContent, DialogActions
} from '@mui/material';
import PaletteIcon from '@mui/icons-material/Palette';
import TvIcon from '@mui/icons-material/Tv';
import SecurityIcon from '@mui/icons-material/Security';
import VolumeUpIcon from '@mui/icons-material/VolumeUp';
import NetworkCheckIcon from '@mui/icons-material/NetworkCheck';
import PersonAddIcon from '@mui/icons-material/PersonAdd';
import DeleteIcon from '@mui/icons-material/Delete';
import RefreshIcon from '@mui/icons-material/Refresh';
import CheckIcon from '@mui/icons-material/Check';
import CloseIcon from '@mui/icons-material/Close';
import VideocamIcon from '@mui/icons-material/Videocam';
import CameraManagement from './CameraManagement';

export default function SettingsConsole({
  settings,
  onChangeSettings,
  token,
  role,
  usersList = [],
  requests = [],
  onUpdateRole,
  onUpdateStatus,
  onResetPassword,
  onSoftDelete,
  onHardDelete,
  onResolveRequest,
  onTriggerScan,
  scanning,
  discovered = [],
  resolvedUrls = [],
  onResolveStreamUri,
  _onRegisterDiscovered,
  onReloadUsers,
  onReloadRequests
}) {
  const [activeSection, setActiveSection] = useState('appearance');

  // Directory Management States
  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newRole, setNewRole] = useState('viewer');
  const [userError, setUserError] = useState('');
  const [userSuccess, setUserSuccess] = useState('');
  const [resetPwdUserId, setResetPwdUserId] = useState(null);
  const [resetPwdText, setResetPwdText] = useState('');
  const [confirmAdminPass, setConfirmAdminPass] = useState('');
  const [hardDeleteUserId, setHardDeleteUserId] = useState(null);
  const [softDeleteUser, setSoftDeleteUser] = useState(null);

  // ONVIF Discovery Settings
  const [onvifUser, setOnvifUser] = useState('');
  const [onvifPass, setOnvifPass] = useState('');

  const handleCreateUser = (e) => {
    e.preventDefault();
    setUserError('');
    setUserSuccess('');

    fetch('/api/v1/admin/users', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({ username: newUsername, password: newPassword, role: newRole })
    })
      .then(async res => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'User creation failed');
        return data;
      })
      .then(() => {
        setUserSuccess(`User ${newUsername} successfully created.`);
        setNewUsername('');
        setNewPassword('');
        setNewRole('viewer');
        if (onReloadUsers) onReloadUsers();
      })
      .catch(err => setUserError(err.message));
  };

  const handleLocalResetPassword = (userId) => {
    if (!resetPwdText) return;
    onResetPassword(userId, resetPwdText);
    setResetPwdUserId(null);
    setResetPwdText('');
  };

  const handleLocalHardDelete = (userId) => {
    if (!confirmAdminPass) return;
    onHardDelete(userId, confirmAdminPass);
    setHardDeleteUserId(null);
    setConfirmAdminPass('');
  };

  const menuSections = [
    { id: 'appearance', label: 'Appearance & UI Theme', icon: <PaletteIcon /> },
    { id: 'video', label: 'Live Grid & Video Scaling', icon: <TvIcon /> },
    { id: 'network', label: 'ONVIF Probe & Network Scan', icon: <NetworkCheckIcon /> },
    { id: 'alerts', label: 'Watchlist & Audible Alarms', icon: <VolumeUpIcon /> },
    { id: 'security', label: 'RBAC Directory Console', icon: <SecurityIcon />, adminOnly: true },
    { id: 'cameras', label: 'Camera Management', icon: <VideocamIcon />, adminOnly: true }
  ];

  const safeUsersList = Array.isArray(usersList) ? usersList : [];
  const safeRequests = Array.isArray(requests) ? requests : [];

  return (
    <Box sx={{ display: 'flex', height: '100%', minHeight: 'calc(100vh - 180px)', gap: 3, flexWrap: { xs: 'wrap', md: 'nowrap' } }}>
      {/* Settings Navigation */}
      <Paper variant="outlined" sx={{ width: { xs: '100%', md: 280 }, flexShrink: 0, p: 1, height: 'fit-content' }}>
        <Typography variant="subtitle2" sx={{ px: 2, py: 1.5, fontWeight: 'bold', borderBottom: '1px solid', borderColor: 'divider', mb: 1, letterSpacing: '0.5px' }}>
          SYSTEM SETTINGS CONSOLE
        </Typography>
        <List>
          {menuSections.map((sec) => {
            if (sec.adminOnly && role !== 'admin') return null;
            const isActive = activeSection === sec.id;
            return (
              <ListItem key={sec.id} disablePadding>
                <ListItemButton
                  selected={isActive}
                  onClick={() => setActiveSection(sec.id)}
                  sx={{
                    py: 1.2,
                    px: 2,
                    borderRadius: '4px',
                    '&.Mui-selected': {
                      backgroundColor: 'primary.main',
                      color: 'primary.contrastText',
                      '& .MuiListItemIcon-root': { color: 'primary.contrastText' }
                    }
                  }}
                >
                  <ListItemIcon sx={{ minWidth: 36, color: isActive ? 'primary.contrastText' : 'inherit' }}>{sec.icon}</ListItemIcon>
                  <ListItemText primary={sec.label} slotProps={{ primary: { variant: 'body2', sx: { fontWeight: isActive ? 'bold' : 'normal', fontSize: '0.8rem' } } }} />
                </ListItemButton>
              </ListItem>
            );
          })}
        </List>
      </Paper>

      {/* Settings Workspace */}
      <Paper variant="outlined" sx={{ flexGrow: 1, p: 3, minWidth: 0, overflowY: 'auto' }}>
        {activeSection === 'appearance' && (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            <Box>
              <Typography variant="subtitle1" fontWeight="bold">Appearance Settings</Typography>
              <Typography variant="caption" color="text.secondary">Configure the core color themes, typography, and density levels of the dashboard.</Typography>
            </Box>
            <Divider />

            <Grid container spacing={3}>
              <Grid size={{ xs: 12, sm: 6 }}>
                <FormControl fullWidth size="small">
                  <InputLabel id="theme-mode-label">Interface Theme Preset</InputLabel>
                  <Select
                    labelId="theme-mode-label"
                    value={settings.themeMode}
                    label="Interface Theme Preset"
                    onChange={(e) => onChangeSettings({ themeMode: e.target.value })}
                  >
                    <MenuItem value="stark-dark">STARK DARK (Pure B&W Monochrome)</MenuItem>
                    <MenuItem value="stark-light">STARK LIGHT (Monochrome Light)</MenuItem>
                    <MenuItem value="emerald">TACTICAL EMERALD HUD (Emerald Green)</MenuItem>
                    <MenuItem value="amber">RETRO CRT AMBER HUD (Phosphor Amber)</MenuItem>
                  </Select>
                </FormControl>
              </Grid>

              <Grid size={{ xs: 12, sm: 6 }}>
                <FormControl fullWidth size="small">
                  <InputLabel id="density-label">Layout Padding Density</InputLabel>
                  <Select
                    labelId="density-label"
                    value={settings.density}
                    label="Layout Padding Density"
                    onChange={(e) => onChangeSettings({ density: e.target.value })}
                  >
                    <MenuItem value="comfortable">Comfortable Layout</MenuItem>
                    <MenuItem value="compact">Compact Tactical Grid</MenuItem>
                  </Select>
                </FormControl>
              </Grid>

              <Grid size={{ xs: 12, sm: 6 }}>
                <FormControl fullWidth size="small">
                  <InputLabel id="font-family-label">Interface Font Family</InputLabel>
                  <Select
                    labelId="font-family-label"
                    value={settings.fontFamily || 'Inter'}
                    label="Interface Font Family"
                    onChange={(e) => onChangeSettings({ fontFamily: e.target.value })}
                  >
                    <MenuItem value="Inter">Inter (Neo-grotesque sans)</MenuItem>
                    <MenuItem value="Outfit">Outfit (Geometric display)</MenuItem>
                    <MenuItem value="Space Grotesk">Space Grotesk (Tactical display)</MenuItem>
                    <MenuItem value="monospace">JetBrains Mono / monospace</MenuItem>
                  </Select>
                </FormControl>
              </Grid>

              <Grid size={{ xs: 12, sm: 6 }}>
                <FormControl fullWidth size="small">
                  <InputLabel id="edge-roundness-label">Component Edge Roundness</InputLabel>
                  <Select
                    labelId="edge-roundness-label"
                    value={settings.borderRadius === undefined ? 0 : settings.borderRadius}
                    label="Component Edge Roundness"
                    onChange={(e) => onChangeSettings({ borderRadius: e.target.value })}
                  >
                    <MenuItem value={0}>0px (Pure Sharp Tactical Borders)</MenuItem>
                    <MenuItem value={4}>4px (Slight Rounded Soft Corners)</MenuItem>
                    <MenuItem value={12}>12px (Vivid High Rounded Modern Corners)</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
            </Grid>
          </Box>
        )}

        {activeSection === 'video' && (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            <Box>
              <Typography variant="subtitle1" fontWeight="bold">Video Stream Scaling & Grid Config</Typography>
              <Typography variant="caption" color="text.secondary">Configure how camera feeds render dynamically within grid slots without compression or distortion.</Typography>
            </Box>
            <Divider />

            <Grid container spacing={3}>
              <Grid size={{ xs: 12, sm: 6 }}>
                <FormControl fullWidth size="small">
                  <InputLabel id="frame-mode-label">Stream Sizing Frame Mode</InputLabel>
                  <Select
                    labelId="frame-mode-label"
                    value={settings.frameMode}
                    label="Stream Sizing Frame Mode"
                    onChange={(e) => onChangeSettings({ frameMode: e.target.value })}
                  >
                    <MenuItem value="dynamic">Dynamic Aspect Ratio (Respect source resolution dimensions)</MenuItem>
                    <MenuItem value="fixed-16-9">Force 16:9 Standard widescreen aspect ratio</MenuItem>
                    <MenuItem value="fixed-4-3">Force 4:3 Standard CCTV legacy aspect ratio</MenuItem>
                    <MenuItem value="stretch">Fill and Stretch to Frame (Compress/Distort to fit)</MenuItem>
                  </Select>
                </FormControl>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
                  * In <strong>Dynamic Aspect Ratio</strong> mode, each camera block sizes its viewport height automatically to match the true HLS/WebRTC source metadata. This prevents cropped frames or letterboxing.
                </Typography>
              </Grid>

              <Grid size={{ xs: 12, sm: 6 }}>
                <FormControl fullWidth size="small">
                  <InputLabel id="grid-cols-label">Default Live Grid Columns</InputLabel>
                  <Select
                    labelId="grid-cols-label"
                    value={settings.gridCols}
                    label="Default Live Grid Columns"
                    onChange={(e) => onChangeSettings({ gridCols: e.target.value })}
                  >
                    <MenuItem value="auto">Auto-Flow responsive layout sizing</MenuItem>
                    <MenuItem value={1}>Single Channel Focus (1 Column)</MenuItem>
                    <MenuItem value={2}>Classic 2x2 Matrix view (2 Columns)</MenuItem>
                    <MenuItem value={3}>Professional Matrix (3 Columns)</MenuItem>
                    <MenuItem value={4}>Dense NOC Console (4 Columns)</MenuItem>
                  </Select>
                </FormControl>
              </Grid>

              <Grid size={{ xs: 12 }}>
                <Typography variant="body2" color="text.primary" sx={{ mb: 1, fontWeight: 'bold' }}>Diagnostics telemetry polling interval</Typography>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                  <Slider
                    value={settings.refreshRate || 4000}
                    min={1000}
                    max={15000}
                    step={1000}
                    valueLabelDisplay="auto"
                    onChange={(e, val) => onChangeSettings({ refreshRate: val })}
                    sx={{ flexGrow: 1, maxWidth: 400 }}
                  />
                  <Typography variant="body2" color="text.secondary">{(settings.refreshRate || 4000) / 1000}s</Typography>
                </Box>
              </Grid>
            </Grid>
          </Box>
        )}

        {activeSection === 'network' && (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            <Box>
              <Typography variant="subtitle1" fontWeight="bold">ONVIF Scan & Network Probe Controls</Typography>
              <Typography variant="caption" color="text.secondary">Probe the local subnets using WS-Discovery to detect network CCTV IP streams.</Typography>
            </Box>
            <Divider />

            <Grid container spacing={3}>
              <Grid size={{ xs: 12, md: 4 }}>
                <Paper variant="outlined" sx={{ p: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
                  <Typography variant="subtitle2" fontWeight="bold">CREDENTIALS GATE</Typography>
                  <TextField
                    label="ONVIF Username"
                    size="small"
                    value={onvifUser}
                    onChange={e => setOnvifUser(e.target.value)}
                    placeholder="admin"
                  />
                  <TextField
                    label="ONVIF Password"
                    type="password"
                    size="small"
                    value={onvifPass}
                    onChange={e => setOnvifPass(e.target.value)}
                    placeholder="Ã¢â‚¬Â¢Ã¢â‚¬Â¢Ã¢â‚¬Â¢Ã¢â‚¬Â¢Ã¢â‚¬Â¢Ã¢â‚¬Â¢Ã¢â‚¬Â¢Ã¢â‚¬Â¢"
                  />
                  <Button
                    variant="contained"
                    onClick={onTriggerScan}
                    disabled={scanning}
                    sx={{ mt: 1 }}
                  >
                    {scanning ? 'SCANNING SUBNET...' : 'RUN WS-DISCOVERY SCAN'}
                  </Button>
                </Paper>
              </Grid>

              <Grid size={{ xs: 12, md: 8 }}>
                <Paper variant="outlined" sx={{ p: 2, height: '100%', minHeight: 250, display: 'flex', flexDirection: 'column' }}>
                  <Typography variant="subtitle2" fontWeight="bold" sx={{ mb: 2, borderBottom: '1px solid', borderColor: 'divider', pb: 1 }}>
                    DISCOVERED SUBNET NODES
                  </Typography>

                  <TableContainer sx={{ flexGrow: 1, maxHeight: 300 }}>
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell sx={{ fontWeight: 'bold' }}>IP ADDRESS</TableCell>
                          <TableCell sx={{ fontWeight: 'bold' }}>MODEL IDENTIFIER</TableCell>
                          <TableCell sx={{ fontWeight: 'bold' }}>STREAM ENDPOINT URL</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {discovered.length === 0 ? (
                          <TableRow>
                            <TableCell colSpan={3} align="center" sx={{ py: 6, color: 'text.secondary' }}>
                              {scanning ? 'WAITING FOR WS PROBE...' : '[ NETWORK PROBE STANDBY ]'}
                            </TableCell>
                          </TableRow>
                        ) : (
                          discovered.map((dev, idx) => {
                            const rtspUrl = resolvedUrls[idx];
                            return (
                              <TableRow key={idx} hover>
                                <TableCell>{dev.ip}</TableCell>
                                <TableCell>{dev.name}</TableCell>
                                <TableCell>
                                  {rtspUrl ? (
                                    <Typography variant="caption" color="primary">{rtspUrl}</Typography>
                                  ) : (
                                    <Button
                                      size="small"
                                      variant="outlined"
                                      onClick={() => onResolveStreamUri(dev, idx, onvifUser, onvifPass)}
                                    >
                                      RESOLVE STREAM
                                    </Button>
                                  )}
                                </TableCell>
                              </TableRow>
                            );
                          })
                        )}
                      </TableBody>
                    </Table>
                  </TableContainer>
                </Paper>
              </Grid>
            </Grid>
          </Box>
        )}

        {activeSection === 'alerts' && (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            <Box>
              <Typography variant="subtitle1" fontWeight="bold">Watchlist Detections & Audible Warnings</Typography>
              <Typography variant="caption" color="text.secondary">Configure notifications, target profile matching alerts, and console system audio chiming.</Typography>
            </Box>
            <Divider />

            <Grid container spacing={3}>
              <Grid size={{ xs: 12, sm: 6 }}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={settings.soundEnabled}
                      onChange={(e) => onChangeSettings({ soundEnabled: e.target.checked })}
                      color="primary"
                    />
                  }
                  label="Play Synth Warning Alarm on POI Match"
                />
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
                  Synthesizes immediate dual-tone chime alerts on the client machine using Web Audio API when a face matching the Watchlist registry is processed.
                </Typography>
              </Grid>

              <Grid size={{ xs: 12, sm: 6 }}>
                <FormControl fullWidth size="small">
                  <InputLabel id="alarm-severity-label">Alert Banner Autohide Delay</InputLabel>
                  <Select
                    labelId="alarm-severity-label"
                    value={settings.alertTimeout || 6000}
                    label="Alert Banner Autohide Delay"
                    onChange={(e) => onChangeSettings({ alertTimeout: e.target.value })}
                  >
                    <MenuItem value={3000}>3 Seconds (Quick fade)</MenuItem>
                    <MenuItem value={6000}>6 Seconds (Standard)</MenuItem>
                    <MenuItem value={15000}>15 Seconds (Persistent)</MenuItem>
                    <MenuItem value={0}>Never Auto-dismiss (Manual close only)</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
            </Grid>
          </Box>
        )}

        {activeSection === 'security' && role === 'admin' && (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <Box>
              <Typography variant="subtitle1" fontWeight="bold">RBAC Directory Console</Typography>
              <Typography variant="caption" color="text.secondary">Register, suspend, audit, or permanently remove operators and viewers inside the VMS database.</Typography>
            </Box>
            <Divider />

            <Grid container spacing={3}>
              <Grid size={{ xs: 12, md: 4 }}>
                <Paper variant="outlined" sx={{ p: 2 }}>
                  <Typography variant="subtitle2" fontWeight="bold" sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 1, borderBottom: '1px solid', borderColor: 'divider', pb: 1 }}>
                    <PersonAddIcon fontSize="small" /> ADD OPERATIONAL USER
                  </Typography>
                  <Box component="form" onSubmit={handleCreateUser} sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                    <TextField label="User Account ID" size="small" required value={newUsername} onChange={(e) => setNewUsername(e.target.value)} placeholder="e.g. m_ross" />
                    <TextField label="Password" type="password" size="small" required value={newPassword} onChange={(e) => setNewPassword(e.target.value)} placeholder="Ã¢â‚¬Â¢Ã¢â‚¬Â¢Ã¢â‚¬Â¢Ã¢â‚¬Â¢Ã¢â‚¬Â¢Ã¢â‚¬Â¢Ã¢â‚¬Â¢Ã¢â‚¬Â¢" />
                    <FormControl size="small" fullWidth>
                      <InputLabel id="add-role-select-label">Access Level Role</InputLabel>
                      <Select labelId="add-role-select-label" value={newRole} label="Access Level Role" onChange={(e) => setNewRole(e.target.value)}>
                        <MenuItem value="viewer">VIEWER (Read-only feeds)</MenuItem>
                        <MenuItem value="operator">OPERATOR (Read + Forensic Export)</MenuItem>
                        <MenuItem value="admin">ADMINISTRATOR (Full operations)</MenuItem>
                      </Select>
                    </FormControl>

                    {userError && <Alert severity="error">{userError}</Alert>}
                    {userSuccess && <Alert severity="success">{userSuccess}</Alert>}

                    <Button type="submit" variant="contained" startIcon={<PersonAddIcon />}>
                      Create Account
                    </Button>
                  </Box>
                </Paper>
              </Grid>

              <Grid size={{ xs: 12, md: 8 }}>
                <Paper variant="outlined" sx={{ p: 2, display: 'flex', flexDirection: 'column' }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2, borderBottom: '1px solid', borderColor: 'divider', pb: 1 }}>
                    <Typography variant="subtitle2" fontWeight="bold">DIRECTORY REGISTRY</Typography>
                    <IconButton size="small" onClick={onReloadUsers}><RefreshIcon fontSize="small" /></IconButton>
                  </Box>

                  <TableContainer sx={{ maxHeight: 300 }}>
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell sx={{ fontWeight: 'bold' }}>USER</TableCell>
                          <TableCell sx={{ fontWeight: 'bold' }}>ROLE</TableCell>
                          <TableCell sx={{ fontWeight: 'bold' }}>STATUS</TableCell>
                          <TableCell align="center" sx={{ fontWeight: 'bold' }}>ACTIONS</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {safeUsersList.length === 0 ? (
                          <TableRow>
                            <TableCell colSpan={4} align="center" sx={{ py: 4, color: 'text.secondary' }}>NO USERS REGISTERED IN DIRECTORY</TableCell>
                          </TableRow>
                        ) : (
                          safeUsersList.map((u) => (
                            <TableRow key={u.id} hover sx={{ opacity: u.deleted_at ? 0.4 : 1 }}>
                              <TableCell sx={{ fontWeight: 'bold' }}>{u.username} {u.deleted_at && <Typography component="span" variant="caption" color="error"> (DELETED)</Typography>}</TableCell>
                              <TableCell>
                                <Select
                                  value={u.role || 'viewer'}
                                  disabled={!!u.deleted_at}
                                  onChange={(e) => onUpdateRole(u.id, e.target.value)}
                                  size="small"
                                  variant="standard"
                                >
                                  <MenuItem value="viewer">VIEWER</MenuItem>
                                  <MenuItem value="operator">OPERATOR</MenuItem>
                                  <MenuItem value="admin">ADMIN</MenuItem>
                                </Select>
                              </TableCell>
                              <TableCell>
                                <Select
                                  value={u.status || 'active'}
                                  disabled={!!u.deleted_at}
                                  onChange={(e) => onUpdateStatus(u.id, e.target.value)}
                                  size="small"
                                  variant="standard"
                                  sx={{ color: u.status === 'active' ? 'success.main' : 'error.main', fontWeight: 'bold' }}
                                >
                                  <MenuItem value="active">ACTIVE</MenuItem>
                                  <MenuItem value="suspended">SUSPENDED</MenuItem>
                                </Select>
                              </TableCell>
                              <TableCell align="center">
                                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 1 }}>
                                  <IconButton
                                    size="small"
                                    disabled={!!u.deleted_at}
                                    onClick={() => setResetPwdUserId(resetPwdUserId === u.id ? null : u.id)}
                                    title="Reset Password"
                                    aria-label={`Reset password for ${u.username}`}
                                  >
                                    <RefreshIcon fontSize="small" />
                                  </IconButton>
                                  {!u.deleted_at && (
                                    <IconButton
                                      size="small"
                                      color="error"
                                      onClick={() => setSoftDeleteUser(u)}
                                      title="Disable / Deactivate"
                                      aria-label={`Deactivate user ${u.username}`}
                                    >
                                      <DeleteIcon fontSize="small" />
                                    </IconButton>
                                  )}
                                  <IconButton
                                    size="small"
                                    color="warning"
                                    onClick={() => setHardDeleteUserId(hardDeleteUserId === u.id ? null : u.id)}
                                    title="Purge Record"
                                    aria-label={`Permanently purge user ${u.username}`}
                                  >
                                    <DeleteIcon fontSize="small" />
                                  </IconButton>
                                </Box>
                              </TableCell>
                            </TableRow>
                          ))
                        )}
                      </TableBody>
                    </Table>
                  </TableContainer>
                </Paper>
              </Grid>

              {/* Password Reset Section */}
              {resetPwdUserId && (
                <Grid size={{ xs: 12 }}>
                  <Paper variant="outlined" sx={{ p: 2, display: 'flex', alignItems: 'center', gap: 2 }}>
                    <Typography variant="body2" sx={{ fontWeight: 'bold' }}>New Password for Target User:</Typography>
                    <TextField
                      type="password"
                      size="small"
                      placeholder="Ã¢â‚¬Â¢Ã¢â‚¬Â¢Ã¢â‚¬Â¢Ã¢â‚¬Â¢Ã¢â‚¬Â¢Ã¢â‚¬Â¢Ã¢â‚¬Â¢Ã¢â‚¬Â¢"
                      value={resetPwdText}
                      onChange={(e) => setResetPwdText(e.target.value)}
                    />
                    <Button variant="contained" onClick={() => handleLocalResetPassword(resetPwdUserId)}>Confirm Password Change</Button>
                    <Button variant="outlined" onClick={() => setResetPwdUserId(null)}>Cancel</Button>
                  </Paper>
                </Grid>
              )}

              {/* Hard Delete Purge Section */}
              {hardDeleteUserId && (
                <Grid size={{ xs: 12 }}>
                  <Alert severity="warning" sx={{ p: 2 }}>
                    <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 'bold' }}>ERASE DATA ROW PERMANENTLY?</Typography>
                    <Typography variant="body2" sx={{ mb: 2 }}>This will remove user metadata permanently from SQL databases. Re-enter your current Admin Password to execute.</Typography>
                    <Box sx={{ display: 'flex', gap: 2 }}>
                      <TextField
                        type="password"
                        size="small"
                        placeholder="Admin confirmation password"
                        value={confirmAdminPass}
                        onChange={(e) => setConfirmAdminPass(e.target.value)}
                      />
                      <Button variant="contained" color="error" onClick={() => handleLocalHardDelete(hardDeleteUserId)}>PURGE RECORD</Button>
                      <Button variant="outlined" color="inherit" onClick={() => setHardDeleteUserId(null)}>Cancel</Button>
                    </Box>
                  </Alert>
                </Grid>
              )}

              {/* Elevation Queue */}
              <Grid size={{ xs: 12 }}>
                <Paper variant="outlined" sx={{ p: 2 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2, borderBottom: '1px solid', borderColor: 'divider', pb: 1 }}>
                    <Typography variant="subtitle2" fontWeight="bold">OPERATIONAL ELEVATION REQUESTS</Typography>
                    <IconButton size="small" onClick={onReloadRequests}><RefreshIcon fontSize="small" /></IconButton>
                  </Box>

                  <TableContainer>
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell sx={{ fontWeight: 'bold' }}>USER</TableCell>
                          <TableCell sx={{ fontWeight: 'bold' }}>REQUEST TYPE</TableCell>
                          <TableCell sx={{ fontWeight: 'bold' }}>EXPLANATION</TableCell>
                          <TableCell sx={{ fontWeight: 'bold' }}>STATUS</TableCell>
                          <TableCell align="center" sx={{ fontWeight: 'bold' }}>ACTION</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {safeRequests.length === 0 ? (
                          <TableRow>
                            <TableCell colSpan={5} align="center" sx={{ py: 4, color: 'text.secondary' }}>NO PENDING ELEVATION ACTIONS</TableCell>
                          </TableRow>
                        ) : (
                          safeRequests.map((r) => (
                            <TableRow key={r.id} hover>
                              <TableCell sx={{ fontWeight: 'bold' }}>{r.username}</TableCell>
                              <TableCell>
                                <Chip label={r.request_type.toUpperCase().replace('_', ' ')} size="small" color={r.request_type === 'role_elevation' ? 'primary' : 'warning'} />
                              </TableCell>
                              <TableCell>{r.details}</TableCell>
                              <TableCell>{r.status.toUpperCase()}</TableCell>
                              <TableCell align="center">
                                {r.status === 'pending' ? (
                                  <Box sx={{ display: 'flex', gap: 1, justifyContent: 'center' }}>
                                    <IconButton size="small" color="success" onClick={() => onResolveRequest(r.id, r.username, 'approved')}><CheckIcon fontSize="small" /></IconButton>
                                    <IconButton size="small" color="error" onClick={() => onResolveRequest(r.id, r.username, 'rejected')}><CloseIcon fontSize="small" /></IconButton>
                                  </Box>
                                ) : (
                                  <Typography variant="caption" color="text.secondary">CLOSED</Typography>
                                )}
                              </TableCell>
                            </TableRow>
                          ))
                        )}
                      </TableBody>
                    </Table>
                  </TableContainer>
                </Paper>
              </Grid>
            </Grid>
          </Box>
        )}

        {activeSection === 'cameras' && (
          <CameraManagement token={token} />
        )}
      </Paper>

      {/* Soft Delete Confirmation Dialog (Issue 6) */}
      <Dialog open={Boolean(softDeleteUser)} onClose={() => setSoftDeleteUser(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Confirm User Deactivation</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            Are you sure you want to deactivate user <strong>"{softDeleteUser?.username}"</strong>? They will be unable to log in until reactivated by an admin.
          </Typography>
        </DialogContent>
        <DialogActions sx={{ p: 2 }}>
          <Button onClick={() => setSoftDeleteUser(null)} variant="outlined">Cancel</Button>
          <Button
            onClick={() => {
              if (softDeleteUser) {
                onSoftDelete(softDeleteUser.id);
                setSoftDeleteUser(null);
              }
            }}
            color="error"
            variant="contained"
          >
            Deactivate User
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}


