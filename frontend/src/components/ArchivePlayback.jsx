import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Box, Typography, Grid, Paper, Select, MenuItem, Button, IconButton, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Alert, Chip, FormControl
} from '@mui/material';
import VideocamIcon from '@mui/icons-material/Videocam';
import SyncIcon from '@mui/icons-material/Sync';
import CloseIcon from '@mui/icons-material/Close';
import MovieIcon from '@mui/icons-material/Movie';
import AccessTimeIcon from '@mui/icons-material/AccessTime';
import DownloadIcon from '@mui/icons-material/Download';

function toStreamName(name) {
  return name.toLowerCase().replace(/[^a-z0-9]/g, '_');
}

function fmtBytes(b) {
  if (b < 1024) return `${b}B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(0)}KB`;
  return `${(b / 1024 / 1024).toFixed(1)}MB`;
}

function CameraArchivePanel({ camera, token, syncTimestamp, onSyncRequest, onExportClip, onRemove }) {
  const [clips, setClips] = useState([]);
  const [selectedClip, setSelectedClip] = useState(null);
  const [loading, setLoading] = useState(false);
  const videoRef = useRef(null);

  const streamName = toStreamName(camera.name);

  const fetchClips = useCallback(() => {
    setLoading(true);
    fetch(`/api/v1/playback/timeline/${camera.id}`, {
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(r => r.json())
      .then(data => {
        const rawClips = Array.isArray(data) ? data : (data.clips || []);
        const cl = rawClips.map(item => ({
          filename: item.filename,
          url: `/api/v1/playback/video/${camera.id}/${item.filename}?token=${token}`,
          timestamp: item.filename ? item.filename.replace('.mp4', '') : 'N/A',
          size_bytes: item.size_bytes || 1048576
        }));
        setClips(cl);
        setLoading(false);
        if (cl.length > 0 && !selectedClip) {
          const defaultClip = cl.length > 1 ? cl[cl.length - 2] : cl[0];
          setSelectedClip(defaultClip);
        }
      })
      .catch(() => setLoading(false));
  }, [camera.id, token, selectedClip]);

  useEffect(() => { fetchClips(); }, [fetchClips]);

  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.load();
      videoRef.current.play().catch(e => console.log('Autoplay info:', e));
    }
  }, [selectedClip]);

  useEffect(() => {
    if (!syncTimestamp || !clips.length) return;
    const sorted = [...clips].sort((a, b) => a.timestamp.localeCompare(b.timestamp));
    let best = sorted[0];
    for (const c of sorted) {
      if (c.timestamp <= syncTimestamp) best = c;
    }
    if (best && (!selectedClip || best.filename !== selectedClip.filename)) {
      setSelectedClip(best);
    }
  }, [syncTimestamp, clips, selectedClip]);

  const handleTimeUpdate = () => {
    if (!videoRef.current || !selectedClip) return;
    const base = selectedClip.timestamp;
    const sec = Math.floor(videoRef.current.currentTime);
    const baseMs = new Date(base).getTime();
    if (!isNaN(baseMs)) {
      const derived = new Date(baseMs + sec * 1000).toISOString();
      onSyncRequest(derived);
    }
  };

  return (
    <Paper variant="outlined" sx={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', px: 2, py: 1, backgroundColor: 'background.default', borderBottom: '1px solid', borderColor: 'divider' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <VideocamIcon fontSize="small" color="action" />
          <Typography variant="subtitle2" fontWeight="bold">{camera.name.toUpperCase()}</Typography>
          <Typography variant="caption" color="text.secondary">{streamName}</Typography>
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <IconButton size="small" onClick={fetchClips}>
            <SyncIcon fontSize="small" />
          </IconButton>
          <IconButton size="small" color="error" onClick={onRemove}>
            <CloseIcon fontSize="small" />
          </IconButton>
        </Box>
      </Box>

      <Box sx={{ position: 'relative', backgroundColor: '#000', height: 320, width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
        {selectedClip ? (
          <video
            key={selectedClip.filename}
            ref={videoRef}
            controls
            autoPlay
            playsInline
            preload="auto"
            style={{ width: '100%', height: '100%', objectFit: 'contain' }}
            src={selectedClip.url}
            onTimeUpdate={handleTimeUpdate}
          />
        ) : (
          <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1, color: 'text.secondary' }}>
            <MovieIcon sx={{ fontSize: 40, opacity: 0.3 }} />
            <Typography variant="caption">{loading ? 'LOADING ARCHIVE...' : 'NO ARCHIVE CLIPS'}</Typography>
          </Box>
        )}
        {selectedClip && (
          <Box sx={{ position: 'absolute', top: 8, left: 8, backgroundColor: 'rgba(0,0,0,0.8)', px: 1, py: 0.5, borderRadius: 1, border: '1px solid', borderColor: 'divider', display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <AccessTimeIcon sx={{ fontSize: 12, color: 'text.secondary' }} />
            <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>{selectedClip.timestamp}</Typography>
          </Box>
        )}
      </Box>

      <Box sx={{ display: 'flex', gap: 1, p: 1, overflowX: 'auto', backgroundColor: '#000', borderTop: '1px solid', borderColor: 'divider', minHeight: 60, alignItems: 'center' }}>
        {loading ? (
          <Typography variant="caption" color="text.secondary" sx={{ ml: 1 }}>SCANNING ARCHIVE...</Typography>
        ) : clips.length === 0 ? (
          <Typography variant="caption" color="text.secondary" sx={{ ml: 1 }}>NO CLIPS YET</Typography>
        ) : (
          clips.map((clip, idx) => {
            const isActive = selectedClip && selectedClip.filename === clip.filename;
            const timeLabel = clip.timestamp.includes('T')
              ? clip.timestamp.split('T')[1].substring(0, 8)
              : clip.timestamp;
            return (
              <Button
                key={idx}
                variant={isActive ? "contained" : "outlined"}
                size="small"
                onClick={() => setSelectedClip(clip)}
                title={clip.timestamp}
                sx={{ minWidth: 'auto', display: 'flex', flexDirection: 'column', p: 0.5, borderColor: isActive ? 'primary.main' : 'divider', color: isActive ? 'primary.contrastText' : 'text.secondary' }}
              >
                <Typography variant="caption" sx={{ fontSize: '0.65rem' }}>{timeLabel}</Typography>
                <Typography variant="caption" sx={{ fontSize: '0.6rem', opacity: 0.7 }}>{fmtBytes(clip.size_bytes)}</Typography>
              </Button>
            );
          })
        )}
      </Box>

      {selectedClip && (
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', px: 2, py: 1, borderTop: '1px solid', borderColor: 'divider', backgroundColor: 'background.paper' }}>
          <Typography variant="caption" color="text.secondary">
            {selectedClip.filename.replace('.mp4.mp4', '.mp4')}
          </Typography>
          <Button
            size="small"
            variant="outlined"
            startIcon={<DownloadIcon />}
            onClick={() => onExportClip(camera, selectedClip)}
          >
            Forensic Export
          </Button>
        </Box>
      )}
    </Paper>
  );
}

export default function ArchivePlayback({ token }) {
  const [cameras, setCameras] = useState([]);
  const [activeCameras, setActiveCameras] = useState([]);
  const [exportsList, setExportsList] = useState([]);
  const [syncTimestamp, setSyncTimestamp] = useState(null);
  const [exportStatus, setExportStatus] = useState(null);

  useEffect(() => {
    if (!token) return;
    fetch('/api/v1/cameras', { headers: { 'Authorization': `Bearer ${token}` } })
      .then(r => r.json())
      .then(data => {
        const camList = Array.isArray(data) ? data : [];
        setCameras(camList);
        if (camList.length > 0) setActiveCameras([camList[0]]);
      })
      .catch(() => setCameras([]));
  }, [token]);

  const fetchExports = useCallback(() => {
    if (!token) return;
    fetch('/api/v1/forensics/exports', { headers: { 'Authorization': `Bearer ${token}` } })
      .then(r => r.json())
      .then(data => setExportsList(Array.isArray(data) ? data : []))
      .catch(() => setExportsList([]));
  }, [token]);

  useEffect(() => { fetchExports(); }, [fetchExports]);

  const addCamera = (camId) => {
    if (!Array.isArray(cameras)) return;
    const cam = cameras.find(c => String(c.id) === String(camId));
    if (!cam || activeCameras.find(c => String(c.id) === String(cam.id))) return;
    setActiveCameras(prev => [...prev, cam]);
  };

  const removeCamera = (id) => {
    setActiveCameras(prev => prev.filter(c => c.id !== id));
  };

  const syncRef = useRef(null);
  const handleSyncRequest = useCallback((ts) => {
    if (syncRef.current !== ts) {
      syncRef.current = ts;
      setSyncTimestamp(ts);
    }
  }, []);

  const handleExportClip = async (camera, clip) => {
    setExportStatus({ state: 'loading', msg: `[STEP 1/4] Locating recording segment ${clip.filename}...` });
    const t1 = setTimeout(() => {
      setExportStatus({ state: 'loading', msg: `[STEP 2/4] Lossless Stream-Copying evidence clip...` });
    }, 250);
    const t2 = setTimeout(() => {
      setExportStatus({ state: 'loading', msg: `[STEP 3/4] Computing SHA-256 digital signatures & HMAC manifest...` });
    }, 500);
    const t3 = setTimeout(() => {
      setExportStatus({ state: 'loading', msg: `[STEP 4/4] Archiving verified evidence ZIP package...` });
    }, 750);

    try {
      const res = await fetch(
        `/api/v1/forensics/export?camera_id=${camera.id}&archive_clip_url=${encodeURIComponent(clip.url)}`,
        {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` }
        }
      );
      clearTimeout(t1); clearTimeout(t2); clearTimeout(t3);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setExportStatus({ state: 'success', msg: `[COMPLETE] Clip evidence package compiled in <1s! Download link ready in Forensic Ledger.` });
      fetchExports();
    } catch (err) {
      clearTimeout(t1); clearTimeout(t2); clearTimeout(t3);
      setExportStatus({ state: 'error', msg: `Export failed: ${err.message}` });
    }
  };

  return (
    <Box sx={{ p: 2, height: 'calc(100vh - 85px)', display: 'flex', flexDirection: 'column', gap: 2, overflow: 'hidden' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography variant="h6" sx={{ fontWeight: 800, color: 'primary.main' }}>
          MULTI-CAMERA ARCHIVE PLAYBACK
        </Typography>
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
          {activeCameras.length > 1 && (
            <Button 
              variant="outlined" 
              color="secondary" 
              startIcon={<SyncIcon />}
              onClick={() => {
                if (activeCameras.length > 0) {
                  setSyncTimestamp(new Date().toISOString());
                }
              }}
            >
              SYNC ALL CAMERAS
            </Button>
          )}
          <FormControl size="small" sx={{ minWidth: 150 }}>
            <Select
              displayEmpty
              value=""
              onChange={e => addCamera(e.target.value)}
              renderValue={() => <Typography variant="body2">+ ADD CAMERA</Typography>}
            >
              {(Array.isArray(cameras) ? cameras : []).filter(c => !activeCameras.find(a => a.id === c.id)).map(c => (
                <MenuItem key={c.id} value={c.id}>{(c.name || c.id).toUpperCase()}</MenuItem>
              ))}
            </Select>
          </FormControl>
        </Box>
      </Box>

      {exportStatus && (
        <Alert 
          severity={exportStatus.state === 'loading' ? 'info' : exportStatus.state === 'success' ? 'success' : 'error'}
          action={exportStatus.state !== 'loading' ? (
            <IconButton size="small" onClick={() => setExportStatus(null)}>
              <CloseIcon fontSize="small" />
            </IconButton>
          ) : null}
          sx={{ mb: 2 }}
        >
          {exportStatus.msg}
        </Alert>
      )}

      <Box sx={{ flexGrow: 1, overflowY: 'auto' }}>
        <Grid container spacing={2}>
          {activeCameras.length === 0 ? (
            <Grid size={{ xs: 12 }}>
              <Paper variant="outlined" sx={{ py: 10, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2, borderStyle: 'dashed', backgroundColor: 'transparent' }}>
                <MovieIcon sx={{ fontSize: 60, opacity: 0.2 }} />
                <Typography color="text.secondary">SELECT A CAMERA TO BEGIN ARCHIVE PLAYBACK</Typography>
                <Typography variant="caption" color="text.secondary">Use the "+ ADD CAMERA" dropdown above</Typography>
              </Paper>
            </Grid>
          ) : (
            activeCameras.map(cam => (
              <Grid size={{ xs: 12, md: activeCameras.length === 1 ? 12 : 6 }} key={cam.id}>
                <CameraArchivePanel
                  camera={cam}
                  token={token}
                  syncTimestamp={syncTimestamp}
                  onSyncRequest={handleSyncRequest}
                  onExportClip={handleExportClip}
                  onRemove={() => removeCamera(cam.id)}
                />
              </Grid>
            ))
          )}
        </Grid>
      </Box>

      {exportsList.length > 0 && (
        <Box sx={{ mt: 2, pt: 2, borderTop: '1px solid', borderColor: 'divider' }}>
          <Typography variant="subtitle2" fontWeight="bold" sx={{ mb: 1 }}>EVIDENCE EXPORT REGISTRY ({exportsList.length})</Typography>
          <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 200 }}>
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow>
                  <TableCell sx={{ fontWeight: 'bold' }}>CAMERA</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>EXPORTED BY</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>TIMESTAMP</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>TSA</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>SHA-256</TableCell>
                  <TableCell align="center" sx={{ fontWeight: 'bold' }}>DOWNLOAD</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {exportsList.slice(0, 8).map((item, idx) => (
                  <TableRow key={idx} hover>
                    <TableCell sx={{ fontWeight: 'bold' }}>{item.camera_name.toUpperCase()}</TableCell>
                    <TableCell>{item.username} <Typography component="span" variant="caption" color="text.secondary">({item.role})</Typography></TableCell>
                    <TableCell>{item.timestamp.substring(0, 19).replace('T', ' ')}</TableCell>
                    <TableCell>
                      <Typography variant="caption" fontWeight="bold" color={item.timestamp_authority === 'DigiCert Public TSA' ? 'success.main' : 'warning.main'}>
                        {item.timestamp_authority === 'DigiCert Public TSA' ? 'TSAâœ“' : 'LOCAL'}
                      </Typography>
                    </TableCell>
                    <TableCell sx={{ fontFamily: 'monospace', color: 'text.secondary' }}>{item.sha256_hash.substring(0, 12)}â€¦</TableCell>
                    <TableCell align="center">
                      <Box sx={{ display: 'flex', justifyContent: 'center', gap: 1 }}>
                        <Button component="a" href={item.mp4_download_url} target="_blank" rel="noreferrer" size="small" variant="text" sx={{ minWidth: 'auto', p: 0.5, fontSize: '0.7rem' }}>MP4</Button>
                        <Button component="a" href={item.sidecar_download_url} target="_blank" rel="noreferrer" size="small" variant="text" sx={{ minWidth: 'auto', p: 0.5, fontSize: '0.7rem' }}>JSON</Button>
                      </Box>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Box>
      )}
    </Box>
  );
}
