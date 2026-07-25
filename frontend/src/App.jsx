import React, { useState, useEffect, useMemo } from 'react';
import {
  Box, Drawer, List, ListItem, ListItemButton, ListItemIcon, ListItemText,
  AppBar, Toolbar, Typography, Button, Snackbar, Alert, Chip, Menu, MenuItem,
  Divider, TextField, InputAdornment, IconButton, useMediaQuery
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

const drawerWidth = 240;

export default function App() {
  const [activeTab, setActiveTab] = useState('live');
  const [token, setToken] = useState(localStorage.getItem('vms_token') || '');
  const [role, setRole] = useState(localStorage.getItem('vms_role') || 'admin');
  const [username, setUsername] = useState(localStorage.getItem('vms_username') || 'admin');

  const [wsAlert, setWsAlert] = useState(null);
  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [anchorEl, setAnchorEl] = useState(null);
  const [mobileOpen, setMobileOpen] = useState(false);

  // Global Search State
  const [globalSearchQuery, setGlobalSearchQuery] = useState('');

  // Customizable Settings State
  const [settings, setSettings] = useState(() => {
    try {
      const saved = localStorage.getItem('sybau_ui_settings');
      if (saved) return JSON.parse(saved);
    } catch (e) {}
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

  // Shared ONVIF Scan States
  const [scanning, setScanning] = useState(false);
  const [discovered, setDiscovered] = useState([]);
  const [resolvedUrls, setResolvedUrls] = useState({});

  // Responsive breakpoint checkers
  const isMdUp = useMediaQuery(activeTheme.breakpoints.up('md'));

  // Validate stored token on mount
  useEffect(() => {
    if (!token) return;
    fetch('/api/cameras', {
      headers: { 'Authorization': `Bearer ${token}` }
    }).then(res => {
      if (res.status === 401) {
        console.warn('[Auth] Stored token is invalid/expired — clearing for re-login');
        localStorage.removeItem('vms_token');
        localStorage.removeItem('vms_role');
        localStorage.removeItem('vms_username');
        setToken('');
      }
    }).catch(() => {});
  }, []);

  // Auto login with default credentials if no token exists
  useEffect(() => {
    if (!token) {
      handleLogin('admin', 'Admin@123456');
    }
  }, [token]);

  // Load Admin Data when authenticated
  const loadAdminData = () => {
    if (!token || role !== 'admin') return;

    // Load users
    fetch('/api/admin/users?include_deleted=true', {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(res => res.json())
      .then(data => {
        if (Array.isArray(data)) setUsersList(data);
      })
      .catch(() => {});

    // Load elevation requests
    fetch('/api/admin/elevation-requests', {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(res => res.json())
      .then(data => {
        if (Array.isArray(data)) setRequests(data);
      })
      .catch(() => {});
  };

  useEffect(() => {
    loadAdminData();
  }, [token, role]);

  // Establish WebSocket for alerts
  useEffect(() => {
    if (!token) return;

    let ws = null;
    let reconnectDelay = 1000;
    const MAX_RECONNECT_DELAY = 30000;
    let destroyed = false;

    // Dual-Tone alarm synthesizer simulator
    const playConsoleAlarm = () => {
      if (!settings.soundEnabled) return;
      try {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        
        // Tone 1
        const osc1 = audioCtx.createOscillator();
        const gain1 = audioCtx.createGain();
        osc1.type = 'square';
        osc1.frequency.setValueAtTime(880, audioCtx.currentTime);
        gain1.gain.setValueAtTime(0.1, audioCtx.currentTime);
        gain1.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.1);
        osc1.connect(gain1);
        gain1.connect(audioCtx.destination);
        osc1.start();
        osc1.stop(audioCtx.currentTime + 0.1);

        // Tone 2
        setTimeout(() => {
          const osc2 = audioCtx.createOscillator();
          const gain2 = audioCtx.createGain();
          osc2.type = 'square';
          osc2.frequency.setValueAtTime(660, audioCtx.currentTime);
          gain2.gain.setValueAtTime(0.08, audioCtx.currentTime);
          gain2.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.15);
          osc2.connect(gain2);
          gain2.connect(audioCtx.destination);
          osc2.start();
          osc2.stop(audioCtx.currentTime + 0.15);
        }, 80);
      } catch (e) {
        console.warn('Audio synthesis block:', e);
      }
    };

    function connect() {
      if (destroyed) return;

      const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      ws = new WebSocket(`${wsProtocol}//${window.location.host}/ws/alerts`);

      ws.onopen = () => {
        reconnectDelay = 1000;
      };

      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.topic === 'alerts') {
            setWsAlert(payload.data);
            setSnackbarOpen(true);

            if (payload.data.type === 'POI_MATCH') {
              playConsoleAlarm();
            }
          }
        } catch (err) {
          console.error('[WS] Event decode error:', err);
        }
      };

      ws.onclose = () => {
        if (destroyed) return;
        setTimeout(connect, reconnectDelay);
        reconnectDelay = Math.min(reconnectDelay * 2, MAX_RECONNECT_DELAY);
      };
    }

    connect();

    return () => {
      destroyed = true;
      if (ws) {
        ws.onclose = null;
        ws.close();
      }
    };
  }, [token, settings.soundEnabled]);

  const handleLogin = async (uname, pwd, retryCount = 0) => {
    try {
      const formData = new URLSearchParams();
      formData.append('username', uname);
      formData.append('password', pwd);

      const res = await fetch('/api/auth/login', {
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
      } else {
        if (retryCount < 6) {
          console.warn(`[Auth] Login failed. Retrying in 2s (Attempt ${retryCount + 1}/6)...`);
          setTimeout(() => handleLogin(uname, pwd, retryCount + 1), 2000);
        } else {
          alert("Authentication failed! Verify that backend service is running.");
        }
      }
    } catch (e) {
      console.error(e);
      if (retryCount < 6) {
        console.warn(`[Auth] Connection failed. Retrying in 2s (Attempt ${retryCount + 1}/6)...`);
        setTimeout(() => handleLogin(uname, pwd, retryCount + 1), 2000);
      }
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('vms_token');
    localStorage.removeItem('vms_role');
    localStorage.removeItem('vms_username');
    setToken('');
    setRole('viewer');
    setUsername('');
    setAnchorEl(null);
  };

  const handleRoleSwitch = (targetRole) => {
    const passwordMap = { admin: 'Admin@123456', operator: 'Operator@123456', viewer: 'Viewer@123456' };
    handleLogin(targetRole, passwordMap[targetRole]);
    setAnchorEl(null);
  };

  // Admin Console actions mapped from Settings page
  const handleUpdateRole = (userId, newRole) => {
    fetch(`/api/admin/users/${userId}`, {
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
    fetch(`/api/admin/users/${userId}`, {
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
    fetch(`/api/admin/users/${userId}`, {
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
    fetch(`/api/admin/users/${userId}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}` }
    }).then(res => {
      if (res.ok) loadAdminData();
    });
  };

  const handleHardDelete = (userId, adminPass) => {
    fetch(`/api/admin/users/${userId}/hard-delete`, {
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
    fetch(`/api/admin/elevation-requests/${reqId}/resolve`, {
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

    fetch('/api/cameras/scan', {
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
      const res = await fetch('/api/cameras/resolve-onvif', {
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
    } catch (e) {
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
      <Box sx={{ p: 2, borderTop: '1px solid', borderColor: 'divider', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Typography variant="caption" color="text.secondary">SYBAU SECURE CONSOLE v1.1</Typography>
      </Box>
    </Box>
  );

  return (
    <ThemeProvider theme={activeTheme}>
      <CssBaseline />
      <Box sx={{ display: 'flex', minHeight: '100vh', backgroundColor: 'background.default' }}>
        {/* Top Navbar */}
        <AppBar position="fixed" sx={{ zIndex: (theme) => theme.zIndex.drawer + 1, backdropFilter: 'blur(10px)' }}>
          <Toolbar sx={{ justifyContent: 'space-between' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              {!isMdUp && (
                <IconButton color="inherit" onClick={() => setMobileOpen(!mobileOpen)} sx={{ mr: 1 }}>
                  <MenuIcon />
                </IconButton>
              )}
              <Typography variant="h6" noWrap component="div" sx={{ fontWeight: 'bold', letterSpacing: '0.5px' }}>
                SYBAU <span style={{ color: activeTheme.palette.text.secondary }}>VMS</span>
              </Typography>
            </Box>

            {/* Global Search Box */}
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
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
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
                <MenuItem disabled><Typography variant="caption">RBAC Quick-Switch Controls</Typography></MenuItem>
                <MenuItem onClick={() => handleRoleSwitch('admin')}>Admin Console Link</MenuItem>
                <MenuItem onClick={() => handleRoleSwitch('operator')}>Operator Terminal</MenuItem>
                <MenuItem onClick={() => handleRoleSwitch('viewer')}>Viewer Feed Mode</MenuItem>
                <Divider />
                <MenuItem onClick={handleLogout}>Sign Out Link</MenuItem>
              </Menu>
            </Box>
          </Toolbar>
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
      </Box>
    </ThemeProvider>
  );
}