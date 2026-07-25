import React, { useState, useEffect, useRef } from 'react';
import {
  Tv,
  Users,
  FileSearch,
  Network,
  ShieldAlert,
  Volume2,
  VolumeX,
  Lock,
  Play,
  Shield,
  Store,
  Building2,
  Eye,
  ClipboardList,
  Key
} from 'lucide-react';
import LiveGrid from './components/LiveGrid';
import AlertsPanel from './components/AlertsPanel';
import WatchlistManager from './components/WatchlistManager';
import ForensicsManager from './components/ForensicsManager';
import InvestigationSearch from './components/InvestigationSearch';
import DiscoveryScanner from './components/DiscoveryScanner';
import ArchivePlayback from './components/ArchivePlayback';
import AdminConsole from './components/AdminConsole';

const ROLES = [
  { id: 'admin', label: 'ADMIN', icon: Shield },
  { id: 'retail_operator', label: 'RETAIL', icon: Store },
  { id: 'mall_operator', label: 'MALL', icon: Building2 },
  { id: 'viewer', label: 'VIEWER', icon: Eye },
];

const MODULES = [
  { id: 'live', index: '01', label: 'Live Cam Grid', icon: Tv },
  { id: 'watchlist', index: '02', label: 'POI Watchlist', icon: Users },
  { id: 'forensics', index: '03', label: 'Forensic Export', icon: FileSearch },
  { id: 'search', index: '04', label: 'Investigation Search', icon: FileSearch },
  { id: 'discovery', index: '05', label: 'ONVIF Probe', icon: Network },
  { id: 'playback', index: '06', label: 'Archive Playback', icon: Play },
  { id: 'admin', index: '07', label: 'Admin Console', icon: ClipboardList },
];

