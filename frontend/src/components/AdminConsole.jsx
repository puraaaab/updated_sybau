import React, { useEffect, useState, useCallback } from 'react';
import {
  Box, Typography, Grid, Paper, Tabs, Tab, TextField, Button, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Select, MenuItem, InputLabel, FormControl, IconButton, Alert, Chip, Dialog, DialogTitle, DialogContent, DialogActions
} from '@mui/material';
import PeopleIcon from '@mui/icons-material/People';
import VpnKeyIcon from '@mui/icons-material/VpnKey';
import AssignmentIcon from '@mui/icons-material/Assignment';
import DeleteIcon from '@mui/icons-material/Delete';
import RefreshIcon from '@mui/icons-material/Refresh';
import CheckIcon from '@mui/icons-material/Check';
import CloseIcon from '@mui/icons-material/Close';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';

export default function AdminConsole({ token }) {
  const [activeSubTab, setActiveSubTab] = useState(0);
  
  // Users States
  const [usersList, setUsersList] = useState([]);
  const [usernameInput, setUsernameInput] = useState('');
  const [passwordInput, setPasswordInput] = useState('');
  const [roleInput, setRoleInput] = useState('viewer');
  const [userError, setUserError] = useState('');
  const [userSuccess, setUserSuccess] = useState('');
  const [editingUser, setEditingUser] = useState(null);
  const [resetPwdText, setResetPwdText] = useState('');
  const [showDangerZoneId, setShowDangerZoneId] = useState(null);
  const [confirmAdminPassword, setConfirmAdminPassword] = useState('');

  // Elevation Requests States
  const [requests, setRequests] = useState([]);
  const [reqError, setReqError] = useState('');
  const [activeResetToken, setActiveResetToken] = useState(null);
  const [activeResetUser, setActiveResetUser] = useState('');

  // Audit Logs States
  const [logs, setLogs] = useState([]);
  const [filterUser, setFilterUser] = useState('');
  const [filterAction, setFilterAction] = useState('');
  const [filterStart, setFilterStart] = useState('');
  const [filterEnd, setFilterEnd] = useState('');
  const [logsError, setLogsError] = useState('');

  const loadUsers = useCallback(() => {
    setUserError('');
    fetch('/api/admin/users?include_deleted=true', {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(res => {
        if (!res.ok) throw new Error("Failed to load user accounts list");
        return res.json();
      })
      .then(data => setUsersList(data))
      .catch(err => setUserError(err.message));
  }, [token]);

  const loadRequests = useCallback(() => {
    setReqError('');
    fetch('/api/admin/elevation-requests', {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(res => {
        if (!res.ok) throw new Error("Failed to load elevation requests queue");
        return res.json();
      })
      .then(data => setRequests(data))
      .catch(err => setReqError(err.message));
  }, [token]);

  const loadLogs = useCallback(() => {
    setLogsError('');
    let url = '/api/admin/audit-logs';
    const params = [];
    if (filterUser) params.push(`username=${encodeURIComponent(filterUser)}`);
    if (filterAction) params.push(`action=${encodeURIComponent(filterAction)}`);
    if (filterStart) params.push(`start=${encodeURIComponent(filterStart)}`);
    if (filterEnd) params.push(`end=${encodeURIComponent(filterEnd)}`);
    if (params.length > 0) url += `?${params.join('&')}`;

    fetch(url, {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(res => {
        if (!res.ok) throw new Error("Failed to query audit logbook");
        return res.json();
      })
      .then(data => setLogs(data))
      .catch(err => setLogsError(err.message));
  }, [token, filterUser, filterAction, filterStart, filterEnd]);

  useEffect(() => {
    if (!token) return;
    loadUsers();
    loadRequests();
    loadLogs();
  }, [token, activeSubTab, loadUsers, loadRequests, loadLogs]);

  const handleCreateUser = (e) => {
    e.preventDefault();
    setUserError('');
    setUserSuccess('');

    fetch('/api/admin/users', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({ username: usernameInput, password: passwordInput, role: roleInput })
    })
      .then(async res => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "User creation failed");
        return data;
      })
      .then(() => {
        setUserSuccess(`User ${usernameInput} successfully created.`);
        setUsernameInput('');
        setPasswordInput('');
        setRoleInput('viewer');
        loadUsers();
      })
      .catch(err => setUserError(err.message));
  };

  const handleUpdateStatus = (userId, newStatus) => {
    setUserError('');
    fetch(`/api/admin/users/${userId}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({ status: newStatus })
    })
      .then(async res => {
        if (!res.ok) {
          const data = await res.json();
          throw new Error(data.detail || "Update status failed");
        }
        loadUsers();
      })
      .catch(err => setUserError(err.message));
  };

  const handleUpdateRole = (userId, newRole) => {
    setUserError('');
    fetch(`/api/admin/users/${userId}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({ role: newRole })
    })
      .then(async res => {
        if (!res.ok) {
          const data = await res.json();
          throw new Error(data.detail || "Update role failed");
        }
        loadUsers();
      })
      .catch(err => setUserError(err.message));
  };

  const handleResetPassword = (userId) => {
    setUserError('');
    setUserSuccess('');
    if (!resetPwdText) {
      setUserError("Must specify a new password.");
      return;
    }

    fetch(`/api/admin/users/${userId}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({ password: resetPwdText })
    })
      .then(async res => {
        if (!res.ok) {
          const data = await res.json();
          throw new Error(data.detail || "Password reset failed");
        }
        setUserSuccess("Password successfully reset. User will be forced to change it on next login.");
        setResetPwdText('');
        setEditingUser(null);
        loadUsers();
      })
      .catch(err => setUserError(err.message));
  };

  const handleSoftDelete = (userId) => {
    setUserError('');
    fetch(`/api/admin/users/${userId}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(async res => {
        if (!res.ok) {
          const data = await res.json();
          throw new Error(data.detail || "Deletion failed");
        }
        loadUsers();
      })
      .catch(err => setUserError(err.message));
  };

  const handleHardDelete = (userId) => {
    setUserError('');
    if (!confirmAdminPassword) {
      setUserError("Must re-enter your admin password for permanent erasure.");
      return;
    }

    fetch(`/api/admin/users/${userId}/hard-delete`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({ admin_password: confirmAdminPassword })
    })
      .then(async res => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Hard deletion failed");
        return data;
      })
      .then(() => {
        setUserSuccess("Row permanently erased from database.");
        setConfirmAdminPassword('');
        setShowDangerZoneId(null);
        loadUsers();
      })
      .catch(err => setUserError(err.message));
  };

  const handleResolveRequest = (reqId, requesterName, action) => {
    setReqError('');
    setActiveResetToken(null);

    fetch(`/api/admin/elevation-requests/${reqId}/resolve`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({ action })
    })
      .then(async res => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Resolution failed");
        return data;
      })
      .then(data => {
        if (data.reset_token) {
          setActiveResetToken(data.reset_token);
          setActiveResetUser(requesterName);
        }
        loadRequests();
      })
      .catch(err => setReqError(err.message));
  };

  return (
    <Box sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}>
        <Tabs value={activeSubTab} onChange={(e, v) => setActiveSubTab(v)} aria-label="admin tabs">
          <Tab icon={<PeopleIcon />} iconPosition="start" label="Directory Accounts" />
          <Tab icon={<VpnKeyIcon />} iconPosition="start" label="Elevation Queue" />
          <Tab icon={<AssignmentIcon />} iconPosition="start" label="Security Audit Logs" />
        </Tabs>
      </Box>

      {/* Directory Accounts workspace */}
      {activeSubTab === 0 && (
        <Grid container spacing={3} sx={{ flexGrow: 1, minHeight: 0 }}>
          <Grid item xs={12} md={4}>
            <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
              <Typography variant="subtitle2" fontWeight="bold" sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 1, borderBottom: '1px solid', borderColor: 'divider', pb: 1 }}>
                <PeopleIcon fontSize="small" /> CREATE SYSTEM ACCOUNT
              </Typography>

              <Box component="form" onSubmit={handleCreateUser} sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                <TextField label="User Classification" size="small" required value={usernameInput} onChange={(e) => setUsernameInput(e.target.value)} placeholder="e.g. j_miller" />
                <TextField label="Initial Password" type="password" size="small" required value={passwordInput} onChange={(e) => setPasswordInput(e.target.value)} placeholder="••••••••" />
                <FormControl size="small">
                  <InputLabel id="role-select-label">Assigned RBAC Role</InputLabel>
                  <Select labelId="role-select-label" value={roleInput} label="Assigned RBAC Role" onChange={(e) => setRoleInput(e.target.value)}>
                    <MenuItem value="viewer">VIEWER (READ-ONLY LIVE)</MenuItem>
                    <MenuItem value="operator">OPERATOR (LIVE, PLAYBACK, FORENSICS)</MenuItem>
                    <MenuItem value="auditor">AUDITOR (EXPORTS & AUDITS ONLY)</MenuItem>
                    <MenuItem value="admin">ADMINISTRATOR (FULL SECURE PRIVILEGES)</MenuItem>
                  </Select>
                </FormControl>

                {userError && <Alert severity="error" sx={{ mt: 1 }}>{userError}</Alert>}
                {userSuccess && <Alert severity="success" sx={{ mt: 1 }}>{userSuccess}</Alert>}

                <Button type="submit" variant="contained" startIcon={<PeopleIcon />} sx={{ mt: 2 }}>
                  Commit Account
                </Button>
              </Box>
            </Paper>
          </Grid>

          <Grid item xs={12} md={8}>
            <Paper variant="outlined" sx={{ p: 2, height: '100%', display: 'flex', flexDirection: 'column' }}>
              <Typography variant="subtitle2" fontWeight="bold" sx={{ mb: 2, borderBottom: '1px solid', borderColor: 'divider', pb: 1 }}>
                DIRECTORY ACCOUNT DIRECTORY
              </Typography>

              <TableContainer sx={{ flexGrow: 1, overflowY: 'auto' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell sx={{ fontWeight: 'bold' }}>ACCOUNT</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }}>ROLE</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }}>STATUS</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }}>PWD RESET</TableCell>
                      <TableCell align="center" sx={{ fontWeight: 'bold' }}>ACTIONS</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {usersList.map((u) => (
                      <TableRow key={u.id} hover sx={{ opacity: u.deleted_at ? 0.5 : 1 }}>
                        <TableCell sx={{ fontWeight: 'bold' }}>
                          {u.username} {u.deleted_at && <Typography component="span" variant="caption" color="error"> (DELETED)</Typography>}
                        </TableCell>
                        <TableCell>
                          <Select
                            value={u.role}
                            disabled={!!u.deleted_at}
                            onChange={(e) => handleUpdateRole(u.id, e.target.value)}
                            size="small"
                            variant="standard"
                          >
                            <MenuItem value="viewer">VIEWER</MenuItem>
                            <MenuItem value="operator">OPERATOR</MenuItem>
                            <MenuItem value="auditor">AUDITOR</MenuItem>
                            <MenuItem value="admin">ADMIN</MenuItem>
                          </Select>
                        </TableCell>
                        <TableCell>
                          <Select
                            value={u.status}
                            disabled={!!u.deleted_at}
                            onChange={(e) => handleUpdateStatus(u.id, e.target.value)}
                            size="small"
                            variant="standard"
                            sx={{ color: u.status === 'active' ? 'success.main' : 'error.main', fontWeight: 'bold' }}
                          >
                            <MenuItem value="active">ACTIVE</MenuItem>
                            <MenuItem value="suspended">SUSPENDED</MenuItem>
                            <MenuItem value="disabled">DISABLED</MenuItem>
                          </Select>
                        </TableCell>
                        <TableCell>{u.must_change_password ? 'YES' : 'CLEARED'}</TableCell>
                        <TableCell align="center">
                          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 1 }}>
                            <IconButton size="small" disabled={!!u.deleted_at} onClick={() => setEditingUser(editingUser === u.id ? null : u.id)} title="Reset Password">
                              <RefreshIcon fontSize="small" />
                            </IconButton>
                            {!u.deleted_at && (
                              <IconButton size="small" color="error" onClick={() => handleSoftDelete(u.id)} title="Soft Delete">
                                <DeleteIcon fontSize="small" />
                              </IconButton>
                            )}
                            <IconButton size="small" color="warning" onClick={() => setShowDangerZoneId(showDangerZoneId === u.id ? null : u.id)} title="Hard Delete">
                              <WarningAmberIcon fontSize="small" />
                            </IconButton>
                          </Box>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>

              {/* Password Reset Dialog */}
              <Dialog open={Boolean(editingUser)} onClose={() => setEditingUser(null)}>
                <DialogTitle>Reset Password</DialogTitle>
                <DialogContent>
                  <TextField
                    label="New Secure Password"
                    type="password"
                    fullWidth
                    variant="outlined"
                    size="small"
                    value={resetPwdText}
                    onChange={(e) => setResetPwdText(e.target.value)}
                    sx={{ mt: 1 }}
                  />
                </DialogContent>
                <DialogActions>
                  <Button onClick={() => setEditingUser(null)}>Cancel</Button>
                  <Button onClick={() => handleResetPassword(editingUser)} variant="contained" startIcon={<CheckIcon />}>Confirm Reset</Button>
                </DialogActions>
              </Dialog>

              {/* Danger Zone Dialog */}
              <Dialog open={Boolean(showDangerZoneId)} onClose={() => setShowDangerZoneId(null)}>
                <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1, color: 'error.main' }}>
                  <WarningAmberIcon /> Danger Zone: Permanent Erasure
                </DialogTitle>
                <DialogContent>
                  <Typography variant="body2" sx={{ mb: 2 }}>
                    This action will permanently remove the user from the database. Please enter your admin password to confirm.
                  </Typography>
                  <TextField
                    label="Admin Confirmation Password"
                    type="password"
                    fullWidth
                    variant="outlined"
                    size="small"
                    value={confirmAdminPassword}
                    onChange={(e) => setConfirmAdminPassword(e.target.value)}
                  />
                </DialogContent>
                <DialogActions>
                  <Button onClick={() => setShowDangerZoneId(null)}>Cancel</Button>
                  <Button onClick={() => handleHardDelete(showDangerZoneId)} variant="contained" color="error">Erase Row</Button>
                </DialogActions>
              </Dialog>
            </Paper>
          </Grid>
        </Grid>
      )}

      {/* Elevation Requests workspace */}
      {activeSubTab === 1 && (
        <Paper variant="outlined" sx={{ p: 2, display: 'flex', flexDirection: 'column', flexGrow: 1 }}>
          <Typography variant="subtitle2" fontWeight="bold" sx={{ mb: 2, display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid', borderColor: 'divider', pb: 1 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}><VpnKeyIcon fontSize="small" /> OPERATIONAL ELEVATION & PASSWORD RESET REQUESTS</Box>
            <Typography variant="caption" color="text.secondary">Enforces explicit role boundaries</Typography>
          </Typography>

          {reqError && <Alert severity="error" sx={{ mb: 2 }}>{reqError}</Alert>}

          {activeResetToken && (
            <Alert severity="success" sx={{ mb: 2 }}>
              <Typography variant="subtitle2" fontWeight="bold" sx={{ mb: 1 }}>PASSWORD RESET APPROVAL SUCCESSFUL</Typography>
              <Typography variant="body2">Single-use, 15-minute token generated for user <strong>{activeResetUser}</strong>:</Typography>
              <Box sx={{ mt: 1, p: 2, backgroundColor: 'background.default', border: '1px solid', borderColor: 'divider', textAlign: 'center' }}>
                <Typography variant="h6" sx={{ fontFamily: 'monospace', letterSpacing: 2 }}>{activeResetToken}</Typography>
              </Box>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
                ⚠️ Relay this token securely to the user verbally or out-of-band. They will need it to establish a new password link.
              </Typography>
            </Alert>
          )}

          <TableContainer sx={{ flexGrow: 1, overflowY: 'auto' }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell sx={{ fontWeight: 'bold' }}>USER</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>REQUEST</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>EXPLANATION</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>SUBMITTED</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>STATUS</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>RESOLVER</TableCell>
                  <TableCell align="center" sx={{ fontWeight: 'bold' }}>ACTION</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {requests.map((r) => {
                  const isSelf = r.username === 'admin';
                  return (
                    <TableRow key={r.id} hover>
                      <TableCell sx={{ fontWeight: 'bold' }}>{r.username}</TableCell>
                      <TableCell>
                        <Chip 
                          label={r.request_type.toUpperCase().replace('_', ' ')} 
                          size="small" 
                          color={r.request_type === 'role_elevation' ? 'primary' : 'warning'} 
                        />
                      </TableCell>
                      <TableCell>{r.details || 'N/A'}</TableCell>
                      <TableCell>{r.created_at ? new Date(r.created_at).toLocaleString('en-GB') : 'N/A'}</TableCell>
                      <TableCell>
                        <Typography variant="caption" fontWeight="bold" color={r.status === 'pending' ? 'warning.main' : r.status === 'approved' ? 'success.main' : 'error.main'}>
                          {r.status.toUpperCase()}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        {r.resolved_by ? (
                          <Typography variant="caption">{r.resolved_by} ({new Date(r.resolved_at).toLocaleTimeString()})</Typography>
                        ) : 'N/A'}
                      </TableCell>
                      <TableCell align="center">
                        {r.status === 'pending' ? (
                          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 1 }}>
                            <IconButton 
                              size="small" 
                              color="success" 
                              disabled={isSelf} 
                              onClick={() => handleResolveRequest(r.id, r.username, 'approved')}
                              title={isSelf ? 'Cannot self-approve elevation requests.' : 'Approve request'}
                            >
                              <CheckIcon fontSize="small" />
                            </IconButton>
                            <IconButton 
                              size="small" 
                              color="error" 
                              disabled={isSelf} 
                              onClick={() => handleResolveRequest(r.id, r.username, 'rejected')}
                              title={isSelf ? 'Cannot self-resolve elevation requests.' : 'Reject request'}
                            >
                              <CloseIcon fontSize="small" />
                            </IconButton>
                          </Box>
                        ) : (
                          <Typography variant="caption" color="text.secondary">CLOSED</Typography>
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })}
                {requests.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={7} align="center" sx={{ py: 6, color: 'text.secondary' }}>NO ELEVATION REQUESTS REPORTED</TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>
      )}

      {/* Audit logs workspace */}
      {activeSubTab === 2 && (
        <Paper variant="outlined" sx={{ p: 2, display: 'flex', flexDirection: 'column', flexGrow: 1 }}>
          <Typography variant="subtitle2" fontWeight="bold" sx={{ mb: 2, borderBottom: '1px solid', borderColor: 'divider', pb: 1 }}>
            SECURITY EVENT LOGBOOK AUDITING
          </Typography>

          <Box sx={{ display: 'flex', gap: 2, mb: 3, flexWrap: 'wrap' }}>
            <TextField label="Username Filter" size="small" value={filterUser} onChange={(e) => setFilterUser(e.target.value)} placeholder="e.g. admin" />
            <TextField label="Action Type" size="small" value={filterAction} onChange={(e) => setFilterAction(e.target.value)} placeholder="e.g. LOGIN_FAILED" />
            <TextField label="From Date" type="datetime-local" size="small" value={filterStart} onChange={(e) => setFilterStart(e.target.value)} InputLabelProps={{ shrink: true }} />
            <TextField label="To Date" type="datetime-local" size="small" value={filterEnd} onChange={(e) => setFilterEnd(e.target.value)} InputLabelProps={{ shrink: true }} />
            <Button variant="contained" onClick={loadLogs}>Execute Query</Button>
            <Button variant="outlined" onClick={() => { setFilterUser(''); setFilterAction(''); setFilterStart(''); setFilterEnd(''); setTimeout(loadLogs, 50); }}>Reset</Button>
          </Box>

          {logsError && <Alert severity="error" sx={{ mb: 2 }}>{logsError}</Alert>}

          <TableContainer sx={{ flexGrow: 1, overflowY: 'auto' }}>
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow>
                  <TableCell sx={{ fontWeight: 'bold' }}>DATE & TIME</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>OPERATOR</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>ROLE</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>SECURITY ACTION</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>METADATA / DETAILS</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {logs.map((l) => (
                  <TableRow key={l.id} hover>
                    <TableCell>{new Date(l.timestamp).toLocaleString('en-GB')}</TableCell>
                    <TableCell sx={{ fontWeight: 'bold' }}>{l.username}</TableCell>
                    <TableCell><Typography variant="caption" color="text.secondary">{l.role.toUpperCase()}</Typography></TableCell>
                    <TableCell>
                      <Chip 
                        label={l.action} 
                        size="small" 
                        color={l.action.includes('FAILED') || l.action.includes('LOCKOUT') || l.action.includes('DELETE') ? 'error' : l.action.includes('SUCCESS') ? 'success' : 'default'}
                      />
                    </TableCell>
                    <TableCell>{l.details}</TableCell>
                  </TableRow>
                ))}
                {logs.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={5} align="center" sx={{ py: 6, color: 'text.secondary' }}>NO EVENT RECORDS RETURNED FROM DB</TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>
      )}
    </Box>
  );
}
