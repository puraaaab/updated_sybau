import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Box, Typography, Button, IconButton, Tooltip, Switch, FormControlLabel,
  Dialog, DialogTitle, DialogContent, DialogActions, TextField, MenuItem, Select,
  FormControl, InputLabel, CircularProgress, Alert
} from '@mui/material';
import HubIcon from '@mui/icons-material/Hub';
import AddLinkIcon from '@mui/icons-material/AddLink';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import DeleteForeverIcon from '@mui/icons-material/DeleteForever';
import ZoomInIcon from '@mui/icons-material/ZoomIn';
import ZoomOutIcon from '@mui/icons-material/ZoomOut';
import CenterFocusStrongIcon from '@mui/icons-material/CenterFocusStrong';
import CloseIcon from '@mui/icons-material/Close';
import './TopologyEditor.css';

export default function TopologyEditor({ token }) {
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  
  // Canvas Transform (Pan & Zoom)
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const [panStart, setPanStart] = useState({ x: 0, y: 0 });
  
  // Dragging State
  const [draggingNodeId, setDraggingNodeId] = useState(null);
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });
  const [snapToGrid, setSnapToGrid] = useState(true);
  
  // Selection & Modal States
  const [selectedEdge, setSelectedEdge] = useState(null);
  const [addEdgeOpen, setAddEdgeOpen] = useState(false);
  const [newEdgeSource, setNewEdgeSource] = useState('');
  const [newEdgeTarget, setNewEdgeTarget] = useState('');
  const [newEdgeDistance, setNewEdgeDistance] = useState(500);
  const [newEdgeMinSec, setNewEdgeMinSec] = useState(60);
  const [newEdgeMaxSec, setNewEdgeMaxSec] = useState(300);

  // Predictive Simulation State
  const [predictTargetId, setPredictTargetId] = useState('KA51MB8811');
  const [predicting, setPredicting] = useState(false);
  const [pulseCameraId, setPulseCameraId] = useState(null);
  const [simulationResult, setSimulationResult] = useState(null);

  const containerRef = useRef(null);

  // 1. Fetch Topology Graph
  const loadTopology = useCallback(() => {
    setLoading(true);
    fetch('/api/v1/topology', {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(res => res.ok ? res.json() : Promise.reject('Failed to load topology graph'))
      .then(data => {
        setNodes(data.nodes || []);
        setEdges(data.edges || []);
        setLoading(false);
      })
      .catch(err => {
        setError(String(err));
        setLoading(false);
      });
  }, [token]);

  useEffect(() => {
    loadTopology();
  }, [loadTopology]);

  // 2. Node Drag & Drop Handlers
  const handleNodeMouseDown = (e, node) => {
    e.stopPropagation();
    setDraggingNodeId(node.camera_id);
    const clientX = e.clientX;
    const clientY = e.clientY;
    setDragOffset({
      x: (clientX / zoom - pan.x) - node.map_x,
      y: (clientY / zoom - pan.y) - node.map_y
    });
  };

  const handleCanvasMouseMove = (e) => {
    if (isPanning) {
      setPan({
        x: pan.x + (e.clientX - panStart.x) / zoom,
        y: pan.y + (e.clientY - panStart.y) / zoom
      });
      setPanStart({ x: e.clientX, y: e.clientY });
      return;
    }

    if (draggingNodeId) {
      let nextX = (e.clientX / zoom - pan.x) - dragOffset.x;
      let nextY = (e.clientY / zoom - pan.y) - dragOffset.y;

      if (snapToGrid) {
        nextX = Math.round(nextX / 20) * 20;
        nextY = Math.round(nextY / 20) * 20;
      }

      setNodes(prev => prev.map(n => n.camera_id === draggingNodeId ? { ...n, map_x: nextX, map_y: nextY } : n));
    }
  };

  // 3. Debounced Persistence on MouseUp / Drop
  const handleCanvasMouseUp = () => {
    if (draggingNodeId) {
      const movedNode = nodes.find(n => n.camera_id === draggingNodeId);
      if (movedNode) {
        // Debounced Save on Drop
        fetch(`/api/v1/topology/nodes/${movedNode.camera_id}`, {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`
          },
          body: JSON.stringify({
            map_x: movedNode.map_x,
            map_y: movedNode.map_y,
            zone_group: movedNode.zone_group
          })
        }).catch(err => console.error('Failed to persist node position:', err));
      }
      setDraggingNodeId(null);
    }
    setIsPanning(false);
  };

  const handleCanvasMouseDown = (e) => {
    if (e.target.tagName === 'svg' || e.target.classList.contains('topology-canvas-wrap')) {
      setIsPanning(true);
      setPanStart({ x: e.clientX, y: e.clientY });
      setSelectedEdge(null);
    }
  };

  // 4. Reset Layout Action
  const handleResetLayout = () => {
    fetch('/api/v1/topology/reset-layout', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(res => res.ok ? loadTopology() : Promise.reject('Failed to reset layout'))
      .catch(err => alert(String(err)));
  };

  // 5. Create Edge Action
  const handleCreateEdge = () => {
    if (!newEdgeSource || !newEdgeTarget || newEdgeSource === newEdgeTarget) return;

    fetch('/api/v1/topology/edges', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({
        source_camera_id: newEdgeSource,
        target_camera_id: newEdgeTarget,
        distance_meters: parseFloat(newEdgeDistance) || 500,
        expected_transit_sec_min: parseInt(newEdgeMinSec, 10) || 60,
        expected_transit_sec_max: parseInt(newEdgeMaxSec, 10) || 300,
        allowed_directions: ['forward']
      })
    })
      .then(res => res.ok ? res.json() : Promise.reject('Failed to create edge'))
      .then(() => {
        setAddEdgeOpen(false);
        loadTopology();
      })
      .catch(err => alert(String(err)));
  };

  // 6. Delete Edge Action
  const handleDeleteEdge = (edgeId) => {
    fetch(`/api/v1/topology/edges/${edgeId}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(res => res.ok ? res.json() : Promise.reject('Failed to delete edge'))
      .then(() => {
        setSelectedEdge(null);
        loadTopology();
      })
      .catch(err => alert(String(err)));
  };

  // 7. Predictive Route Simulator Trigger
  const handleRunSimulation = (sourceCamId) => {
    setPredicting(true);
    setPulseCameraId(sourceCamId);
    fetch('/api/v1/topology/predict', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({
        source_camera_id: sourceCamId,
        target_identifier: predictTargetId,
        target_type: 'vehicle',
        heading_direction: 'forward',
        observed_speed_kmh: 42.0
      })
    })
      .then(res => res.ok ? res.json() : Promise.reject('Predictive routing failed'))
      .then(data => {
        setSimulationResult(data);
        setPredicting(false);
        setTimeout(() => setPulseCameraId(null), 3000);
      })
      .catch(err => {
        alert(String(err));
        setPredicting(false);
        setPulseCameraId(null);
      });
  };

  const nodeMap = React.useMemo(() => {
    const map = {};
    nodes.forEach(n => { map[n.camera_id] = n; });
    return map;
  }, [nodes]);

  return (
    <div className="topology-container" ref={containerRef}>
      {/* Top Action Ribbon */}
      <div className="topology-header">
        <div className="topology-title">
          <HubIcon sx={{ color: '#00e5ff', fontSize: 24 }} />
          <span>Camera Network Topology & Transit Routing Engine</span>
        </div>

        <div className="topology-controls">
          <FormControlLabel
            control={
              <Switch
                checked={snapToGrid}
                onChange={e => setSnapToGrid(e.target.checked)}
                size="small"
                sx={{ '& .MuiSwitch-switchBase.Mui-checked': { color: '#00e676' } }}
              />
            }
            label={<Typography sx={{ fontSize: '0.8rem', color: '#94a3b8' }}>Grid Snap (20px)</Typography>}
          />

          <button className="topology-btn" onClick={() => setAddEdgeOpen(true)}>
            <AddLinkIcon sx={{ fontSize: 16 }} />
            <span>Connect Cameras</span>
          </button>

          <button className="topology-btn" onClick={handleResetLayout}>
            <RestartAltIcon sx={{ fontSize: 16 }} />
            <span>Reset Geometry</span>
          </button>

          <button className="topology-btn" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }}>
            <CenterFocusStrongIcon sx={{ fontSize: 16 }} />
            <span>Fit Screen</span>
          </button>

          <IconButton size="small" onClick={() => setZoom(z => Math.min(2.5, z + 0.15))} sx={{ color: '#00e5ff' }}>
            <ZoomInIcon fontSize="small" />
          </IconButton>
          <IconButton size="small" onClick={() => setZoom(z => Math.max(0.4, z - 0.15))} sx={{ color: '#00e5ff' }}>
            <ZoomOutIcon fontSize="small" />
          </IconButton>
        </div>
      </div>

      {/* Main Interactive SVG Canvas */}
      <div
        className={`topology-canvas-wrap ${isPanning ? 'panning' : ''}`}
        onMouseDown={handleCanvasMouseDown}
        onMouseMove={handleCanvasMouseMove}
        onMouseUp={handleCanvasMouseUp}
      >
        {loading ? (
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', gap: 2 }}>
            <CircularProgress size={32} sx={{ color: '#00e5ff' }} />
            <Typography sx={{ color: '#00e5ff', fontWeight: 600 }}>Loading Camera Topology Graph...</Typography>
          </Box>
        ) : (
          <svg className="topology-svg">
            <g transform={`scale(${zoom}) translate(${pan.x}, ${pan.y})`}>
              {/* Marker definitions for directional arrows */}
              <defs>
                <marker
                  id="arrow-default"
                  viewBox="0 0 10 10"
                  refX="22"
                  refY="5"
                  markerWidth="6"
                  markerHeight="6"
                  orient="auto-start-reverse"
                >
                  <path d="M 0 1 L 10 5 L 0 9 z" fill="#00e5ff" />
                </marker>
                <marker
                  id="arrow-selected"
                  viewBox="0 0 10 10"
                  refX="22"
                  refY="5"
                  markerWidth="7"
                  markerHeight="7"
                  orient="auto-start-reverse"
                >
                  <path d="M 0 1 L 10 5 L 0 9 z" fill="#00e676" />
                </marker>
              </defs>

              {/* Render Directed Transit Edges */}
              {edges.map(edge => {
                const sNode = nodeMap[edge.source];
                const tNode = nodeMap[edge.target];
                if (!sNode || !tNode) return null;

                const sx = sNode.map_x;
                const sy = sNode.map_y;
                const tx = tNode.map_x;
                const ty = tNode.map_y;

                const isSel = selectedEdge && selectedEdge.id === edge.id;
                const midX = (sx + tx) / 2;
                const midY = (sy + ty) / 2;

                return (
                  <g key={`edge-${edge.id}`}>
                    <path
                      d={`M ${sx} ${sy} Q ${midX + 15} ${midY - 15} ${tx} ${ty}`}
                      className={`edge-path ${isSel ? 'selected' : ''}`}
                      markerEnd={isSel ? 'url(#arrow-selected)' : 'url(#arrow-default)'}
                      onClick={(e) => { e.stopPropagation(); setSelectedEdge(edge); }}
                    />
                    {/* Edge Transit Window Label Badge */}
                    <g transform={`translate(${midX}, ${midY})`} onClick={(e) => { e.stopPropagation(); setSelectedEdge(edge); }} style={{ cursor: 'pointer' }}>
                      <rect x="-38" y="-10" width="76" height="20" className="edge-badge" />
                      <text x="0" y="0" className="edge-text">
                        {`${edge.expected_transit_sec_min}s-${edge.expected_transit_sec_max}s`}
                      </text>
                    </g>
                  </g>
                );
              })}

              {/* Render Camera Nodes */}
              {nodes.map(node => {
                const isDragging = draggingNodeId === node.camera_id;
                const isPulsing = pulseCameraId === node.camera_id;

                return (
                  <g
                    key={`node-${node.camera_id}`}
                    transform={`translate(${node.map_x}, ${node.map_y})`}
                    className={`node-group ${isDragging ? 'dragging' : ''}`}
                    onMouseDown={(e) => handleNodeMouseDown(e, node)}
                  >
                    {isPulsing && (
                      <circle cx="0" cy="0" r="10" className="pulse-circle" />
                    )}

                    <rect x="-65" y="-28" width="130" height="56" className="node-box" />

                    <circle cx="-48" cy="-14" r="4" className="node-status-dot" />
                    <text x="0" y="-10" className="node-title">{node.label}</text>
                    <text x="0" y="10" className="node-sub">{node.camera_id.toUpperCase()}</text>

                    {/* Quick Simulation Trigger Icon on Node */}
                    <g
                      transform="translate(44, -14)"
                      onClick={(e) => { e.stopPropagation(); handleRunSimulation(node.camera_id); }}
                      style={{ cursor: 'pointer' }}
                    >
                      <circle cx="0" cy="0" r="9" fill="rgba(0, 229, 255, 0.2)" stroke="#00e5ff" strokeWidth="1" />
                      <path d="M -3 -4 L 4 0 L -3 4 Z" fill="#00e5ff" />
                    </g>
                  </g>
                );
              })}
            </g>
          </svg>
        )}
      </div>

      {/* Selected Edge Detail Overlay */}
      {selectedEdge && (
        <div className="topology-sidebar">
          <div className="sidebar-header">
            <span>Transit Edge #{selectedEdge.id}</span>
            <IconButton size="small" onClick={() => setSelectedEdge(null)} sx={{ color: '#94a3b8' }}>
              <CloseIcon fontSize="small" />
            </IconButton>
          </div>

          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, fontSize: '0.85rem' }}>
            <Box><strong>Origin:</strong> {nodeMap[selectedEdge.source]?.label || selectedEdge.source}</Box>
            <Box><strong>Destination:</strong> {nodeMap[selectedEdge.target]?.label || selectedEdge.target}</Box>
            <Box><strong>Distance:</strong> {selectedEdge.distance_meters} meters</Box>
            <Box>
              <strong>Calibrated Transit Window:</strong>
              <Typography sx={{ color: '#00e676', fontFamily: 'monospace', fontWeight: 'bold' }}>
                {selectedEdge.expected_transit_sec_min}s – {selectedEdge.expected_transit_sec_max}s
              </Typography>
            </Box>

            <Button
              variant="outlined"
              color="error"
              size="small"
              startIcon={<DeleteForeverIcon />}
              onClick={() => handleDeleteEdge(selectedEdge.id)}
              sx={{ mt: 1 }}
            >
              Delete Edge
            </Button>
          </Box>
        </div>
      )}

      {/* Connect Cameras Modal */}
      <Dialog open={addEdgeOpen} onClose={() => setAddEdgeOpen(false)} PaperProps={{ sx: { background: '#0f172a', color: '#f8fafc', border: '1px solid rgba(0, 229, 255, 0.3)' } }}>
        <DialogTitle sx={{ color: '#00e5ff', fontWeight: 700 }}>Connect Camera Transit Route</DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: 1, minWidth: 320 }}>
          <FormControl fullWidth size="small">
            <InputLabel sx={{ color: '#94a3b8' }}>Source Camera (Origin)</InputLabel>
            <Select
              value={newEdgeSource}
              onChange={e => setNewEdgeSource(e.target.value)}
              label="Source Camera (Origin)"
              sx={{ color: '#f8fafc', '& .MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.2)' } }}
            >
              {nodes.map(n => <MenuItem key={n.camera_id} value={n.camera_id}>{n.label} ({n.camera_id})</MenuItem>)}
            </Select>
          </FormControl>

          <FormControl fullWidth size="small">
            <InputLabel sx={{ color: '#94a3b8' }}>Target Camera (Destination)</InputLabel>
            <Select
              value={newEdgeTarget}
              onChange={e => setNewEdgeTarget(e.target.value)}
              label="Target Camera (Destination)"
              sx={{ color: '#f8fafc', '& .MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.2)' } }}
            >
              {nodes.filter(n => n.camera_id !== newEdgeSource).map(n => <MenuItem key={n.camera_id} value={n.camera_id}>{n.label} ({n.camera_id})</MenuItem>)}
            </Select>
          </FormControl>

          <TextField
            label="Distance (Meters)"
            type="number"
            size="small"
            value={newEdgeDistance}
            onChange={e => setNewEdgeDistance(e.target.value)}
            InputLabelProps={{ sx: { color: '#94a3b8' } }}
            InputProps={{ sx: { color: '#f8fafc' } }}
          />

          <Box sx={{ display: 'flex', gap: 1.5 }}>
            <TextField
              label="Min Transit (Sec)"
              type="number"
              size="small"
              value={newEdgeMinSec}
              onChange={e => setNewEdgeMinSec(e.target.value)}
              InputLabelProps={{ sx: { color: '#94a3b8' } }}
              InputProps={{ sx: { color: '#f8fafc' } }}
            />
            <TextField
              label="Max Transit (Sec)"
              type="number"
              size="small"
              value={newEdgeMaxSec}
              onChange={e => setNewEdgeMaxSec(e.target.value)}
              InputLabelProps={{ sx: { color: '#94a3b8' } }}
              InputProps={{ sx: { color: '#f8fafc' } }}
            />
          </Box>
        </DialogContent>
        <DialogActions sx={{ p: 2 }}>
          <Button onClick={() => setAddEdgeOpen(false)} sx={{ color: '#94a3b8' }}>Cancel</Button>
          <Button onClick={handleCreateEdge} variant="contained" sx={{ background: '#00e5ff', color: '#090d16', fontWeight: 'bold' }}>Save Route</Button>
        </DialogActions>
      </Dialog>
    </div>
  );
}
