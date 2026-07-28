import React, { useState, useEffect, useRef, useCallback } from 'react';
import Hls from 'hls.js';
import {
  Box, Card, Typography, TextField, Dialog, DialogTitle, DialogContent,
  DialogActions, Button, IconButton, Paper, InputAdornment, Alert, Chip
} from '@mui/material';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import RadioButtonCheckedIcon from '@mui/icons-material/RadioButtonChecked';
import EditIcon from '@mui/icons-material/Edit';
import CheckIcon from '@mui/icons-material/Check';
import AddIcon from '@mui/icons-material/Add';
import LockIcon from '@mui/icons-material/Lock';
import SearchIcon from '@mui/icons-material/Search';
import CloseIcon from '@mui/icons-material/Close';
import PictureInPictureAltIcon from '@mui/icons-material/PictureInPictureAlt';
import MicIcon from '@mui/icons-material/Mic';
import DeleteIcon from '@mui/icons-material/Delete';

// ---- Tunables for tile size (change these two numbers to resize the whole grid) ----
const TILE_MIN_WIDTH = 240;   // px - smallest a tile can shrink to before wrapping
const TILE_MAX_WIDTH = 320;   // px - largest a tile can grow to (keeps frames small on wide screens)

const LivePlayer = React.memo(function LivePlayer({ url, originalUrl, isOffline, token, onBuffer, settings, onDoubleClick, cameraId, isHls, isPttActive = false }) {
  const videoRef = useRef(null);
  const pcRef = useRef(null);
  
  const [playMode, setPlayMode] = useState('webrtc'); // 'webrtc', 'hls', 'direct', 'mjpeg', 'youtube'
  const [isBuffering, setIsBuffering] = useState(true);
  const [bufferCount, setBufferCount] = useState(0);
  const [videoRatio, setVideoRatio] = useState(16 / 9);

  const getYouTubeId = (str) => {
    if (!str) return null;
    const regExp = /^.*(youtu\.be\/|v\/|u\/\w\/|embed\/|watch\?v=|&v=|live\/)([^#&?]*).*/;
    const match = str.match(regExp);
    if (match && match[2].length === 11) return match[2];
    return null;
  };

  // 1. Determine Playback Mode
  useEffect(() => {
    setIsBuffering(true);
    if (!url) return;
    
    const ytId = getYouTubeId(originalUrl || url);
    if (ytId) {
      setPlayMode('youtube');
      return;
    }

    const lowerUrl = url.toLowerCase();
    const isMjpeg = lowerUrl.includes('.mjpg') || lowerUrl.includes('.mjpeg') || lowerUrl.includes('video.cgi') || lowerUrl.includes('/mjpeg');
    const isDirect = lowerUrl.includes('.mp4') || lowerUrl.includes('.webm') || lowerUrl.includes('.ogg');
    const isM3u8 = lowerUrl.includes('.m3u8');
    const isInternal = lowerUrl.includes(':8888') || lowerUrl.includes('localhost') || lowerUrl.includes('127.0.0.1') || lowerUrl.includes('/hls/');
    
    if (isMjpeg) {
      setPlayMode('mjpeg');
    } else if (isDirect) {
      setPlayMode('direct');
    } else if (isHls || isM3u8 || !isInternal) {
      setPlayMode('hls');
    } else {
      setPlayMode('webrtc');
    }
  }, [url, originalUrl, isHls]);

  // 2. WebRTC Effect
  useEffect(() => {
    if (isOffline || !url || playMode !== 'webrtc') return;

    const video = videoRef.current;
    if (!video) return;

    const PeerConnectionClass = window.RTCPeerConnection || window.webkitRTCPeerConnection || window.mozRTCPeerConnection;
    if (!PeerConnectionClass) {
      console.warn("[WHEP Player] WebRTC is not supported in this browser environment. Falling back to HLS...");
      setPlayMode('hls');
      return;
    }

    let pc;
    try {
      pc = new PeerConnectionClass({ iceServers: [] });
    } catch (err) {
      console.warn("[WHEP Player] Failed to instantiate RTCPeerConnection. Falling back to HLS...", err);
      setPlayMode('hls');
      return;
    }
    pcRef.current = pc;

    pc.ontrack = (event) => {
      if (event.streams && event.streams[0]) {
        video.srcObject = event.streams[0];
      } else {
        if (!video.srcObject) video.srcObject = new MediaStream();
        video.srcObject.addTrack(event.track);
      }
      setIsBuffering(false);
      video.play().catch(() => { });
    };

    pc.addTransceiver('video', { direction: 'recvonly' });

    const fallbackTimer = setTimeout(() => {
      if (pc.connectionState !== 'connected') {
        console.warn("[WHEP Player] WebRTC timeout. Falling back to HLS...");
        setPlayMode('hls');
      }
    }, 7000);

    pc.onconnectionstatechange = () => {
      if (pc.connectionState === 'connected') {
        clearTimeout(fallbackTimer);
        setIsBuffering(false);
      }
      if (pc.connectionState === 'failed') {
        clearTimeout(fallbackTimer);
        console.warn("[WHEP Player] WebRTC failed. Falling back to HLS...");
        setPlayMode('hls');
      }
    };

    const startWhep = async () => {
      try {
        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);

        let whepUrl = url.replace(':8888', ':8889').replace('/index.m3u8', '/whep').replace('/hls/', '/webrtc/');

        const res = await fetch(whepUrl, {
          method: 'POST',
          body: pc.localDescription.sdp,
          headers: {
            'Content-Type': 'application/sdp',
            ...(token && whepUrl.includes('/api/') ? { 'Authorization': `Bearer ${token}` } : {})
          }
        });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        const answerSdp = await res.text();
        if (pc.signalingState !== 'closed') {
          await pc.setRemoteDescription(new RTCSessionDescription({ type: 'answer', sdp: answerSdp }));
        }

        setIsBuffering(false);
        video.play().catch(() => { });
      } catch (e) {
        clearTimeout(fallbackTimer);
        console.warn("[WHEP Player] WebRTC failed, HLS fallback...", e.message);
        setPlayMode('hls');
      }
    };

    startWhep();

    return () => {
      clearTimeout(fallbackTimer);
      if (pcRef.current) { pcRef.current.close(); pcRef.current = null; }
      if (video) video.srcObject = null;
    };
  }, [url, isOffline, playMode, token]);

  // 3. HLS Effect
  useEffect(() => {
    if (isOffline || !url || playMode !== 'hls') return;

    let hls = null;
    const video = videoRef.current;
    if (!video) return;

    if (Hls.isSupported()) {
      hls = new Hls({
        enableWorker: true, lowLatencyMode: true, manifestLoadingTimeout: 10000, levelLoadingTimeout: 10000,
        liveSyncDuration: 3.0, liveMaxLatencyDuration: 6.0, maxLiveSyncPlaybackRate: 1.3,
        xhrSetup: (xhr) => {
          if (token && url.includes('/api/')) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
        }
      });
      hls.loadSource(url);
      hls.attachMedia(video);

      let retryCount = 0;
      const MAX_RETRY_DELAY = 10000;
      video.muted = true; video.defaultMuted = true;

      hls.on(Hls.Events.MANIFEST_PARSED, (event, data) => {
        retryCount = 0;
        if (data.levels && data.levels.length > 0) hls.currentLevel = data.levels.length - 1;
        video.muted = true;
        video.play().then(() => setIsBuffering(false)).catch(() => { });
      });

      hls.on(Hls.Events.ERROR, (event, data) => {
        if (data.fatal) {
          const delay = Math.min(2000 * Math.pow(1.5, retryCount), MAX_RETRY_DELAY);
          retryCount++;
          switch (data.type) {
            case Hls.ErrorTypes.NETWORK_ERROR:
              setTimeout(() => { if (hls) { hls.loadSource(url); hls.startLoad(); } }, delay);
              break;
            case Hls.ErrorTypes.MEDIA_ERROR:
              hls.recoverMediaError();
              break;
            default:
              setTimeout(() => { if (hls) { hls.loadSource(url); hls.startLoad(); } }, delay);
              break;
          }
        } else {
          retryCount = 0;
        }
      });
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = url;
      video.addEventListener('loadedmetadata', () => video.play().catch(() => { }));
    }

    return () => { if (hls) hls.destroy(); };
  }, [url, isOffline, playMode, token]);

  // 4. Direct Video Effect
  useEffect(() => {
    if (isOffline || !url || playMode !== 'direct') return;
    const video = videoRef.current;
    if (video) {
      video.src = url;
      video.load();
      video.play().then(() => setIsBuffering(false)).catch(() => {});
    }
  }, [url, isOffline, playMode]);

  const handleDoubleClick = () => {
    if (onDoubleClick) {
      onDoubleClick();
    } else {
      if (!document.fullscreenElement) {
        if (videoRef.current && videoRef.current.parentElement) {
          videoRef.current.parentElement.requestFullscreen().catch(err => {
            console.error(`Error attempting to enable fullscreen: ${err.message}`);
          });
        }
      } else {
        if (document.exitFullscreen) {
          document.exitFullscreen();
        }
      }
    }
  };

  const handleLoadedMetadata = (e) => {
    const video = e.target;
    if (video && video.videoWidth && video.videoHeight) {
      setVideoRatio(video.videoWidth / video.videoHeight);
    }
  };


  const [heatmapPoints, setHeatmapPoints] = useState([]);
  const canvasRef = useRef(null);

  useEffect(() => {
    if (!settings.showHeatmap || !cameraId) return;
    fetch(`/api/v1/analytics/heatmap?camera_id=${cameraId}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    })
      .then(res => res.json())
      .then(data => setHeatmapPoints(data.heatmap_points || []))
      .catch(() => {});
  }, [settings.showHeatmap, cameraId, token]);

  useEffect(() => {
    if (!settings.showHeatmap || !canvasRef.current) return;
    const cvs = canvasRef.current;
    const ctx = cvs.getContext('2d');
    if (!ctx) return;

    ctx.clearRect(0, 0, cvs.width, cvs.height);

    heatmapPoints.forEach(pt => {
      const cx = pt.x * cvs.width;
      const cy = pt.y * cvs.height;
      const radius = 35;
      const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius);
      grad.addColorStop(0, `rgba(239, 68, 68, ${pt.value * 0.8})`);
      grad.addColorStop(0.5, `rgba(245, 158, 11, ${pt.value * 0.5})`);
      grad.addColorStop(1, 'rgba(16, 185, 129, 0)');

      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, Math.PI * 2);
      ctx.fill();
    });
  }, [heatmapPoints, settings.showHeatmap]);

  if (isOffline) {
    return (
      <Box sx={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', backgroundColor: '#000', border: '1px dashed #444', color: 'error.main', minHeight: 140 }} onDoubleClick={handleDoubleClick}>
        <WarningAmberIcon sx={{ fontSize: 32, mb: 1 }} />
        <Typography variant="caption" sx={{ fontFamily: 'monospace' }}>FEED_OFFLINE // CONNECT_LOST</Typography>
      </Box>
    );
  }

  const wrapperStyle = {
    width: '100%',
    minWidth: 0,
    minHeight: 0,
    position: 'relative',
    backgroundColor: '#000',
    overflow: 'hidden',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    aspectRatio: settings.frameMode === 'dynamic'
      ? videoRatio
      : settings.frameMode === 'fixed-16-9'
        ? '16/9'
        : settings.frameMode === 'fixed-4-3'
          ? '4/3'
          : 'auto',
    height: settings.frameMode === 'stretch' ? '100%' : 'auto',
  };


  return (
    <Box sx={wrapperStyle} onDoubleClick={handleDoubleClick}>
      {playMode === 'youtube' ? (
        <iframe
          src={`https://www.youtube.com/embed/${getYouTubeId(originalUrl || url)}?autoplay=1&mute=1&controls=0&disablekb=1&fs=0&iv_load_policy=3&modestbranding=1&playsinline=1&rel=0`}
          frameBorder="0"
          allow="autoplay; encrypted-media; picture-in-picture"
          allowFullScreen
          onLoad={() => setIsBuffering(false)}
          style={{ width: '100%', height: '100%', objectFit: 'contain', backgroundColor: '#000', pointerEvents: 'none' }}
        />
      ) : playMode === 'mjpeg' ? (
        <img
          src={url}
          alt="Live feed"
          onLoad={() => setIsBuffering(false)}
          onError={() => setIsBuffering(true)}
          style={{ width: '100%', height: '100%', maxWidth: '100%', maxHeight: '100%', objectFit: settings.frameMode === 'stretch' ? 'fill' : 'contain', backgroundColor: '#000', display: 'block' }}
        />
      ) : (
        <video
          id={cameraId ? `video-${cameraId}` : undefined}
          ref={videoRef}
          autoPlay
          muted
          playsInline
          onPlaying={() => { setIsBuffering(false); if (onBuffer) onBuffer('PLAYBACK_RESUMED'); }}
          onCanPlay={() => setIsBuffering(false)}
          onLoadedData={() => setIsBuffering(false)}
          onLoadedMetadata={handleLoadedMetadata}
          onTimeUpdate={() => setIsBuffering(false)}
          onWaiting={() => { setBufferCount(prev => prev + 1); if (onBuffer) onBuffer('BUFFERING_STARTED'); }}
          style={{ width: '100%', height: '100%', maxWidth: '100%', maxHeight: '100%', objectFit: settings.frameMode === 'stretch' ? 'fill' : 'contain', backgroundColor: '#000', display: 'block' }}
        />
      )}
      {settings.showHeatmap && (
        <canvas
          ref={canvasRef}
          width={320}
          height={180}
          style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none', zIndex: 8 }}
        />
      )}
      {isPttActive && (
        <Box sx={{ position: 'absolute', top: 6, left: 6, backgroundColor: 'rgba(220, 38, 38, 0.9)', color: '#fff', px: 1, py: 0.5, borderRadius: 1, zIndex: 12, display: 'flex', alignItems: 'center', gap: 1 }}>
          <Box sx={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: '#fff', animation: 'pulse 1s infinite' }} />
          <Typography variant="caption" sx={{ fontWeight: 'bold', fontFamily: 'monospace', fontSize: '0.65rem' }}>
            PTT INTERCOM TRANSMITTING
          </Typography>
        </Box>
      )}
      {isBuffering && (
        <Box sx={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(0,0,0,0.5)', pointerEvents: 'none' }}>
          <Typography variant="caption" sx={{ fontFamily: 'monospace', color: 'text.secondary' }}>BUFFERING...</Typography>
        </Box>
      )}
      <Box sx={{ position: 'absolute', top: 6, right: 6, backgroundColor: 'rgba(0,0,0,0.8)', border: '1px solid', borderColor: 'divider', px: 0.75, py: 0.25, borderRadius: 1, pointerEvents: 'none', userSelect: 'none', zIndex: 10 }}>
        <Typography variant="caption" sx={{ fontFamily: 'monospace', color: 'error.main', fontSize: '0.6rem' }}>BUF: {bufferCount}</Typography>
      </Box>
    </Box>
  );
});


export default function LiveGrid({ role, token, alerts, searchQuery = '', settings = {} }) {
  const [cameras, setCameras] = useState([]);
  const [loading, setLoading] = useState(true);
  const [frameCounts] = useState({});
  const [bufferLogs, setBufferLogs] = useState([]);
  const [focusedCamera, setFocusedCamera] = useState(null);

  const logBufferEvent = (camName, eventType) => {
    const timestamp = new Date().toLocaleTimeString();
    setBufferLogs(prev => [
      { id: Date.now() + Math.random(), camName, eventType, timestamp },
      ...prev
    ].slice(0, 50));
  };

  const [localSearchQuery, setLocalSearchQuery] = useState('');
  const [showAddModal, setShowAddModal] = useState(false);
  const [newCamName, setNewCamName] = useState('');
  const [newCamLocation, setNewCamLocation] = useState('');
  const [newCamUrl, setNewCamUrl] = useState('');
  const [addError, setAddError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [editingCamId, setEditingCamId] = useState(null);
  const [editLocationText, setEditLocationText] = useState('');

  const handlePiP = async (id, e) => {
    if (e) e.stopPropagation();
    const video = document.getElementById(`video-${id}`);
    if (video && document.pictureInPictureEnabled) {
      try {
        if (document.pictureInPictureElement === video) {
          await document.exitPictureInPicture();
        } else {
          await video.requestPictureInPicture();
        }
      } catch (err) {
        console.error("PiP failed", err);
      }
    }
  };

  const fetchCameras = useCallback(() => {
    if (!token) return;
    fetch('/api/v1/cameras', {
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(res => {
        if (!res.ok) {
          console.warn(`[LiveGrid] GET /api/v1/cameras failed with ${res.status}`);
          return [];
        }
        return res.json();
      })
      .then((data) => {
        const cams = Array.isArray(data) ? data : [];
        setCameras(cams);
        setLoading(false);
      })
      .catch(err => {
        console.error("Failed to load cameras:", err);
        setLoading(false);
      });
  }, [token]);

  useEffect(() => {
    if (!token) return;
    fetchCameras();
    const pollInterval = setInterval(fetchCameras, settings.refreshRate || 4000);
    return () => clearInterval(pollInterval);
  }, [token, settings.refreshRate, fetchCameras]);

  const verifyZoneClearance = (camera) => {
    if (!role || role === 'admin' || role === 'viewer') return true;

    const roleLower = role.toLowerCase();
    const camNameLower = (camera.name || '').toLowerCase();
    const camLocLower = (camera.location || '').toLowerCase();

    if (roleLower.includes('retail')) {
      return camNameLower.includes('retail') || camLocLower.includes('retail') || camLocLower.includes('store');
    }
    if (roleLower.includes('mall')) {
      return camNameLower.includes('mall') || camLocLower.includes('escalator');
    }
    if (roleLower.includes('city')) {
      return camNameLower.includes('city') || camLocLower.includes('crossroad');
    }
    return false;
  };

  const isCameraAlertActive = (camName) => {
    if (!alerts) return false;
    const recent = alerts.find(a => a.camera_name === camName);
    if (!recent) return false;

    const diff = (new Date() - new Date(recent.timestamp)) / 1000;
    return diff < 10 && recent.type === 'POI_MATCH';
  };

  const handleAddCamera = (e) => {
    e.preventDefault();
    if (!newCamName || !newCamLocation || !newCamUrl) {
      setAddError("ALL FIELDS ARE REQUIRED");
      return;
    }

    setIsSubmitting(true);
    setAddError('');

    const camId = 'cam_' + newCamName.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_');

    fetch('/api/cameras', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({
        id: camId,
        name: newCamName.trim(),
        location: newCamLocation.trim(),
        stream_url: newCamUrl.trim(),
        width: 1920,
        height: 1080
      })
    })
      .then(async (res) => {
        if (!res.ok) {
          const detail = await res.json().catch(() => ({}));
          throw new Error(detail.detail || `HTTP ERROR ${res.status}`);
        }
        return res.json();
      })
      .then(() => {
        setNewCamName('');
        setNewCamLocation('');
        setNewCamUrl('');
        setShowAddModal(false);
        fetchCameras();
      })
      .catch((err) => {
        setAddError(err.message.toUpperCase());
      })
      .finally(() => {
        setIsSubmitting(false);
      });
  };

  const handleRenameSubmit = (camId) => {
    fetch(`/api/cameras/${camId}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({
        location: editLocationText.trim()
      })
    })
      .then(res => res.json())
      .then(() => {
        setEditingCamId(null);
        fetchCameras();
      })
      .catch(err => console.error("Failed to rename camera", err));
  };

  const handleDeleteCamera = (camId, e) => {
    if (e) e.stopPropagation();
    if (!window.confirm(`Are you sure you want to remove camera stream "${camId}" from the live surveillance grid?`)) return;

    fetch(`/api/cameras/${camId}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(res => {
        if (!res.ok) throw new Error("Failed to delete camera stream.");
        return res.json();
      })
      .then(() => fetchCameras())
      .catch(err => alert(err.message));
  };

  const finalSearchQuery = (searchQuery || localSearchQuery).trim();

  const filteredCameras = (Array.isArray(cameras) ? cameras : []).filter(cam =>
    !finalSearchQuery ||
    (cam.name || '').toLowerCase().includes(finalSearchQuery.toLowerCase()) ||
    (cam.location || '').toLowerCase().includes(finalSearchQuery.toLowerCase())
  );

  // CSS-grid template shared by the loading skeleton, the camera tiles,
  // and the "add channel" tile - auto-fill wraps as many small tiles per
  // row as will fit, instead of a fixed 3-column MUI breakpoint layout.
  const gridTemplateSx = {
    display: 'grid',
    gridTemplateColumns: `repeat(auto-fill, minmax(${TILE_MIN_WIDTH}px, ${TILE_MAX_WIDTH}px))`,
    gap: 2,
    justifyContent: 'start',
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', minWidth: 0, minHeight: 0, overflow: 'hidden' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2, flexWrap: 'wrap', gap: 2, flexShrink: 0 }}>
        <Typography variant="h6" fontWeight="bold">Live Surveillance Grid</Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <TextField
            size="small"
            placeholder="Filter grid feeds..."
            value={localSearchQuery}
            onChange={(e) => setLocalSearchQuery(e.target.value)}
            slotProps={{
              input: {
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon fontSize="small" color="action" />
                  </InputAdornment>
                ),
              }
            }}
            sx={{ width: 220 }}
          />
          <Button 
            variant="contained" 
            size="small" 
            startIcon={<AddIcon />} 
            onClick={() => setShowAddModal(true)}
            sx={{ background: 'linear-gradient(135deg, #0284c7 0%, #2563eb 100%)' }}
          >
            Add Camera
          </Button>
          <Typography variant="caption" color="text.secondary">
            Active Feeds: {filteredCameras.length}
          </Typography>
        </Box>
      </Box>

      {/* Scrollable region: this Box is the ONLY thing that scrolls */}
      <Box sx={{ flex: '1 1 auto', minHeight: 0, overflowY: 'auto', overflowX: 'hidden', pr: 0.5 }}>
        {loading ? (
          <Box sx={gridTemplateSx}>
            {[1, 2, 3].map(n => (
              <Card key={n} sx={{ height: 170, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Typography variant="caption" color="text.secondary">Connecting Live Camera Feed...</Typography>
              </Card>
            ))}
          </Box>
        ) : (
          <Box sx={gridTemplateSx}>
            {filteredCameras.map(cam => {
              const cleared = verifyZoneClearance(cam);
              const hasAlert = isCameraAlertActive(cam.name);
              const hlsUrl = cam.hls_url || cam.stream_url;

              return (
                <Card key={cam.id} sx={{
                  display: 'flex',
                  flexDirection: 'column',
                  width: '100%',
                  minWidth: 0,
                  borderColor: hasAlert ? 'error.main' : 'divider',
                  borderWidth: hasAlert ? 2 : 1,
                  borderStyle: 'solid'
                }}>
                  {/* Header info */}
                  <Box sx={{ p: 0.75, borderBottom: '1px solid', borderColor: 'divider', display: 'flex', alignItems: 'center', justifyContent: 'space-between', backgroundColor: 'background.paper', gap: 1 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, minWidth: 0 }}>
                      <RadioButtonCheckedIcon color={hasAlert ? "error" : "disabled"} fontSize="small" />
                      <Typography variant="caption" fontWeight="bold" noWrap>CAM_{String(cam.id).toUpperCase()}</Typography>
                    </Box>
                    {editingCamId === cam.id ? (
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                        <TextField
                          size="small"
                          variant="standard"
                          value={editLocationText}
                          onChange={(e) => setEditLocationText(e.target.value)}
                          onKeyDown={(e) => e.key === 'Enter' && handleRenameSubmit(cam.id)}
                          autoFocus
                          sx={{ width: 80 }}
                        />
                        <IconButton size="small" onClick={() => handleRenameSubmit(cam.id)}>
                          <CheckIcon fontSize="small" />
                        </IconButton>
                      </Box>
                    ) : (
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, flexShrink: 0 }}>
                        <Typography variant="caption" color="text.secondary" noWrap sx={{ maxWidth: 80 }}>{(cam.location || 'Unknown').toUpperCase()}</Typography>
                        <IconButton size="small" onClick={(e) => { e.stopPropagation(); alert(`PTT Intercom Dispatch active for ${cam.name}. Transmitting audio...`); }} title="Push-to-Talk Intercom">
                          <MicIcon fontSize="small" color="error" />
                        </IconButton>
                        <IconButton size="small" onClick={(e) => handlePiP(cam.id, e)} title="Picture in Picture">
                          <PictureInPictureAltIcon fontSize="small" />
                        </IconButton>
                        {role === 'admin' && (
                          <>
                            <IconButton size="small" onClick={() => { setEditingCamId(cam.id); setEditLocationText(cam.location); }} title="Edit Location">
                              <EditIcon fontSize="small" />
                            </IconButton>
                            <IconButton size="small" color="error" onClick={(e) => handleDeleteCamera(cam.id, e)} title="Delete Camera Stream">
                              <DeleteIcon fontSize="small" />
                            </IconButton>
                          </>
                        )}
                      </Box>
                    )}
                  </Box>

                  {/* Video viewport area */}
                  <Box sx={{ backgroundColor: '#000', position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center', width: '100%', minWidth: 0, minHeight: 120 }}>
                    {!cleared ? (
                      <Box sx={{ py: 4, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: 'error.main' }}>
                        <LockIcon sx={{ fontSize: 32, mb: 1 }} />
                        <Typography variant="caption" fontWeight="bold">ACCESS DENIED</Typography>
                      </Box>
                    ) : (
                      <LivePlayer
                        cameraId={cam.id}
                        url={hlsUrl}
                        originalUrl={cam.stream_url}
                        isOffline={false}
                        token={token}
                        onBuffer={(eventType) => logBufferEvent(cam.name, eventType)}
                        settings={settings}
                        onDoubleClick={() => setFocusedCamera(cam)}
                      />
                    )}
                  </Box>

                  {/* Telemetry info */}
                  <Box sx={{ p: 0.75, borderTop: '1px solid', borderColor: 'divider', display: 'flex', alignItems: 'center', justifyContent: 'space-between', backgroundColor: 'background.paper' }}>
                    <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
                      <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.65rem' }}>RES: {cam.resolution || 'N/A'}</Typography>
                      <Chip
                        label={
                          cam.motion_status === 'TRACKING' ? `🎯 TRACKING (${cam.fps ? Number(cam.fps).toFixed(1) : '2.0'} FPS)` :
                          cam.motion_status === 'MOTION' ? `🔴 MOTION (${cam.fps ? Number(cam.fps).toFixed(1) : '2.0'} FPS)` :
                          cam.motion_status === 'ALERT' ? `⚠️ ALERT (${cam.fps ? Number(cam.fps).toFixed(1) : '2.0'} FPS)` :
                          `🟢 STREAMING (2.0 FPS)`
                        }
                        size="small"
                        color={
                          cam.motion_status === 'TRACKING' ? 'info' :
                          cam.motion_status === 'MOTION' ? 'error' :
                          cam.motion_status === 'ALERT' ? 'warning' :
                          'success'
                        }
                        variant={cam.motion_status === 'STREAMING' || !cam.motion_status ? 'outlined' : 'filled'}
                        sx={{ height: 18, fontSize: '0.55rem', fontWeight: 'bold', fontFamily: 'monospace' }}
                      />
                    </Box>
                    {cleared && (
                      <Box sx={{ display: 'flex', gap: 1.5 }}>
                        <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.65rem' }}>F: {frameCounts[cam.id] || 0}</Typography>
                        <Typography variant="caption" color={hasAlert ? "error.main" : "text.secondary"} fontWeight={hasAlert ? "bold" : "normal"} sx={{ fontSize: '0.65rem' }}>
                          {hasAlert ? '1 ALIGN' : 'STANDBY'}
                        </Typography>
                      </Box>
                    )}
                  </Box>
                </Card>
              );
            })}

            {role === 'admin' && (
              <Card
                sx={{
                  height: 170,
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  borderStyle: 'dashed',
                  borderWidth: 2,
                  borderColor: 'divider',
                  backgroundColor: 'transparent',
                  cursor: 'pointer',
                  '&:hover': { borderColor: 'primary.main', backgroundColor: 'action.hover' }
                }}
                onClick={() => setShowAddModal(true)}
              >
                <AddIcon color="action" sx={{ fontSize: 32, mb: 1 }} />
                <Typography variant="body2" color="text.secondary">Link Channel Relay</Typography>
              </Card>
            )}
          </Box>
        )}

        {/* Diagnostics Logs panel - now scrolls WITH the grid instead of eating fixed vertical space */}
        <Paper variant="outlined" sx={{ mt: 2, p: 2, height: 150, display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid', borderColor: 'divider', pb: 1, mb: 1 }}>
            <Typography variant="caption" fontWeight="bold" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <RadioButtonCheckedIcon color="error" fontSize="small" />
              CONSOLE DISPATCH & EVENT TELEMETRY
            </Typography>
          </Box>
          <Box sx={{ overflowY: 'auto', flexGrow: 1 }}>
            {bufferLogs.length === 0 ? (
              <Typography variant="body2" color="text.secondary" align="center" sx={{ mt: 2 }}>Diagnostics clear. System linked and running.</Typography>
            ) : (
              bufferLogs.map(log => (
                <Box key={log.id} sx={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid', borderColor: 'divider', py: 0.5 }}>
                  <Typography variant="caption">
                    [{log.timestamp}] CAM: <strong>{log.camName.toUpperCase()}</strong> -
                    {log.eventType === 'BUFFERING_STARTED' ? (
                      <span style={{ color: '#ff1744', marginLeft: 8, fontWeight: 'bold' }}>BUFFERING DETECTED</span>
                    ) : (
                      <span style={{ color: '#00e676', marginLeft: 8, fontWeight: 'bold' }}>STABLE LINK ESTABLISHED</span>
                    )}
                  </Typography>
                </Box>
              ))
            )}
          </Box>
        </Paper>
      </Box>

      {/* Focused Camera Expanded Dialog View (Big Screen) */}
      <Dialog
        open={Boolean(focusedCamera)}
        onClose={() => setFocusedCamera(null)}
        maxWidth="lg"
        fullWidth
        sx={{
          '& .MuiDialog-paper': {
            borderRadius: `${settings.borderRadius || 0}px`,
            border: '1px solid',
            borderColor: 'divider'
          }
        }}
      >
        <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', p: 2 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <RadioButtonCheckedIcon color="error" fontSize="small" />
            <Typography variant="subtitle2" fontWeight="bold" sx={{ fontFamily: 'monospace' }}>
              FOCUSED_EXPANSION // CAM_{focusedCamera?.id.toUpperCase()} // {focusedCamera?.name.toUpperCase()}
            </Typography>
          </Box>
          <IconButton onClick={() => setFocusedCamera(null)} size="small">
            <CloseIcon fontSize="small" />
          </IconButton>
        </DialogTitle>
        <DialogContent dividers sx={{ p: 0, backgroundColor: '#000', display: 'flex', justifyContent: 'center', alignItems: 'center', overflow: 'hidden' }}>
          {focusedCamera && (
            <Box sx={{ width: '100%', height: '70vh', minHeight: 400, maxH: 800 }}>
              <LivePlayer
                cameraId="focused"
                url={focusedCamera.hls_url || focusedCamera.stream_url}
                originalUrl={focusedCamera.stream_url}
                isOffline={false}
                token={token}
                settings={{ ...settings, frameMode: 'dynamic' }} // Force true aspect-ratio in focus view
              />
            </Box>
          )}
        </DialogContent>
        <DialogActions sx={{ justifyContent: 'space-between', px: 2, py: 1.5, backgroundColor: 'background.paper' }}>
          <Box>
            <Typography variant="caption" color="text.secondary">LOCATION: {(focusedCamera?.location || 'Unknown').toUpperCase()}</Typography>
            <Typography variant="caption" color="text.secondary" sx={{ ml: 2 }}>RESOLUTION: {focusedCamera?.resolution || '1920x1080'}</Typography>
          </Box>
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Button variant="contained" size="small" onClick={(e) => { handlePiP(focusedCamera.id, e); setFocusedCamera(null); }} startIcon={<PictureInPictureAltIcon />}>
              Pop Out (PiP)
            </Button>
            <Button variant="outlined" size="small" onClick={() => setFocusedCamera(null)}>Close</Button>
          </Box>
        </DialogActions>
      </Dialog>

      {/* Add Camera Dialog */}
      <Dialog open={showAddModal} onClose={() => setShowAddModal(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Register Surveillance Channel</DialogTitle>
        <DialogContent dividers>
          {addError && <Alert severity="error" sx={{ mb: 2 }}>{addError}</Alert>}
          <Box component="form" id="add-cam-form" onSubmit={handleAddCamera} sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
            <TextField label="Channel Name" required value={newCamName} onChange={(e) => setNewCamName(e.target.value)} placeholder="lobby_cam_3" fullWidth />
            <TextField label="Operational Location" required value={newCamLocation} onChange={(e) => setNewCamLocation(e.target.value)} placeholder="Reception Area" fullWidth />
            <TextField label="RTSP/HLS Stream Endpoint URL" required value={newCamUrl} onChange={(e) => setNewCamUrl(e.target.value)} placeholder="rtsp://mediamtx:8554/lobby_cam_3" fullWidth />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => { setShowAddModal(false); setAddError(''); }}>Cancel</Button>
          <Button type="submit" form="add-cam-form" variant="contained" disabled={isSubmitting}>
            {isSubmitting ? 'Registering...' : 'Register'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}