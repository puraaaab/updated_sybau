import React, { useState, useEffect, useRef, useCallback } from 'react';
import Hls from 'hls.js';
import {
  Box, Card, Typography, TextField, Dialog, DialogTitle, DialogContent,
  DialogActions, Button, IconButton, Paper, InputAdornment, Alert, Chip,
  Grid, Avatar, Badge, Tabs, Tab, Tooltip
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
import NotificationsActiveIcon from '@mui/icons-material/NotificationsActive';
import PersonSearchIcon from '@mui/icons-material/PersonSearch';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import CameraAltIcon from '@mui/icons-material/CameraAlt';

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
    const isWhep = lowerUrl.includes('/whep') || lowerUrl.includes(':8889');
    
    if (isMjpeg) {
      setPlayMode('mjpeg');
    } else if (isDirect) {
      setPlayMode('direct');
    } else if (isWhep) {
      setPlayMode('webrtc');
    } else if (isHls || isM3u8) {
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

    let isCancelled = false;
    pc.createOffer()
      .then(offer => {
        if (isCancelled || !pcRef.current) return null;
        return pcRef.current.setLocalDescription(offer).then(() => offer);
      })
      .then(offer => {
        if (!offer || isCancelled) return;
        return fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/sdp' },
          body: offer.sdp
        });
      })
      .then(res => {
        if (!res) return;
        if (!res.ok) throw new Error(`WHEP Handshake HTTP ${res.status}`);
        return res.text();
      })
      .then(answerSdp => {
        if (!answerSdp || isCancelled || !pcRef.current) return;
        return pcRef.current.setRemoteDescription({ type: 'answer', sdp: answerSdp });
      })
      .catch(err => {
        if (isCancelled) return;
        console.warn(`[WHEP Player] Failed WebRTC handshake for ${url}:`, err);
        setPlayMode('hls');
      });

    return () => {
      isCancelled = true;
      if (pcRef.current) {
        pcRef.current.close();
        pcRef.current = null;
      }
      if (video) video.srcObject = null;
    };
  }, [url, isOffline, playMode]);

  // Jump player directly to live edge when returning to tab or window focus
  const jumpToLiveEdge = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;
    if (video.buffered && video.buffered.length > 0) {
      const liveEdge = video.buffered.end(video.buffered.length - 1);
      if (liveEdge - video.currentTime > 1.2) {
        video.currentTime = Math.max(0, liveEdge - 0.3);
      }
    }
    if (video.paused) {
      video.play().catch(() => { });
    }
  }, []);

  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        jumpToLiveEdge();
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);
    window.addEventListener('focus', jumpToLiveEdge);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibility);
      window.removeEventListener('focus', jumpToLiveEdge);
    };
  }, [jumpToLiveEdge]);

  // 3. HLS.js Effect
  useEffect(() => {
    if (isOffline || !url || playMode !== 'hls') return;

    const video = videoRef.current;
    if (!video) return;

    let hls;
    const isM3u8Native = video.canPlayType('application/vnd.apple.mpegurl');

    if (Hls.isSupported()) {
      hls = new Hls({
        enableWorker: true,
        lowLatencyMode: true,
        backBufferLength: 5,
        maxBufferLength: 3,
        maxMaxBufferLength: 6,
        liveSyncDurationCount: 2,
        liveMaxLatencyDurationCount: 3,
        liveDurationInfinity: true,
        highBufferWatchdogPeriod: 1,
        maxLiveSyncPlaybackRate: 1.5
      });
      hls.loadSource(url);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        setIsBuffering(false);
        video.play().catch(() => { });
        jumpToLiveEdge();
      });
      hls.on(Hls.Events.ERROR, (event, data) => {
        if (data.fatal) {
          switch (data.type) {
            case Hls.ErrorTypes.NETWORK_ERROR:
              hls.startLoad();
              break;
            case Hls.ErrorTypes.MEDIA_ERROR:
              hls.recoverMediaError();
              break;
            default:
              hls.destroy();
              break;
          }
        }
      });
    } else if (isM3u8Native) {
      video.src = url;
      video.addEventListener('loadedmetadata', () => {
        setIsBuffering(false);
        video.play().catch(() => { });
        jumpToLiveEdge();
      });
    }

    return () => {
      if (hls) hls.destroy();
      if (video) video.src = '';
    };
  }, [url, isOffline, playMode, jumpToLiveEdge]);

  const handleLoadedMetadata = () => {
    setIsBuffering(false);
    if (videoRef.current) {
      const { videoWidth, videoHeight } = videoRef.current;
      if (videoWidth && videoHeight) {
        setVideoRatio(videoWidth / videoHeight);
      }
    }
  };

  const bufferTimerRef = useRef(null);

  const handleWaiting = () => {
    if (bufferTimerRef.current) clearTimeout(bufferTimerRef.current);
    bufferTimerRef.current = setTimeout(() => {
      setIsBuffering(true);
      setBufferCount(prev => prev + 1);
      if (onBuffer) onBuffer();
    }, 1500);
  };

  const handlePlaying = () => {
    if (bufferTimerRef.current) {
      clearTimeout(bufferTimerRef.current);
      bufferTimerRef.current = null;
    }
    setIsBuffering(false);
  };

  const handleTimeUpdate = () => {
    if (bufferTimerRef.current) {
      clearTimeout(bufferTimerRef.current);
      bufferTimerRef.current = null;
    }
    setIsBuffering(false);

    const video = videoRef.current;
    if (video && video.buffered && video.buffered.length > 0) {
      const liveEdge = video.buffered.end(video.buffered.length - 1);
      const latency = liveEdge - video.currentTime;
      if (latency > 2.2) {
        video.currentTime = Math.max(0, liveEdge - 0.3);
      }
    }
  };

  const handleCaptureFrame = (e) => {
    if (e) e.stopPropagation();
    const video = videoRef.current;
    if (!video || !video.videoWidth) {
      alert("Stream video frame is not currently ready for capture.");
      return;
    }
    try {
      const canvas = document.createElement('canvas');
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

      const dataUrl = canvas.toDataURL('image/jpeg', 0.95);
      const link = document.createElement('a');
      link.href = dataUrl;
      const ts = new Date().toISOString().replace(/[:.]/g, '-');
      link.download = `CAM_${String(cameraId || 'STREAM').toUpperCase()}_Snapshot_${ts}.jpg`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (err) {
      console.error("Failed to capture stream frame snapshot:", err);
    }
  };

  const currentFrameMode = settings?.frameMode || 'dynamic';
  let dynamicPaddingTop = '56.25%'; // default 16:9 fallback
  if (currentFrameMode === 'fixed-16-9') {
    dynamicPaddingTop = '56.25%';
  } else if (currentFrameMode === 'fixed-4-3') {
    dynamicPaddingTop = '75%';
  } else if (currentFrameMode === 'stretch') {
    dynamicPaddingTop = '56.25%';
  } else if (videoRatio) {
    dynamicPaddingTop = `${(1 / videoRatio) * 100}%`;
  }

  const objectFitStyle = currentFrameMode === 'stretch' ? 'fill' : 'contain';
  const youtubeId = getYouTubeId(originalUrl || url);

  return (
    <Box
      onDoubleClick={onDoubleClick}
      tabIndex={0}
      role="button"
      aria-label={`Live camera player stream ${cameraId || ''}`}
      onKeyDown={(e) => {
        if ((e.key === 'Enter' || e.key === ' ') && onDoubleClick) {
          e.preventDefault();
          onDoubleClick(e);
        }
      }}
      sx={{
        position: 'relative',
        width: '100%',
        paddingTop: dynamicPaddingTop,
        backgroundColor: '#000',
        overflow: 'hidden',
        cursor: onDoubleClick ? 'pointer' : 'default',
        borderRadius: (settings?.borderRadius !== undefined ? settings.borderRadius : 0),
        border: isPttActive ? '2px solid #ef4444' : 'none',
        '&:focus-visible': {
          outline: '2px solid primary.main',
          outlineOffset: '2px'
        }
      }}
    >
      {isOffline ? (
        <Box sx={{
          position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
          backgroundColor: '#0f172a', color: 'text.secondary'
        }}>
          <WarningAmberIcon sx={{ fontSize: 32, mb: 1, color: 'warning.main' }} />
          <Typography variant="caption" fontWeight="bold">CAMERA OFFLINE</Typography>
        </Box>
      ) : playMode === 'youtube' && youtubeId ? (
        <iframe
          src={`https://www.youtube.com/embed/${youtubeId}?autoplay=1&mute=1&controls=0&loop=1&playlist=${youtubeId}`}
          title="Live Stream"
          style={{
            position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', border: 0
          }}
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
        />
      ) : playMode === 'mjpeg' ? (
        <img
          src={url}
          alt="Live MJPEG Stream"
          onLoad={() => setIsBuffering(false)}
          onError={() => setIsBuffering(true)}
          style={{
            position: 'absolute', top: 0, left: 0, width: '100%', height: '100%',
            objectFit: objectFitStyle
          }}
        />
      ) : (
        <video
          id={`video-${cameraId}`}
          ref={videoRef}
          autoPlay
          muted
          playsInline
          onLoadedMetadata={handleLoadedMetadata}
          onWaiting={handleWaiting}
          onPlaying={handlePlaying}
          onTimeUpdate={handleTimeUpdate}
          style={{
            position: 'absolute', top: 0, left: 0, width: '100%', height: '100%',
            objectFit: objectFitStyle
          }}
        />
      )}

      {isBuffering && !isOffline && playMode !== 'youtube' && (
        <Box sx={{
          position: 'absolute', top: 8, right: 8,
          backgroundColor: 'rgba(0,0,0,0.65)', px: 1, py: 0.25, borderRadius: 1,
          backdropFilter: 'blur(4px)'
        }}>
          <Typography variant="caption" sx={{ color: '#38bdf8', fontSize: '0.65rem', fontWeight: 'bold' }}>
            CONNECTING...
          </Typography>
        </Box>
      )}

      {!isOffline && playMode !== 'youtube' && (
        <Tooltip title="Capture Instant Frame Snapshot">
          <IconButton
            size="small"
            onClick={handleCaptureFrame}
            sx={{
              position: 'absolute',
              bottom: 6,
              right: 6,
              backgroundColor: 'rgba(15, 23, 42, 0.75)',
              color: '#00e676',
              backdropFilter: 'blur(4px)',
              border: '1px solid rgba(0, 230, 118, 0.4)',
              transition: 'all 0.15s ease-in-out',
              '&:hover': { backgroundColor: 'rgba(0, 230, 118, 0.95)', color: '#000', transform: 'scale(1.1)' }
            }}
          >
            <CameraAltIcon sx={{ fontSize: 16 }} />
          </IconButton>
        </Tooltip>
      )}

      {isPttActive && (
        <Box sx={{
          position: 'absolute', bottom: 8, left: 8,
          backgroundColor: 'rgba(239, 68, 68, 0.9)', color: '#fff', px: 1, py: 0.25, borderRadius: 1,
          display: 'flex', alignItems: 'center', gap: 0.5
        }}>
          <MicIcon fontSize="small" />
          <Typography variant="caption" fontWeight="bold">PTT BROADCASTING</Typography>
        </Box>
      )}
    </Box>
  );
});