export default function App() {
  const [activeTab, setActiveTab] = useState('live');
  const [role, setRole] = useState(localStorage.getItem('sybau_role') || 'admin'); // Default role
  const [tokens, setTokens] = useState({});
  const [activeToken, setActiveToken] = useState(localStorage.getItem('sybau_token') || null);
  const [alerts, setAlerts] = useState([]);
  const [searchEvents, setSearchEvents] = useState([]);
  const [wsStatus, setWsStatus] = useState('OFFLINE');
  const [muted, setMuted] = useState(false);
  const [systemLoad, setSystemLoad] = useState({ cpu: 12, ram: 42, dbSize: 0, onlineCams: 0, totalCams: 0, uptime: 0 });
  const [clockNow, setClockNow] = useState(new Date());

  const wsRef = useRef(null);

  // 0. Live clock — gives officers a fixed time reference on every screen
  useEffect(() => {
    const t = setInterval(() => setClockNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loginError, setLoginError] = useState('');
  const [isDemoMode, setIsDemoMode] = useState(true);
  const [isBooting, setIsBooting] = useState(!localStorage.getItem('sybau_token'));
  
  // Forced password change & elevation request states
  const [mustChangePassword, setMustChangePassword] = useState(false);
  const [showElevationModal, setShowElevationModal] = useState(false);
  const [elevationType, setElevationType] = useState('role_elevation');
  const [elevationDetails, setElevationDetails] = useState('');
  const [elevationSuccess, setElevationSuccess] = useState('');
  const [elevationError, setElevationError] = useState('');
  const [newPasswordInput, setNewPasswordInput] = useState('');
  const [changePwdError, setChangePwdError] = useState('');

  // Public reset request states
  const [showPublicResetModal, setShowPublicResetModal] = useState(false);
  const [publicResetUsername, setPublicResetUsername] = useState('');
  const [publicResetDetails, setPublicResetDetails] = useState('');
  const [publicResetSuccess, setPublicResetSuccess] = useState('');
  const [publicResetError, setPublicResetError] = useState('');

  // Reset token reset states
  const [showResetTokenModal, setShowResetTokenModal] = useState(false);
  const [resetTokenInput, setResetTokenInput] = useState('');
  const [resetTokenPassword, setResetTokenPassword] = useState('');
  const [resetTokenSuccess, setResetTokenSuccess] = useState('');
  const [resetTokenError, setResetTokenError] = useState('');

  const handlePasswordChangeSubmit = (e) => {
    e.preventDefault();
    setChangePwdError('');
    fetch('/api/auth/change-password', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${activeToken}`
      },
      body: JSON.stringify({ old_password: password, new_password: newPasswordInput })
    })
      .then(async res => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Password change failed");
        return data;
      })
      .then(data => {
        setPassword(newPasswordInput);
        setNewPasswordInput('');
        setMustChangePassword(false);
        setActiveToken(data.access_token);
      })
      .catch(err => {
        setChangePwdError(err.message);
      });
  };

  const handleRequestElevation = (e) => {
    e.preventDefault();
    setElevationError('');
    setElevationSuccess('');
    
    fetch('/api/auth/request-elevation', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${activeToken}`
      },
      body: JSON.stringify({ request_type: elevationType, details: elevationDetails })
    })
      .then(async res => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Elevation request failed");
        return data;
      })
      .then(() => {
        setElevationSuccess("Elevation request submitted successfully.");
        setElevationDetails('');
      })
      .catch(err => setElevationError(err.message));
  };

  const handlePublicResetSubmit = (e) => {
    e.preventDefault();
    setPublicResetError('');
    setPublicResetSuccess('');

    fetch('/api/auth/request-reset-public', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: publicResetUsername, details: publicResetDetails })
    })
      .then(async res => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Failed to file request");
        return data;
      })
      .then(() => {
        setPublicResetSuccess("Reset request filed. Contact your administrator to receive your one-time reset token.");
        setPublicResetUsername('');
        setPublicResetDetails('');
      })
      .catch(err => setPublicResetError(err.message));
  };

  const handleResetWithTokenSubmit = (e) => {
    e.preventDefault();
    setResetTokenError('');
    setResetTokenSuccess('');

    fetch('/api/auth/reset-password-with-token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: resetTokenInput, new_password: resetTokenPassword })
    })
      .then(async res => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Reset failed");
        return data;
      })
      .then(() => {
        setResetTokenSuccess("Password reset successfully. You may now log in.");
        setResetTokenInput('');
        setResetTokenPassword('');
      })
      .catch(err => setResetTokenError(err.message));
  };

  // 1. Fetch Demo Signatures on Boot
  useEffect(() => {
    fetch('/api/auth/demo-tokens')
      .then(res => {
        if (!res.ok) throw new Error("Demo tokens unavailable (production mode)");
        return res.json();
      })
      .then(data => {
        setTokens(data);
        setIsDemoMode(true);
        const existingToken = localStorage.getItem('sybau_token');
        if (!existingToken && data.admin) {
            setActiveToken(data.admin);
            localStorage.setItem('sybau_token', data.admin);
            localStorage.setItem('sybau_role', 'admin');
        } else if (existingToken) {
            setActiveToken(existingToken);
        } else {
            setActiveToken(data.admin || '');
        }
      })
      .catch(err => {
        console.log("[Auth] Demo tokens not fetched. Standard production login required.");
        setIsDemoMode(false);
      })
      .finally(() => {
        setIsBooting(false);
      });
  }, []);

  const handleLogin = (e) => {
    if (e) e.preventDefault();
    setLoginError('');
    
    fetch('/api/auth/login', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ username, password })
    })
      .then(async res => {
        const contentType = res.headers.get("content-type");
        if (!contentType || !contentType.includes("application/json")) {
          throw new Error("Backend server is still starting up or unavailable. Please wait a few seconds and try again.");
        }
        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.detail || 'Login failed');
        }
        return data;
      })
      .then(data => {
        setActiveToken(data.access_token);
        setRole(data.role);
        localStorage.setItem('sybau_token', data.access_token);
        localStorage.setItem('sybau_role', data.role);
        setTokens(prev => ({ ...prev, [data.role]: data.access_token }));
        if (data.must_change_password) {
          setMustChangePassword(true);
        } else {
          setMustChangePassword(false);
        }
      })
      .catch(err => {
        setLoginError(err.message);
      });
  };

  const handleDemoQuickLogin = (userRole) => {
    let u = 'admin';
    let p = 'admin_pass';
    if (userRole === 'operator') {
      u = 'operator';
      p = 'operator_pass';
    } else if (userRole === 'viewer') {
      u = 'viewer';
      p = 'viewer_pass';
    }
    
    setUsername(u);
    setPassword(p);
    
    fetch('/api/auth/login', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ username: u, password: p })
    })
      .then(async res => {
        const contentType = res.headers.get("content-type");
        if (!contentType || !contentType.includes("application/json")) {
          throw new Error("Backend server is still starting up or unavailable. Please wait a few seconds and try again.");
        }
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Login failed');
        return data;
      })
      .then(data => {
        setActiveToken(data.access_token);
        setRole(data.role);
        localStorage.setItem('sybau_token', data.access_token);
        localStorage.setItem('sybau_role', data.role);
      })
      .catch(err => {
        setLoginError(err.message);
      });
  };


  // 2. Handle Role Transition (Security Check)
  const handleRoleChange = (newRole) => {
    setRole(newRole);
    const token = tokens[newRole] || '';
    setActiveToken(token);

    // Dynamic Role Routing Enforcement (Visual Gating)
    if (newRole === 'viewer') {
      // Viewer has no access to watchlist or forensics or discovery
      setActiveTab('live');
    } else if (newRole === 'operator' || newRole === 'retail_operator' || newRole === 'mall_operator') {
      // Operators have no access to watchlist config or camera discovery
      if (activeTab === 'watchlist' || activeTab === 'discovery') {
        setActiveTab('live');
      }
    }
  };

  // 3. Two-Tone Synth warning alarm via Web Audio API (Hardware simulator)
  const playConsoleAlarm = () => {
    if (muted) return;
    try {
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)();

      // Tone 1 (High chime)
      const osc1 = audioCtx.createOscillator();
      const gain1 = audioCtx.createGain();
      osc1.type = 'square';
      osc1.frequency.setValueAtTime(880, audioCtx.currentTime); // A5 note
      gain1.gain.setValueAtTime(0.15, audioCtx.currentTime);
      gain1.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.08);
      osc1.connect(gain1);
      gain1.connect(audioCtx.destination);
      osc1.start();
      osc1.stop(audioCtx.currentTime + 0.08);

      // Tone 2 (Lower drop chime)
      setTimeout(() => {
        const osc2 = audioCtx.createOscillator();
        const gain2 = audioCtx.createGain();
        osc2.type = 'square';
        osc2.frequency.setValueAtTime(660, audioCtx.currentTime); // E5 note
        gain2.gain.setValueAtTime(0.12, audioCtx.currentTime);
        gain2.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.12);
        osc2.connect(gain2);
        gain2.connect(audioCtx.destination);
        osc2.start();
        osc2.stop(audioCtx.currentTime + 0.12);
      }, 80);

    } catch (e) {
      console.warn("Audio alarm failed to initiate:", e);
    }
  };

  // 4. WebSocket Subprotocol Auth Handshake Loop with Auto-Reconnect
  useEffect(() => {
    if (!activeToken) return;

    let ws = null;
    let reconnectTimeout = null;
    let isCleanup = false;

    const connectWs = () => {
      if (isCleanup) return;
      setWsStatus('CONNECTING');

      // Hex encode signed token to conform to RFC 2616 subprotocol constraints
      const hexToken = Array.from(new TextEncoder().encode(activeToken))
        .map(b => b.toString(16).padStart(2, '0'))
        .join('');

      const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${wsProtocol}//${window.location.host}/api/ws/alerts`;
      console.log(`[WebSocket] Connecting using access_token subprotocol hex: ${hexToken.slice(0, 10)}...`);

      // Pass access_token and the hex token in subprotocol array
      ws = new WebSocket(wsUrl, ["access_token", hexToken]);
      wsRef.current = ws;

      ws.onopen = () => {
        setWsStatus('CONNECTED');
        console.log("[WebSocket] Handshake completed successfully.");
      };

      ws.onmessage = (event) => {
        try {
          const alertData = JSON.parse(event.data);
          console.log("[WebSocket] Received Alert:", alertData);

          // Append alert to top of inbox log list, but only if it's a real live alert
          if (alertData.type === 'search_snapshot_boxed') {
            setSearchEvents(prev => [alertData, ...prev].slice(0, 50));
          } else {
            setAlerts(prev => [alertData, ...prev].slice(0, 50));
          }

          // Synthesize audible alarms for watchlist detections
          if (alertData.type === 'POI_MATCH') {
            playConsoleAlarm();
          }
        } catch (e) {
          console.error("[WebSocket] Message parsing error:", e);
        }
      };

      ws.onerror = (err) => {
        console.error("[WebSocket] Socket error:", err);
      };

      ws.onclose = (event) => {
        if (isCleanup) return;
        setWsStatus('OFFLINE');
        console.log(`[WebSocket] Connection terminated. Reconnecting in 3s...`);
        reconnectTimeout = setTimeout(connectWs, 3000);
      };
    };

    connectWs();

    return () => {
      isCleanup = true;
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [activeToken, muted]);

  // 5. Telemetry Ticker fetching actual VMS system metrics
  useEffect(() => {
    const fetchTelemetry = () => {
      fetch('/api/system/telemetry')
        .then(res => {
          if (!res.ok) throw new Error("Telemetry unavailable");
          return res.json();
        })
        .then(data => {
          setSystemLoad({
            cpu: data.cpu_load,
            ram: data.ram_usage_pct,
            dbSize: data.db_size_kb,
            onlineCams: data.online_cameras,
            totalCams: data.total_cameras,
            uptime: data.uptime_seconds
          });
        })
        .catch(err => {
          console.warn("Failed to fetch system telemetry:", err);
        });
    };

    fetchTelemetry();
    const timer = setInterval(fetchTelemetry, 3000);
    return () => clearInterval(timer);
  }, []);

  // Helper to check navigation gates
  const hasAccess = (tabName) => {
    if (role === 'viewer') {
      return tabName === 'live';
    }
    if (role === 'operator' || role === 'retail_operator' || role === 'mall_operator') {
      return tabName === 'live' || tabName === 'forensics' || tabName === 'playback' || tabName === 'search';
    }
    return true; // admin
  };

  const clockTime = clockNow.toLocaleTimeString('en-GB', { hour12: false });
  const clockDate = clockNow.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });

  if (showPublicResetModal) {
    return (
      <div className="noc-app-container flex items-center justify-center font-mono">
        <div className="scanline-overlay" aria-hidden="true" />
        <div className="panel-border bg-neutral-950 p-6 w-96 max-w-sm flex flex-col gap-4 text-xs">
          <h3 className="text-neutral-300 font-semibold border-b border-neutral-800 pb-2 uppercase">REQUEST PASSWORD RESET</h3>
          <form onSubmit={handlePublicResetSubmit} className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <label className="text-neutral-500">YOUR USERNAME</label>
              <input
                type="text"
                value={publicResetUsername}
                onChange={(e) => setPublicResetUsername(e.target.value)}
                placeholder="Enter username"
                className="noc-input bg-neutral-900 border-neutral-700 text-white"
                required
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-neutral-500">JUSTIFICATION / CONTACT DETAILS</label>
              <textarea
                value={publicResetDetails}
                onChange={(e) => setPublicResetDetails(e.target.value)}
                placeholder="Provide details to help admin identify you"
                className="noc-input bg-neutral-900 border-neutral-700 text-white resize-none h-16 text-[10px]"
                required
              />
            </div>
            {publicResetError && <div className="text-red-500 bg-red-950/20 border border-red-900 p-2 text-[9px]">{publicResetError}</div>}
            {publicResetSuccess && <div className="text-green-400 bg-green-950/20 border border-green-900 p-2 text-[9px]">{publicResetSuccess}</div>}
            <div className="flex gap-2">
              <button type="button" onClick={() => { setShowPublicResetModal(false); setPublicResetSuccess(''); setPublicResetError(''); }} className="noc-button flex-1 py-1 text-center">CANCEL</button>
              <button type="submit" className="noc-button flex-1 py-1 text-center bg-white text-black font-bold">SUBMIT REQUEST</button>
            </div>
          </form>
        </div>
      </div>
    );
  }

  if (isBooting) {
    return (
      <div className="noc-app-container flex items-center justify-center font-mono">
        <div className="scanline-overlay" aria-hidden="true" />
        <div className="text-neutral-500 text-xs animate-pulse tracking-widest">INITIALIZING SECURE LINK...</div>
      </div>
    );
  }

  if (showResetTokenModal) {
    return (
      <div className="noc-app-container flex items-center justify-center font-mono">
        <div className="scanline-overlay" aria-hidden="true" />
        <div className="panel-border bg-neutral-950 p-6 w-96 max-w-sm flex flex-col gap-4 text-xs">
          <h3 className="text-neutral-300 font-semibold border-b border-neutral-800 pb-2 uppercase font-bold">RESET WITH ONE-TIME TOKEN</h3>
          <form onSubmit={handleResetWithTokenSubmit} className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <label className="text-neutral-500">ADMIN-ISSUED RESET TOKEN</label>
              <input
                type="text"
                value={resetTokenInput}
                onChange={(e) => setResetTokenInput(e.target.value)}
                placeholder="Paste token here"
                className="noc-input bg-neutral-900 border-neutral-700 text-white font-bold tracking-widest text-center"
                required
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-neutral-500">NEW SECURE PASSWORD</label>
              <input
                type="password"
                value={resetTokenPassword}
                onChange={(e) => setResetTokenPassword(e.target.value)}
                placeholder="••••••••"
                className="noc-input bg-neutral-900 border-neutral-700 text-white"
                required
              />
            </div>
            {resetTokenError && <div className="text-red-500 bg-red-950/20 border border-red-900 p-2 text-[9px]">{resetTokenError}</div>}
            {resetTokenSuccess && <div className="text-green-400 bg-green-950/20 border border-green-900 p-2 text-[9px]">{resetTokenSuccess}</div>}
            <div className="flex gap-2">
              <button type="button" onClick={() => { setShowResetTokenModal(false); setResetTokenSuccess(''); setResetTokenError(''); }} className="noc-button flex-1 py-1 text-center">CANCEL</button>
              <button type="submit" className="noc-button flex-1 py-1 text-center bg-white text-black font-bold">RESET PASSWORD</button>
            </div>
          </form>
        </div>
      </div>
    );
  }

  if (mustChangePassword) {
    return (
      <div className="noc-app-container flex items-center justify-center font-mono">
        <div className="scanline-overlay" aria-hidden="true" />
        <div className="panel-border bg-neutral-950 p-6 w-96 max-w-sm flex flex-col gap-4 text-xs">
          <div className="flex items-center gap-3 border-b border-neutral-800 pb-3">
            <div className="brand-mark">
              <ShieldAlert className="w-4 h-4 text-white" strokeWidth={1.5} />
            </div>
            <div>
              <span className="brand-title">SYBAU</span>
              <span className="brand-subtitle">Forced Security Hardening</span>
            </div>
          </div>
          
          <div className="text-[10px] text-neutral-400 mb-2">
            ⚠️ You are required to update your temporary or admin-reset password before establishing other links.
          </div>

          <form onSubmit={handlePasswordChangeSubmit} className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <label className="text-neutral-500">NEW SECURE PASSWORD</label>
              <input
                type="password"
                value={newPasswordInput}
                onChange={(e) => setNewPasswordInput(e.target.value)}
                placeholder="Enter new password"
                className="noc-input bg-neutral-900 border-neutral-700 text-neutral-200"
                required
              />
            </div>

            {changePwdError && (
              <div className="text-red-500 bg-red-950/20 border border-red-900 p-2 text-[10px] uppercase">
                {changePwdError}
              </div>
            )}

            <button type="submit" className="noc-button w-full flex items-center justify-center gap-1.5 py-2 font-bold bg-white text-black mt-2">
              <Lock className="w-3.5 h-3.5" />
              <span>COMMIT PASSWORD CHANGE</span>
            </button>
          </form>
        </div>
      </div>
    );
  }

  if (!activeToken) {
    return (
      <div className="noc-app-container flex items-center justify-center font-mono">
        <div className="scanline-overlay" aria-hidden="true" />
        
        <div className="panel-border bg-neutral-950 p-6 w-96 max-w-sm flex flex-col gap-4 text-xs">
          <div className="flex items-center gap-3 border-b border-neutral-800 pb-3">
            <div className="brand-mark">
              <ShieldAlert className="w-4 h-4 text-white" strokeWidth={1.5} />
            </div>
            <div>
              <span className="brand-title">SYBAU</span>
              <span className="brand-subtitle">Tactical Authentication Panel</span>
            </div>
          </div>

          <form onSubmit={handleLogin} className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <label className="text-neutral-500">USER CLASSIFICATION</label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="e.g. admin, operator, viewer"
                className="noc-input bg-neutral-900 border-neutral-700 text-neutral-200"
                required
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-neutral-500">OPERATIONAL PASSWORD</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="noc-input bg-neutral-900 border-neutral-700 text-neutral-200"
                required
              />
            </div>

            {loginError && (
              <div className="text-red-500 bg-red-950/20 border border-red-900 p-2 text-[10px] uppercase">
                {loginError}
              </div>
            )}

            <button type="submit" className="noc-button w-full flex items-center justify-center gap-1.5 py-2 font-bold bg-white text-black mt-2">
              <Lock className="w-3.5 h-3.5" />
              <span>ESTABLISH SECURE LINK</span>
            </button>
          </form>

          {isDemoMode && (
            <div className="border-t border-neutral-900 pt-4 flex flex-col gap-2">
              <span className="text-[10px] text-neutral-600 tracking-wider">DEMO CONVENIENCE LOGIN</span>
              <div className="grid grid-cols-3 gap-2">
                <button onClick={() => handleDemoQuickLogin('admin')} className="noc-button py-1 text-[9px] text-center">ADMIN</button>
                <button onClick={() => handleDemoQuickLogin('operator')} className="noc-button py-1 text-[9px] text-center">OPERATOR</button>
                <button onClick={() => handleDemoQuickLogin('viewer')} className="noc-button py-1 text-[9px] text-center">VIEWER</button>
              </div>
            </div>
          )}

          <div className="border-t border-neutral-900 pt-3 flex justify-between text-[9px] text-neutral-500">
            <button onClick={() => setShowPublicResetModal(true)} className="hover:text-neutral-300">FORGOT PASSWORD?</button>
            <button onClick={() => setShowResetTokenModal(true)} className="hover:text-neutral-300">HAVE RESET TOKEN?</button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="noc-app-container">
      <div className="scanline-overlay" aria-hidden="true" />

      {/* 1. Persistently Visible Command Header */}
      <header className="noc-header">
        <div className="header-brand">
          <div className="brand-mark">
            <ShieldAlert className="w-4 h-4 text-white" strokeWidth={1.5} />
          </div>
          <div>
            <span className="brand-title">SYBAU</span>
            <span className="brand-subtitle">Tactical Surveillance Command</span>
          </div>
          <div className="status-badge">
            <span className={`status-dot ${wsStatus === 'CONNECTED' ? 'live' : 'alert-pulse-fast'}`} />
            <span className={wsStatus === 'CONNECTED' ? 'text-neutral-300' : 'text-neutral-500'}>
              {wsStatus === 'CONNECTED' ? 'FEED LINKED' : wsStatus}
            </span>
          </div>
        </div>

        <div className="header-clock" aria-live="off">
          <span className="clock-time">{clockTime}</span>
          <span className="clock-date">{clockDate}</span>
        </div>

        {/* Telemetry Readouts */}
        <div className="header-telemetry">
          <div className="telemetry-item">
            <span>CPU</span>
            <span className={`telemetry-item-value ${systemLoad.cpu > 80 ? 'warn' : ''}`}>{systemLoad.cpu}%</span>
          </div>
          <div className="telemetry-item">
            <span>MEM</span>
            <span className={`telemetry-item-value ${systemLoad.ram > 80 ? 'warn' : ''}`}>{systemLoad.ram}%</span>
          </div>
          <div className="telemetry-item">
            <span>CAMS</span>
            <span className="telemetry-item-value">{systemLoad.onlineCams}/{systemLoad.totalCams}</span>
          </div>
          <div className="telemetry-item">
            <span>DB</span>
            <span className="telemetry-item-value">{systemLoad.dbSize} KB</span>
          </div>

          <button
            onClick={() => setMuted(!muted)}
            className={`audio-toggle ${muted ? 'muted' : ''}`}
            aria-pressed={muted}
            aria-label={muted ? 'Unmute alert audio' : 'Mute alert audio'}
          >
            {muted ? (
              <>
                <VolumeX className="w-3 h-3" />
                <span>Muted</span>
              </>
            ) : (
              <>
                <Volume2 className="w-3 h-3" />
                <span>Audio On</span>
              </>
            )}
          </button>

          {/* RBAC clearance switcher — one-tap segmented control */}
          <div className="clearance-group">
            <span className="clearance-label">Clearance</span>
            <div className="clearance-toggle" role="group" aria-label="Select clearance level">
              {ROLES.map(({ id, label, icon: Icon }) => (
                <button
                  key={id}
                  onClick={() => handleRoleChange(id)}
                  className={role === id ? 'active' : ''}
                  aria-pressed={role === id}
                >
                  <span className="flex items-center gap-1">
                    <Icon className="w-3 h-3" strokeWidth={2} />
                    {label}
                  </span>
                </button>
              ))}
            </div>
            
            <button 
              onClick={() => {
                setActiveToken(null);
                setUsername('');
                setPassword('');
                localStorage.removeItem('sybau_token');
                localStorage.removeItem('sybau_role');
              }} 
              className="audio-toggle ml-3 border-red-950 text-red-500 hover:border-red-600 hover:text-red-400"
              aria-label="Logout session"
            >
              <span>TERMINATE LINK</span>
            </button>
          </div>
        </div>
      </header>

      {/* 2. Main Console Layout */}
      <div className="noc-main-layout">

        {/* Sidebar Nav */}
        <nav className="noc-sidebar">
          <span className="noc-sidebar-label">Ops Modules</span>

          {MODULES.map(({ id, index, label, icon: Icon }) => {
            const enabled = hasAccess(id);
            return (
              <button
                key={id}
                disabled={!enabled}
                onClick={() => setActiveTab(id)}
                className={`noc-sidebar-btn ${activeTab === id ? 'active' : ''}`}
                aria-current={activeTab === id ? 'page' : undefined}
              >
                <div className="flex items-center">
                  <span className="module-index">{index}</span>
                  <Icon className="w-3.5 h-3.5 mr-2" strokeWidth={1.5} />
                  <span>{label}</span>
                </div>
                {!enabled && <Lock className="w-3 h-3 text-neutral-500" />}
              </button>
            );
          })}

          {role !== 'admin' && (
            <button
              onClick={() => setShowElevationModal(true)}
              className="noc-sidebar-btn border-neutral-850 text-amber-500 hover:text-amber-400 mt-2"
              style={{ borderLeftColor: 'var(--alert-pulse-fast)' }}
            >
              <div className="flex items-center">
                <span className="module-index">REQ</span>
                <Key className="w-3.5 h-3.5 mr-2" strokeWidth={1.5} />
                <span>Request Elevation</span>
              </div>
            </button>
          )}

          <div className="sidebar-spacer" />

          {/* At-a-glance system health, so officers never have to ask "is it working" */}
          <div className="sidebar-health">
            <span className="sidebar-health-label">System Health</span>
            <div className="health-row">
              <span className="health-name">CPU</span>
              <div className="health-bar-track">
                <div
                  className={`health-bar-fill ${systemLoad.cpu > 80 ? 'high' : ''}`}
                  style={{ width: `${Math.min(systemLoad.cpu, 100)}%` }}
                />
              </div>
              <span className="health-value">{systemLoad.cpu}%</span>
            </div>
            <div className="health-row">
              <span className="health-name">MEM</span>
              <div className="health-bar-track">
                <div
                  className={`health-bar-fill ${systemLoad.ram > 80 ? 'high' : ''}`}
                  style={{ width: `${Math.min(systemLoad.ram, 100)}%` }}
                />
              </div>
              <span className="health-value">{systemLoad.ram}%</span>
            </div>
          </div>
        </nav>

        {/* Console Workspace Panel */}
        <main className="noc-workspace">
          <div className="noc-content-area">

            {/* Screen Router */}
            <div 
              style={{ 
                opacity: activeTab === 'live' ? 1 : 0.01,
                pointerEvents: activeTab === 'live' ? 'auto' : 'none',
                position: activeTab === 'live' ? 'relative' : 'absolute',
                zIndex: activeTab === 'live' ? 1 : -1,
                width: '100%',
                height: '100%',
                flex: 1, 
                minHeight: 0, 
                display: 'flex',
                flexDirection: 'column',
                overflow: 'hidden' 
              }}
            >
              <LiveGrid role={role} token={activeToken} alerts={alerts} />
            </div>

            {activeTab === 'watchlist' && (
              <WatchlistManager token={activeToken} />
            )}

            {activeTab === 'forensics' && (
              <ForensicsManager role={role} token={activeToken} />
            )}

            {activeTab === 'search' && (
              <InvestigationSearch role={role} token={activeToken} searchEvents={searchEvents} />
            )}

            {activeTab === 'discovery' && (
              <DiscoveryScanner token={activeToken} />
            )}

            {activeTab === 'playback' && (
              <ArchivePlayback token={activeToken} />
            )}

            {activeTab === 'admin' && (
              <AdminConsole role={role} token={activeToken} />
            )}

          </div>

          {/* Split-bottom live alert log */}
          <footer className="noc-alert-footer">
            <div className="footer-header">
              <span className="footer-header-title">Live Alert Feed</span>
              <span className="footer-count">{alerts.length}</span>
            </div>
            <div className="footer-scroll">
              <AlertsPanel alerts={alerts} />
            </div>
          </footer>
        </main>
      </div>

      {/* Elevation Request Modal */}
      {showElevationModal && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-[2px] flex items-center justify-center font-mono z-50 p-4">
          <div className="panel-border bg-neutral-950 p-6 w-96 max-w-sm flex flex-col gap-4 text-xs">
            <h3 className="text-neutral-300 font-semibold border-b border-neutral-800 pb-2 uppercase flex items-center gap-1.5">
              <Key className="w-4 h-4 text-amber-500" />
              REQUEST SYSTEM ELEVATION
            </h3>
            
            <form onSubmit={handleRequestElevation} className="flex flex-col gap-3">
              <div className="flex flex-col gap-1.5">
                <label className="text-neutral-500">REQUEST TYPE</label>
                <select
                  value={elevationType}
                  onChange={(e) => setElevationType(e.target.value)}
                  className="noc-input bg-neutral-900 border-neutral-700 text-white text-[10px]"
                >
                  <option value="role_elevation">ELEVATE TO OPERATOR</option>
                  <option value="password_reset">ADMIN PASSWORD RESET</option>
                </select>
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-neutral-500">JUSTIFICATION EXPLANATION</label>
                <textarea
                  value={elevationDetails}
                  onChange={(e) => setElevationDetails(e.target.value)}
                  placeholder="State reason or reference case number..."
                  className="noc-input bg-neutral-900 border-neutral-700 text-white resize-none h-20 text-[10px]"
                  required
                />
              </div>

              {elevationError && <div className="text-red-500 bg-red-950/20 border border-red-900 p-2 text-[9px]">{elevationError}</div>}
              {elevationSuccess && <div className="text-green-400 bg-green-950/20 border border-green-900 p-2 text-[9px]">{elevationSuccess}</div>}

              <div className="flex gap-2 mt-2">
                <button type="button" onClick={() => { setShowElevationModal(false); setElevationSuccess(''); setElevationError(''); }} className="noc-button flex-1 py-1.5 text-center">CLOSE</button>
                <button type="submit" className="noc-button flex-1 py-1.5 text-center bg-white text-black font-bold">SUBMIT</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}