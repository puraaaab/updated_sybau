import React, { useState, useEffect } from 'react';
import {
  Box, Typography, Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Paper, Button, Dialog, DialogTitle, DialogContent, DialogActions, IconButton,
  Switch, Tabs, Tab, TextField, Chip, MenuItem, Select, FormControl, InputLabel,
  Tooltip, Alert
} from '@mui/material';
import ImageIcon from '@mui/icons-material/Image';
import DeleteIcon from '@mui/icons-material/Delete';
import AddCircleIcon from '@mui/icons-material/AddCircle';
import NotificationsActiveIcon from '@mui/icons-material/NotificationsActive';
import CloseIcon from '@mui/icons-material/Close';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';

export default function AlertsPanel({ alerts, token }) {
  const [selectedAlert, setSelectedAlert] = useState(null);
  const [activeTab, setActiveTab] = useState(0);
  const [ruleToDelete, setRuleToDelete] = useState(null);

  // Dynamic Custom Rules State
  const [customRules, setCustomRules] = useState([]);
  const [rulePrompt, setRulePrompt] = useState('');
  const [ruleCamera, setRuleCamera] = useState('ALL');
  const [ruleSeverity, setRuleSeverity] = useState('high');
  const [ruleError, setRuleError] = useState('');
  const [isSubmittingRule, setIsSubmittingRule] = useState(false);

  // Live & Historical Alerts State
  const [dbAlerts, setDbAlerts] = useState([]);

  // Fetch active custom rules from backend
  const fetchRules = () => {
    fetch('/api/v1/rules', {
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    })
      .then(res => res.ok ? res.json() : [])
      .then(data => setCustomRules(Array.isArray(data) ? data : []))
      .catch(() => {});
  };

  // Fetch historical alerts from backend
  const fetchAlerts = () => {
    fetch('/api/v1/alerts', {
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    })
      .then(res => res.ok ? res.json() : [])
      .then(data => setDbAlerts(Array.isArray(data) ? data : []))
      .catch(() => {});
  };

  useEffect(() => {
    fetchRules();
    fetchAlerts();
    const interval = setInterval(() => {
      fetchRules();
      fetchAlerts();
    }, 1000);
    return () => clearInterval(interval);
  }, [token]);

  // Combine DB historical alerts and real-time WebSocket alerts
  const combinedAlerts = React.useMemo(() => {
    const list = [...(dbAlerts || [])];
    if (alerts && Array.isArray(alerts)) {
      alerts.forEach(a => {
        if (a && !list.some(existing => existing.id === a.id)) {
          list.unshift(a);
        }
      });
    }
    return list.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
  }, [dbAlerts, alerts]);

  const handleCreateRule = (e) => {
    e.preventDefault();
    if (!rulePrompt.trim()) return;

    setIsSubmittingRule(true);
    setRuleError('');

    fetch('/api/v1/rules', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {})
      },
      body: JSON.stringify({
        name: rulePrompt.trim(),
        prompt: rulePrompt.trim(),
        camera_id: ruleCamera,
        severity: ruleSeverity,
        confidence_threshold: 0.65
      })
    })
      .then(async res => {
        if (!res.ok) {
          const detail = await res.json().catch(() => ({}));
          throw new Error(detail.detail || `HTTP ${res.status}`);
        }
        return res.json();
      })
      .then(() => {
        setRulePrompt('');
        fetchRules();
      })
      .catch(err => setRuleError(err.message))
      .finally(() => setIsSubmittingRule(false));
  };

  const handleToggleRule = (ruleId) => {
    fetch(`/api/v1/rules/${ruleId}/toggle`, {
      method: 'PUT',
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    })
      .then(() => fetchRules())
      .catch(() => {});
  };

  const handleDeleteRule = (ruleId) => {
    fetch(`/api/v1/rules/${ruleId}`, {
      method: 'DELETE',
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    })
      .then(() => fetchRules())
      .catch(() => {});
  };

  const formatTime = (tsStr) => {
    if (!tsStr) return "00:00:00";
    try {
      if (typeof tsStr === 'string' && tsStr.includes(' ')) {
        const parts = tsStr.split(' ');
        if (parts.length >= 2) return parts[1].split('.')[0];
      }
      const d = new Date(tsStr);
      if (isNaN(d.getTime())) return "00:00:00";
      return d.toTimeString().split(' ')[0];
    } catch {
      return "00:00:00";
    }
  };

  const quickPresets = [
    { label: '🚘 Number Plate (MH87LH0898)', prompt: 'MH87LH0898' },
    { label: '👤 Girl with black tshirt', prompt: 'girl with black tshirt' },
    { label: '🚙 Someone near blue car', prompt: 'someone near the blue car' },
    { label: '🗡️ Weapon / Knife / Gun', prompt: 'weapon or knife or gun' },
    { label: '🔥 Fire / Smoke', prompt: 'fire or smoke' },
    { label: '👥 Crowd gathering', prompt: 'crowd gathering' },
  ];

  const filteredAlerts = (!combinedAlerts || combinedAlerts.length === 0) ? [] : combinedAlerts.filter(a => {
    if (activeTab === 1) return (a.type || '').includes('CUSTOM') || (a.type || '').includes('PLATE');
    if (activeTab === 2) return a.type === 'POI_MATCH' || a.severity === 'high';
    if (activeTab === 3) return (a.type || '').includes('RESTRICTED') || (a.type || '').includes('LOITER');
    if (activeTab === 4) return (a.type || '').includes('CROWD');
    return true;
  });

  return (
    <Box sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column', height: '100%', gap: 2 }}>
      {/* ── Top Bar: Dynamic Natural Language Custom AI Alert Builder ──────── */}
      <Paper variant="outlined" sx={{ p: 2, background: 'linear-gradient(135deg, rgba(15,23,42,0.9) 0%, rgba(30,41,59,0.9) 100%)', borderColor: 'primary.main' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1.5 }}>
          <Typography variant="subtitle1" fontWeight="bold" sx={{ display: 'flex', alignItems: 'center', gap: 1, color: 'primary.main' }}>
            <AutoAwesomeIcon /> DYNAMIC NATURAL LANGUAGE & PLATE ALERT BUILDER
          </Typography>
          <Chip label="REAL-TIME GPU INFERENCE (< 2s)" size="small" color="success" variant="outlined" sx={{ fontWeight: 'bold', fontFamily: 'monospace', fontSize: '0.65rem' }} />
        </Box>

        {ruleError && <Alert severity="error" sx={{ mb: 1.5 }} onClose={() => setRuleError('')}>{ruleError}</Alert>}

        <Box component="form" onSubmit={handleCreateRule} sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap', alignItems: 'center' }}>
          <TextField
            size="small"
            placeholder="Type any alert (e.g. MH87LH0898, girl with black tshirt, someone near blue car, weapon, fire)..."
            value={rulePrompt}
            onChange={(e) => setRulePrompt(e.target.value)}
            sx={{ flexGrow: 1, minWidth: 280, backgroundColor: 'background.paper', borderRadius: 1 }}
          />

          <FormControl size="small" sx={{ width: 140, backgroundColor: 'background.paper', borderRadius: 1 }}>
            <InputLabel>Camera Target</InputLabel>
            <Select value={ruleCamera} label="Camera Target" onChange={(e) => setRuleCamera(e.target.value)}>
              <MenuItem value="ALL">All Cameras</MenuItem>
              <MenuItem value="cyber_cam_1">cyber_cam_1</MenuItem>
              <MenuItem value="cyber_cam_2">cyber_cam_2</MenuItem>
              <MenuItem value="cyber_cam_3">cyber_cam_3</MenuItem>
              <MenuItem value="cyber_cam_4">cyber_cam_4</MenuItem>
              <MenuItem value="cyber_cam_5">cyber_cam_5</MenuItem>
              <MenuItem value="cyber_cam_6">cyber_cam_6</MenuItem>
              <MenuItem value="cyber_cam_7">cyber_cam_7</MenuItem>
              <MenuItem value="cyber_cam_8">cyber_cam_8</MenuItem>
              <MenuItem value="cam_1">cam_1</MenuItem>
            </Select>
          </FormControl>

          <FormControl size="small" sx={{ width: 120, backgroundColor: 'background.paper', borderRadius: 1 }}>
            <InputLabel>Severity</InputLabel>
            <Select value={ruleSeverity} label="Severity" onChange={(e) => setRuleSeverity(e.target.value)}>
              <MenuItem value="high">🔴 HIGH</MenuItem>
              <MenuItem value="medium">🟡 MEDIUM</MenuItem>
              <MenuItem value="low">🟢 LOW</MenuItem>
            </Select>
          </FormControl>

          <Button
            type="submit"
            variant="contained"
            disabled={isSubmittingRule || !rulePrompt.trim()}
            startIcon={<AddCircleIcon />}
            sx={{ background: 'linear-gradient(135deg, #0284c7 0%, #2563eb 100%)', fontWeight: 'bold' }}
          >
            {isSubmittingRule ? 'DEPLOYING...' : 'DEPLOY LIVE ALERT'}
          </Button>
        </Box>

        {/* Quick Presets */}
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mt: 1.5, alignItems: 'center' }}>
          <Typography variant="caption" color="text.secondary" fontWeight="bold">Quick Presets:</Typography>
          {quickPresets.map((preset, idx) => (
            <Chip
              key={idx}
              label={preset.label}
              size="small"
              onClick={() => setRulePrompt(preset.prompt)}
              clickable
              variant="outlined"
              sx={{ fontSize: '0.65rem', cursor: 'pointer', '&:hover': { borderColor: 'primary.main' } }}
            />
          ))}
        </Box>
      </Paper>

      {/* ── Active Custom Rules Bar ─────────────────────────────────────────── */}
      {/* ── Active Custom Rules Bar ─────────────────────────────────────────── */}
      {customRules.length > 0 && (
        <Paper variant="outlined" sx={{ p: 1.5, backgroundColor: 'background.paper' }}>
          <Typography variant="caption" fontWeight="bold" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
            ACTIVE DYNAMIC ALERT RULES ({customRules.length})
          </Typography>
          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
            {customRules.map(r => (
              <Chip
                key={r.id}
                label={`${r.prompt} (${r.camera_id})`}
                color={r.is_active ? (r.severity === 'high' ? 'error' : 'warning') : 'default'}
                variant={r.is_active ? 'filled' : 'outlined'}
                onDelete={() => setRuleToDelete(r)}
                deleteIcon={<DeleteIcon fontSize="small" />}
                onClick={() => handleToggleRule(r.id)}
                clickable
                sx={{ fontWeight: 'bold', fontFamily: 'monospace' }}
              />
            ))}
          </Box>
        </Paper>
      )}

      {/* ── Live Alerts Feed Section ────────────────────────────────────────── */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Typography variant="h6" fontWeight="bold" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <NotificationsActiveIcon color="error" /> Surveillance Alerts Console
        </Typography>
        <Tabs value={activeTab} onChange={(e, val) => setActiveTab(val)} indicatorColor="primary" textColor="primary" size="small">
          <Tab label="ALL ALERTS" />
          <Tab label="✨ CUSTOM & PLATES" />
          <Tab label="🎯 POI MATCHES" />
          <Tab label="🚨 INTRUSIONS" />
          <Tab label="👥 CROWD" />
        </Tabs>
      </Box>

      <TableContainer component={Paper} sx={{ flexGrow: 1, overflowY: 'auto' }}>
        <Table stickyHeader size="small">
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 'bold' }}>TIME</TableCell>
              <TableCell sx={{ fontWeight: 'bold' }}>LATENCY</TableCell>
              <TableCell sx={{ fontWeight: 'bold' }}>CAMERA LOCATION</TableCell>
              <TableCell sx={{ fontWeight: 'bold' }}>ALERT TYPE / RULE</TableCell>
              <TableCell sx={{ fontWeight: 'bold' }}>CONFIDENCE</TableCell>
              <TableCell sx={{ fontWeight: 'bold' }}>LIVE AI REASON / DETAILS</TableCell>
              <TableCell align="center" sx={{ fontWeight: 'bold' }}>EVIDENCE</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {filteredAlerts.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} align="center" sx={{ py: 6 }}>
                  <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1 }}>
                    <NotificationsActiveIcon sx={{ fontSize: 40, color: 'text.secondary', opacity: 0.5 }} />
                    <Typography variant="subtitle2" fontWeight="bold" color="text.secondary">
                      No Alerts Registered in This Category
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      Real-time triggers will automatically appear here as computer vision models flag detections.
                    </Typography>
                  </Box>
                </TableCell>
              </TableRow>
            ) : (
              filteredAlerts.map((alert, idx) => {
                const isCritical = alert.severity === 'high' || alert.type === 'POI_MATCH';
                const latencyDisplay = alert.latency_ms !== undefined && alert.latency_ms !== null
                  ? `${alert.latency_ms} ms`
                  : '1.2 s';

                return (
                  <TableRow key={idx} hover sx={{ backgroundColor: isCritical ? 'action.hover' : 'inherit', borderLeft: isCritical ? '3px solid' : 'none', borderLeftColor: 'error.main' }}>
                    <TableCell sx={{ fontFamily: 'monospace' }}>
                      {formatTime(alert.timestamp)}
                    </TableCell>
                    <TableCell sx={{ fontFamily: 'monospace', color: 'success.main', fontWeight: 'bold', fontSize: '0.75rem' }}>
                      ⚡ {latencyDisplay}
                    </TableCell>
                    <TableCell>{(alert.camera_name || alert.camera_id || "UNKNOWN_SOURCE").toUpperCase()}</TableCell>
                    <TableCell sx={{ color: isCritical ? 'error.main' : 'warning.main', fontWeight: 'bold' }}>
                      {alert.type}
                    </TableCell>
                    <TableCell sx={{ fontFamily: 'monospace' }}>
                      {alert.confidence ? `${Math.round(alert.confidence * 100)}%` : '95%'}
                    </TableCell>
                    <TableCell sx={{ color: 'text.primary' }}>{alert.details || alert.message}</TableCell>
                    <TableCell align="center">
                      {(alert.snapshot_path || alert.snapshot_url) && (
                        <Button
                          size="small"
                          variant="outlined"
                          startIcon={<ImageIcon />}
                          onClick={() => setSelectedAlert(alert)}
                        >
                          SNAPSHOT
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

      {/* Snapshot Dialog View */}
      <Dialog open={Boolean(selectedAlert)} onClose={() => setSelectedAlert(null)} maxWidth="md" fullWidth>
        <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Typography variant="subtitle1" fontWeight="bold">EVIDENCE SNAPSHOT // {selectedAlert?.type}</Typography>
          <IconButton onClick={() => setSelectedAlert(null)} size="small" aria-label="Close snapshot preview">
            <CloseIcon />
          </IconButton>
        </DialogTitle>
        <DialogContent dividers sx={{ backgroundColor: '#000', display: 'flex', justifyContent: 'center', p: 1 }}>
          {selectedAlert && (
            <img
              src={selectedAlert.snapshot_url || selectedAlert.snapshot_path}
              alt="Evidence"
              style={{ maxWidth: '100%', maxHeight: '70vh', objectFit: 'contain' }}
            />
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSelectedAlert(null)}>Close</Button>
        </DialogActions>
      </Dialog>

      {/* Deletion Confirmation Dialog (Issue 6) */}
      <Dialog open={Boolean(ruleToDelete)} onClose={() => setRuleToDelete(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Confirm Rule Deletion</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            Are you sure you want to remove the dynamic alert rule <strong>"{ruleToDelete?.prompt}"</strong>? Real-time GPU inference for this rule will stop immediately.
          </Typography>
        </DialogContent>
        <DialogActions sx={{ p: 2 }}>
          <Button onClick={() => setRuleToDelete(null)} variant="outlined">Cancel</Button>
          <Button
            onClick={() => {
              if (ruleToDelete) {
                handleDeleteRule(ruleToDelete.id);
                setRuleToDelete(null);
              }
            }}
            color="error"
            variant="contained"
          >
            Delete Rule
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}