export default function LiveGrid({ token, role, alerts, searchQuery, settings = {} }) {
  const [cameras, setCameras] = useState([]);
  const [loading, setLoading] = useState(true);
  const [localSearchQuery, setLocalSearchQuery] = useState('');
  
  // Live Alert Ticker State
  const [liveAlerts, setLiveAlerts] = useState([]);
  const [selectedAlert, setSelectedAlert] = useState(null);

  // Criminal POI & Face Spotter Dialog State
  const [spottedFaces, setSpottedFaces] = useState([]);
  const [showFaceSpotter, setShowFaceSpotter] = useState(false);
  const [suspectQuery, setSuspectQuery] = useState('');
  const [expandedCamera, setExpandedCamera] = useState(null);

  // Add Camera Modal State
  const [showAddModal, setShowAddModal] = useState(false);
  const [newCamName, setNewCamName] = useState('');
  const [newCamLocation, setNewCamLocation] = useState('');
  const [newCamUrl, setNewCamUrl] = useState('');
  const [addError, setAddError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Florence Telemetry Counter State
  const [florenceStats, setFlorenceStats] = useState({ captioning: 0, queue: 0, captioned: 0, camera_stats: {} });

  useEffect(() => {
    const fetchFlorenceStats = () => {
      fetch('/api/v1/florence/stats')
        .then(res => res.ok ? res.json() : { captioning: 0, queue: 0, captioned: 0, camera_stats: {} })
        .then(data => setFlorenceStats(data))
        .catch(() => {});
    };
    fetchFlorenceStats();
    const interval = setInterval(fetchFlorenceStats, 1000);
    return () => clearInterval(interval);
  }, []);

  // ── Caption timestamp helpers ────────────────────────────────────────────
  // Parse the `ts=YYYY-MM-DDTHH:MM:SS+05:30` field embedded in stored captions.
  // Returns a Date object or null — all errors return null (never crash the UI).
  const parseCapTs = (caption) => {
    try {
      const m = caption?.match(/\bts=(\S+)/);
      if (!m) return null; // No ts= field — badge hidden silently
      const d = new Date(m[1]);
      return isNaN(d.getTime()) ? null : d; // Invalid date — badge hidden
    } catch {
      return null; // Any parse error — never crash UI
    }
  };

  // Convert a captured-at Date into a human-readable age string.
  // Returns null when the badge should be hidden (clock skew, >1 hour, or any error).
  const getAgeLabel = (ts) => {
    try {
      const ageSeconds = Math.floor((Date.now() - ts.getTime()) / 1000);
      if (ageSeconds < 0) return null;    // Clock skew — hide badge
      if (ageSeconds > 3600) return null; // >1 hour old — treat as archival
      if (ageSeconds < 60) return `${ageSeconds}s ago`;
      return `${Math.floor(ageSeconds / 60)}m ${ageSeconds % 60}s ago`;
    } catch {
      return null; // Never crash on age calculation
    }
  };
  // ────────────────────────────────────────────────────────────────────────


  const fetchCameras = useCallback(() => {
    if (!token) return;
    fetch('/api/v1/cameras', {
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(res => res.ok ? res.json() : [])
      .then(data => {
        setCameras(Array.isArray(data) ? data : []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [token]);

  const fetchLiveAlerts = useCallback(() => {
    fetch('/api/v1/alerts', {
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    })
      .then(res => res.ok ? res.json() : [])
      .then(data => {
        setLiveAlerts(Array.isArray(data) ? data : []);
      })
      .catch(() => {});
  }, [token]);

  const fetchSpottedFaces = useCallback(() => {
    fetch('/api/v1/records/faces?limit=24', {
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    })
      .then(res => res.ok ? res.json() : { items: [] })
      .then(data => {
        setSpottedFaces(Array.isArray(data.items) ? data.items : []);
      })
      .catch(() => {});
  }, [token]);

  // Load cameras on mount & auto-recover if backend is restarting/initializing
  useEffect(() => {
    if (!token) return;
    fetchCameras();
    const intervalTime = cameras.length === 0 ? 2000 : 8000;
    const interval = setInterval(fetchCameras, intervalTime);
    return () => clearInterval(interval);
  }, [token, fetchCameras, cameras.length]);

  // Poll alerts lightly every 5s
  useEffect(() => {
    if (!token) return;
    fetchLiveAlerts();
    const alertInterval = setInterval(fetchLiveAlerts, 1000);
    return () => clearInterval(alertInterval);
  }, [token, fetchLiveAlerts]);

  // Fetch spotted faces ONLY when spotter dialog is opened
  useEffect(() => {
    if (showFaceSpotter && token) {
      fetchSpottedFaces();
      const faceInterval = setInterval(fetchSpottedFaces, 4000);
      return () => clearInterval(faceInterval);
    }
  }, [showFaceSpotter, token, fetchSpottedFaces]);

  // Merge live WebSocket alert and polled DB alerts
  const latestAlert = React.useMemo(() => {
    if (alerts && Array.isArray(alerts) && alerts.length > 0 && alerts[0]) {
      return alerts[0];
    }
    return liveAlerts.length > 0 ? liveAlerts[0] : null;
  }, [alerts, liveAlerts]);

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
      .catch((err) => setAddError(err.message.toUpperCase()))
      .finally(() => setIsSubmitting(false));
  };

  const handleDeleteCamera = (camId, e) => {
    if (e) e.stopPropagation();
    if (!window.confirm(`Are you sure you want to remove camera stream "${camId}" from live surveillance?`)) return;

    fetch(`/api/cameras/${camId}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(res => res.json())
      .then(() => fetchCameras())
      .catch(err => alert(err.message));
  };

  const finalSearchQuery = (searchQuery || localSearchQuery).trim();
  const filteredCameras = (Array.isArray(cameras) ? cameras : []).filter(cam =>
    !finalSearchQuery ||
    (cam.name || '').toLowerCase().includes(finalSearchQuery.toLowerCase()) ||
    (cam.location || '').toLowerCase().includes(finalSearchQuery.toLowerCase())
  );

  const gridTemplateSx = {
    display: 'grid',
    gridTemplateColumns: `repeat(auto-fill, minmax(${TILE_MIN_WIDTH}px, ${TILE_MAX_WIDTH}px))`,
    gap: 2,
    justifyContent: 'start',
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', minWidth: 0, minHeight: 0, overflow: 'hidden', gap: 1.5 }}>
      
      {/* ── Top Bar: Title & Controls ──────────────────────────────────────── */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 2, flexShrink: 0 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Typography variant="h6" fontWeight="bold">Live Surveillance Grid</Typography>
          <Chip
            icon={<AutoAwesomeIcon sx={{ fontSize: '1rem !important' }} />}
            label={`captioning:- ${florenceStats.captioning} imegs queue: ${florenceStats.queue} imgs captioned: ${florenceStats.captioned || 0} imgs`}
            color="secondary"
            size="small"
            variant="filled"
            sx={{ fontWeight: 'bold', fontFamily: 'monospace', borderRadius: 2 }}
          />
          <Button
            variant="outlined"
            size="small"
            color="error"
            startIcon={<PersonSearchIcon />}
            onClick={() => setShowFaceSpotter(true)}
            sx={{ fontWeight: 'bold', borderRadius: 2 }}
          >
            🎯 CRIMINAL & FACE SPOTTER
          </Button>
        </Box>

        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
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
        </Box>
      </Box>

      {/* ── Scrollable Grid Region ────────────────────────────────────────── */}
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
              const activeUrl = cam.webrtc_url || cam.hls_url || cam.stream_url;
              return (
                <Card key={cam.id} sx={{
                  display: 'flex',
                  flexDirection: 'column',
                  width: '100%',
                  minWidth: 0,
                  borderColor: 'divider',
                  borderWidth: 1,
                  borderStyle: 'solid'
                }}>
                  {/* Header info */}
                  <Box sx={{ p: 0.75, borderBottom: '1px solid', borderColor: 'divider', display: 'flex', alignItems: 'center', justifyContent: 'space-between', backgroundColor: 'background.paper', gap: 1 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, minWidth: 0 }}>
                      <RadioButtonCheckedIcon color="success" fontSize="small" />
                      <Typography variant="caption" fontWeight="bold" noWrap>CAM_{String(cam.id).toUpperCase()}</Typography>
                    </Box>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                      <IconButton size="small" onClick={(e) => handleDeleteCamera(cam.id, e)} color="error">
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </Box>
                  </Box>

                  {/* Video Stream Container */}
                  <LivePlayer
                    url={activeUrl}
                    originalUrl={cam.stream_url}
                    isOffline={cam.status === 'offline'}
                    token={token}
                    settings={settings}
                    cameraId={cam.id}
                    isHls={Boolean(cam.hls_url && !cam.webrtc_url)}
                    onDoubleClick={() => setExpandedCamera(cam)}
                  />

                  {/* Bottom Camera Info */}
                  {(() => {
                    // Resolve the last caption for this camera from Florence stats.
                    // Falls back gracefully: no stats → no badge, bad data → no badge.
                    const camStat = florenceStats?.camera_stats?.[cam.id];
                    const lastCaption = camStat?.last_caption || null;
                    const capTs = lastCaption ? parseCapTs(lastCaption) : null;
                    const ageLabel = capTs ? getAgeLabel(capTs) : null;

                    return (
                      <Box sx={{ p: 0.75, backgroundColor: 'background.default', borderTop: '1px solid', borderColor: 'divider', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 0.5 }}>
                        <Typography variant="caption" color="text.secondary" noWrap sx={{ flex: 1, minWidth: 0 }}>
                          {cam.location || cam.name}
                        </Typography>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, flexShrink: 0 }}>
                          {ageLabel && (
                            <Tooltip title={`Florence-2 scene caption was captured ${ageLabel}. YOLO detection is always live.`}>
                              <Chip
                                label={`📷 ${ageLabel}`}
                                size="small"
                                sx={{
                                  height: 16,
                                  fontSize: '0.58rem',
                                  fontFamily: 'monospace',
                                  backgroundColor: 'rgba(245,158,11,0.15)',
                                  color: '#f59e0b',
                                  border: '1px solid rgba(245,158,11,0.4)',
                                  cursor: 'default',
                                }}
                              />
                            </Tooltip>
                          )}
                          <Chip label="LIVE" size="small" color="primary" variant="outlined" sx={{ height: 16, fontSize: '0.6rem' }} />
                        </Box>
                      </Box>
                    );
                  })()}
                </Card>
              );
            })}
          </Box>
        )}
      </Box>

      {/* ── Live Alert Notification Ticker Banner (Positioned BELOW Streams Grid) ────────── */}
      {latestAlert && (
        <Paper
          variant="outlined"
          sx={{
            p: 1.25,
            display: 'flex',
            alignItems: 'center',
            justify: 'space-between',
            background: latestAlert.type === 'POI_MATCH' || latestAlert.severity === 'high'
              ? 'linear-gradient(90deg, rgba(239,68,68,0.2) 0%, rgba(15,23,42,0.9) 100%)'
              : 'linear-gradient(90deg, rgba(234,179,8,0.2) 0%, rgba(15,23,42,0.9) 100%)',
            borderColor: latestAlert.type === 'POI_MATCH' || latestAlert.severity === 'high' ? 'error.main' : 'warning.main',
            borderRadius: 1.5,
            flexShrink: 0
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, minWidth: 0 }}>
            <NotificationsActiveIcon color={latestAlert.severity === 'high' ? "error" : "warning"} />
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="subtitle2" fontWeight="bold" sx={{ color: latestAlert.severity === 'high' ? 'error.main' : 'warning.main', display: 'flex', alignItems: 'center', gap: 1 }}>
                🚨 {latestAlert.type} <Chip label={(latestAlert.camera_name || latestAlert.camera_id || "CAM").toUpperCase()} size="small" color="default" sx={{ height: 18, fontSize: '0.65rem' }} />
              </Typography>
              <Typography variant="body2" color="text.primary" sx={{ wordBreak: 'break-word', whiteSpace: 'pre-wrap' }}>
                {latestAlert.details || latestAlert.message}
              </Typography>
            </Box>
          </Box>

          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexShrink: 0 }}>
            {(latestAlert.snapshot_url || latestAlert.snapshot_path) && (
              <Button
                size="small"
                variant="contained"
                color="error"
                startIcon={<CameraAltIcon />}
                onClick={() => setSelectedAlert(latestAlert)}
                sx={{ fontSize: '0.7rem', fontWeight: 'bold' }}
              >
                EVIDENCE SNAPSHOT
              </Button>
            )}
          </Box>
        </Paper>
      )}

      {/* ── Criminal & Face Spotter Dialog ────────────────────────────────── */}
      <Dialog open={showFaceSpotter} onClose={() => setShowFaceSpotter(false)} maxWidth="md" fullWidth>
        <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid', borderColor: 'divider' }}>
          <Typography variant="h6" fontWeight="bold" sx={{ display: 'flex', alignItems: 'center', gap: 1, color: 'error.main' }}>
            <PersonSearchIcon /> CRIMINAL & LIVE FACE SPOTTER CONSOLE
          </Typography>
          <IconButton onClick={() => setShowFaceSpotter(false)} size="small">
            <CloseIcon />
          </IconButton>
        </DialogTitle>
        <DialogContent dividers sx={{ backgroundColor: 'background.default' }}>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Typography variant="subtitle2" fontWeight="bold" sx={{ mb: 1 }}>SEARCH CRIMINAL TARGET / POI NAME</Typography>
              <TextField
                fullWidth
                size="small"
                placeholder="Filter spotted criminal faces or suspect identities..."
                value={suspectQuery}
                onChange={(e) => setSuspectQuery(e.target.value)}
              />
            </Paper>

            <Typography variant="subtitle2" fontWeight="bold" sx={{ mt: 1 }}>
              LIVE SPOTTED FACES & TARGET CROPS ({spottedFaces.length})
            </Typography>

            <Grid container spacing={1.5}>
              {spottedFaces
                .filter(f => !suspectQuery || (f.label || '').toLowerCase().includes(suspectQuery.toLowerCase()))
                .slice(0, 18)
                .map((face, idx) => (
                  <Grid size={{ xs: 6, sm: 4, md: 2 }} key={idx}>
                    <Paper variant="outlined" sx={{ p: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1, textAlign: 'center' }}>
                      <Avatar
                        src={face.snapshot_url}
                        variant="square"
                        sx={{ width: 80, height: 80, borderRadius: 1 }}
                      />
                      <Typography variant="caption" fontWeight="bold" noWrap sx={{ maxWidth: 100 }}>
                        {face.label || `FACE_${face.id}`}
                      </Typography>
                      <Chip
                        label={face.confidence ? `${Math.round(face.confidence * 100)}%` : '85%'}
                        size="small"
                        color={face.label && face.label.startsWith('POI_') ? 'error' : 'default'}
                        sx={{ height: 16, fontSize: '0.6rem' }}
                      />
                    </Paper>
                  </Grid>
                ))}
            </Grid>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowFaceSpotter(false)}>Close</Button>
        </DialogActions>
      </Dialog>

      {/* Snapshot Dialog */}
      <Dialog open={Boolean(selectedAlert)} onClose={() => setSelectedAlert(null)} maxWidth="md" fullWidth>
        <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Typography variant="subtitle1" fontWeight="bold">LIVE EVIDENCE SNAPSHOT // {selectedAlert?.type}</Typography>
          <IconButton onClick={() => setSelectedAlert(null)} size="small">
            <CloseIcon />
          </IconButton>
        </DialogTitle>
        <DialogContent dividers sx={{ backgroundColor: '#000', display: 'flex', justifyContent: 'center', p: 1 }}>
          {selectedAlert && (
            <img
              src={selectedAlert.snapshot_url || selectedAlert.snapshot_path}
              alt="Evidence Snapshot"
              style={{ maxWidth: '100%', maxHeight: '70vh', objectFit: 'contain' }}
            />
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSelectedAlert(null)}>Close</Button>
        </DialogActions>
      </Dialog>

      {/* ── Independent Window Focused Stream Dialog (Double-Click Trigger) ────────── */}
      <Dialog
        open={Boolean(expandedCamera)}
        onClose={() => setExpandedCamera(null)}
        maxWidth="lg"
        fullWidth
        PaperProps={{
          sx: {
            backgroundColor: '#090d16',
            border: '1px solid rgba(0, 230, 118, 0.4)',
            borderRadius: 2,
          }
        }}
      >
        <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', pb: 1, borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
            <RadioButtonCheckedIcon color="success" />
            <Typography variant="h6" fontWeight="bold" sx={{ color: '#00e676', fontFamily: 'monospace' }}>
              INDEPENDENT FOCUS STREAM // CAM_{String(expandedCamera?.id || '').toUpperCase()}
            </Typography>
            <Chip label={expandedCamera?.location || expandedCamera?.name} size="small" variant="outlined" color="primary" />
          </Box>
          <IconButton onClick={() => setExpandedCamera(null)} size="small" sx={{ color: 'text.secondary' }}>
            <CloseIcon />
          </IconButton>
        </DialogTitle>
        <DialogContent sx={{ p: 2, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', backgroundColor: '#000' }}>
          {expandedCamera && (
            <Box sx={{ width: '100%', minHeight: '65vh', position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <LivePlayer
                url={expandedCamera.webrtc_url || expandedCamera.hls_url || expandedCamera.stream_url}
                originalUrl={expandedCamera.stream_url}
                isOffline={expandedCamera.status === 'offline'}
                token={token}
                settings={settings}
                cameraId={expandedCamera.id}
                isHls={Boolean(expandedCamera.hls_url && !expandedCamera.webrtc_url)}
              />
            </Box>
          )}
        </DialogContent>
        <DialogActions sx={{ px: 3, py: 1.5, borderTop: '1px solid rgba(255,255,255,0.1)', justifyContent: 'space-between' }}>
          <Typography variant="caption" color="text.secondary">
            Double-click stream tile or click Return to return to multi-camera grid layout.
          </Typography>
          <Button variant="contained" color="primary" onClick={() => setExpandedCamera(null)} size="small">
            Return to Live Grid
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}