import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Box, Drawer, List, ListItem, ListItemButton, ListItemIcon, ListItemText,
  AppBar, Toolbar, Typography, Button, Snackbar, Alert, Chip, Menu, MenuItem,
  Divider, TextField, InputAdornment, IconButton, useMediaQuery, Tooltip,
  Dialog, DialogTitle, DialogContent, DialogActions
} from '@mui/material';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';

// Icons
import GridViewIcon from '@mui/icons-material/GridView';
import NotificationsActiveIcon from '@mui/icons-material/NotificationsActive';
import SearchIcon from '@mui/icons-material/Search';
import CameraAltIcon from '@mui/icons-material/CameraAlt';
import SettingsIcon from '@mui/icons-material/Settings';
import MonitorHeartIcon from '@mui/icons-material/MonitorHeart';
import AccountCircleIcon from '@mui/icons-material/AccountCircle';
import MenuIcon from '@mui/icons-material/Menu';
import ReceiptLongIcon from '@mui/icons-material/ReceiptLong';
import AccessTimeIcon from '@mui/icons-material/AccessTime';

function ISTClock() {
  const [timeStr, setTimeStr] = useState('');

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      const formatted = now.toLocaleTimeString('en-IN', {
        timeZone: 'Asia/Kolkata',
        hour: '2-digit',
        minute: '2-digit',
        hour12: true
      }).toUpperCase();
      setTimeStr(formatted);
    };

    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
      <AccessTimeIcon sx={{ fontSize: 13, color: '#00e676' }} />
      <Typography variant="caption" sx={{ fontFamily: 'monospace', fontWeight: 'bold', color: '#00e676', letterSpacing: '0.5px' }}>
        {timeStr} IST
      </Typography>
    </Box>
  );
}

// Components
import LiveGrid from './components/LiveGrid';
import AlertsPanel from './components/AlertsPanel';
import InvestigationSearch from './components/InvestigationSearch';
import AdminConsole from './components/AdminConsole';
import WatchlistManager from './components/WatchlistManager';
import ArchivePlayback from './components/ArchivePlayback';
import DiscoveryScanner from './components/DiscoveryScanner';
import ForensicsManager from './components/ForensicsManager';
import SettingsConsole from './components/SettingsConsole';
import TrajectoryMap from './components/TrajectoryMap';
import RecordsConsole from './components/RecordsConsole';
import LoginModal from './components/LoginModal';

const drawerWidth = 240;

