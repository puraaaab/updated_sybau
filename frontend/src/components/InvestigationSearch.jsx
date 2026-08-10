import React, { useEffect, useState, useMemo, useCallback } from 'react';
import {
  Box, Typography, Paper, TextField, Button, Select, MenuItem, InputLabel, FormControl, Card, CardMedia, CardContent, CardActions, Chip, Alert, Slider, IconButton, Tooltip
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import SyncIcon from '@mui/icons-material/Sync';
import DownloadIcon from '@mui/icons-material/Download';
import ImageSearchIcon from '@mui/icons-material/ImageSearch';
import CloseIcon from '@mui/icons-material/Close';
import ClearIcon from '@mui/icons-material/Clear';
import CancelIcon from '@mui/icons-material/Cancel';

const computeBboxStyle = (bbox) => {
  if (!bbox || !Array.isArray(bbox) || bbox.length < 4) return null;
  let [ymin, xmin, ymax, xmax] = bbox;
  if (ymax <= ymin || xmax <= xmin) return null;
  if (ymax > 1 || xmax > 1) {
    ymin = (ymin / 1080) * 100;
    ymax = (ymax / 1080) * 100;
    xmin = (xmin / 1920) * 100;
    xmax = (xmax / 1920) * 100;
  } else {
    ymin = ymin * 100;
    ymax = ymax * 100;
    xmin = xmin * 100;
    xmax = xmax * 100;
  }
  const top = `${Math.max(2, Math.min(85, ymin))}%`;
  const left = `${Math.max(2, Math.min(85, xmin))}%`;
  const width = `${Math.max(5, Math.min(95, xmax - xmin))}%`;
  const height = `${Math.max(5, Math.min(95, ymax - ymin))}%`;
  return { top, left, width, height };
};

export default function InvestigationSearch({ role, token, searchEvents = [], initialQuery = '' }) {
  const [cameras, setCameras] = useState([]);
  const [query, setQuery] = useState(initialQuery);
  const [selectedCamera, setSelectedCamera] = useState('');
  const [kind, setKind] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [limit, setLimit] = useState(25);
  const [minConfidence, setMinConfidence] = useState(20);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [selectedFaceFile, setSelectedFaceFile] = useState(null);
  const [selectedVisionFile, setSelectedVisionFile] = useState(null);
  const [extractedAiPrompt, setExtractedAiPrompt] = useState('');

  const handleVisionImageSearchUpload = (file) => {
    if (!file || !token) return;
    setLoading(true);
    setError('');
    setExtractedAiPrompt('Analyzing image with Florence-2 VLM on GPU...');

    const formData = new FormData();
    formData.append('file', file);

    fetch('/api/search/image-query', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: formData
    })
      .then(async res => {
        const body = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(body.detail || 'Vision image query failed');
        return body;
      })
      .then(data => {
        const prompt = data.extracted_prompt || 'Extracted Target';
        setQuery(prompt);
        setExtractedAiPrompt(prompt);
        let list = Array.isArray(data.results) ? data.results : [];
        const transformed = list.map((item, idx) => {
          const p = item.payload || {};
          const score = item.score || 0;
          return {
            id: `vlm-${idx}-${p.timestamp}`,
            kind: p.type || 'scene',
            title: p.type === 'scene' ? 'Scene Match' : (p.vehicle_type ? `Vehicle: ${p.vehicle_type}` : 'Forensic Match'),
            summary: p.caption || `Cosine similarity match score of ${Math.round(score * 100)}%`,
            camera_name: p.camera_id || 'Unknown',
            timestamp: p.timestamp ? p.timestamp.substring(0, 19).replace('T', ' ') : 'N/A',
            confidence: Math.round(score * 100),
            snapshot_path: resolveSnapshotUrl(p.snapshot_url),
            target_label: prompt.length > 20 ? prompt.substring(0, 20) + '...' : prompt,
            bbox_style: computeBboxStyle(p.bbox)
          };
        });
        setResults(transformed);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setExtractedAiPrompt('');
        setLoading(false);
      });
  };

  // Enhanced Advanced Search States
  const [timePreset, setTimePreset] = useState('all');
  const [sortBy, setSortBy] = useState('confidence'); // newest | oldest | confidence
  const [classFilter, setClassFilter] = useState('all'); // all | person | vehicle | poi | export

  const loadCameras = useCallback(() => {
    if (!token) return;
    fetch('/api/v1/cameras', {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(res => res.ok ? res.json() : [])
      .then(data => {
        setCameras(Array.isArray(data) ? data : []);
      })
      .catch(() => { setCameras([]); });
  }, [token]);

  useEffect(() => {
    loadCameras();
  }, [loadCameras]);

  useEffect(() => {
    if (initialQuery) {
      setQuery(initialQuery);
    }
  }, [initialQuery]);

  useEffect(() => {
    if (searchEvents.length > 0) {
      setResults(prev => prev
        .map(res => {
          const matchingEvent = searchEvents.find(e => 
            e.type === 'search_snapshot_boxed' && 
            e.search_hit_id === res.id &&
            e.query.trim() === query.trim()
          );
          if (matchingEvent) {
            return {
              ...res,
              snapshot_path: matchingEvent.boxed_snapshot_url,
              confidence: matchingEvent.confidence
            };
          }
          return res;
        })
        .filter(res => !(res.kind === 'object' && res.confidence === 0))
      );
    }
  }, [searchEvents, query]);

  // Handle Quick Time Presets
  const handleTimePresetChange = (preset) => {
    setTimePreset(preset);
    if (preset === 'all') {
      setStart('');
      setEnd('');
      return;
    }

    const now = new Date();
    let fromDate;
    if (preset === '15m') {
      fromDate = new Date(now.getTime() - 15 * 60 * 1000);
    } else if (preset === '1h') {
      fromDate = new Date(now.getTime() - 60 * 60 * 1000);
    } else if (preset === '24h') {
      fromDate = new Date(now.getTime() - 24 * 60 * 60 * 1000);
    } else if (preset === '7d') {
      fromDate = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    }

    if (fromDate) {
      const offset = fromDate.getTimezoneOffset();
      const localTime = new Date(fromDate.getTime() - offset * 60 * 1000);
      setStart(localTime.toISOString().slice(0, 16));

      const localNow = new Date(now.getTime() - offset * 60 * 1000);
      setEnd(localNow.toISOString().slice(0, 16));
    }
  };

  // Helper to ensure snapshot URLs match the Vite proxy mapping cleanly
  const resolveSnapshotUrl = (url) => {
    if (!url) return null;
    // Replace "/api/v1/" prefix with "/api/" so Vite does not double-prefix it to "/api/v1/v1/"
    if (url.startsWith('/api/v1/')) {
      return url.replace('/api/v1/', '/api/');
    }
    return url;
  };

  const runSearch = (e) => {
    if (e) e.preventDefault();
    if (!token) return;

    // Date range validation (Issue 4)
    if (start && end && new Date(start) > new Date(end)) {
      setError('Invalid Time Bound: Starting date cannot be later than ending date.');
      return;
    }

    setLoading(true);
    setError('');

    // Scenario A: Face Vector similarity matching
    if (kind === 'face_search') {
      const faceImage = selectedFaceFile || document.getElementById('faceImageInput')?.files?.[0];
      
      if (!faceImage) {
        setError('Please select/upload a face image file first to match against target database.');
        setLoading(false);
        return;
      }

      const formData = new FormData();
      formData.append('file', faceImage);

      fetch(`/api/search/face`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData
      })
        .then(async res => {
          const body = await res.json().catch(() => ([]));
          if (!res.ok) throw new Error(body.detail || 'Face search failed');
          return body;
        })
        .then(data => {
          const transformed = (Array.isArray(data) ? data : []).map((item, idx) => {
            const p = item.payload || {};
            const score = item.score || 0;
            return {
              id: `face-${idx}-${p.timestamp}`,
              kind: 'face',
              title: `Watchlist Match: ${p.label || 'Unknown POI'}`,
              summary: `Cosine similarity vector match score of ${Math.round(score * 100)}%. Record timestamp: ${p.timestamp}`,
              camera_name: p.camera_id || 'Unknown',
              timestamp: p.timestamp ? p.timestamp.substring(0, 19).replace('T', ' ') : 'N/A',
              confidence: Math.round(score * 100),
              snapshot_path: resolveSnapshotUrl(p.snapshot_url)
            };
          });
          setResults(transformed);
          setLoading(false);
        })
        .catch(err => {
          setError(err.message);
          setResults([]);
          setLoading(false);
        });
      return;
    }

    // Scenario B: Database Alerts search
    if (kind === 'alert') {
      fetch('/api/alerts', {
        headers: { Authorization: `Bearer ${token}` }
      })
        .then(async res => {
          const body = await res.json().catch(() => ([]));
          if (!res.ok) throw new Error(body.detail || 'Failed to fetch alert logs');
          return body;
        })
        .then(data => {
          let filtered = Array.isArray(data) ? data : [];
          
          if (query.trim()) {
            const q = query.toLowerCase();
            filtered = filtered.filter(item => 
              (item.type || '').toLowerCase().includes(q) ||
              (item.message || '').toLowerCase().includes(q)
            );
          }
          if (selectedCamera) {
            filtered = filtered.filter(item => (item.camera_id || '').toLowerCase() === selectedCamera.toLowerCase());
          }

          const transformed = filtered.map(item => ({
            id: `alert-${item.id}`,
            kind: 'alert',
            title: `Chime Alert: ${item.type.toUpperCase()}`,
            summary: item.message || 'No remarks recorded',
            camera_name: item.camera_id,
            timestamp: item.timestamp ? item.timestamp.substring(0, 19).replace('T', ' ') : 'N/A',
            confidence: item.severity === 'high' ? 95 : item.severity === 'medium' ? 70 : 40,
            snapshot_path: resolveSnapshotUrl(item.snapshot_url)
          }));
          setResults(transformed);
          setLoading(false);
        })
        .catch(err => {
          setError(err.message);
          setResults([]);
          setLoading(false);
        });
      return;
    }

    // Scenario C: Forensic Exports search
    if (kind === 'export') {
      fetch('/api/forensics/exports', {
        headers: { Authorization: `Bearer ${token}` }
      })
        .then(async res => {
          const body = await res.json().catch(() => ([]));
          if (!res.ok) throw new Error(body.detail || 'Failed to load exports ledger');
          return body;
        })
        .then(data => {
          let filtered = Array.isArray(data) ? data : [];

          if (query.trim()) {
            const q = query.toLowerCase();
            filtered = filtered.filter(item => 
              (item.camera_name || '').toLowerCase().includes(q) ||
              (item.username || '').toLowerCase().includes(q) ||
              (item.sha256_hash || '').toLowerCase().includes(q)
            );
          }
          if (selectedCamera) {
            filtered = filtered.filter(item => (item.camera_name || '').toLowerCase() === selectedCamera.toLowerCase());
          }

          const transformed = filtered.map(item => ({
            id: `export-${item.export_uuid || item.timestamp}`,
            kind: 'export',
            title: `Evidence Export: CAM_${item.camera_name.toUpperCase()}`,
            summary: `Hash index: sha256:${item.sha256_hash.substring(0, 16)}... Compiled under authority of operator: ${item.username}`,
            camera_name: item.camera_name,
            timestamp: item.timestamp ? item.timestamp.substring(0, 19).replace('T', ' ') : 'N/A',
            confidence: 100,
            mp4_download_url: resolveSnapshotUrl(item.mp4_download_url),
            sidecar_download_url: resolveSnapshotUrl(item.sidecar_download_url)
          }));
          setResults(transformed);
          setLoading(false);
        })
        .catch(err => {
          setError(err.message);
          setResults([]);
          setLoading(false);
        });
      return;
    }

    // Scenario E: License Plate search
    if (kind === 'license_plate') {
      const params = new URLSearchParams();
      params.set('q', query.trim() || 'KA');

      fetch(`/api/search/license-plate?${params.toString()}`, {
        headers: { Authorization: `Bearer ${token}` }
      })
        .then(async res => {
          const body = await res.json().catch(() => ([]));
          if (!res.ok) throw new Error(body.detail || 'License plate database query failed');
          return body;
        })
        .then(data => {
          let list = Array.isArray(data) ? data : [];
          if (selectedCamera) {
            list = list.filter(item => (item.camera_name || '').toLowerCase() === selectedCamera.toLowerCase());
          }

          const transformed = list.map((item) => ({
            id: `plate-${item.id}-${item.timestamp}`,
            kind: 'vehicle',
            title: `Plate Match: ${item.license_plate}`,
            summary: `Vehicle Class: ${(item.vehicle_type || 'Unknown').toUpperCase()} (OCR Confidence: ${Math.round(item.ocr_confidence * 100)}%)`,
            camera_name: item.camera_name || 'Unknown',
            timestamp: item.timestamp ? String(item.timestamp).substring(0, 19).replace('T', ' ') : 'N/A',
            confidence: Math.round(item.ocr_confidence * 100),
            snapshot_path: resolveSnapshotUrl(item.snapshot_url || (item.track_uuid ? `/api/v1/playback/snapshot/${item.track_uuid}` : null)),
            bbox_style: computeBboxStyle(typeof item.bbox === 'string' ? JSON.parse(item.bbox || '[]') : item.bbox)
          }));
          setResults(transformed);
          setLoading(false);
        })
        .catch(err => {
          setError(err.message);
          setResults([]);
          setLoading(false);
        });
      return;
    }

    // Scenario D: Vector / Semantic search (Default)
    const params = new URLSearchParams();
    params.set('q', query.trim() || 'person');
    params.set('limit', String(limit));
    if (start) params.set('start_time', start);
    if (end) params.set('end_time', end);

    fetch(`/api/search/semantic?${params.toString()}`, {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(async res => {
        const body = await res.json().catch(() => ([]));
        if (!res.ok) throw new Error(body.detail || 'Semantic database query failed');
        return body;
      })
      .then(data => {
        let list = Array.isArray(data) ? data : [];

        // Apply camera filter locally if query has selectedCamera
        if (selectedCamera) {
          list = list.filter(item => {
            const p = item.payload || {};
            return (p.camera_id || '').toLowerCase() === selectedCamera.toLowerCase();
          });
        }

        const transformed = list.map((item, idx) => {
          const p = item.payload || {};
          const score = item.score || 0;

          let title = 'Scene Tracking';
          let summary = '';
          if (p.type === 'scene') {
            title = 'Scene Event';
            summary = p.caption || 'No caption';
          } else if (p.type === 'vehicle') {
            title = `Vehicle: ${p.vehicle_type || 'Unknown'}`;
            summary = `License Plate: ${p.license_plate || 'N/A'}`;
          } else if (p.type === 'face') {
            title = `Face Recognition: ${p.label || 'Unknown Target'}`;
            summary = `Matched registered target profile in database.`;
          }

          return {
            id: `semantic-${idx}-${p.timestamp}`,
            kind: p.type || 'scene',
            title: title,
            summary: summary,
            camera_name: p.camera_id || 'Unknown',
            timestamp: p.timestamp ? p.timestamp.substring(0, 19).replace('T', ' ') : 'N/A',
            confidence: Math.round(score * 100),
            snapshot_path: resolveSnapshotUrl(
              p.full_snapshot_url ||
              p.full_scene_url ||
              (p.camera_id ? `/api/v1/playback/snapshot/full_cam_${p.camera_id}` : null) ||
              p.snapshot_url
            ),
            target_label: query.trim() || p.vehicle_type || p.label || 'Target',
            bbox_style: computeBboxStyle(p.bbox)
          };
        });
        setResults(transformed);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setResults([]);
        setLoading(false);
      });
  };

  // Perform robust client-side filters and sorting to make searching stronger
  const processedResults = useMemo(() => {
    let list = [...results];

    // 1. Filter by target class classification
    if (classFilter !== 'all') {
      list = list.filter(item => {
        const summary = (item.summary || '').toLowerCase();
        const title = (item.title || '').toLowerCase();
        const kindVal = (item.kind || '').toLowerCase();
        
        if (classFilter === 'person') {
          return summary.includes('person') || title.includes('person') || summary.includes('man') || summary.includes('woman') || kindVal === 'face';
        }
        if (classFilter === 'vehicle') {
          return summary.includes('car') || summary.includes('vehicle') || summary.includes('truck') || summary.includes('bus') || summary.includes('motorcycle') || kindVal === 'vehicle';
        }
        if (classFilter === 'poi') {
          return title.includes('poi') || title.includes('watchlist') || item.type === 'POI_MATCH' || summary.includes('watchlist');
        }
        if (classFilter === 'export') {
          return kindVal === 'export';
        }
        return true;
      });
    }

    // 2. Filter by minimum confidence
    list = list.filter(item => (item.confidence ?? 0) >= minConfidence);

    // 3. Local sorting
    if (sortBy === 'newest') {
      list.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
    } else if (sortBy === 'oldest') {
      list.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
    } else if (sortBy === 'confidence') {
      list.sort((a, b) => (b.confidence || 0) - (a.confidence || 0));
    }

    return list;
  }, [results, classFilter, sortBy, minConfidence]);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 85px)', overflow: 'hidden', p: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
        <Typography variant="h6" fontWeight="bold">Forensic Incident Search Ledger</Typography>
        <Typography variant="caption" color="text.secondary">Clearance Authority: {role.toUpperCase()}</Typography>
      </Box>

      {/* Main Search Panel - Responsive CSS Grid Layout */}
      <Paper component="form" onSubmit={runSearch} variant="outlined" sx={{ p: 2, mb: 1.5 }}>
        <Box sx={{
          display: 'grid',
          gridTemplateColumns: {
            xs: '1fr',
            sm: '1fr 1fr',
            md: 'repeat(3, 1fr)',
            lg: 'repeat(4, 1fr)'
          },
          gap: 2,
          alignItems: 'end'
        }}>
          {/* Quick Search Preset Chips for instant 1-click investigations */}
          <Box sx={{ gridColumn: '1 / -1', mb: 1, display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
            <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 'bold', mr: 1 }}>
              QUICK SEARCH PRESETS:
            </Typography>
            {[
              "Man wearing black jacket",
              "White Creta car",
              "Unattended backpack",
              "Crowd gathering",
              "Person wearing red shirt",
              "Running suspect"
            ].map((preset, idx) => (
              <Chip
                key={idx}
                label={preset}
                size="small"
                variant="outlined"
                color="primary"
                clickable
                onClick={() => {
                  setQuery(preset);
                  setKind('');
                  setTimeout(() => runSearch(), 50);
                }}
                sx={{ fontSize: '0.75rem' }}
              />
            ))}
          </Box>

          {/* Semantic Query input + Image Query Uploader */}
          <Box sx={{ gridColumn: { xs: 'span 1', lg: 'span 2' }, display: 'flex', flexDirection: 'column', gap: 0.5 }}>
            <Box sx={{ display: 'flex', gap: 1 }}>
              <TextField
                label="Natural Language Semantic Search"
                fullWidth
                size="small"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="e.g. person in red shirt, white car..."
              />
              <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center' }}>
                <Button
                  component="label"
                  variant={selectedVisionFile ? "contained" : "outlined"}
                  color="secondary"
                  size="small"
                  startIcon={<ImageSearchIcon />}
                  sx={{ whiteSpace: 'nowrap', px: 2, height: 40 }}
                >
                  {selectedVisionFile ? `File: ${selectedVisionFile.name.length > 16 ? selectedVisionFile.name.substring(0, 14) + '...' : selectedVisionFile.name}` : 'Upload Image Query'}
                  <input
                    id="visionImageInput"
                    type="file"
                    accept="image/*"
                    hidden
                    onChange={(e) => {
                      if (e.target.files && e.target.files[0]) {
                        setSelectedVisionFile(e.target.files[0]);
                        handleVisionImageSearchUpload(e.target.files[0]);
                      }
                    }}
                  />
                </Button>
                {selectedVisionFile && (
                  <Tooltip title="Cancel / Remove uploaded query image">
                    <IconButton
                      size="small"
                      color="error"
                      onClick={() => {
                        setSelectedVisionFile(null);
                        setExtractedAiPrompt('');
                        setQuery('');
                        const inp = document.getElementById('visionImageInput');
                        if (inp) inp.value = '';
                      }}
                      sx={{
                        border: '1px solid',
                        borderColor: 'error.main',
                        bgcolor: 'rgba(239, 68, 68, 0.2)',
                        '&:hover': { bgcolor: 'rgba(239, 68, 68, 0.4)' },
                        height: 40,
                        width: 40,
                        borderRadius: 1
                      }}
                    >
                      <CloseIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                )}
              </Box>
            </Box>
            {extractedAiPrompt && (
              <Chip
                label={`✨ AI Extracted Prompt: "${extractedAiPrompt}"`}
                size="small"
                color="info"
                onDelete={() => setExtractedAiPrompt('')}
                sx={{ alignSelf: 'flex-start', fontSize: '0.72rem', fontWeight: 600 }}
              />
            )}
          </Box>

          <Box>
            <FormControl fullWidth size="small">
              <InputLabel id="camera-select-label">Camera Source</InputLabel>
              <Select
                labelId="camera-select-label"
                value={selectedCamera}
                label="Camera Source"
                onChange={(e) => setSelectedCamera(e.target.value)}
              >
                <MenuItem value="">ALL CHANNELS</MenuItem>
                {(Array.isArray(cameras) ? cameras : []).map(cam => (
                  <MenuItem key={cam.id} value={cam.name}>{cam.name.toUpperCase()}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </Box>

          <Box>
            <FormControl fullWidth size="small">
              <InputLabel id="kind-select-label">Incident Type</InputLabel>
              <Select
                labelId="kind-select-label"
                value={kind}
                label="Incident Type"
                onChange={(e) => setKind(e.target.value)}
              >
                <MenuItem value="">ALL KINDS</MenuItem>
                <MenuItem value="alert">LIVE ALERTS ONLY</MenuItem>
                <MenuItem value="export">FORENSIC EXPORTS ONLY</MenuItem>
                <MenuItem value="face_search">POI WATCHLIST SEARCH</MenuItem>
                <MenuItem value="license_plate">LICENSE PLATE LOOKUP</MenuItem>
              </Select>
            </FormControl>
          </Box>

          <Box sx={{ gridColumn: { xs: 'span 1', sm: 'span 2' } }}>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
              <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
                <TextField
                  id="faceIdInput"
                  label="Enrollment Face ID"
                  size="small"
                  placeholder="e.g. track_15"
                  sx={{ width: 140 }}
                />
                <Box sx={{ display: 'flex', gap: 0.5, flexGrow: 1, alignItems: 'center' }}>
                  <Button
                    component="label"
                    variant={selectedFaceFile ? "contained" : "outlined"}
                    color={selectedFaceFile ? "success" : "primary"}
                    size="small"
                    startIcon={<ImageSearchIcon />}
                    sx={{ flexGrow: 1, height: 40, whiteSpace: 'nowrap', overflow: 'hidden' }}
                  >
                    {selectedFaceFile ? `File: ${selectedFaceFile.name.length > 18 ? selectedFaceFile.name.substring(0, 16) + '...' : selectedFaceFile.name}` : 'Upload Target Face Image'}
                    <input
                      id="faceImageInput"
                      type="file"
                      accept="image/*"
                      hidden
                      onChange={(e) => {
                        if (e.target.files && e.target.files[0]) {
                          setSelectedFaceFile(e.target.files[0]);
                        }
                      }}
                    />
                  </Button>
                  {selectedFaceFile && (
                    <Tooltip title="Cancel / Remove target face image">
                      <IconButton
                        size="small"
                        color="error"
                        onClick={() => {
                          setSelectedFaceFile(null);
                          const inp = document.getElementById('faceImageInput');
                          if (inp) inp.value = '';
                        }}
                        sx={{
                          border: '1px solid',
                          borderColor: 'error.main',
                          bgcolor: 'rgba(239, 68, 68, 0.25)',
                          '&:hover': { bgcolor: 'rgba(239, 68, 68, 0.5)' },
                          height: 40,
                          width: 40,
                          borderRadius: 1,
                          flexShrink: 0
                        }}
                      >
                        <CloseIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  )}
                </Box>
              </Box>
              <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.7rem' }}>
                Supports JPG, PNG, WEBP (Max 10MB) for vector similarity matching.
              </Typography>
            </Box>
          </Box>

          <Box>
            <FormControl fullWidth size="small">
              <InputLabel id="time-preset-label">Time Horizon Preset</InputLabel>
              <Select
                labelId="time-preset-label"
                value={timePreset}
                label="Time Horizon Preset"
                onChange={(e) => handleTimePresetChange(e.target.value)}
              >
                <MenuItem value="all">ALL HISTORY</MenuItem>
                <MenuItem value="15m">Last 15 Minutes</MenuItem>
                <MenuItem value="1h">Last 1 Hour</MenuItem>
                <MenuItem value="24h">Last 24 Hours</MenuItem>
                <MenuItem value="7d">Last 7 Days</MenuItem>
              </Select>
            </FormControl>
          </Box>

          <Box>
            <TextField
              label="Starting Bound"
              type="datetime-local"
              fullWidth
              size="small"
              value={start}
              onChange={(e) => { setStart(e.target.value); setTimePreset('custom'); }}
              slotProps={{ inputLabel: { shrink: true } }}
            />
          </Box>

          <Box>
            <TextField
              label="Ending Bound"
              type="datetime-local"
              fullWidth
              size="small"
              value={end}
              onChange={(e) => { setEnd(e.target.value); setTimePreset('custom'); }}
              slotProps={{ inputLabel: { shrink: true } }}
            />
          </Box>

          <Box>
            <TextField
              label="Matches Cap"
              type="number"
              fullWidth
              size="small"
              value={limit}
              onChange={(e) => setLimit(Math.max(1, Math.min(100, parseInt(e.target.value || '25', 10))))}
              slotProps={{ htmlInput: { min: 1, max: 100 } }}
            />
          </Box>

          <Box sx={{ px: 1 }}>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>Min Confidence: {minConfidence}%</Typography>
            <Slider
              value={minConfidence}
              min={0}
              max={100}
              size="small"
              onChange={(e, val) => setMinConfidence(val)}
              valueLabelDisplay="auto"
            />
          </Box>

          <Box sx={{
            gridColumn: '1 / -1',
            display: 'flex',
            justifyContent: 'flex-end',
            gap: 1.5,
            mt: 1,
            flexWrap: 'wrap'
          }}>
            <Button variant="outlined" startIcon={<SyncIcon />} onClick={loadCameras}>
              Refresh Channels
            </Button>
            <Button type="submit" variant="contained" startIcon={loading ? <SyncIcon sx={{ animation: 'spin 2s linear infinite' }} /> : <SearchIcon />}>
              Execute Forensic Query
            </Button>
          </Box>
        </Box>
      </Paper>

      {error && <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>}

      {/* Main Results section: Responsive Flex Layout to utilize 100% space without empty gaps */}
      <Box sx={{
        display: 'flex',
        flexDirection: { xs: 'column', md: 'row' },
        gap: 3,
        flexGrow: 1,
        minHeight: 0,
        width: '100%'
      }}>
        {/* Left Side: Filter Options */}
        <Box sx={{ width: { xs: '100%', md: '25%' }, flexShrink: 0 }}>
          <Paper variant="outlined" sx={{ p: 2.5, display: 'flex', flexDirection: 'column', gap: 3 }}>
            <Box>
              <Typography variant="subtitle2" fontWeight="bold" sx={{ borderBottom: '1px solid', borderColor: 'divider', pb: 1, mb: 1.5 }}>
                LOCAL LEDGER FILTER
              </Typography>
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                <Typography variant="caption" color="text.secondary">Tag Classificator:</Typography>
                <Box sx={{ display: 'flex', gap: 0.8, flexWrap: 'wrap' }}>
                  <Chip label="All Kinds" size="small" variant={classFilter === 'all' ? 'filled' : 'outlined'} onClick={() => setClassFilter('all')} />
                  <Chip label="Person" size="small" variant={classFilter === 'person' ? 'filled' : 'outlined'} onClick={() => setClassFilter('person')} />
                  <Chip label="Vehicle" size="small" variant={classFilter === 'vehicle' ? 'filled' : 'outlined'} onClick={() => setClassFilter('vehicle')} />
                  <Chip label="POI Target" size="small" variant={classFilter === 'poi' ? 'filled' : 'outlined'} onClick={() => setClassFilter('poi')} />
                  <Chip label="Exports" size="small" variant={classFilter === 'export' ? 'filled' : 'outlined'} onClick={() => setClassFilter('export')} />
                </Box>
              </Box>
            </Box>

            <Box>
              <Typography variant="subtitle2" fontWeight="bold" sx={{ borderBottom: '1px solid', borderColor: 'divider', pb: 1, mb: 1.5 }}>
                RESULTS SORTING
              </Typography>
              <FormControl fullWidth size="small">
                <Select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
                  <MenuItem value="newest">Newest/Recent First</MenuItem>
                  <MenuItem value="oldest">Oldest First</MenuItem>
                  <MenuItem value="confidence">Highest Match Score</MenuItem>
                </Select>
              </FormControl>
            </Box>

            <Box sx={{ p: 1.5, backgroundColor: 'background.default', border: '1px solid', borderColor: 'divider' }}>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
                <strong>Semantic Search:</strong> Florence-2 scene caption embeds are cross-matched with client query vectors.
              </Typography>
              <Typography variant="caption" color="text.secondary">
                <strong>Forensic Redaction:</strong> Non-watchlist faces are auto-masked to comply with privacy security frameworks.
              </Typography>
            </Box>
          </Paper>
        </Box>

        {/* Right Side: Ledger Results List (spans 100% remaining width) */}
        <Box sx={{ flexGrow: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          <Paper variant="outlined" sx={{ p: 3, flexGrow: 1, display: 'flex', flexDirection: 'column', width: '100%' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2, borderBottom: '1px solid', borderColor: 'divider', pb: 1.5 }}>
              <Typography variant="subtitle2" fontWeight="bold">MUTABLE HISTORICAL LEDGER</Typography>
              <Typography variant="caption" color="text.secondary">
                {loading ? 'QUERIES DISPATCHED...' : `RECORDED COUNT: ${processedResults.length}`}
              </Typography>
            </Box>

            <Box sx={{ overflowY: 'auto', flexGrow: 1, maxHeight: 'calc(100vh - 430px)' }}>
              {loading ? (
                <Typography variant="body2" color="text.secondary" align="center" sx={{ mt: 4 }}>RETRIEVING ENCODINGS...</Typography>
              ) : processedResults.length === 0 ? (
                <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', py: 8, px: 2, border: '1px dashed', borderColor: 'divider', borderRadius: 2, textAlign: 'center' }}>
                  <SearchIcon sx={{ fontSize: 48, color: 'text.secondary', mb: 1, opacity: 0.5 }} />
                  <Typography variant="subtitle1" fontWeight="bold" sx={{ mb: 0.5 }}>
                    No Forensic Records Found
                  </Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 400 }}>
                    No events matched your current semantic query, class filter, or time horizon parameters. Try clearing your filters or selecting "ALL HISTORY".
                  </Typography>
                </Box>
              ) : (
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                  {processedResults.map((item, index) => (
                    <Card
                      key={`${item.kind}-${item.id || item.export_uuid || index}`}
                      variant="outlined"
                      tabIndex={0}
                      role="article"
                      aria-label={`${item.title} at ${item.camera_name}`}
                      sx={{
                        display: 'flex',
                        flexDirection: { xs: 'column', sm: 'row' },
                        '&:focus-visible': {
                          outline: '2px solid primary.main',
                          outlineOffset: '2px'
                        }
                      }}
                    >
                      {item.snapshot_path && (
                        <Box sx={{ position: 'relative', width: { xs: '100%', sm: 220 }, height: 145, flexShrink: 0, backgroundColor: '#000', overflow: 'hidden' }}>
                          <CardMedia
                            component="img"
                            sx={{ width: '100%', height: '100%', objectFit: 'cover' }}
                            image={item.snapshot_path}
                            alt="Forensic Frame Capture"
                            onError={(e) => { e.target.style.display = 'none'; }}
                          />
                          {item.confidence > 0 && item.bbox_style ? (
                            <Box
                              sx={{
                                position: 'absolute',
                                top: item.bbox_style.top,
                                left: item.bbox_style.left,
                                width: item.bbox_style.width,
                                height: item.bbox_style.height,
                                border: '2px solid #00e676',
                                boxShadow: '0 0 10px rgba(0, 230, 118, 0.8), inset 0 0 6px rgba(0, 230, 118, 0.3)',
                                borderRadius: '4px',
                                pointerEvents: 'none',
                                zIndex: 2,
                                transition: 'all 0.2s ease-in-out'
                              }}
                            >
                              <Box
                                sx={{
                                  position: 'absolute',
                                  top: -20,
                                  left: -2,
                                  backgroundColor: '#00e676',
                                  color: '#000',
                                  fontSize: '0.62rem',
                                  fontWeight: 800,
                                  px: 0.8,
                                  py: 0.1,
                                  borderRadius: '3px 3px 0 0',
                                  whiteSpace: 'nowrap',
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: 0.4,
                                  boxShadow: '0 2px 4px rgba(0,0,0,0.6)',
                                  letterSpacing: '0.3px',
                                  textTransform: 'uppercase'
                                }}
                              >
                                <span>🎯 {item.target_label || query || 'MATCH'}</span>
                                <span>•</span>
                                <span>{item.confidence}%</span>
                              </Box>
                            </Box>
                          ) : item.confidence > 0 ? (
                            <Chip 
                              label={`🎯 ${item.target_label || query || 'MATCH'} • ${item.confidence}%`}
                              size="small" 
                              color="success" 
                              sx={{
                                position: 'absolute',
                                top: 8,
                                left: 8,
                                borderRadius: 1,
                                fontWeight: 800,
                                fontSize: '0.68rem',
                                textTransform: 'uppercase',
                                boxShadow: '0 2px 6px rgba(0,0,0,0.6)',
                                zIndex: 2
                              }} 
                            />
                          ) : null}
                          {item.confidence === 0 && (
                            <Box sx={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(0,0,0,0.5)' }}>
                              <Chip label="NO TARGETS" size="small" sx={{ borderRadius: 1, fontWeight: 'bold' }} />
                            </Box>
                          )}
                        </Box>
                      )}
                      
                      <Box sx={{ display: 'flex', flexDirection: 'column', flexGrow: 1 }}>
                        <CardContent sx={{ flexGrow: 1, pb: 1 }}>
                          <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1, flexWrap: 'wrap', gap: 1 }}>
                            <Box>
                              <Typography variant="subtitle2" fontWeight="bold" sx={{ textTransform: 'uppercase' }}>{item.title}</Typography>
                              <Typography variant="caption" color="text.secondary">{item.camera_name.toUpperCase()} // {item.timestamp}</Typography>
                            </Box>
                            <Chip label={item.kind} size="small" variant="outlined" sx={{ textTransform: 'uppercase', borderRadius: 1 }} />
                          </Box>
                          <Typography variant="body2" color="text.secondary">
                            {item.summary}
                          </Typography>
                        </CardContent>
                        <CardActions sx={{ display: 'flex', justifyContent: 'space-between', px: 2, pb: 2, flexWrap: 'wrap', gap: 1 }}>
                          <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap' }}>
                            {item.username && <Typography variant="caption" color="text.secondary">OPERATOR: {item.username.toUpperCase()}</Typography>}
                            {item.sha256_hash && <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>HASH: {item.sha256_hash.substring(0, 12)}</Typography>}
                          </Box>
                          <Box sx={{ display: 'flex', gap: 1 }}>
                            {item.mp4_download_url && (
                              <Button component="a" href={item.mp4_download_url} download size="small" variant="outlined" startIcon={<DownloadIcon />}>
                                MP4 Clip
                              </Button>
                            )}
                            {item.sidecar_download_url && (
                              <Button component="a" href={item.sidecar_download_url} download size="small" variant="outlined" startIcon={<DownloadIcon />}>
                                Sidecar JSON
                              </Button>
                            )}
                            {item.snapshot_path && (
                              <Button component="a" href={item.snapshot_path} target="_blank" rel="noreferrer" size="small" variant="outlined" startIcon={<ImageSearchIcon />}>
                                View Original
                              </Button>
                            )}
                          </Box>
                        </CardActions>
                      </Box>
                    </Card>
                  ))}
                </Box>
              )}
            </Box>
          </Paper>
        </Box>
      </Box>
    </Box>
  );
}