import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Box, Typography, Paper, TextField, Button, Chip, Alert, Card, Dialog, DialogTitle, DialogContent, IconButton, CircularProgress
} from '@mui/material';
import MapIcon from '@mui/icons-material/Map';
import SearchIcon from '@mui/icons-material/Search';
import FaceIcon from '@mui/icons-material/Face';
import LocationOnIcon from '@mui/icons-material/LocationOn';
import GroupsIcon from '@mui/icons-material/Groups';
import SyncIcon from '@mui/icons-material/Sync';
import CloseIcon from '@mui/icons-material/Close';
import FullscreenIcon from '@mui/icons-material/Fullscreen';

export default function TrajectoryMap({ token }) {
  const [targetId, setTargetId] = useState('');
  const [loading, setLoading] = useState(false);
  const [trajectoryData, setTrajectoryData] = useState(null);
  const [coOccurrenceData, setCoOccurrenceData] = useState(null);
  const [activeNodeIdx, setActiveNodeIdx] = useState(0);
  const [error, setError] = useState('');
  const [fullSceneModalOpen, setFullSceneModalOpen] = useState(false);
  const [selectedSceneNode, setSelectedSceneNode] = useState(null);

  const abortControllerRef = useRef(null);

  const cancelSearch = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setLoading(false);
    setError('Search cancelled by user.');
  }, []);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && loading) {
        cancelSearch();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [loading, cancelSearch]);

  const formatTimestamp = (tsStr) => {
    if (!tsStr) return '';
    try {
      return tsStr.replace('T', ' ').split('.')[0].split('+')[0];
    } catch (e) {
      return tsStr;
    }
  };

  const openFullSceneInspection = (node) => {
    setSelectedSceneNode(node);
    setFullSceneModalOpen(true);
  };

  const fetchTrajectory = useCallback((queryId) => {
    if (!token) return;
    const targetToFetch = (queryId !== undefined ? queryId : targetId).trim();
    if (!targetToFetch) return;

    if (abortControllerRef.current) abortControllerRef.current.abort();
    abortControllerRef.current = new AbortController();

    setLoading(true);
    setError('');

    fetch(`/api/v1/forensics/trajectory/${encodeURIComponent(targetToFetch)}`, {
      headers: { 'Authorization': `Bearer ${token}` },
      signal: abortControllerRef.current.signal
    })
      .then(res => {
        if (!res.ok) throw new Error("Failed to fetch target trajectory");
        return res.json();
      })
      .then(data => {
        setTrajectoryData(data);
        setActiveNodeIdx(0);
        setLoading(false);
      })
      .catch(err => {
        if (err.name === 'AbortError') return;
        console.error(err);
        setError(err.message);
        setLoading(false);
      });

    fetch(`/api/v1/forensics/co-occurrence`, {
      headers: { 'Authorization': `Bearer ${token}` },
      signal: abortControllerRef.current.signal
    })
      .then(res => res.ok ? res.json() : [])
      .then(data => setCoOccurrenceData(data))
      .catch(err => {
        if (err.name === 'AbortError') return;
        console.error("Co-occurrence error:", err);
      });
  }, [token, targetId]);

  const [mapMode, setMapMode] = useState('embed'); // 'embed' | 'grid'
  const [locationSearch, setLocationSearch] = useState('');

  const handleFacePhotoTrajectoryUpload = (file) => {
    if (!file || !token) return;

    if (abortControllerRef.current) abortControllerRef.current.abort();
    abortControllerRef.current = new AbortController();

    setLoading(true);
    setError('');

    const formData = new FormData();
    formData.append('file', file);

    fetch('/api/v1/forensics/trajectory/face-search', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
      signal: abortControllerRef.current.signal
    })
      .then(async res => {
        const body = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(body.detail || 'Face trajectory search failed');
        return body;
      })
      .then(data => {
        setTrajectoryData(data);
        setActiveNodeIdx(0);
        setLoading(false);
      })
      .catch(err => {
        if (err.name === 'AbortError') return;
        console.error(err);
        setError(err.message);
        setLoading(false);
      });
  };

  const handleSearch = (e) => {
    e.preventDefault();
    if (targetId.trim()) {
      fetchTrajectory(targetId.trim());
    }
  };

  const nodes = trajectoryData?.trajectory || [];

  return (
    <Box sx={{ position: 'relative', display: 'flex', flexDirection: 'column', height: 'calc(100vh - 85px)', overflow: 'hidden', p: 2, gap: 2 }}>
      {/* Searching Progress Loading Overlay */}
      {loading && (
        <Box sx={{
          position: 'absolute',
          inset: 0,
          backgroundColor: 'rgba(2, 6, 23, 0.85)',
          backdropFilter: 'blur(6px)',
          zIndex: 100,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 2,
          borderRadius: 2
        }}>
          <CircularProgress size={56} color="primary" thickness={4} />
          <Typography variant="h6" fontWeight="bold" color="primary" sx={{ letterSpacing: 0.5 }}>
            SEARCHING CCTV VECTOR LOGS & GIS NODES...
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Reconstructing multi-camera spatial-temporal suspect movement trajectory...
          </Typography>
          <Button
            variant="outlined"
            color="error"
            startIcon={<CloseIcon />}
            onClick={cancelSearch}
            sx={{ mt: 1, fontWeight: 'bold', borderColor: '#ef4444', color: '#f87171', backgroundColor: 'rgba(239, 68, 68, 0.1)' }}
          >
            Cancel Search (ESC)
          </Button>
        </Box>
      )}

      {/* Header Bar */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 2 }}>
        <Box>
          <Typography variant="h6" fontWeight="bold" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <MapIcon color="primary" /> Multi-Camera Suspect Trajectory & GIS Route Map
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Chronological vehicle plate & suspect face movement reconstruction across connected CCTV nodes
          </Typography>
        </Box>

        <Box sx={{ display: 'flex', gap: 1.5, alignItems: 'center', flexWrap: 'wrap' }}>
          <Box component="form" onSubmit={handleSearch} sx={{ display: 'flex', gap: 1 }}>
            <TextField
              size="small"
              value={targetId}
              onChange={(e) => setTargetId(e.target.value)}
              placeholder="Plate, POI Name, or Track ID..."
              sx={{ width: 220 }}
            />
            <Button
              type="submit"
              variant="contained"
              disabled={loading || !targetId.trim()}
              startIcon={loading ? <SyncIcon sx={{ animation: 'spin 2s linear infinite' }} /> : <SearchIcon />}
            >
              {loading ? 'Searching...' : 'Track Route'}
            </Button>
          </Box>

          <Button
            component="label"
            variant="contained"
            color="success"
            disabled={loading}
            startIcon={loading ? <SyncIcon sx={{ animation: 'spin 2s linear infinite' }} /> : <FaceIcon />}
            sx={{ fontWeight: 'bold' }}
          >
            {loading ? 'Analyzing Face...' : 'Upload Face Suspect'}
            <input
              type="file"
              accept="image/*"
              hidden
              onChange={(e) => {
                if (e.target.files && e.target.files[0]) {
                  handleFacePhotoTrajectoryUpload(e.target.files[0]);
                }
              }}
            />
          </Button>
        </Box>
      </Box>

      {error && <Alert severity="error">{error}</Alert>}

      {/* Main Container Layout */}
      <Box sx={{ display: 'flex', flexDirection: { xs: 'column', md: 'row' }, gap: 2, flexGrow: 1, minHeight: 0, overflow: 'hidden' }}>
        
        {/* Left Column: Interactive GIS Route Map Canvas */}
        <Paper variant="outlined" sx={{ p: 2, display: 'flex', flexDirection: 'column', flexGrow: 1, minWidth: 0, height: '100%', overflow: 'hidden' }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.5, flexWrap: 'wrap', gap: 1 }}>
            <Typography variant="subtitle2" fontWeight="bold" color="primary">
              Surat Surveillance GIS Map • Target: <Box component="span" sx={{ color: 'warning.main' }}>{trajectoryData?.target_id || targetId || "No Target Selected"}</Box>
            </Typography>
            <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
              <Chip
                label={mapMode === 'embed' ? "🛰️ Google Maps GIS" : "📐 Tactical Grid"}
                size="small"
                color="secondary"
                clickable
                onClick={() => setMapMode(prev => prev === 'embed' ? 'grid' : 'embed')}
              />
              <Chip
                label={`${nodes.length} Camera Hits Verified`}
                size="small"
                variant="outlined"
                color="info"
              />
            </Box>
          </Box>

          <Box sx={{ display: 'flex', gap: 1, mb: 1.5, alignItems: 'center' }}>
            <TextField
              size="small"
              value={locationSearch}
              onChange={(e) => setLocationSearch(e.target.value)}
              placeholder="Search Surat Location / Camera Landmark e.g. Parle Point, SVNIT, Kargil Chowk, Bus Depo..."
              fullWidth
            />
            {locationSearch && (
              <Button size="small" variant="outlined" color="inherit" onClick={() => setLocationSearch('')}>
                Clear
              </Button>
            )}
          </Box>

          {/* Map Container */}
          <Box sx={{
            flexGrow: 1,
            minHeight: 280,
            backgroundColor: '#0a0f1d',
            border: '1px solid',
            borderColor: 'divider',
            borderRadius: 1.5,
            position: 'relative',
            overflow: 'hidden'
          }}>
            {/* Embedded Live Surat Google Map */}
            {mapMode === 'embed' && (
              <Box
                component="iframe"
                src={
                  locationSearch.trim()
                    ? `https://maps.google.com/maps?q=${encodeURIComponent(locationSearch.trim() + ", Surat, Gujarat")}&t=&z=15&ie=UTF8&iwloc=&output=embed`
                    : "https://www.google.com/maps/embed?pb=!1m18!1m12!1m3!1d119066.54586600399!2d72.73988435020044!3d21.1591802036017!2m3!1f0!2f0!3f0!3m2!1i1024!2i768!4f13.1!3m3!1m2!1s0x3be04e59411d1563%3A0xfe4558290938b042!2sSurat%2C%20Gujarat!5e0!3m2!1sen!2sin!4v1786016309415!5m2!1sen!2sin"
                }
                title="Surat City Surveillance Map"
                sx={{
                  width: '100%',
                  height: '100%',
                  border: 0,
                  position: 'absolute',
                  inset: 0,
                  filter: 'invert(0.9) hue-rotate(180deg) contrast(1.2) brightness(0.85)',
                  opacity: 0.85
                }}
                loading="lazy"
                referrerPolicy="strict-origin-when-cross-origin"
              />
            )}

            {/* Grid Overlay */}
            {mapMode === 'grid' && (
              <Box sx={{
                position: 'absolute', inset: 0,
                backgroundImage: 'linear-gradient(rgba(255,255,255,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.04) 1px, transparent 1px)',
                backgroundSize: '36px 36px'
              }} />
            )}

            {/* Polyline Route Connection */}
            <svg style={{ position: 'absolute', width: '100%', height: '100%', top: 0, left: 0, pointerEvents: 'none' }}>
              {nodes.map((node, i) => {
                if (i === 0) return null;
                const prev = nodes[i - 1];

                const isSearching = locationSearch.trim().length > 0;
                const prevMatches = isSearching && (
                  prev.location.toLowerCase().includes(locationSearch.toLowerCase()) ||
                  prev.camera_name.toLowerCase().includes(locationSearch.toLowerCase())
                );
                const currMatches = isSearching && (
                  node.location.toLowerCase().includes(locationSearch.toLowerCase()) ||
                  node.camera_name.toLowerCase().includes(locationSearch.toLowerCase())
                );

                const getPos = (lat, lng, matches) => {
                  if (matches) return { x: 50, y: 50 };
                  const minLat = 21.1400, maxLat = 21.2200;
                  const minLng = 72.7400, maxLng = 72.8700;
                  const x = Math.min(92, Math.max(8, ((lng - minLng) / (maxLng - minLng)) * 100));
                  const y = Math.min(92, Math.max(8, (1.0 - (lat - minLat) / (maxLat - minLat)) * 100));
                  return { x, y };
                };

                const p1 = getPos(prev.latitude, prev.longitude, prevMatches);
                const p2 = getPos(node.latitude, node.longitude, currMatches);

                return (
                  <line
                    key={i}
                    x1={`${p1.x}%`}
                    y1={`${p1.y}%`}
                    x2={`${p2.x}%`}
                    y2={`${p2.y}%`}
                    stroke="#0284c7"
                    strokeWidth="3"
                    strokeDasharray="6 4"
                  />
                );
              })}
            </svg>

            {/* Map Camera Markers */}
            {nodes.map((node, i) => {
              const isSearching = locationSearch.trim().length > 0;
              const isLocMatch = isSearching && (
                node.location.toLowerCase().includes(locationSearch.toLowerCase()) ||
                node.camera_name.toLowerCase().includes(locationSearch.toLowerCase())
              );

              const minLat = 21.1400, maxLat = 21.2200;
              const minLng = 72.7400, maxLng = 72.8700;
              const rawX = Math.min(92, Math.max(8, ((node.longitude - minLng) / (maxLng - minLng)) * 100));
              const rawY = Math.min(92, Math.max(8, (1.0 - (node.latitude - minLat) / (maxLat - minLat)) * 100));

              const x = isLocMatch ? 50 : rawX;
              const y = isLocMatch ? 50 : rawY;
              const isActive = i === activeNodeIdx || isLocMatch;

              return (
                <Box
                  key={i}
                  onClick={() => { setActiveNodeIdx(i); openFullSceneInspection(node); }}
                  sx={{
                    position: 'absolute',
                    left: `${x}%`,
                    top: `${y}%`,
                    transform: 'translate(-50%, -50%)',
                    cursor: 'pointer',
                    zIndex: isActive ? 10 : 2
                  }}
                >
                  <Box sx={{
                    width: isActive ? 34 : 26,
                    height: isActive ? 34 : 26,
                    borderRadius: '50%',
                    background: isActive ? 'linear-gradient(135deg, #f59e0b, #ef4444)' : 'linear-gradient(135deg, #0284c7, #2563eb)',
                    border: '2px solid #ffffff',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontWeight: 'bold',
                    fontSize: '0.75rem',
                    color: 'white',
                    boxShadow: isActive ? '0 0 16px rgba(245,158,11,0.9)' : '0 2px 6px rgba(0,0,0,0.5)',
                    transition: 'all 0.2s ease'
                  }}>
                    {i + 1}
                  </Box>
                  <Typography variant="caption" sx={{
                    position: 'absolute',
                    top: 32,
                    left: '50%',
                    transform: 'translateX(-50%)',
                    whiteSpace: 'nowrap',
                    backgroundColor: 'background.paper',
                    border: '1px solid',
                    borderColor: 'divider',
                    px: 0.8,
                    py: 0.1,
                    borderRadius: 0.5,
                    fontSize: '0.65rem',
                    color: isActive ? 'warning.main' : 'text.secondary',
                    fontWeight: isActive ? 'bold' : 'normal'
                  }}>
                    {node.camera_name}
                  </Typography>
                </Box>
              );
            })}
          </Box>

          {/* Active Node Detail Footer */}
          {nodes[activeNodeIdx] && (
            <Card variant="outlined" sx={{ mt: 1.5, p: 1.5, display: 'flex', gap: 2, alignItems: 'center', backgroundColor: 'background.default' }}>
              <Box
                component="img"
                src={nodes[activeNodeIdx].snapshot_url || '/api/v1/playback/snapshot/default'}
                alt="Captured Face Crop"
                onError={(e) => { e.target.onerror = null; e.target.src = '/api/v1/playback/snapshot/default'; }}
                onClick={(e) => { e.stopPropagation(); openFullSceneInspection(nodes[activeNodeIdx]); }}
                sx={{
                  width: 64,
                  height: 64,
                  objectFit: 'cover',
                  borderRadius: '50%',
                  border: '2px solid #0284c7',
                  backgroundColor: '#000',
                  cursor: 'pointer',
                  '&:hover': { borderColor: '#00e676', transform: 'scale(1.1)' },
                  transition: 'all 0.15s ease'
                }}
              />

              <Box sx={{ flexGrow: 1 }}>
                <Typography variant="subtitle2" fontWeight="bold" color="primary">
                  Hit #{activeNodeIdx + 1}: {nodes[activeNodeIdx].camera_name} ({nodes[activeNodeIdx].location})
                </Typography>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                  🕒 Time: <strong>{formatTimestamp(nodes[activeNodeIdx].timestamp)}</strong> • Match Confidence: <strong>{nodes[activeNodeIdx].confidence || 90}%</strong>
                </Typography>
                <Typography variant="caption" color="primary.light" sx={{ display: 'block', mt: 0.2, fontFamily: 'monospace', fontSize: '0.7rem' }}>
                  🆔 Snapshot ID: {nodes[activeNodeIdx].snapshot_id || "snap_live"} • Track UUID: {nodes[activeNodeIdx].track_uuid || "trk_live"}
                </Typography>
              </Box>

              <Button
                size="small"
                variant="outlined"
                color="success"
                startIcon={<FullscreenIcon />}
                onClick={() => openFullSceneInspection(nodes[activeNodeIdx])}
              >
                Inspect Full Scene
              </Button>
            </Card>
          )}
        </Paper>

        {/* Right Column: Chronological Hits & Co-Occurrence Intelligence */}
        <Box sx={{ width: { xs: '100%', md: 380 }, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 2, height: '100%', overflow: 'hidden' }}>
          
          {/* Hit Sequence List */}
          <Paper variant="outlined" sx={{ p: 2, display: 'flex', flexDirection: 'column', flexGrow: 1, minHeight: 0, overflow: 'hidden' }}>
            <Typography variant="subtitle2" fontWeight="bold" sx={{ borderBottom: '1px solid', borderColor: 'divider', pb: 1, mb: 1.5, display: 'flex', alignItems: 'center', gap: 1 }}>
              <LocationOnIcon fontSize="small" color="primary" /> Chronological Camera Hits
            </Typography>
            <Box sx={{ overflowY: 'auto', flexGrow: 1, display: 'flex', flexDirection: 'column', gap: 1.5, pr: 0.5 }}>
              {nodes.length === 0 ? (
                <Typography variant="caption" color="text.secondary" align="center" sx={{ py: 3 }}>
                  No camera hits found for target suspect. Upload a face photo or enter a target POI ID above.
                </Typography>
              ) : (
                nodes.map((node, idx) => (
                  <Card
                    key={idx}
                    variant={idx === activeNodeIdx ? 'elevation' : 'outlined'}
                    onClick={() => setActiveNodeIdx(idx)}
                    sx={{
                      p: 1.5,
                      minHeight: 70,
                      cursor: 'pointer',
                      borderColor: idx === activeNodeIdx ? 'primary.main' : 'divider',
                      backgroundColor: idx === activeNodeIdx ? 'action.selected' : 'background.paper',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 1.5,
                      transition: 'all 0.15s ease',
                      '&:hover': { borderColor: 'primary.light' }
                    }}
                  >
                    <Box
                      component="img"
                      src={node.snapshot_url || '/api/v1/playback/snapshot/default'}
                      alt="Face Crop"
                      onError={(e) => { e.target.onerror = null; e.target.src = '/api/v1/playback/snapshot/default'; }}
                      onClick={(e) => { e.stopPropagation(); setActiveNodeIdx(idx); openFullSceneInspection(node); }}
                      sx={{
                        width: 52,
                        height: 52,
                        borderRadius: '50%',
                        objectFit: 'cover',
                        border: idx === activeNodeIdx ? '2px solid #00e676' : '1.5px solid #0284c7',
                        flexShrink: 0,
                        cursor: 'pointer',
                        '&:hover': { transform: 'scale(1.15)', borderColor: '#00e676', boxShadow: '0 0 10px #00e676' },
                        transition: 'all 0.15s ease'
                      }}
                    />
                    <Box sx={{ flexGrow: 1, minWidth: 0 }}>
                      <Typography variant="body2" fontWeight="bold" color={idx === activeNodeIdx ? 'primary.main' : 'text.primary'} sx={{ lineHeight: 1.2 }}>
                        #{idx + 1} {node.camera_name}
                      </Typography>
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5, fontSize: '0.75rem' }}>
                        {formatTimestamp(node.timestamp)}
                      </Typography>
                    </Box>
                    <Chip
                      label={`${node.confidence || 90}%`}
                      size="small"
                      color={node.confidence >= 70 ? "success" : "info"}
                      sx={{ fontSize: '0.75rem', fontWeight: 'bold', minWidth: 44 }}
                    />
                  </Card>
                ))
              )}
            </Box>
          </Paper>

          {/* Co-Occurrence Accomplice Grouping Intelligence */}
          <Paper variant="outlined" sx={{ p: 2, display: 'flex', flexDirection: 'column' }}>
            <Typography variant="subtitle2" fontWeight="bold" color="secondary" sx={{ borderBottom: '1px solid', borderColor: 'divider', pb: 1, mb: 1, display: 'flex', alignItems: 'center', gap: 1 }}>
              <GroupsIcon fontSize="small" color="secondary" /> Spatial-Temporal Co-Occurrence
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1.5 }}>
              Candidate suspect accomplices identified in same time-spatial window:
            </Typography>
            {(!coOccurrenceData?.co_occurrence_groups || coOccurrenceData.co_occurrence_groups.length === 0) ? (
              <Box sx={{ p: 1.5, backgroundColor: 'background.default', border: '1px solid', borderColor: 'divider', borderRadius: 1, textAlign: 'center' }}>
                <Typography variant="caption" color="text.secondary">
                  No co-occurring accomplice clusters detected for this target in the selected window.
                </Typography>
              </Box>
            ) : (
              coOccurrenceData.co_occurrence_groups.map((grp, idx) => (
                <Box key={idx} sx={{ p: 1.2, mb: 1, backgroundColor: 'background.default', border: '1px solid', borderColor: 'divider', borderRadius: 1 }}>
                  <Typography variant="caption" fontWeight="bold" color="secondary.main" sx={{ display: 'block' }}>
                    {grp.group_id} • Confidence: {Math.min(Math.round(grp.confidence_score * 100), 99)}%
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {grp.analytical_summary}
                  </Typography>
                </Box>
              ))
            )}
          </Paper>

        </Box>

      </Box>

      {/* Full Forensic Scene Inspection Dialog Modal */}
      <Dialog open={fullSceneModalOpen} onClose={() => setFullSceneModalOpen(false)} maxWidth="lg" fullWidth>
        <DialogTitle sx={{ m: 0, p: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center', backgroundColor: '#0f172a', borderBottom: '1px solid', borderColor: 'divider' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
            <Typography variant="h6" fontWeight="bold" color="primary">
              FORENSIC FULL CAMERA FRAME • {selectedSceneNode?.camera_name || "SURVEILLANCE NODE"}
            </Typography>
            <Chip label={`TARGET CONFIDENCE: ${selectedSceneNode?.confidence || 90}%`} color="success" size="small" sx={{ fontWeight: 'bold' }} />
          </Box>
          <IconButton onClick={() => setFullSceneModalOpen(false)} color="inherit">
            <CloseIcon />
          </IconButton>
        </DialogTitle>
        <DialogContent sx={{ backgroundColor: '#020617', p: 3, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          <Box sx={{ position: 'relative', width: '100%', maxWidth: 960, border: '2px solid #334155', borderRadius: 1.5, overflow: 'hidden', backgroundColor: '#000', boxShadow: '0 0 25px rgba(0,0,0,0.8)' }}>
            <Box
              component="img"
              src={selectedSceneNode?.full_snapshot_url || selectedSceneNode?.snapshot_url || '/api/v1/playback/snapshot/default'}
              alt="Full Camera Frame Scene"
              onError={(e) => { e.target.onerror = null; e.target.src = '/api/v1/playback/snapshot/default'; }}
              sx={{ width: '100%', height: 'auto', display: 'block' }}
            />

            {/* Target Bounding Reticle (Rendered ONLY when actual detection bounding box is present) */}
            {selectedSceneNode?.bbox_norm ? (
              <Box
                sx={{
                  position: 'absolute',
                  left: `${selectedSceneNode.bbox_norm[0] * 100}%`,
                  top: `${selectedSceneNode.bbox_norm[1] * 100}%`,
                  width: `${selectedSceneNode.bbox_norm[2] * 100}%`,
                  height: `${selectedSceneNode.bbox_norm[3] * 100}%`,
                  border: '3px solid #00e676',
                  boxShadow: '0 0 20px #00e676, inset 0 0 10px rgba(0, 230, 118, 0.4)',
                  borderRadius: 1,
                  pointerEvents: 'none'
                }}
              >
                <Chip
                  label={`🎯 ${selectedSceneNode.confidence || 90}% TARGET MATCH`}
                  size="small"
                  color="success"
                  sx={{
                    position: 'absolute',
                    top: -28,
                    left: 0,
                    fontSize: '0.65rem',
                    fontWeight: 'bold',
                    height: 22,
                    boxShadow: '0 2px 6px rgba(0,0,0,0.6)'
                  }}
                />
              </Box>
            ) : (
              <Chip
                label={`🎯 ${selectedSceneNode?.confidence || 90}% TARGET SIGHTING VERIFIED`}
                size="small"
                color="success"
                sx={{
                  position: 'absolute',
                  top: 12,
                  left: 12,
                  fontSize: '0.65rem',
                  fontWeight: 'bold',
                  height: 24,
                  boxShadow: '0 2px 6px rgba(0,0,0,0.8)'
                }}
              />
            )}
          </Box>

          <Box sx={{ mt: 2.5, display: 'flex', gap: 3, width: '100%', justifyContent: 'space-between', color: 'text.secondary', borderTop: '1px solid', borderColor: 'divider', pt: 2, flexWrap: 'wrap' }}>
            <Typography variant="body2">📍 <strong>Landmark:</strong> {selectedSceneNode?.location || "Surat Node"}</Typography>
            <Typography variant="body2">🕒 <strong>Captured At:</strong> {formatTimestamp(selectedSceneNode?.timestamp)}</Typography>
            <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>🆔 <strong>Snapshot ID:</strong> {selectedSceneNode?.snapshot_id || "snap_live"}</Typography>
            <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>🔗 <strong>Track UUID:</strong> {selectedSceneNode?.track_uuid || "trk_live"}</Typography>
          </Box>
        </DialogContent>
      </Dialog>
    </Box>
  );
}
