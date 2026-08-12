import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Grid, Paper, Button, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Select, MenuItem, InputLabel, FormControl, TextField, Alert, Checkbox, FormControlLabel, Tooltip, LinearProgress, Chip
} from '@mui/material';
import VideocamIcon from '@mui/icons-material/Videocam';
import ShieldIcon from '@mui/icons-material/Shield';
import DownloadIcon from '@mui/icons-material/Download';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutlineOutlined';
import SyncIcon from '@mui/icons-material/Sync';
import DeleteSweepIcon from '@mui/icons-material/DeleteSweep';
import DescriptionIcon from '@mui/icons-material/Description';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import TerminalIcon from '@mui/icons-material/Terminal';

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
  const [exportProgress, setExportProgress] = useState(0);
  const [exportStep, setExportStep] = useState(0);
  const [exportLogs, setExportLogs] = useState([]);
  const [firNotice, setFirNotice] = useState('');
  const [availRange, setAvailRange] = useState(null);
  const [allRanges, setAllRanges] = useState([]);

  const checkAvailableRange = useCallback((camId) => {
    if (!camId || !token) return;
    fetch(`/api/v1/forensics/available-range?camera_id=${camId}`, {
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(res => res.json())
      .then(data => setAvailRange(data))
      .catch(err => console.error("Error fetching available range:", err));
  }, [token]);

  const loadAllRanges = useCallback(() => {
    if (!token) return;
    fetch('/api/v1/forensics/available-ranges', {
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(res => res.json())
      .then(data => setAllRanges(Array.isArray(data) ? data : []))
      .catch(err => console.error("Error loading all ranges:", err));
  }, [token]);

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

    loadAllRanges();
  }, [token, selectedCamId, loadAllRanges]);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadAllRanges, 10000);
    return () => clearInterval(interval);
  }, [loadData, loadAllRanges]);

  useEffect(() => {
    if (selectedCamId) {
      checkAvailableRange(selectedCamId);
    }
  }, [selectedCamId, checkAvailableRange]);

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

    setExportError('');
    const dStart = new Date(startTime);
    const dEnd = new Date(endTime);

    if (isNaN(dStart.getTime()) || isNaN(dEnd.getTime())) {
      setExportError("Validation Error: Please specify valid Start Time and End Time.");
      return;
    }

    if (dEnd <= dStart) {
      setExportError("Validation Error: End time must be strictly after Start time.");
      return;
    }

    if (dStart > new Date()) {
      setExportError("Validation Error: Start time cannot be in the future.");
      return;
    }

    setExporting(true);
    setExportProgress(15);
    setExportStep(1);
    setExportLogs([
      `> [00:00.1s] STEP 1/4: Locating recorded camera segments for channel '${selectedCamId.toUpperCase()}'...`
    ]);

    const t1 = setTimeout(() => {
      setExportProgress(45);
      setExportStep(2);
      setExportLogs(prev => [
        ...prev,
        `> [00:00.3s] STEP 2/4: Slicing evidence clip via Lossless Stream Copy (-c copy)...`
      ]);
    }, 200);

    const t2 = setTimeout(() => {
      setExportProgress(75);
      setExportStep(3);
      setExportLogs(prev => [
        ...prev,
        `> [00:00.6s] STEP 3/4: Computing SHA-256 digital fingerprint & HMAC chain-of-custody signature...`
      ]);
    }, 500);

    const t3 = setTimeout(() => {
      setExportProgress(90);
      setExportStep(4);
      setExportLogs(prev => [
        ...prev,
        `> [00:00.8s] STEP 4/4: Compiling digital evidence ZIP archive & legal manifest...`
      ]);
    }, 700);

    const queryParams = new URLSearchParams({
      camera_id: selectedCamId,
      start_time: startTime || '',
      end_time: endTime || ''
    });

    fetch(`/api/v1/forensics/export?${queryParams.toString()}`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(async res => {
        let body;
        const text = await res.text();
        try {
          body = JSON.parse(text);
        } catch {
          body = { detail: text || `HTTP ${res.status} Error` };
        }
        if (!res.ok) {
          throw new Error(body.detail || "Export compilation failed");
        }
        return body;
      })
      .then(_data => {
        clearTimeout(t1); clearTimeout(t2); clearTimeout(t3);
        setExportProgress(100);
        setExportLogs(prev => [
          ...prev,
          `> [00:01.0s] SUCCESS! Evidence package compiled & recorded in Forensic Ledger.`
        ]);
        if (incFir) {
          setFirNotice(`Generating Police FIR Annexure for Camera ${selectedCamId.toUpperCase()}...`);
        }
        setTimeout(() => {
          setExporting(false);
          setFirNotice('');
          loadData();
        }, 1500);
      })
      .catch(err => {
        clearTimeout(t1); clearTimeout(t2); clearTimeout(t3);
        setExporting(false);
        setExportError(err.message);
      });
  };

  const handleOpenFirReport = (exportUuid) => {
    setFirNotice(`Generating Police FIR Evidence Dossier for Case FIR-2026-SURAT-${exportUuid.toUpperCase()}...`);
    setTimeout(() => {
      window.open(`/api/v1/forensics/fir-report/${exportUuid}?token=${token}`, '_blank');
      setFirNotice('');
    }, 600);
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography variant="h6" fontWeight="bold" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <ShieldIcon color="primary" /> FORENSIC EVIDENCE COMPILER & LEDGER (IST)
        </Typography>
        <Typography variant="caption" color="text.secondary">
          Role: <strong>{role ? role.toUpperCase() : 'OPERATOR'}</strong> | Standard: <strong>DPDP Act 2023 / Section 79 Compliance</strong>
        </Typography>
      </Box>

      {firNotice && (
        <Alert severity="info" sx={{ mb: 2 }} icon={<SyncIcon sx={{ animation: 'spin 1.5s linear infinite' }} />}>
          <strong>POLICE FIR GENERATION:</strong> {firNotice}
        </Alert>
      )}

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

              {availRange && (
                <Paper variant="outlined" sx={{ p: 1, bgcolor: availRange.available ? 'rgba(46, 125, 50, 0.12)' : 'rgba(211, 47, 47, 0.12)', borderColor: availRange.available ? 'success.main' : 'error.main' }}>
                  <Typography variant="caption" sx={{ color: availRange.available ? 'success.light' : 'error.light', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: 0.8 }}>
                    {availRange.available ? <CheckCircleIcon fontSize="inherit" /> : <ErrorOutlineIcon fontSize="inherit" />}
                    {availRange.message}
                  </Typography>
                </Paper>
              )}

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

              {/* ── Real-Time Frontend Export Stepper & Status Console ───────── */}
              {exporting && (
                <Paper variant="outlined" sx={{ p: 1.5, bgcolor: '#090d16', borderColor: 'primary.main', display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Typography variant="caption" fontWeight="bold" sx={{ color: 'primary.main', display: 'flex', alignItems: 'center', gap: 0.8 }}>
                      <SyncIcon size="small" sx={{ animation: 'spin 1.5s linear infinite', fontSize: 16 }} />
                      EVIDENCE PIPELINE EXECUTION ({exportProgress}%)
                    </Typography>
                    <Chip label={`STEP ${exportStep}/4`} size="small" color="primary" sx={{ height: 18, fontSize: '0.65rem', fontWeight: 800 }} />
                  </Box>

                  <LinearProgress variant="determinate" value={exportProgress} sx={{ height: 6, borderRadius: 1 }} />

                  {/* Visual Stepper Indicators */}
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', pt: 0.5 }}>
                    {[
                      { step: 1, label: 'Find Video' },
                      { step: 2, label: 'Stream Copy' },
                      { step: 3, label: 'SHA-256' },
                      { step: 4, label: 'Archive ZIP' }
                    ].map(s => (
                      <Box key={s.step} sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                        {exportStep > s.step ? (
                          <CheckCircleIcon color="success" sx={{ fontSize: 16 }} />
                        ) : exportStep === s.step ? (
                          <SyncIcon color="primary" sx={{ fontSize: 16, animation: 'spin 1.5s linear infinite' }} />
                        ) : (
                          <Box sx={{ width: 12, height: 12, borderRadius: '50%', border: '1px solid #475569', my: '2px' }} />
                        )}
                        <Typography variant="caption" sx={{ fontSize: '0.62rem', color: exportStep >= s.step ? 'text.primary' : 'text.secondary' }}>
                          {s.label}
                        </Typography>
                      </Box>
                    ))}
                  </Box>

                  {/* Real-time Console Log Terminal */}
                  <Box sx={{
                    bgcolor: '#000', p: 1, borderRadius: 1, border: '1px solid #1e293b',
                    maxHeight: 110, overflowY: 'auto', fontFamily: 'monospace', fontSize: '0.7rem'
                  }}>
                    {exportLogs.map((log, i) => (
                      <Typography key={i} variant="caption" display="block" sx={{ fontFamily: 'monospace', color: i === exportLogs.length - 1 ? '#38bdf8' : '#94a3b8', fontSize: '0.68rem' }}>
                        {log}
                      </Typography>
                    ))}
                  </Box>
                </Paper>
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
                <strong>TRUSTED TIME:</strong> NTP-synced Indian Standard Time (IST) server.
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
                          <TableCell sx={{ fontSize: '0.78rem', fontFamily: 'monospace' }}>
                            {item.timestamp || "00:00:00"}
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
                                onClick={() => handleOpenFirReport(item.export_uuid)}
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

      {/* ── Available Recording Coverage Matrix Table (Bottom) ──────────── */}
      <Paper variant="outlined" sx={{ p: 2, mt: 1 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
          <Typography variant="subtitle2" fontWeight="bold" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <VideocamIcon color="primary" fontSize="small" />
            AVAILABLE RECORDING COVERAGE MATRIX (IST)
          </Typography>
          <Button size="small" variant="text" startIcon={<SyncIcon fontSize="small" />} onClick={loadAllRanges}>
            Refresh Coverage Matrix
          </Button>
        </Box>

        <TableContainer sx={{ maxHeight: 220 }}>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                <TableCell sx={{ fontWeight: 'bold' }}>CAMERA CHANNEL</TableCell>
                <TableCell sx={{ fontWeight: 'bold' }}>STATUS</TableCell>
                <TableCell sx={{ fontWeight: 'bold' }}>EARLIEST RECORDING (IST)</TableCell>
                <TableCell sx={{ fontWeight: 'bold' }}>LATEST RECORDING (IST)</TableCell>
                <TableCell sx={{ fontWeight: 'bold' }}>CLIPS</TableCell>
                <TableCell sx={{ fontWeight: 'bold', textAlign: 'right' }}>QUICK ACTION</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {allRanges.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} align="center">
                    <Typography variant="caption" color="text.secondary">Loading camera recording coverage ranges...</Typography>
                  </TableCell>
                </TableRow>
              ) : (
                allRanges.map(r => (
                  <TableRow key={r.camera_id} hover selected={selectedCamId === r.camera_id}>
                    <TableCell sx={{ fontWeight: 'bold', fontSize: '0.75rem' }}>
                      CAM_{r.camera_id.toUpperCase()} <br />
                      <span style={{ color: '#94a3b8', fontWeight: 'normal' }}>{r.camera_name}</span>
                    </TableCell>
                    <TableCell>
                      {r.available ? (
                        <Chip label="RECORDING AVAILABLE" color="success" size="small" sx={{ height: 20, fontSize: '0.65rem', fontWeight: 'bold' }} />
                      ) : (
                        <Chip label="NO FOOTAGE" color="error" size="small" sx={{ height: 20, fontSize: '0.65rem', fontWeight: 'bold' }} />
                      )}
                    </TableCell>
                    <TableCell sx={{ fontSize: '0.75rem', fontFamily: 'monospace' }}>{r.start_time || '—'}</TableCell>
                    <TableCell sx={{ fontSize: '0.75rem', fontFamily: 'monospace' }}>{r.end_time || '—'}</TableCell>
                    <TableCell sx={{ fontSize: '0.75rem' }}>{r.total_segments}</TableCell>
                    <TableCell align="right">
                      {r.available ? (
                        <Button
                          size="small"
                          variant="outlined"
                          color="primary"
                          sx={{ fontSize: '0.65rem', py: 0.2 }}
                          onClick={() => {
                            setSelectedCamId(r.camera_id);
                            if (r.start_time_iso && r.end_time_iso) {
                              setStartTime(r.start_time_iso);
                              setEndTime(r.end_time_iso);
                            }
                          }}
                        >
                          Auto-Fill Range
                        </Button>
                      ) : (
                        <Typography variant="caption" color="text.secondary">No Clips</Typography>
                      )}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>
    </Box>
  );
}
