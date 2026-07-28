import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Grid, Paper, Button, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Select, MenuItem, InputLabel, FormControl, Slider, Alert
} from '@mui/material';
import VideocamIcon from '@mui/icons-material/Videocam';
import ShieldIcon from '@mui/icons-material/Shield';
import DownloadIcon from '@mui/icons-material/Download';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutlineOutlined';
import SyncIcon from '@mui/icons-material/Sync';

export default function ForensicsManager({ role, token }) {
  const [cameras, setCameras] = useState([]);
  const [exportsList, setExportsList] = useState([]);
  const [selectedCamId, setSelectedCamId] = useState('');
  const [duration, setDuration] = useState(10);
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
        if (Array.isArray(data) && data.length > 0) setSelectedCamId(data[0].id);
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

  const handleTriggerExport = (e) => {
    e.preventDefault();
    if (!selectedCamId) return;

    setExporting(true);
    setExportError('');

    fetch(`/api/v1/forensics/export?camera_id=${selectedCamId}&duration_seconds=${duration}`, {
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
        <Grid item xs={12} md={4}>
          <Paper variant="outlined" sx={{ p: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
            <Typography variant="subtitle2" fontWeight="bold" sx={{ borderBottom: '1px solid', borderColor: 'divider', pb: 1 }}>
              COMPILE NEW EVIDENCE CLIP
            </Typography>

            <Box component="form" onSubmit={handleTriggerExport} sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
              <FormControl size="small" fullWidth>
                <InputLabel id="camera-select-label">Select Target Channel</InputLabel>
                <Select
                  labelId="camera-select-label"
                  value={selectedCamId}
                  label="Select Target Channel"
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

              <Box>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                  <Typography variant="body2" color="text.secondary">Clip Duration (Seconds)</Typography>
                  <Typography variant="body2" fontWeight="bold">{duration}s</Typography>
                </Box>
                <Slider
                  value={duration}
                  min={5}
                  max={30}
                  step={1}
                  onChange={(e, val) => setDuration(val)}
                  disabled={exporting}
                  valueLabelDisplay="auto"
                />
              </Box>

              <Button
                type="submit"
                variant="contained"
                disabled={exporting || !selectedCamId}
                startIcon={exporting ? <SyncIcon sx={{ animation: 'spin 2s linear infinite' }} /> : <VideocamIcon />}
              >
                {exporting ? 'FFMPEG Capturing...' : 'Compile Evidence'}
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
                <strong>TRUSTED TIME:</strong> Queried from DigiCert public timestamp servers.
              </Typography>
            </Box>

            {exportError && (
              <Alert severity="error" icon={<ErrorOutlineIcon />}>
                <strong>EXPORT_ERROR_403:</strong> {exportError}
              </Alert>
            )}
          </Paper>
        </Grid>

        <Grid item xs={12} md={8}>
          <Paper variant="outlined" sx={{ p: 2, height: '100%', display: 'flex', flexDirection: 'column' }}>
            <Typography variant="subtitle2" fontWeight="bold" sx={{ mb: 2, borderBottom: '1px solid', borderColor: 'divider', pb: 1 }}>
              FORENSIC EXPORTS LEDGER
            </Typography>

            <TableContainer sx={{ flexGrow: 1, overflowY: 'auto' }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ fontWeight: 'bold' }}>TIME</TableCell>
                    <TableCell sx={{ fontWeight: 'bold' }}>CAM NAME</TableCell>
                    <TableCell sx={{ fontWeight: 'bold' }}>OPERATOR</TableCell>
                    <TableCell sx={{ fontWeight: 'bold' }}>SHA-256 HASH</TableCell>
                    <TableCell align="center" sx={{ fontWeight: 'bold' }}>TSA STATUS</TableCell>
                    <TableCell align="center" sx={{ fontWeight: 'bold' }}>RECOVERY</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {exportsList.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={6} align="center" sx={{ py: 6, color: 'text.secondary' }}>
                        [ NO FORMS OF EVIDENCE RECORDED IN DATABASE ]
                      </TableCell>
                    </TableRow>
                  ) : (
                    exportsList.map((item, idx) => {
                      const isDigiCert = item.timestamp_authority === "DigiCert Public TSA";
                      return (
                        <TableRow key={idx} hover>
                          <TableCell>{item.timestamp.split('T')[1]?.split('.')[0] || "00:00:00"}</TableCell>
                          <TableCell>{item.camera_name.toUpperCase()}</TableCell>
                          <TableCell>{item.username}</TableCell>
                          <TableCell sx={{ color: 'text.secondary', fontFamily: 'monospace' }}>
                            sha256:<strong style={{ color: 'inherit' }}>{item.sha256_hash.substring(0, 10)}</strong>...
                          </TableCell>
                          <TableCell align="center">
                            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 1 }}>
                              <ShieldIcon fontSize="small" color={isDigiCert ? "primary" : "action"} />
                              <Typography variant="caption" fontWeight="bold">{isDigiCert ? 'TSA OK' : 'LOCAL OK'}</Typography>
                            </Box>
                          </TableCell>
                          <TableCell align="center">
                            <Box sx={{ display: 'flex', justifyContent: 'center', gap: 1 }}>
                              <Button
                                component="a"
                                href={item.mp4_download_url}
                                download
                                size="small"
                                variant="outlined"
                                startIcon={<DownloadIcon />}
                                sx={{ textTransform: 'none', px: 1, py: 0.5, fontSize: '0.7rem' }}
                              >
                                MP4
                              </Button>
                              <Button
                                component="a"
                                href={`/api/v1/forensics/fir-report/${item.export_uuid}`}
                                target="_blank"
                                size="small"
                                variant="contained"
                                color="secondary"
                                sx={{ textTransform: 'none', px: 1, py: 0.5, fontSize: '0.7rem' }}
                              >
                                📜 FIR Report
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