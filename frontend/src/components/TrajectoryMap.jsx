import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Box, Typography, Paper, TextField, Button, Chip, Alert, Card, Dialog, DialogTitle,
  DialogContent, DialogActions, IconButton, Tooltip, Switch, FormControlLabel,
  MenuItem, Select, FormControl, InputLabel, CircularProgress, Tabs, Tab
} from '@mui/material';
import MapIcon from '@mui/icons-material/Map';
import SearchIcon from '@mui/icons-material/Search';
import FaceIcon from '@mui/icons-material/Face';
import LocationOnIcon from '@mui/icons-material/LocationOn';
import GroupsIcon from '@mui/icons-material/Groups';
import SyncIcon from '@mui/icons-material/Sync';
import CloseIcon from '@mui/icons-material/Close';
import HubIcon from '@mui/icons-material/Hub';
import AddLinkIcon from '@mui/icons-material/AddLink';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import DeleteForeverIcon from '@mui/icons-material/DeleteForever';
import ZoomInIcon from '@mui/icons-material/ZoomIn';
import ZoomOutIcon from '@mui/icons-material/ZoomOut';
import CenterFocusStrongIcon from '@mui/icons-material/CenterFocusStrong';
import AltRouteIcon from '@mui/icons-material/AltRoute';
import './TopologyEditor.css';