export default function App() {
  const [activeTab, setActiveTab] = useState('live');
  const [token, setToken] = useState(localStorage.getItem('vms_token') || '');
  const [role, setRole] = useState(localStorage.getItem('vms_role') || '');
  const [username, setUsername] = useState(localStorage.getItem('vms_username') || '');
  const [loginError, setLoginError] = useState('');
  const [loginLoading, setLoginLoading] = useState(false);
  const [mustChangePassword, setMustChangePassword] = useState(false);
  const [forcePwdCurrentInput, setForcePwdCurrentInput] = useState('');
  const [forcePwdNewInput, setForcePwdNewInput] = useState('');
  const [forcePwdError, setForcePwdError] = useState('');
  const [forcePwdLoading, setForcePwdLoading] = useState(false);

  const [wsAlert, _setWsAlert] = useState(null);
  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [anchorEl, setAnchorEl] = useState(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [showMobileSearch, setShowMobileSearch] = useState(false);

  // Global Search State
  const [globalSearchQuery, setGlobalSearchQuery] = useState('');

  // AI Model Status Indicator
  const [aiStatus, setAiStatus] = useState({ status: 'PREWARMING', all_ready: false, models: {} });

  useEffect(() => {
    if (!token) return;
    const fetchAiStatus = () => {
      fetch('/api/v1/ai/status', {
        headers: { Authorization: `Bearer ${token}` }
      })
        .then(res => res.ok ? res.json() : null)
        .then(data => { if (data) setAiStatus(data); })
        .catch(() => {});
    };
    fetchAiStatus();
    const interval = setInterval(fetchAiStatus, 4000);
    return () => clearInterval(interval);
  }, [token]);

  // WebSocket real-time alerts client
  useEffect(() => {
    if (!token) return;
    let ws = null;
    let timer = null;
    let isSubscribed = true;

    const connectWS = () => {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.host;
      const wsUrl = `${protocol}//${host}/api/v1/ws/alerts`;
      ws = new WebSocket(wsUrl);

      ws.onmessage = (event) => {
        if (!isSubscribed) return;
        try {
          const payload = JSON.parse(event.data);
          if (payload && payload.topic === 'alerts' && payload.data) {
            _setWsAlert(payload.data);
            setSnackbarOpen(true);
          }
        } catch (e) {}
      };

      ws.onclose = () => {
        if (isSubscribed) {
          timer = setTimeout(connectWS, 5000);
        }
      };

      ws.onerror = () => {
        try { ws.close(); } catch(e) {}
      };
    };

    connectWS();

    return () => {
      isSubscribed = false;
      if (timer) clearTimeout(timer);
      if (ws) try { ws.close(); } catch(e) {}
    };
  }, [token]);

  // Customizable Settings State
  const [settings, setSettings] = useState(() => {
    try {
      const saved = localStorage.getItem('sybau_ui_settings');
      if (saved) return JSON.parse(saved);
    } catch (err) {
      console.warn("Failed to load saved UI settings:", err);
    }
    return {
      themeMode: 'stark-dark', // stark-dark | stark-light | emerald | amber
      density: 'compact', // comfortable | compact
      frameMode: 'dynamic', // dynamic | fixed-16-9 | fixed-4-3 | stretch
      gridCols: 'auto', // auto | 1 | 2 | 3 | 4
      soundEnabled: true,
      fontFamily: 'Space Grotesk',
      borderRadius: 0,
      alertTimeout: 6000,
      refreshRate: 4000
    };
  });

  // Save settings to LocalStorage on change
  const handleChangeSettings = (newSettings) => {
    setSettings((prev) => {
      const updated = { ...prev, ...newSettings };
      localStorage.setItem('sybau_ui_settings', JSON.stringify(updated));
      return updated;
    });
  };

  // Dynamic MUI Theme Construction based on customizable options
  const activeTheme = useMemo(() => {
    const isLight = settings.themeMode === 'stark-light';

    let primaryColor = '#ffffff';
    let secondaryColor = '#8a8a8a';
    let bgColor = '#000000';
    let paperColor = '#0d0d0d';
    let textColor = '#f2f2f2';
    let textSecColor = '#8a8a8a';
    let borderColor = '#232323';
    let errorColor = '#ff1744';
    let warningColor = '#ffc107';

    if (settings.themeMode === 'stark-light') {
      primaryColor = '#000000';
      secondaryColor = '#5c5c5c';
      bgColor = '#ffffff';
      paperColor = '#f5f5f5';
      textColor = '#050505';
      textSecColor = '#5c5c5c';
      borderColor = '#d8d8d8';
      errorColor = '#ff1744';
    } else if (settings.themeMode === 'emerald') {
      primaryColor = '#00e676';
      secondaryColor = '#00a352';
      bgColor = '#020503';
      paperColor = '#0a100c';
      textColor = '#00e676';
      textSecColor = '#5cb878';
      borderColor = '#1b3a24';
      errorColor = '#ff1744';
    } else if (settings.themeMode === 'amber') {
      primaryColor = '#ffb300';
      secondaryColor = '#c78b00';
      bgColor = '#050300';
      paperColor = '#120e06';
      textColor = '#ffb300';
      textSecColor = '#cca852';
      borderColor = '#3a2a0a';
      errorColor = '#ff1744';
    }

    const densitySpacing = settings.density === 'compact' ? 4 : 8;

    return createTheme({
      palette: {
        mode: isLight ? 'light' : 'dark',
        primary: { main: primaryColor },
        secondary: { main: secondaryColor },
        background: { default: bgColor, paper: paperColor },
        text: { primary: textColor, secondary: textSecColor },
        error: { main: errorColor },
        warning: { main: warningColor },
        divider: borderColor
      },
      spacing: densitySpacing,
      typography: {
        fontFamily: `"${settings.fontFamily || 'Space Grotesk'}", "Inter", -apple-system, BlinkMacSystemFont, sans-serif`,
        fontSize: settings.density === 'compact' ? 12 : 14,
        button: {
          textTransform: 'none',
          fontWeight: 600,
        },
      },
      components: {
        MuiButton: {
          styleOverrides: {
            root: {
              borderRadius: `${settings.borderRadius}px`,
              borderColor: borderColor,
              '&.MuiButton-outlined': {
                color: textColor,
                '&:hover': {
                  borderColor: primaryColor,
                  backgroundColor: isLight ? 'rgba(0,0,0,0.04)' : 'rgba(255,255,255,0.04)'
                }
              }
            },
          },
        },
        MuiPaper: {
          styleOverrides: {
            root: {
              backgroundImage: 'none',
              borderRadius: `${settings.borderRadius}px`,
              borderColor: borderColor,
            }
          }
        },
        MuiCard: {
          styleOverrides: {
            root: {
              backgroundImage: 'none',
              borderRadius: `${settings.borderRadius}px`,
              borderColor: borderColor,
            },
          },
        },
        MuiAppBar: {
          styleOverrides: {
            root: {
              backgroundColor: paperColor,
              borderBottom: `1px solid ${borderColor}`,
            }
          }
        },
        MuiDrawer: {
          styleOverrides: {
            paper: {
              backgroundColor: paperColor,
              borderRight: `1px solid ${borderColor}`,
            }
          }
        },
        MuiTableCell: {
          styleOverrides: {
            root: {
              borderBottom: `1px solid ${borderColor}`,
              padding: settings.density === 'compact' ? '6px 12px' : '12px 16px',
            },
            head: {
              backgroundColor: paperColor,
              color: textSecColor,
              fontWeight: 'bold'
            }
          }
        }
      },
    });
  }, [settings]);

  // Shared Admin States
  const [usersList, setUsersList] = useState([]);
  const [requests, setRequests] = useState([]);

  const loadAdminData = useCallback(() => {
    if (!token) return;
    fetch('/api/v1/admin/users', {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(res => res.ok ? res.json() : [])
      .then(data => setUsersList(Array.isArray(data) ? data : []))
      .catch(() => {});

    fetch('/api/v1/admin/elevation-requests', {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(res => res.ok ? res.json() : [])
      .then(data => setRequests(Array.isArray(data) ? data : []))
      .catch(() => {});
  }, [token]);

  useEffect(() => {
    if (token && role === 'admin') {
      loadAdminData();
    }
  }, [token, role, loadAdminData]);

  // Shared ONVIF Scan States
  const [scanning, setScanning] = useState(false);
  const [discovered, setDiscovered] = useState([]);
  const [resolvedUrls, setResolvedUrls] = useState({});

  // Responsive breakpoint checkers
  const isMdUp = useMediaQuery(activeTheme.breakpoints.up('md'));

  // Validate stored token on mount
  useEffect(() => {
    if (!token) return;
    fetch('/api/v1/cameras', {
      headers: { 'Authorization': `Bearer ${token}` }
    }).then(res => {
      if (res.status === 401) {
        console.warn('[Auth] Stored token is invalid/expired â€” clearing for re-login');
        localStorage.removeItem('vms_token');
        localStorage.removeItem('vms_role');
        localStorage.removeItem('vms_username');
        setToken('');
      }
    }).catch(() => {});
  }, [token]);


  const handleLogin = async (uname, pwd) => {
    setLoginError('');
    setLoginLoading(true);
    try {
      const formData = new URLSearchParams();
      formData.append('username', uname);
      formData.append('password', pwd);

      const res = await fetch('/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: formData
      });

      if (res.ok) {
        const data = await res.json();
        localStorage.setItem('vms_token', data.access_token);
        localStorage.setItem('vms_role', data.role);
        localStorage.setItem('vms_username', data.username);
        setToken(data.access_token);
        setRole(data.role);
        setUsername(data.username);
        // BUG-6 FIX: Enforce password change before allowing access
        if (data.must_change_password) {
          setMustChangePassword(true);
        }
      } else {
        const errData = await res.json().catch(() => ({ detail: 'Authentication failed' }));
        setLoginError(errData.detail || 'Invalid username or password');
      }
    } catch (e) {
      console.error(e);
      setLoginError('Could not connect to authentication service.');
    } finally {
      setLoginLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('vms_token');
    localStorage.removeItem('vms_role');
    localStorage.removeItem('vms_username');
    setToken('');
    setRole('');
    setUsername('');
    setMustChangePassword(false);
    setForcePwdCurrentInput('');
    setForcePwdNewInput('');
    setForcePwdError('');
    setAnchorEl(null);
  };

  const handleForcedPasswordChange = async () => {
    setForcePwdError('');
    if (!forcePwdCurrentInput || !forcePwdNewInput) {
      setForcePwdError('Both fields are required.');
      return;
    }
    if (forcePwdNewInput.length < 8) {
      setForcePwdError('New password must be at least 8 characters.');
      return;
    }
    setForcePwdLoading(true);
    try {
      const res = await fetch('/api/v1/auth/change-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ current_password: forcePwdCurrentInput, new_password: forcePwdNewInput })
      });
      if (res.ok) {
        setMustChangePassword(false);
        setForcePwdCurrentInput('');
        setForcePwdNewInput('');
      } else {
        const errData = await res.json().catch(() => ({ detail: 'Password change failed.' }));
        setForcePwdError(errData.detail || 'Password change failed.');
      }
    } catch (e) {
      setForcePwdError('Could not connect to server.');
    } finally {
      setForcePwdLoading(false);
    }
  };


  // handleRoleSwitch removed: it embedded default credentials in the JS bundle (security risk).

  // Admin Console actions mapped from Settings page
  const handleUpdateRole = (userId, newRole) => {
    fetch(`/api/v1/admin/users/${userId}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({ role: newRole })
    }).then(res => {
      if (res.ok) loadAdminData();
    });
  };

  const handleUpdateStatus = (userId, newStatus) => {
    fetch(`/api/v1/admin/users/${userId}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({ status: newStatus })
    }).then(res => {
      if (res.ok) loadAdminData();
    });
  };

  const handleResetPassword = (userId, newPassword) => {
    fetch(`/api/v1/admin/users/${userId}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({ password: newPassword })
    }).then(res => {
      if (res.ok) alert("Password successfully reset.");
    });
  };

  const handleSoftDelete = (userId) => {
    fetch(`/api/v1/admin/users/${userId}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}` }
    }).then(res => {
      if (res.ok) loadAdminData();
    });
  };

  const handleHardDelete = (userId, adminPass) => {
    fetch(`/api/v1/admin/users/${userId}/hard-delete`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({ admin_password: adminPass })
    }).then(res => {
      if (res.ok) {
        alert("User permanently erased.");
        loadAdminData();
      } else {
        alert("Erasure failed. Verify admin password.");
      }
    });
  };

  const handleResolveRequest = (reqId, requesterName, action) => {
    fetch(`/api/v1/admin/elevation-requests/${reqId}/resolve`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({ action })
    }).then(res => {
      if (res.ok) loadAdminData();
    });
  };

  // ONVIF discovery scanner actions mapped from Settings page
  const handleTriggerScan = () => {
    setScanning(true);
    setDiscovered([]);
    setResolvedUrls({});

    fetch('/api/v1/cameras/scan', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(res => res.json())
      .then(data => {
        setDiscovered(data.devices || []);
        setScanning(false);
      })
      .catch(() => setScanning(false));
  };

  const handleResolveStreamUri = async (device, index, onvifUser, onvifPass) => {
    try {
      const res = await fetch('/api/v1/cameras/resolve-onvif', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          onvif_ip: device.ip,
          onvif_port: device.port || 80,
          onvif_username: onvifUser,
          onvif_password: onvifPass
        })
      });
      const data = await res.json();
      if (res.ok) {
        setResolvedUrls(prev => ({ ...prev, [index]: data.stream_url }));
      } else {
        alert(data.detail || "RTSP Resolve failed");
      }
    } catch (err) {
      console.error("Error resolving ONVIF endpoint URL:", err);
      alert("Error resolving ONVIF endpoint URL");
    }
  };

  // Global Search input submit trigger
  const handleGlobalSearchSubmit = (e) => {
    e.preventDefault();
    if (globalSearchQuery.trim()) {
      setActiveTab('search');
    }
  };

  // Navigation Ops list configuration
  const menuItems = [
    { id: 'live', label: 'Live Camera Feeds', icon: <GridViewIcon /> },
    { id: 'records', label: 'Captured Records Ledger', icon: <ReceiptLongIcon /> },
    { id: 'alerts', label: 'Surveillance Alerts', icon: <NotificationsActiveIcon /> },
    { id: 'search', label: 'AI Forensic Search', icon: <SearchIcon /> },
    { id: 'trajectory', label: 'Route Suspect Tracking', icon: <GridViewIcon /> },
    { id: 'watchlist', label: 'POI Target Watchlist', icon: <AccountCircleIcon />, adminOnly: false },
    { id: 'forensics', label: 'Police FIR & Evidence', icon: <CameraAltIcon />, operatorOnly: true },
    { id: 'discovery', label: 'Auto-Scan IP Cameras', icon: <MonitorHeartIcon />, adminOnly: true },
    { id: 'playback', label: 'Archive Video Playback', icon: <CameraAltIcon /> },
    { id: 'admin', label: 'System Administration', icon: <SettingsIcon />, adminOnly: true },
    { id: 'settings', label: 'Platform Settings', icon: <SettingsIcon /> }
  ];

  // Drawer Content Markup
  const drawerContent = (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Toolbar />
      <Box sx={{ overflow: 'auto', mt: 2, flexGrow: 1 }}>
        <List>
          {menuItems.map((item) => {
            // Check clearance gates
            if (item.adminOnly && role !== 'admin') return null;
            if (item.operatorOnly && role === 'viewer') return null;

            return (
              <ListItem key={item.id} disablePadding>
                <ListItemButton
                  selected={activeTab === item.id}
                  onClick={() => {
                    setActiveTab(item.id);
                    setMobileOpen(false);
                  }}
                  sx={{
                    my: 0.5,
                    mx: 1,
                    borderRadius: '4px',
                    '&.Mui-selected': {
                      backgroundColor: 'primary.main',
                      color: 'primary.contrastText',
                      '& .MuiListItemIcon-root': { color: 'primary.contrastText' }
                    }
                  }}
                >
                  <ListItemIcon sx={{ minWidth: 40, color: activeTab === item.id ? 'primary.contrastText' : 'inherit' }}>
                    {item.icon}
                  </ListItemIcon>
                  <ListItemText primary={item.label} slotProps={{ primary: { style: { fontWeight: 'bold' } } }} />
                </ListItemButton>
              </ListItem>
            );
          })}
        </List>
      </Box>
      <Box sx={{ p: 1.5, borderTop: '1px solid', borderColor: 'divider', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 0.5 }}>
        <ISTClock />
        <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.7rem', opacity: 0.8 }}>SYBAU SECURE CONSOLE v1.1</Typography>
      </Box>
    </Box>
  );

  return (
    <ThemeProvider theme={activeTheme}>
      <CssBaseline />
      <Box sx={{ display: 'flex', minHeight: '100vh', backgroundColor: 'background.default' }}>
        {/* Top Navbar */}
        <AppBar position="fixed" sx={{ zIndex: (theme) => theme.zIndex.drawer + 1, backdropFilter: 'blur(10px)' }}>
          <Toolbar sx={{ justifyContent: 'space-between', gap: 1 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              {!isMdUp && (
                <IconButton color="inherit" onClick={() => setMobileOpen(!mobileOpen)} aria-label="Open navigation drawer" sx={{ mr: 1 }}>
                  <MenuIcon />
                </IconButton>
              )}
              <Typography variant="h6" noWrap component="div" sx={{ fontWeight: 'bold', letterSpacing: '0.5px' }}>
                SYBAU <span style={{ color: activeTheme.palette.text.secondary }}>VMS</span>
              </Typography>

              {/* AI Model Status Indicator Light */}
              <Tooltip 
                title={
                  <Box sx={{ p: 0.5 }}>
                    <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 0.5 }}>
                      AI Subsystem Status: {aiStatus.status}
                    </Typography>
                    {Object.entries(aiStatus.models || {}).map(([modelName, status]) => (
                      <Typography key={modelName} variant="caption" display="block" sx={{ color: status === 'LOADED' ? '#00e676' : '#ffb300' }}>
                        ● {modelName}: {status}
                      </Typography>
                    ))}
                  </Box>
                } 
                arrow
              >
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.8, cursor: 'pointer', ml: 1, px: 1, py: 0.3, borderRadius: 1, backgroundColor: 'rgba(255,255,255,0.06)' }}>
                  <Box
                    sx={{
                      width: 9,
                      height: 9,
                      borderRadius: '50%',
                      backgroundColor: aiStatus.all_ready ? '#00e676' : '#ffb300',
                      boxShadow: aiStatus.all_ready 
                        ? '0 0 10px #00e676, 0 0 4px #00e676' 
                        : '0 0 10px #ffb300, 0 0 4px #ffb300'
                    }}
                  />
                  <Typography variant="caption" sx={{ fontSize: '0.7rem', fontWeight: 700, color: aiStatus.all_ready ? '#00e676' : '#ffb300', letterSpacing: '0.5px' }}>
                    {aiStatus.all_ready ? 'AI ONLINE' : 'AI LOADING'}
                  </Typography>
                </Box>
              </Tooltip>
            </Box>

            {/* Global Search Box (Desktop) */}
            <Box component="form" onSubmit={handleGlobalSearchSubmit} sx={{ mx: 3, flexGrow: 0.3, display: { xs: 'none', sm: 'block' } }}>
              <TextField
                size="small"
                fullWidth
                placeholder="Global telemetry & forensic search..."
                value={globalSearchQuery}
                onChange={(e) => setGlobalSearchQuery(e.target.value)}
                slotProps={{
                  input: {
                    startAdornment: (
                      <InputAdornment position="start">
                        <SearchIcon fontSize="small" color="action" />
                      </InputAdornment>
                    ),
                  }
                }}
                sx={{
                  backgroundColor: 'background.default',
                  borderRadius: `${settings.borderRadius}px`,
                  '& .MuiOutlinedInput-root': {
                    '& fieldset': { borderColor: 'divider' },
                  }
                }}
              />
            </Box>

            {/* Session Actions & Switchers */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              {/* Mobile Search Toggle Icon */}
              <IconButton
                color="inherit"
                aria-label="Toggle mobile search"
                onClick={() => setShowMobileSearch(!showMobileSearch)}
                sx={{ display: { xs: 'flex', sm: 'none' } }}
              >
                <SearchIcon />
              </IconButton>

              <Chip
                label={role.toUpperCase()}
                color={role === 'admin' ? 'error' : role === 'operator' ? 'primary' : 'default'}
                size="small"
                sx={{ fontWeight: 'bold', borderRadius: `${settings.borderRadius}px` }}
              />

              <Button
                color="inherit"
                startIcon={<AccountCircleIcon />}
                onClick={(e) => setAnchorEl(e.currentTarget)}
                sx={{ fontWeight: 'bold' }}
              >
                {username || 'Login'}
              </Button>

              <Menu
                anchorEl={anchorEl}
                open={Boolean(anchorEl)}
                onClose={() => setAnchorEl(null)}
              >
                <MenuItem disabled><Typography variant="caption">Logged in as {username} ({role})</Typography></MenuItem>
                <Divider />
                <MenuItem onClick={handleLogout}>Sign Out</MenuItem>
              </Menu>
            </Box>
          </Toolbar>

          {/* Mobile Search Expandable Input Overlay */}
          {showMobileSearch && (
            <Box component="form" onSubmit={handleGlobalSearchSubmit} sx={{ p: 1, px: 2, display: { xs: 'block', sm: 'none' }, borderTop: '1px solid', borderColor: 'divider' }}>
              <TextField
                size="small"
                fullWidth
                autoFocus
                placeholder="Search telemetry..."
                value={globalSearchQuery}
                onChange={(e) => setGlobalSearchQuery(e.target.value)}
                slotProps={{
                  input: {
                    startAdornment: (
                      <InputAdornment position="start">
                        <SearchIcon fontSize="small" color="action" />
                      </InputAdornment>
                    ),
                  }
                }}
              />
            </Box>
          )}
        </AppBar>

        {/* Sidebar Responsive Drawer */}
        <Box component="nav" sx={{ width: { md: drawerWidth }, flexShrink: { md: 0 } }}>
          {/* Mobile Temporary Drawer */}
          {!isMdUp ? (
            <Drawer
              variant="temporary"
              open={mobileOpen}
              onClose={() => setMobileOpen(false)}
              ModalProps={{ keepMounted: true }}
              sx={{
                '& .MuiDrawer-paper': { width: drawerWidth, boxSizing: 'border-box' },
              }}
            >
              {drawerContent}
            </Drawer>
          ) : (
            /* Desktop Permanent Drawer */
            <Drawer
              variant="permanent"
              sx={{
                width: drawerWidth,
                '& .MuiDrawer-paper': { width: drawerWidth, boxSizing: 'border-box' },
              }}
              open
            >
              {drawerContent}
            </Drawer>
          )}
        </Box>

        {/* Main Viewport Content Area */}
        <Box component="main" sx={{ flexGrow: 1, p: settings.density === 'compact' ? 2 : 4, minWidth: 0 }}>
          <Toolbar /> {/* Spacer to prevent content from rendering under the fixed AppBar */}
          <Box sx={{ display: activeTab === 'live' ? 'block' : 'none', height: '100%' }}>
            <LiveGrid
              token={token}
              role={role}
              searchQuery={globalSearchQuery}
              settings={settings}
            />
          </Box>
          <Box sx={{ display: activeTab === 'records' ? 'block' : 'none', height: '100%' }}>
            <RecordsConsole token={token} />
          </Box>
          <Box sx={{ display: activeTab === 'alerts' ? 'block' : 'none', height: '100%' }}>
            <AlertsPanel
              token={token}
              role={role}
              alerts={wsAlert ? [wsAlert] : []}
            />
          </Box>
          <Box sx={{ display: activeTab === 'search' ? 'block' : 'none', height: '100%' }}>
            <InvestigationSearch
              token={token}
              role={role}
              searchEvents={wsAlert ? [wsAlert] : []}
              initialQuery={globalSearchQuery}
            />
          </Box>
          <Box sx={{ display: activeTab === 'trajectory' ? 'block' : 'none', height: '100%' }}>
            <TrajectoryMap
              token={token}
            />
          </Box>
          <Box sx={{ display: activeTab === 'watchlist' ? 'block' : 'none', height: '100%' }}>
            <WatchlistManager
              token={token}
            />
          </Box>
          <Box sx={{ display: activeTab === 'forensics' ? 'block' : 'none', height: '100%' }}>
            <ForensicsManager
              token={token}
              role={role}
            />
          </Box>
          <Box sx={{ display: activeTab === 'discovery' ? 'block' : 'none', height: '100%' }}>
            <DiscoveryScanner
              token={token}
            />
          </Box>
          <Box sx={{ display: activeTab === 'playback' ? 'block' : 'none', height: '100%' }}>
            <ArchivePlayback
              token={token}
            />
          </Box>
          <Box sx={{ display: activeTab === 'admin' ? 'block' : 'none', height: '100%' }}>
            <AdminConsole
              token={token}
              role={role}
            />
          </Box>
          <Box sx={{ display: activeTab === 'settings' ? 'block' : 'none', height: '100%' }}>
            <SettingsConsole
              settings={settings}
              onChangeSettings={handleChangeSettings}
              token={token}
              role={role}
              usersList={usersList}
              requests={requests}
              onReloadUsers={loadAdminData}
              onReloadRequests={loadAdminData}
              onUpdateRole={handleUpdateRole}
              onUpdateStatus={handleUpdateStatus}
              onResetPassword={handleResetPassword}
              onSoftDelete={handleSoftDelete}
              onHardDelete={handleHardDelete}
              onResolveRequest={handleResolveRequest}
              onTriggerScan={handleTriggerScan}
              scanning={scanning}
              discovered={discovered}
              resolvedUrls={resolvedUrls}
              onResolveStreamUri={handleResolveStreamUri}
            />
          </Box>
        </Box>

        {/* WebSocket Alert Snacker */}
        <Snackbar
          open={snackbarOpen}
          autoHideDuration={settings.alertTimeout || 6000}
          onClose={() => setSnackbarOpen(false)}
          anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        >
          {wsAlert && (
            <Alert
              onClose={() => setSnackbarOpen(false)}
              severity={wsAlert.severity === 'high' ? 'error' : wsAlert.severity === 'medium' ? 'warning' : 'info'}
              variant="filled"
              sx={{ width: '100%', fontWeight: 'bold', borderRadius: `${settings.borderRadius}px` }}
            >
              {`[NEW ALERT - ${wsAlert.type.toUpperCase()}] ${wsAlert.message}`}
            </Alert>
          )}
        </Snackbar>

        {/* Authentication Modal */}
        <LoginModal
          open={!token}
          onLogin={handleLogin}
          error={loginError}
          loading={loginLoading}
        />

        {/* BUG-6 FIX: Forced Password Change Dialog — blocks app access until completed */}
        <Dialog open={!!token && mustChangePassword} fullWidth maxWidth="xs" disableEscapeKeyDown>
          <DialogTitle sx={{ bgcolor: 'background.paper', color: 'text.primary', borderBottom: '1px solid', borderColor: 'divider' }}>
            🔐 Password Change Required
          </DialogTitle>
          <DialogContent sx={{ bgcolor: 'background.paper', color: 'text.primary', pt: 3 }}>
            <Typography variant="body2" sx={{ mb: 2, color: 'text.secondary' }}>
              Your account requires a password change before you can access the system.
            </Typography>
            {forcePwdError && <Alert severity="error" sx={{ mb: 2 }}>{forcePwdError}</Alert>}
            <TextField
              fullWidth label="Current Password" type="password"
              value={forcePwdCurrentInput}
              onChange={e => setForcePwdCurrentInput(e.target.value)}
              sx={{ mb: 2 }}
            />
            <TextField
              fullWidth label="New Password" type="password"
              value={forcePwdNewInput}
              onChange={e => setForcePwdNewInput(e.target.value)}
              helperText="Min 8 chars, must include upper, lower, and a digit."
            />
          </DialogContent>
          <DialogActions sx={{ bgcolor: 'background.paper', borderTop: '1px solid', borderColor: 'divider', p: 2, gap: 1 }}>
            <Button onClick={handleLogout} variant="outlined" color="error">Cancel & Logout</Button>
            <Button
              onClick={handleForcedPasswordChange}
              variant="contained"
              disabled={forcePwdLoading || !forcePwdCurrentInput || !forcePwdNewInput}
              sx={{ fontWeight: 700 }}
            >
              {forcePwdLoading ? 'Changing...' : 'Change Password'}
            </Button>
          </DialogActions>
        </Dialog>
      </Box>
    </ThemeProvider>
  );
}
