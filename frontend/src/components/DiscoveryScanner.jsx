import React, { useState } from 'react';
import {
  Box, Typography, Grid, Paper, TextField, Button, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Alert, CircularProgress
} from '@mui/material';
import NetworkWifiIcon from '@mui/icons-material/NetworkWifi';
import AddIcon from '@mui/icons-material/Add';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import LockIcon from '@mui/icons-material/Lock';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutlineOutlined';

export default function DiscoveryScanner({ token }) {
  const [scanning, setScanning] = useState(false);
  const [discovered, setDiscovered] = useState([]);
  const [registeredList, setRegisteredList] = useState({});
  const [registering, setRegistering] = useState({});
  const [errorMsg, setErrorMsg] = useState('');

  const [onvifUser, setOnvifUser] = useState('');
  const [onvifPass, setOnvifPass] = useState('');

  const [resolvedUrls, setResolvedUrls] = useState({});
  const [resolving, setResolving] = useState({});

  const triggerScan = () => {
    setScanning(true);
    setDiscovered([]);
    setRegisteredList({});
    setResolvedUrls({});
    setErrorMsg('');

    fetch('/api/cameras/scan', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(async res => {
        if (!res.ok) {
          const body = await res.json().catch(() => ({ detail: "ONVIF scan failed" }));
          throw new Error(body.detail || "ONVIF scan failed");
        }
        return res.json();
      })
      .then(data => {
        setDiscovered(data.devices || []);
        setScanning(false);
      })
      .catch(err => {
        console.error("ONVIF scan failed:", err);
        setScanning(false);
        setErrorMsg(err.message);
      });
  };

  const handleResolveStreamUri = async (device, index) => {
    if (resolving[index]) return;
    if (!onvifUser || !onvifPass) {
      setErrorMsg("Enter ONVIF credentials first to resolve stream URI.");
      return;
    }
    setResolving(prev => ({ ...prev, [index]: true }));
    setErrorMsg('');

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
      if (!res.ok) throw new Error(data.detail || "Failed to resolve stream URI");
      setResolvedUrls(prev => ({ ...prev, [index]: data.stream_url }));
    } catch (err) {
      setErrorMsg(`Stream resolve failed for ${device.ip}: ${err.message}`);
    } finally {
      setResolving(prev => ({ ...prev, [index]: false }));
    }
  };

  const handleRegisterDiscovered = (device, index) => {
    if (registering[index]) return;
    setRegistering(prev => ({ ...prev, [index]: true }));

    const streamUrl = resolvedUrls[index];
    if (!streamUrl) {
      setErrorMsg(`Resolve the stream URI for ${device.ip} before registering.`);
      setRegistering(prev => ({ ...prev, [index]: false }));
      return;
    }

    const camId = 'cam_onvif_' + device.ip.replace(/\./g, '_');
    const payload = {
      id: camId,
      name: device.name,
      location: `ONVIF Junction ${device.ip}`,
      stream_url: streamUrl,
      onvif_ip: device.ip,
      onvif_port: device.port || 80,
      onvif_username: onvifUser || null,
      onvif_password: onvifPass || null,
      status: "online"
    };

    fetch('/api/cameras', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify(payload)
    })
      .then(res => {
        if (!res.ok) throw new Error("ONVIF registration failed");
        return res.json();
      })
      .then(() => {
        setRegisteredList(prev => ({ ...prev, [index]: true }));
        setRegistering(prev => ({ ...prev, [index]: false }));
      })
      .catch(err => {
        alert(err.message);
        setRegistering(prev => ({ ...prev, [index]: false }));
      });
  };

  return (
    <Box sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
        <Typography variant="h6" fontWeight="bold">ONVIF Access Point Scanner</Typography>
        <Typography variant="caption" color="text.secondary">Multicast Discovery Block</Typography>
      </Box>

      <Grid container spacing={3} sx={{ flexGrow: 1, minHeight: 0 }}>
        <Grid item xs={12} md={4} sx={{ height: '100%' }}>
          <Paper variant="outlined" sx={{ p: 2, height: '100%', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 2 }}>
            <Typography variant="subtitle2" fontWeight="bold" sx={{ borderBottom: '1px solid', borderColor: 'divider', pb: 1 }}>
              SCAN TRIGGER PANEL
            </Typography>

            <Typography variant="body2" color="text.secondary">
              Multicasts WS-Discovery probe messages to subnet address <strong>239.255.255.250:3702</strong> to query ONVIF metadata.
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Identifies video encoder address configurations (XAddr) automatically.
            </Typography>

            <Button
              variant="contained"
              onClick={triggerScan}
              disabled={scanning}
              startIcon={scanning ? <CircularProgress size={20} color="inherit" /> : <NetworkWifiIcon />}
              fullWidth
              sx={{ py: 1 }}
            >
              {scanning ? 'BROADCASTING WS PROBE...' : 'START NETWORK SCAN'}
            </Button>

            <Box sx={{ borderTop: '1px solid', borderColor: 'divider', pt: 2, mt: 1, display: 'flex', flexDirection: 'column', gap: 2 }}>
              <Typography variant="subtitle2" fontWeight="bold" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <LockIcon fontSize="small" /> ONVIF CREDENTIALS
              </Typography>
              <TextField
                label="Username"
                size="small"
                value={onvifUser}
                onChange={e => setOnvifUser(e.target.value)}
                placeholder="admin"
              />
              <TextField
                label="Password"
                type="password"
                size="small"
                value={onvifPass}
                onChange={e => setOnvifPass(e.target.value)}
                placeholder="••••••••"
              />
              <Typography variant="caption" color="text.secondary">
                Required to resolve actual RTSP stream URI from discovered devices.
              </Typography>
            </Box>

            {errorMsg && (
              <Alert severity="error" icon={<ErrorOutlineIcon />}>
                <strong>PROBE_SCAN_FAILED:</strong> {errorMsg}
              </Alert>
            )}
          </Paper>
        </Grid>

        <Grid item xs={12} md={8} sx={{ height: '100%' }}>
          <Paper variant="outlined" sx={{ p: 2, height: '100%', display: 'flex', flexDirection: 'column' }}>
            <Typography variant="subtitle2" fontWeight="bold" sx={{ mb: 2, borderBottom: '1px solid', borderColor: 'divider', pb: 1 }}>
              DISCOVERED IP DEVICES
            </Typography>

            <TableContainer sx={{ flexGrow: 1, overflowY: 'auto' }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ fontWeight: 'bold' }}>DEVICE IP</TableCell>
                    <TableCell sx={{ fontWeight: 'bold' }}>ONVIF MODEL</TableCell>
                    <TableCell sx={{ fontWeight: 'bold' }}>XADDR / RTSP ENDPOINT</TableCell>
                    <TableCell align="center" sx={{ fontWeight: 'bold' }}>ACTION</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {scanning ? (
                    <TableRow>
                      <TableCell colSpan={4} align="center" sx={{ py: 6, color: 'text.secondary' }}>SCANNING SUBNET IP RANGE...</TableCell>
                    </TableRow>
                  ) : discovered.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={4} align="center" sx={{ py: 6, color: 'text.secondary' }}>[ STANDBY // TRIGGER DISCOVERY PROBE ]</TableCell>
                    </TableRow>
                  ) : (
                    discovered.map((dev, idx) => {
                      const isRegistered = registeredList[idx];
                      const rtspUrl = resolvedUrls[idx];
                      return (
                        <TableRow key={idx} hover>
                          <TableCell>{dev.ip}</TableCell>
                          <TableCell>{dev.name.toUpperCase()}</TableCell>
                          <TableCell sx={{ fontFamily: 'monospace' }}>
                            {rtspUrl ? (
                              <Typography variant="caption" color="success.main" fontWeight="bold">{rtspUrl}</Typography>
                            ) : (
                              <Typography variant="caption" color="text.secondary">{dev.xaddr}</Typography>
                            )}
                          </TableCell>
                          <TableCell align="center">
                            {isRegistered ? (
                              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 1, color: 'text.primary' }}>
                                <CheckCircleIcon fontSize="small" />
                                <Typography variant="caption" fontWeight="bold">LINKED</Typography>
                              </Box>
                            ) : rtspUrl ? (
                              <Button
                                size="small"
                                variant="outlined"
                                disabled={registering[idx]}
                                onClick={() => handleRegisterDiscovered(dev, idx)}
                                startIcon={<AddIcon />}
                              >
                                {registering[idx] ? "LINKING..." : "REGISTER"}
                              </Button>
                            ) : (
                              <Button
                                size="small"
                                variant="outlined"
                                disabled={resolving[idx]}
                                onClick={() => handleResolveStreamUri(dev, idx)}
                                startIcon={<LockIcon />}
                                color="secondary"
                              >
                                {resolving[idx] ? "RESOLVING..." : "GET RTSP"}
                              </Button>
                            )}
                          </TableCell>
                        </TableRow>
                      );
                    })
                  )}
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>
        </Grid>
      </Grid>
    </Box>
  );
}