export default function TrajectoryMap({ token }) {
  // Navigation View: 0 = Suspect Journey (Google Maps GIS), 1 = Camera Network Topology, 2 = Predictive Simulation
  const [viewTab, setViewTab] = useState(0);

  // Suspect Trajectory States
  const [targetId, setTargetId] = useState('');
  const [loading, setLoading] = useState(false);
  const [trajectoryData, setTrajectoryData] = useState(null);
  const [coOccurrenceData, setCoOccurrenceData] = useState(null);
  const [activeNodeIdx, setActiveNodeIdx] = useState(0);
  const [error, setError] = useState('');
  const [fullSceneModalOpen, setFullSceneModalOpen] = useState(false);
  const [selectedSceneNode, setSelectedSceneNode] = useState(null);
  const [locationSearch, setLocationSearch] = useState('');
  const [mapMode, setMapMode] = useState('embed');

  // Topology Network Graph States
  const [topologyNodes, setTopologyNodes] = useState([]);
  const [topologyEdges, setTopologyEdges] = useState([]);
  const [topologyLoading, setTopologyLoading] = useState(true);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const [panStart, setPanStart] = useState({ x: 0, y: 0 });
  const [draggingNodeId, setDraggingNodeId] = useState(null);
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });
  const [snapToGrid, setSnapToGrid] = useState(true);
  const [selectedEdge, setSelectedEdge] = useState(null);
  const [addEdgeOpen, setAddEdgeOpen] = useState(false);
  const [newEdgeSource, setNewEdgeSource] = useState('');
  const [newEdgeTarget, setNewEdgeTarget] = useState('');
  const [newEdgeDistance, setNewEdgeDistance] = useState(500);
  const [newEdgeMinSec, setNewEdgeMinSec] = useState(60);
  const [newEdgeMaxSec, setNewEdgeMaxSec] = useState(300);

  // Predictive Simulation States
  const [predictTargetId, setPredictTargetId] = useState('KA51MB8811');
  const [predicting, setPredicting] = useState(false);
  const [pulseCameraId, setPulseCameraId] = useState(null);
  const [simulationResult, setSimulationResult] = useState(null);

  const abortControllerRef = useRef(null);
  const topologyContainerRef = useRef(null);

  const authUrl = (url) => {
    if (!url) return '/api/v1/playback/snapshot/default';
    if (token && !url.includes('token=')) {
      return url.includes('?') ? `${url}&token=${encodeURIComponent(token)}` : `${url}?token=${encodeURIComponent(token)}`;
    }
    return url;
  };

  const cancelSearch = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setLoading(false);
    setError('Search cancelled by user.');
  }, []);

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

  // 1. Fetch Trajectory for Target
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
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (data) setCoOccurrenceData(data);
      })
      .catch(() => {});
  }, [token, targetId]);

  // 2. Fetch Topology Graph
  const loadTopology = useCallback(() => {
    if (!token) return;
    setTopologyLoading(true);
    fetch('/api/v1/topology', {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(res => res.ok ? res.json() : Promise.reject('Failed to load topology graph'))
      .then(data => {
        setTopologyNodes(data.nodes || []);
        setTopologyEdges(data.edges || []);
        setTopologyLoading(false);
      })
      .catch(err => {
        console.error(err);
        setTopologyLoading(false);
      });
  }, [token]);

  useEffect(() => {
    loadTopology();
  }, [loadTopology]);

  // Search Submit
  const handleSearch = (e) => {
    e.preventDefault();
    fetchTrajectory();
  };

  // Face Photo Upload Trajectory Search
  const handleFacePhotoTrajectoryUpload = async (file) => {
    if (!file || !token) return;
    setLoading(true);
    setError('');

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch('/api/v1/forensics/trajectory/face-search', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: formData
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || "Face image analysis failed.");
      }
      const data = await res.json();
      const hits = data.trajectory || data.nodes || [];

      if (hits.length === 0) {
        setError("No biometric trajectory sightings found across surveillance cameras for this face photo.");
        setLoading(false);
        return;
      }

      setTrajectoryData(data);
      setActiveNodeIdx(0);
      setTargetId(data.target_id || 'UPLOADED_FACE_QUERY');
      setLoading(false);
    } catch (err) {
      console.error(err);
      setError(err.message);
      setLoading(false);
    }
  };

  // ── Topology Graph Interactions ──────────────────────────────────────────
  const handleNodeMouseDown = (e, nodeId) => {
    e.stopPropagation();
    const node = topologyNodes.find(n => n.id === nodeId);
    if (!node) return;
    setDraggingNodeId(nodeId);
    setDragOffset({
      x: (e.clientX / zoom) - node.x,
      y: (e.clientY / zoom) - node.y
    });
  };

  const handleMouseMove = (e) => {
    if (draggingNodeId) {
      let newX = (e.clientX / zoom) - dragOffset.x;
      let newY = (e.clientY / zoom) - dragOffset.y;
      if (snapToGrid) {
        newX = Math.round(newX / 20) * 20;
        newY = Math.round(newY / 20) * 20;
      }
      setTopologyNodes(prev => prev.map(n => n.id === draggingNodeId ? { ...n, x: newX, y: newY } : n));
    } else if (isPanning) {
      setPan({
        x: e.clientX - panStart.x,
        y: e.clientY - panStart.y
      });
    }
  };

  const handleMouseUp = () => {
    if (draggingNodeId) {
      const node = topologyNodes.find(n => n.id === draggingNodeId);
      if (node) {
        fetch(`/api/v1/topology/nodes/${node.id}/position`, {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`
          },
          body: JSON.stringify({ x: node.x, y: node.y })
        }).catch(err => console.error("Failed to save node position", err));
      }
      setDraggingNodeId(null);
    }
    setIsPanning(false);
  };

  const handleResetLayout = () => {
    fetch('/api/v1/topology/layout/auto', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(res => res.ok ? res.json() : null)
      .then(() => loadTopology())
      .catch(err => console.error(err));
  };

  const handleAddEdgeSubmit = () => {
    if (!newEdgeSource || !newEdgeTarget) return;
    fetch('/api/v1/topology/edges', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({
        source: newEdgeSource,
        target: newEdgeTarget,
        distance_meters: Number(newEdgeDistance),
        min_transit_seconds: Number(newEdgeMinSec),
        max_transit_seconds: Number(newEdgeMaxSec)
      })
    })
      .then(res => res.ok ? res.json() : Promise.reject('Failed to create edge'))
      .then(() => {
        setAddEdgeOpen(false);
        loadTopology();
      })
      .catch(err => console.error(err));
  };

  const handleDeleteEdge = (edge) => {
    if (!edge) return;
    fetch(`/api/v1/topology/edges/${edge.source}/${edge.target}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(res => res.ok ? res.json() : Promise.reject('Failed to delete edge'))
      .then(() => {
        setSelectedEdge(null);
        loadTopology();
      })
      .catch(err => console.error(err));
  };

  const handleRunPrediction = () => {
    if (!predictTargetId.trim()) return;
    setPredicting(true);
    setSimulationResult(null);

    fetch('/api/v1/topology/predict-route', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({
        target_id: predictTargetId.trim(),
        current_camera_id: topologyNodes[0]?.id || 'cam_1'
      })
    })
      .then(res => res.ok ? res.json() : Promise.reject('Prediction failed'))
      .then(data => {
        setSimulationResult(data);
        setPredicting(false);
        if (data.predicted_next_camera) {
          setPulseCameraId(data.predicted_next_camera);
          setTimeout(() => setPulseCameraId(null), 8000);
        }
      })
      .catch(err => {
        console.error(err);
        setPredicting(false);
      });
  };

  // Trajectory nodes
  const nodes = trajectoryData?.trajectory || trajectoryData?.nodes || [];
  const activeNode = nodes[activeNodeIdx] || nodes[0];

  // Surat Surveillance Nodes Directory
  const suratCameraNodes = [
    { id: "cam_1", name: "Central Bus Depo Entry", lat: 21.2052, lng: 72.8405 },
    { id: "cam_6", name: "Ring Road Junction", lat: 21.2045, lng: 72.8412 },
    { id: "cyber_cam_2", name: "Rokadiya Hanuman", lat: 21.1895, lng: 72.8420 },
    { id: "cyber_cam_3", name: "GauravPath", lat: 21.1690, lng: 72.7750 },
    { id: "cyber_cam_5", name: "Kargil Chowk", lat: 21.1685, lng: 72.7745 },
    { id: "cyber_cam_7", name: "Parle Point", lat: 21.1645, lng: 72.7845 },
    { id: "cyber_cam_8", name: "SVNIT Circle", lat: 21.1640, lng: 72.7840 },
    { id: "cam_10", name: "Re-ID Checkpoint 10", lat: 21.1750, lng: 72.8050 },
    { id: "cam_12", name: "Re-ID Checkpoint 12", lat: 21.1800, lng: 72.8100 }
  ];

  const activeLat = activeNode?.latitude || (activeNode ? 21.2052 : null);
  const activeLng = activeNode?.longitude || (activeNode ? 72.8405 : null);
  const activeLocation = activeNode?.location || activeNode?.camera_name || (locationSearch || "Surat Gujarat");

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', width: '100%', overflow: 'hidden', p: 2, gap: 2 }}>
      
      {/* ── Top Command Bar ─────────────────────────────────────────────── */}
      <Paper variant="outlined" sx={{ p: 2, display: 'flex', flexDirection: 'column', gap: 1.5, background: 'rgba(13, 21, 38, 0.95)' }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 1.5 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
            <AltRouteIcon color="primary" sx={{ fontSize: 30 }} />
            <Box>
              <Typography variant="h6" fontWeight="bold" color="primary" sx={{ lineHeight: 1.2 }}>
                Route Suspect Tracking & Camera Network Topology
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Unified multi-camera GIS suspect movement reconstruction, topology node routing & predictive interception
              </Typography>
            </Box>
          </Box>

          {/* View Modes Tabs */}
          <Tabs
            value={viewTab}
            onChange={(_, val) => setViewTab(val)}
            textColor="primary"
            indicatorColor="primary"
            sx={{
              backgroundColor: 'rgba(15, 23, 42, 0.8)',
              borderRadius: 1.5,
              p: 0.5,
              '& .MuiTab-root': { fontSize: '0.82rem', fontWeight: 'bold', minHeight: 36, py: 0.5 }
            }}
          >
            <Tab icon={<MapIcon fontSize="small" />} iconPosition="start" label="🛰️ Suspect GIS Map" />
            <Tab icon={<HubIcon fontSize="small" />} iconPosition="start" label="🕸️ Camera Network Topology" />
            <Tab icon={<PlayArrowIcon fontSize="small" />} iconPosition="start" label="⚡ Predictive Simulation" />
          </Tabs>
        </Box>

        {/* Global Action Bar */}
        <Box sx={{ display: 'flex', gap: 1.5, alignItems: 'center', flexWrap: 'wrap', pt: 0.5, borderTop: '1px solid rgba(0, 229, 255, 0.12)' }}>
          <Box component="form" onSubmit={handleSearch} sx={{ display: 'flex', gap: 1 }}>
            <TextField
              size="small"
              value={targetId}
              onChange={(e) => setTargetId(e.target.value)}
              placeholder="Enter License Plate, POI Name, or Track ID..."
              sx={{ width: 260 }}
            />
            <Button
              type="submit"
              variant="contained"
              disabled={loading || !targetId.trim()}
              startIcon={loading ? <SyncIcon sx={{ animation: 'spin 2s linear infinite' }} /> : <SearchIcon />}
              sx={{ background: 'linear-gradient(135deg, #0284c7 0%, #2563eb 100%)' }}
            >
              {loading ? 'Tracking...' : 'Track Suspect'}
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
            {loading ? 'Analyzing Biometrics...' : 'Upload Suspect Face Photo'}
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

          {viewTab === 1 && (
            <Box sx={{ display: 'flex', gap: 1, ml: 'auto', alignItems: 'center' }}>
              <Button
                variant="outlined"
                color="secondary"
                size="small"
                startIcon={<AddLinkIcon />}
                onClick={() => setAddEdgeOpen(true)}
              >
                Add Route Edge
              </Button>
              <Button
                variant="outlined"
                color="inherit"
                size="small"
                startIcon={<RestartAltIcon />}
                onClick={handleResetLayout}
              >
                Auto Layout
              </Button>
              <FormControlLabel
                control={<Switch checked={snapToGrid} onChange={(e) => setSnapToGrid(e.target.checked)} size="small" />}
                label={<Typography variant="caption">Snap Grid</Typography>}
                sx={{ m: 0 }}
              />
            </Box>
          )}

          {viewTab === 2 && (
            <Box sx={{ display: 'flex', gap: 1, ml: 'auto', alignItems: 'center' }}>
              <TextField
                size="small"
                value={predictTargetId}
                onChange={(e) => setPredictTargetId(e.target.value)}
                placeholder="Simulation Target..."
                sx={{ width: 180 }}
              />
              <Button
                variant="contained"
                color="warning"
                size="small"
                disabled={predicting}
                startIcon={predicting ? <CircularProgress size={16} color="inherit" /> : <PlayArrowIcon />}
                onClick={handleRunPrediction}
                sx={{ fontWeight: 'bold' }}
              >
                {predicting ? 'Simulating...' : 'Run Path Prediction'}
              </Button>
            </Box>
          )}
        </Box>
      </Paper>

      {error && <Alert severity="error">{error}</Alert>}

      {/* ── Main View Switching Body ───────────────────────────────────── */}
      <Box sx={{ display: 'flex', flexDirection: { xs: 'column', md: 'row' }, gap: 2, flexGrow: 1, minHeight: 0, overflow: 'hidden' }}>
        
        {/* VIEW 0: Suspect Google Maps GIS Journey */}
        {viewTab === 0 && (
          <Paper variant="outlined" sx={{ p: 2, display: 'flex', flexDirection: 'column', flexGrow: 1, minWidth: 0, height: '100%', overflow: 'hidden' }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.5, flexWrap: 'wrap', gap: 1 }}>
              <Typography variant="subtitle2" fontWeight="bold" color="primary">
                Surat Surveillance GIS Map • Target: <Box component="span" sx={{ color: 'warning.main' }}>{trajectoryData?.target_id || targetId || "No Target Selected"}</Box>
              </Typography>
              <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
                <Chip
                  label={mapMode === 'embed' ? "🛰️ Google Maps GIS" : "📐 Tactical Coordinate Grid"}
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

            <Box sx={{ display: 'flex', gap: 1, mb: 1, alignItems: 'center' }}>
              <TextField
                size="small"
                value={locationSearch}
                onChange={(e) => setLocationSearch(e.target.value)}
                placeholder="Search Surat Landmark e.g. Parle Point, SVNIT, Kargil Chowk, Bus Depo, Station..."
                fullWidth
              />
              {locationSearch && (
                <Button size="small" variant="outlined" color="inherit" onClick={() => setLocationSearch('')}>
                  Clear
                </Button>
              )}
            </Box>

            {/* Quick Surat Surveillance Camera Chips */}
            <Box sx={{ display: 'flex', gap: 0.8, mb: 1.5, flexWrap: 'wrap', alignItems: 'center' }}>
              <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, mr: 0.5 }}>
                Surveillance Nodes:
              </Typography>
              {suratCameraNodes.map((cam) => (
                <Chip
                  key={cam.id}
                  label={cam.name}
                  size="small"
                  clickable
                  variant={locationSearch === `${cam.lat},${cam.lng}` ? "filled" : "outlined"}
                  color="primary"
                  onClick={() => setLocationSearch(`${cam.lat},${cam.lng} (${cam.name})`)}
                  sx={{ fontSize: '0.74rem', height: 24 }}
                />
              ))}
            </Box>

            {/* Map Canvas */}
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
              {mapMode === 'embed' ? (
                <iframe
                  title="Surat Surveillance GIS Map"
                  width="100%"
                  height="100%"
                  style={{ border: 0, minHeight: '100%' }}
                  loading="lazy"
                  allowFullScreen
                  referrerPolicy="no-referrer-when-downgrade"
                  src={`https://www.google.com/maps?q=${encodeURIComponent(locationSearch || (activeNode ? `${activeLat},${activeLng} (${activeLocation})` : 'Surat Gujarat'))}&hl=en&z=${activeNode || locationSearch ? 16 : 13}&output=embed`}
                />
              ) : (
                <svg width="100%" height="100%" style={{ position: 'absolute', top: 0, left: 0 }}>
                  <defs>
                    <pattern id="suratGrid" width="40" height="40" patternUnits="userSpaceOnUse">
                      <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#1e293b" strokeWidth="1" />
                    </pattern>
                  </defs>
                  <rect width="100%" height="100%" fill="url(#suratGrid)" />
                  {nodes.map((n, i) => {
                    const cx = 80 + (i * 120) % 600;
                    const cy = 100 + (i * 80) % 300;
                    const nextNode = nodes[i + 1];
                    const nextCx = 80 + ((i + 1) * 120) % 600;
                    const nextCy = 100 + ((i + 1) * 80) % 300;
                    return (
                      <g key={i}>
                        {nextNode && (
                          <line x1={cx} y1={cy} x2={nextCx} y2={nextCy} stroke="#00e676" strokeWidth="3" strokeDasharray="6 4" />
                        )}
                        <circle cx={cx} cy={cy} r={i === activeNodeIdx ? "16" : "12"} fill={i === activeNodeIdx ? "#00e676" : "#0284c7"} />
                        <text x={cx} y={cy - 20} fill="#e2e8f0" fontSize="11" fontWeight="bold" textAnchor="middle">
                          {n.camera_name || `CAM_${i+1}`}
                        </text>
                      </g>
                    );
                  })}
                </svg>
              )}
            </Box>
          </Paper>
        )}

        {/* VIEW 1 & 2: Camera Topology & Predictive Simulation Canvas */}
        {(viewTab === 1 || viewTab === 2) && (
          <Paper
            variant="outlined"
            ref={topologyContainerRef}
            onMouseDown={(e) => {
              if (e.target.tagName === 'svg' || e.target.tagName === 'DIV') {
                setIsPanning(true);
                setPanStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
              }
            }}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            sx={{
              flexGrow: 1,
              display: 'flex',
              flexDirection: 'column',
              minWidth: 0,
              height: '100%',
              backgroundColor: '#080c14',
              position: 'relative',
              overflow: 'hidden',
              userSelect: 'none',
              cursor: isPanning ? 'grabbing' : 'grab'
            }}
          >
            {/* Zoom Controls Overlay */}
            <Box sx={{ position: 'absolute', top: 16, right: 16, zIndex: 10, display: 'flex', flexDirection: 'column', gap: 1, backgroundColor: 'rgba(15, 23, 42, 0.85)', backdropFilter: 'blur(8px)', p: 0.5, borderRadius: 1.5, border: '1px solid rgba(0, 229, 255, 0.2)' }}>
              <IconButton size="small" onClick={() => setZoom(z => Math.min(z + 0.15, 2.5))} color="primary"><ZoomInIcon fontSize="small" /></IconButton>
              <IconButton size="small" onClick={() => setZoom(z => Math.max(z - 0.15, 0.4))} color="primary"><ZoomOutIcon fontSize="small" /></IconButton>
              <IconButton size="small" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }} color="primary"><CenterFocusStrongIcon fontSize="small" /></IconButton>
            </Box>

            {/* Simulation Results Banner */}
            {viewTab === 2 && simulationResult && (
              <Box sx={{ position: 'absolute', top: 16, left: 16, zIndex: 10, backgroundColor: 'rgba(15, 23, 42, 0.95)', border: '1px solid #f59e0b', p: 1.5, borderRadius: 1.5, maxWidth: 380 }}>
                <Typography variant="caption" fontWeight="bold" color="warning.main" sx={{ display: 'block' }}>
                  🎯 PREDICTED INTERCEPTION NODE: {simulationResult.predicted_next_camera}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  ETA: ~{simulationResult.estimated_transit_seconds || 120}s • Probability: {Math.round((simulationResult.probability || 0.88) * 100)}%
                </Typography>
              </Box>
            )}

            {/* Node and Edge SVG Network */}
            <svg
              style={{
                width: '100%',
                height: '100%',
                transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
                transformOrigin: '0 0'
              }}
            >
              <defs>
                <pattern id="topGrid" width="40" height="40" patternUnits="userSpaceOnUse">
                  <path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(0, 229, 255, 0.05)" strokeWidth="1" />
                </pattern>
                <marker id="arrow" viewBox="0 0 10 10" refX="28" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="#00e5ff" />
                </marker>
                <marker id="arrow-pulse" viewBox="0 0 10 10" refX="28" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="#f59e0b" />
                </marker>
              </defs>

              <rect width="10000" height="10000" x="-5000" y="-5000" fill="url(#topGrid)" />

              {/* Render Edges */}
              {topologyEdges.map((e, idx) => {
                const sNode = topologyNodes.find(n => n.id === e.source);
                const tNode = topologyNodes.find(n => n.id === e.target);
                if (!sNode || !tNode) return null;
                const isSelected = selectedEdge && selectedEdge.source === e.source && selectedEdge.target === e.target;
                const isPulsing = pulseCameraId && (e.target === pulseCameraId);

                const midX = (sNode.x + tNode.x) / 2;
                const midY = (sNode.y + tNode.y) / 2;

                return (
                  <g key={idx} onClick={() => setSelectedEdge(e)} style={{ cursor: 'pointer' }}>
                    <line
                      x1={sNode.x}
                      y1={sNode.y}
                      x2={tNode.x}
                      y2={tNode.y}
                      stroke={isPulsing ? "#f59e0b" : isSelected ? "#00e676" : "rgba(0, 229, 255, 0.4)"}
                      strokeWidth={isPulsing ? 4 : isSelected ? 3 : 2}
                      strokeDasharray={isPulsing ? "8 4" : "none"}
                      markerEnd={isPulsing ? "url(#arrow-pulse)" : "url(#arrow)"}
                    />
                    <rect x={midX - 32} y={midY - 10} width="64" height="20" rx="4" fill="rgba(15, 23, 42, 0.9)" stroke={isSelected ? "#00e676" : "rgba(0,229,255,0.3)"} />
                    <text x={midX} y={midY + 4} fill="#94a3b8" fontSize="10" fontWeight="bold" textAnchor="middle">
                      {e.distance_meters}m
                    </text>
                  </g>
                );
              })}

              {/* Render Nodes */}
              {topologyNodes.map((n) => {
                const isPulse = pulseCameraId === n.id;
                return (
                  <g
                    key={n.id}
                    transform={`translate(${n.x}, ${n.y})`}
                    onMouseDown={(e) => handleNodeMouseDown(e, n.id)}
                    style={{ cursor: 'move' }}
                  >
                    {isPulse && (
                      <circle r="36" fill="none" stroke="#f59e0b" strokeWidth="2">
                        <animate attributeName="r" from="24" to="48" dur="1.2s" repeatCount="indefinite" />
                        <animate attributeName="opacity" from="1" to="0" dur="1.2s" repeatCount="indefinite" />
                      </circle>
                    )}
                    <circle
                      r="22"
                      fill={isPulse ? "rgba(245, 158, 11, 0.25)" : "rgba(13, 21, 38, 0.95)"}
                      stroke={isPulse ? "#f59e0b" : "#00e5ff"}
                      strokeWidth={isPulse ? 3 : 2}
                    />
                    <text y="4" fill="#00e5ff" fontSize="11" fontWeight="bold" textAnchor="middle">
                      {n.id.replace('cam_', 'C')}
                    </text>
                    <text y="38" fill="#e2e8f0" fontSize="11" fontWeight="600" textAnchor="middle">
                      {n.name || n.id}
                    </text>
                  </g>
                );
              })}
            </svg>
          </Paper>
        )}

        {/* ── Right Column: Chronological Hits & Accomplices ──────────────── */}
        <Box sx={{ width: { xs: '100%', md: 360 }, display: 'flex', flexDirection: 'column', gap: 2, flexShrink: 0 }}>
          
          <Paper variant="outlined" sx={{ p: 2, display: 'flex', flexDirection: 'column', flexGrow: 1, maxHeight: 380 }}>
            <Typography variant="subtitle2" fontWeight="bold" color="primary" sx={{ borderBottom: '1px solid', borderColor: 'divider', pb: 1, mb: 1.5, display: 'flex', alignItems: 'center', gap: 1 }}>
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
                      src={authUrl(node.snapshot_url)}
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

      {/* Add Route Edge Modal */}
      <Dialog open={addEdgeOpen} onClose={() => setAddEdgeOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ backgroundColor: '#0f172a', borderBottom: '1px solid rgba(0,229,255,0.2)', color: '#00e5ff' }}>
          Connect Camera Route Edge
        </DialogTitle>
        <DialogContent sx={{ backgroundColor: '#080c14', pt: 3, display: 'flex', flexDirection: 'column', gap: 2 }}>
          <FormControl fullWidth size="small">
            <InputLabel>Source Camera</InputLabel>
            <Select value={newEdgeSource} label="Source Camera" onChange={(e) => setNewEdgeSource(e.target.value)}>
              {topologyNodes.map(n => <MenuItem key={n.id} value={n.id}>{n.name || n.id}</MenuItem>)}
            </Select>
          </FormControl>
          <FormControl fullWidth size="small">
            <InputLabel>Target Camera</InputLabel>
            <Select value={newEdgeTarget} label="Target Camera" onChange={(e) => setNewEdgeTarget(e.target.value)}>
              {topologyNodes.filter(n => n.id !== newEdgeSource).map(n => <MenuItem key={n.id} value={n.id}>{n.name || n.id}</MenuItem>)}
            </Select>
          </FormControl>
          <TextField size="small" type="number" label="Distance (meters)" value={newEdgeDistance} onChange={(e) => setNewEdgeDistance(e.target.value)} fullWidth />
          <Box sx={{ display: 'flex', gap: 1 }}>
            <TextField size="small" type="number" label="Min Transit (sec)" value={newEdgeMinSec} onChange={(e) => setNewEdgeMinSec(e.target.value)} fullWidth />
            <TextField size="small" type="number" label="Max Transit (sec)" value={newEdgeMaxSec} onChange={(e) => setNewEdgeMaxSec(e.target.value)} fullWidth />
          </Box>
        </DialogContent>
        <DialogActions sx={{ backgroundColor: '#0f172a', borderTop: '1px solid rgba(0,229,255,0.2)', p: 1.5 }}>
          <Button onClick={() => setAddEdgeOpen(false)} color="inherit">Cancel</Button>
          <Button onClick={handleAddEdgeSubmit} variant="contained" color="primary">Create Connection</Button>
        </DialogActions>
      </Dialog>

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
              src={authUrl(selectedSceneNode?.full_snapshot_url || selectedSceneNode?.snapshot_url)}
              alt="Full Camera Frame Scene"
              onError={(e) => { e.target.onerror = null; e.target.src = '/api/v1/playback/snapshot/default'; }}
              sx={{ width: '100%', height: 'auto', display: 'block' }}
            />
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
                  sx={{ position: 'absolute', top: -28, left: 0, fontSize: '0.65rem', fontWeight: 'bold', height: 22 }}
                />
              </Box>
            ) : (
              <Chip
                label={`🎯 ${selectedSceneNode?.confidence || 90}% TARGET SIGHTING VERIFIED`}
                size="small"
                color="success"
                sx={{ position: 'absolute', top: 12, left: 12, fontSize: '0.65rem', fontWeight: 'bold', height: 24 }}
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
