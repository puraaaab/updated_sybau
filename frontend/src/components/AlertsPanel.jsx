import React, { useState } from 'react';
import {
  Box, Typography, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper, Button, Dialog, DialogTitle, DialogContent, DialogActions, IconButton, Switch, FormControlLabel, Tabs, Tab
} from '@mui/material';
import ImageIcon from '@mui/icons-material/Image';
import ShieldIcon from '@mui/icons-material/Shield';
import CloseIcon from '@mui/icons-material/Close';

export default function AlertsPanel({ alerts }) {
  const [selectedAlert, setSelectedAlert] = useState(null);
  const [showRaw, setShowRaw] = useState(false);
  const [activeTab, setActiveTab] = useState(0);

  const formatTime = (tsStr) => {
    try {
      const d = new Date(tsStr);
      return d.toTimeString().split(' ')[0];
    } catch {
      return "00:00:00";
    }
  };

  const filteredAlerts = (!alerts || alerts.length === 0) ? [] : alerts.filter(a => {
    if (activeTab === 1) return a.type === 'POI_MATCH' || a.severity === 'high';
    if (activeTab === 2) return (a.type || '').includes('WRONG') || (a.type || '').includes('PARK') || (a.type || '').includes('SPEED');
    if (activeTab === 3) return (a.type || '').includes('RESTRICTED') || (a.type || '').includes('LOITER');
    if (activeTab === 4) return (a.type || '').includes('CROWD');
    return true;
  });

  return (
    <Box sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1.5 }}>
        <Typography variant="h6" fontWeight="bold">Surveillance Alerts Console</Typography>
        <Tabs value={activeTab} onChange={(e, val) => setActiveTab(val)} indicatorColor="primary" textColor="primary" size="small">
          <Tab label="ALL ALERTS" />
          <Tab label="🎯 POI MATCHES" />
          <Tab label="🚗 TRAFFIC" />
          <Tab label="🚨 INTRUSIONS" />
          <Tab label="👥 CROWD" />
        </Tabs>
      </Box>

      <TableContainer component={Paper} sx={{ flexGrow: 1, overflowY: 'auto' }}>
        <Table stickyHeader size="small">
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 'bold' }}>TIME</TableCell>
              <TableCell sx={{ fontWeight: 'bold' }}>CAMERA LOCATION</TableCell>
              <TableCell sx={{ fontWeight: 'bold' }}>ALERT TYPE</TableCell>
              <TableCell sx={{ fontWeight: 'bold' }}>CONFIDENCE</TableCell>
              <TableCell sx={{ fontWeight: 'bold' }}>ALERT REASON / DETAILS</TableCell>
              <TableCell align="center" sx={{ fontWeight: 'bold' }}>EVIDENCE ACTIONS</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {filteredAlerts.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                  [ NO ALERTS REGISTERED IN THIS CATEGORY ]
                </TableCell>
              </TableRow>
            ) : (
              filteredAlerts.map((alert, idx) => {
                const isCritical = alert.type === 'POI_MATCH';
                return (
                  <TableRow key={idx} hover sx={{ backgroundColor: isCritical ? 'action.hover' : 'inherit', borderLeft: isCritical ? '3px solid' : 'none', borderLeftColor: 'error.main' }}>
                    <TableCell>
                      {formatTime(alert.timestamp)}
                    </TableCell>
                    <TableCell>{(alert.camera_name || "UNKNOWN_SOURCE").toUpperCase()}</TableCell>
                    <TableCell sx={{ color: isCritical ? 'error.main' : 'warning.main', fontWeight: 'bold' }}>
                      {alert.type === 'POI_MATCH' ? 'TARGET PERSON DETECTED' : alert.type}
                    </TableCell>
                    <TableCell>CONF: {alert.confidence}%</TableCell>
                    <TableCell sx={{ color: 'text.secondary' }}>{alert.details || alert.message}</TableCell>
                    <TableCell align="center">
                      <Box sx={{ display: 'flex', gap: 1, justifyContent: 'center' }}>
                        {(alert.snapshot_path || alert.snapshot_url) && (
                          <Button 
                            size="small" 
                            variant="outlined" 
                            startIcon={<ImageIcon />} 
                            onClick={() => { setSelectedAlert(alert); setShowRaw(false); }}
                          >
                            SNAPSHOT
                          </Button>
                        )}
                        <Button
                          size="small"
                          variant="contained"
                          color="error"
                          onClick={() => window.open(`/api/v1/challan/generate/${alert.id || (idx + 1)}`, '_blank')}
                        >
                          CHALLAN
                        </Button>
                      </Box>
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </TableContainer>

      <Dialog open={Boolean(selectedAlert)} onClose={() => setSelectedAlert(null)} maxWidth="md" fullWidth>
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <ShieldIcon color="primary" />
            <Typography variant="subtitle1" fontWeight="bold">
              FORENSIC IMAGE VERIFIER // CAM: {selectedAlert?.camera_name?.toUpperCase()}
            </Typography>
          </Box>
          <IconButton onClick={() => setSelectedAlert(null)} size="small">
            <CloseIcon />
          </IconButton>
        </DialogTitle>
        <DialogContent dividers sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Paper variant="outlined" sx={{ p: 2, backgroundColor: 'background.default' }}>
            <Typography variant="body2"><strong>INCIDENT:</strong> {selectedAlert?.type} // {selectedAlert?.details}</Typography>
            <Typography variant="body2"><strong>VERIFICATION TIME:</strong> {selectedAlert?.timestamp}</Typography>
            <Typography variant="body2"><strong>MATCH CONFIDENCE:</strong> {selectedAlert?.confidence}%</Typography>
          </Paper>

          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <Typography variant="subtitle2" fontWeight="bold">COMPLIANCE REDACTION COMPARISON</Typography>
            <FormControlLabel 
              control={<Switch checked={showRaw} onChange={(e) => setShowRaw(e.target.checked)} color="primary" />} 
              label="SHOW WATCHLIST TARGET" 
            />
          </Box>

          <Paper variant="outlined" sx={{ height: 300, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: '#000', position: 'relative', overflow: 'hidden' }}>
            {showRaw ? (
              <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                <Box sx={{ width: 120, height: 120, border: '2px solid', borderColor: 'primary.main', mb: 2, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: 'background.paper' }}>
                  <ShieldIcon sx={{ fontSize: 60, color: 'primary.main' }} />
                </Box>
                <Typography variant="subtitle2" fontWeight="bold" color="primary.main">POI WATCHLIST ENROLLED FACE</Typography>
                <Typography variant="caption" color="text.secondary">Unredacted reference face from security watchlist databases.</Typography>
              </Box>
            ) : (
              <Box sx={{ position: 'relative', width: '100%', height: '100%' }}>
                <Box 
                  component="img" 
                  src={(selectedAlert?.snapshot_path || selectedAlert?.snapshot_url)?.replace(/^\/api\/v1\//, '/api/')} 
                  alt="Privacy Redacted Frame" 
                  sx={{ width: '100%', height: '100%', objectFit: 'contain' }} 
                />
                <Box sx={{ position: 'absolute', bottom: 8, left: 8, backgroundColor: 'rgba(0,0,0,0.8)', px: 1, py: 0.5, borderRadius: 1, border: '1px solid', borderColor: 'divider' }}>
                  <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>PRIVACY_REDACTED_DEFAULT // BYSTANDERS_MASKED</Typography>
                </Box>
              </Box>
            )}
          </Paper>
        </DialogContent>
        <DialogActions sx={{ justifyContent: 'space-between', px: 3, py: 2 }}>
          <Button 
            variant="contained" 
            color="error" 
            onClick={() => {
              const alertId = selectedAlert?.id || 1;
              window.open(`/api/v1/challan/generate/${alertId}`, '_blank');
            }}
          >
            📋 ISSUE E-CHALLAN CITATION
          </Button>
          <Button variant="outlined" onClick={() => setSelectedAlert(null)}>Close Verifier</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}