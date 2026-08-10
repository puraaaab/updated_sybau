import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Grid, Paper, Button, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Select, MenuItem, InputLabel, FormControl, TextField, Alert, Checkbox, FormControlLabel, Tooltip
} from '@mui/material';
import VideocamIcon from '@mui/icons-material/Videocam';
import ShieldIcon from '@mui/icons-material/Shield';
import DownloadIcon from '@mui/icons-material/Download';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutlineOutlined';
import SyncIcon from '@mui/icons-material/Sync';
import DeleteSweepIcon from '@mui/icons-material/DeleteSweep';
import DescriptionIcon from '@mui/icons-material/Description';

export default function ForensicsManager({ role, token }) {
  const [cameras, setCameras] = useState([]);
  const [exportsList, setExportsList] = useState([]);
  const [selectedCamId, setSelectedCamId] = useState('');
  
  const getNowStr = (hoursAgo = 0) => {
    const d = new Date(Date.now() - hoursAgo * 3600 * 1000);
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  };

  const [startTime, setStartTime] = useState(getNowStr(1));
  const [endTime, setEndTime] = useState(getNowStr(0));
  const [incMp4, setIncMp4] = useState(true);
  const [incSnapshots, setIncSnapshots] = useState(true);
  const [incFir, setIncFir] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState('');

  const loadData = useCallback(() => {
    if (!token) return;

    fetch('/api/v1/cameras', {
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(res => res.json())
      .then(data => {
        setCameras(Array.isArray(data) ? data : []);
        if (Array.isArray(data) && data.length > 0 && !selectedCamId) {
          setSelectedCamId(data[0].id);
        }
      })
      .catch(err => console.error("Error loading cameras:", err));

    fetch('/api/v1/forensics/exports', {
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(res => {
        if (!res.ok) throw new Error("Forensics access denied");
        return res.json();
      })
      .then(data => setExportsList(Array.isArray(data) ? data : []))
      .catch(err => console.error("Error loading exports:", err));
  }, [token]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleClearHistory = () => {
    if (!token) return;
    fetch('/api/v1/forensics/exports/clear', {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(res => res.ok ? loadData() : alert("Failed to clear ledger"))
      .catch(err => console.error("Error clearing exports:", err));
  };

  const handleTriggerExport = (e) => {
    e.preventDefault();
    if (!selectedCamId) return;

    setExporting(true);
    setExportError('');

    const queryParams = new URLSearchParams({
      camera_id: selectedCamId,
      start_time: startTime ? new Date(startTime).toISOString() : '',
      end_time: endTime ? new Date(endTime).toISOString() : ''
    });

    fetch(`/api/v1/forensics/export?${queryParams.toString()}`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(async res => {
        const body = await res.json();
        if (!res.ok) {
          throw new Error(body.detail || "Export compilation failed");
        }
        return body;
      })
      .then(_data => {
        setExporting(false);
        loadData();
      })
      .catch(err => {
        setExporting(false);
        setExportError(err.message);
      });
  };

  return (
    <Box sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
        <Typography variant="h6" fontWeight="bold">Forensic Export Manager</Typography>
        <Typography variant="caption" color="text.secondary">RBAC Clearance: {role.toUpperCase()}</Typography>
      </Box>

      <Grid container spacing={3}>
        <Grid size={{ xs: 12, md: 4 }}>
          <Paper variant="outlined" sx={{ p: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
            <Typography variant="subtitle2" fontWeight="bold" sx={{ borderBottom: '1px solid', borderColor: 'divider', pb: 1 }}>
              COMPILE NEW EVIDENCE CLIP
            </Typography>

            <Box component="form" onSubmit={handleTriggerExport} sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <FormControl size="small" fullWidth>
                <InputLabel id="camera-select-label">Select Target CCTV Channel</InputLabel>
                <Select
                  labelId="camera-select-label"
                  value={selectedCamId}
                  label="Select Target CCTV Channel"
                  onChange={(e) => setSelectedCamId(e.target.value)}
                  disabled={exporting}
                >
                  {cameras.map(cam => (
                    <MenuItem key={cam.id} value={cam.id}>
                      CAM_{String(cam.id).padStart(2, '0')} // {cam.name.toUpperCase()}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>

              <TextField
                label="From (Start Time)"
                type="datetime-local"
                size="small"
                fullWidth
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
                slotProps={{ inputLabel: { shrink: true }, htmlInput: { step: 1 } }}
                disabled={exporting}
              />

              <TextField
                label="To (End Time)"
                type="datetime-local"
                size="small"
                fullWidth
                value={endTime}
                onChange={(e) => setEndTime(e.target.value)}
                slotProps={{ inputLabel: { shrink: true }, htmlInput: { step: 1 } }}
                disabled={exporting}
              />

              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
                <Typography variant="caption" color="text.secondary" fontWeight="bold">PACKAGE CONTENT OPTIONS:</Typography>
                <FormControlLabel
                  control={<Checkbox size="small" checked={incMp4} onChange={(e) => setIncMp4(e.target.checked)} />}
                  label={<Typography variant="caption">🎥 Video Clip Segment (.mp4)</Typography>}
                />
                <FormControlLabel
                  control={<Checkbox size="small" checked={incSnapshots} onChange={(e) => setIncSnapshots(e.target.checked)} />}
                  label={<Typography variant="caption">📸 High-Res Frame Keyframes</Typography>}
                />
                <FormControlLabel
                  control={<Checkbox size="small" checked={incFir} onChange={(e) => setIncFir(e.target.checked)} />}
                  label={<Typography variant="caption">📜 Official Police FIR Evidence Annexure</Typography>}
                />
              </Box>

              {exporting && (
                <Alert severity="info" icon={<SyncIcon sx={{ animation: 'spin 2s linear infinite' }} />}>
                  Compiling clip & computing SHA-256 evidence package... (~3-5s)
                </Alert>
              )}

              <Button
                type="submit"
                variant="contained"
                disabled={exporting || !selectedCamId}
                startIcon={exporting ? <SyncIcon sx={{ animation: 'spin 2s linear infinite' }} /> : <VideocamIcon />}
              >
                {exporting ? 'Compiling Evidence...' : 'Compile Custom Evidence'}
              </Button>
            </Box>

            <Box sx={{ p: 1.5, backgroundColor: 'background.default', border: '1px solid', borderColor: 'divider', mt: 1 }}>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                <strong>SECURITY POLICY:</strong> Non-flagged faces redacted (blurred) by default inside exported segments.
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                <strong>CRYPTOGRAPHY:</strong> SHA-256 hash computed immediately post-capture.
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                <strong>TRUSTED TIME:</strong> NTP-synced UTC timestamping server.
              </Typography>
            </Box>

            {exportError && (
              <Alert severity="error" icon={<ErrorOutlineIcon />}>
                <strong>EXPORT_ERROR:</strong> {exportError}
              </Alert>
            )}
          </Paper>
        </Grid>

        <Grid size={{ xs: 12, md: 8 }}>
          <Paper variant="outlined" sx={{ p: 2, height: '100%', display: 'flex', flexDirection: 'column' }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2, borderBottom: '1px solid', borderColor: 'divider', pb: 1 }}>
              <Typography variant="subtitle2" fontWeight="bold">
                FORENSIC EXPORTS LEDGER
              </Typography>
              {exportsList.length > 0 && (
                <Button
                  size="small"
                  color="error"
                  variant="outlined"
                  startIcon={<DeleteSweepIcon />}
                  onClick={handleClearHistory}
                >
                  Clear History
                </Button>
              )}
            </Box>

            <TableContainer sx={{ flexGrow: 1, overflowY: 'auto' }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ fontWeight: 'bold' }}>TIME / RANGE</TableCell>
                    <TableCell sx={{ fontWeight: 'bold' }}>CAM NAME</TableCell>
                    <TableCell sx={{ fontWeight: 'bold' }}>OPERATOR</TableCell>
                    <TableCell sx={{ fontWeight: 'bold' }}>SHA-256 HASH</TableCell>
                    <TableCell align="center" sx={{ fontWeight: 'bold' }}>RECOVERY</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {exportsList.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5} align="center" sx={{ py: 6, color: 'text.secondary' }}>
                        [ NO FORMS OF EVIDENCE RECORDED IN DATABASE ]
                      </TableCell>
                    </TableRow>
                  ) : (
                    exportsList.map((item, idx) => {
                      return (
                        <TableRow key={idx} hover>
                          <TableCell sx={{ fontSize: '0.8rem' }}>
                            {item.timestamp.split('T')[1]?.split('.')[0] || "00:00:00"}
                          </TableCell>
                          <TableCell sx={{ fontWeight: 'bold' }}>{item.camera_name.toUpperCase()}</TableCell>
                          <TableCell>{item.username}</TableCell>
                          <TableCell sx={{ color: 'text.secondary', fontFamily: 'monospace' }}>
                            sha256:<strong style={{ color: 'inherit' }}>{item.sha256_hash.substring(0, 10)}</strong>...
                          </TableCell>
                          <TableCell align="center">
                            <Box sx={{ display: 'flex', justifyContent: 'center', gap: 1 }}>
                              <Button
                                component="a"
                                href={item.mp4_download_url ? `${item.mp4_download_url}?token=${token}` : '#'}
                                download
                                size="small"
                                variant="outlined"
                                startIcon={<DownloadIcon />}
                                sx={{ textTransform: 'none', px: 1, py: 0.5, fontSize: '0.7rem' }}
                              >
                                ZIP / MP4
                              </Button>
                              <Button
                                component="a"
                                href={`/api/v1/forensics/fir-report/${item.export_uuid}?token=${token}`}
                                target="_blank"
                                size="small"
                                variant="contained"
                                color="secondary"
                                startIcon={<DescriptionIcon />}
                                sx={{ textTransform: 'none', px: 1, py: 0.5, fontSize: '0.7rem' }}
                              >
                                FIR Report
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
          </Paper>
        </Grid>
      </Grid>
    </Box>
  );
}
