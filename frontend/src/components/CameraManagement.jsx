import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  IconButton, Button, Dialog, DialogTitle, DialogContent, DialogActions, TextField, Alert, Chip, CircularProgress
} from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import VideocamIcon from '@mui/icons-material/Videocam';
import RefreshIcon from '@mui/icons-material/Refresh';

export default function CameraManagement({ token }) {
  const [cameras, setCameras] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // Dialog State
  const [openDialog, setOpenDialog] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [formData, setFormData] = useState({ id: '', name: '', location: '', stream_url: '', width: 1920, height: 1080 });

  const fetchCameras = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/v1/cameras', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (!res.ok) throw new Error('Failed to fetch cameras');
      const data = await res.json();
      setCameras(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    if (token) fetchCameras();
  }, [token, fetchCameras]);

  const handleOpenAdd = () => {
    setFormData({ id: '', name: '', location: '', stream_url: '', width: 1920, height: 1080 });
    setIsEditing(false);
    setOpenDialog(true);
    setError(null);
    setSuccess(null);
  };

  const handleOpenEdit = (cam) => {
    setFormData({ ...cam });
    setIsEditing(true);
    setOpenDialog(true);
    setError(null);
    setSuccess(null);
  };

  const handleCloseDialog = () => {
    setOpenDialog(false);
  };

  const handleSubmit = async () => {
    try {
      const method = isEditing ? 'PUT' : 'POST';
      const url = isEditing ? `/api/v1/cameras/${formData.id}` : '/api/v1/cameras';
      
      const res = await fetch(url, {
        method,
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(formData)
      });
      
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Operation failed');
      
      setSuccess(`Camera ${isEditing ? 'updated' : 'added'} successfully.`);
      setOpenDialog(false);
      fetchCameras();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Are you sure you want to delete this camera? This will tear down its active streams.')) return;
    try {
      const res = await fetch(`/api/v1/cameras/${id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (!res.ok) throw new Error('Failed to delete camera');
      setSuccess('Camera deleted successfully.');
      fetchCameras();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <Box>
          <Typography variant="subtitle1" fontWeight="bold">Camera Management</Typography>
          <Typography variant="caption" color="text.secondary">Add, edit, and manage surveillance camera feeds in real-time.</Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button variant="outlined" startIcon={<RefreshIcon />} onClick={fetchCameras} disabled={loading}>Refresh</Button>
          <Button variant="contained" startIcon={<VideocamIcon />} onClick={handleOpenAdd}>Add Camera</Button>
        </Box>
      </Box>

      {error && <Alert severity="error" onClose={() => setError(null)}>{error}</Alert>}
      {success && <Alert severity="success" onClose={() => setSuccess(null)}>{success}</Alert>}

      <Paper variant="outlined" sx={{ overflow: 'hidden' }}>
        <TableContainer>
          <Table size="small">
            <TableHead sx={{ backgroundColor: 'action.hover' }}>
              <TableRow>
                <TableCell sx={{ fontWeight: 'bold' }}>ID</TableCell>
                <TableCell sx={{ fontWeight: 'bold' }}>Name</TableCell>
                <TableCell sx={{ fontWeight: 'bold' }}>Location</TableCell>
                <TableCell sx={{ fontWeight: 'bold' }}>Status</TableCell>
                <TableCell sx={{ fontWeight: 'bold' }} align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {loading && cameras.length === 0 ? (
                <TableRow><TableCell colSpan={5} align="center"><CircularProgress size={24} sx={{ my: 2 }} /></TableCell></TableRow>
              ) : cameras.length === 0 ? (
                <TableRow><TableCell colSpan={5} align="center" sx={{ py: 3, color: 'text.secondary' }}>No cameras configured.</TableCell></TableRow>
              ) : (
                cameras.map((cam) => (
                  <TableRow key={cam.id} hover>
                    <TableCell sx={{ fontFamily: 'monospace' }}>{cam.id}</TableCell>
                    <TableCell>{cam.name}</TableCell>
                    <TableCell>{cam.location}</TableCell>
                    <TableCell>
                      <Chip label={cam.status ? cam.status.toUpperCase() : 'UNKNOWN'} size="small" color={cam.status === 'online' ? 'success' : (cam.status === 'failed' ? 'error' : 'warning')} />
                    </TableCell>
                    <TableCell align="right">
                      <IconButton size="small" color="primary" onClick={() => handleOpenEdit(cam)}>
                        <EditIcon fontSize="small" />
                      </IconButton>
                      <IconButton size="small" color="error" onClick={() => handleDelete(cam.id)}>
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>

      {/* Add / Edit Dialog */}
      <Dialog open={openDialog} onClose={handleCloseDialog} maxWidth="sm" fullWidth>
        <DialogTitle>{isEditing ? 'Edit Camera' : 'Add New Camera'}</DialogTitle>
        <DialogContent dividers sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <TextField 
            label="Camera ID" 
            size="small" 
            fullWidth 
            value={formData.id} 
            onChange={(e) => setFormData({ ...formData, id: e.target.value })} 
            disabled={isEditing} 
            required 
            placeholder="e.g. cam_01"
          />
          <TextField 
            label="Name" 
            size="small" 
            fullWidth 
            value={formData.name} 
            onChange={(e) => setFormData({ ...formData, name: e.target.value })} 
            required 
          />
          <TextField 
            label="Location" 
            size="small" 
            fullWidth 
            value={formData.location} 
            onChange={(e) => setFormData({ ...formData, location: e.target.value })} 
          />
          <TextField 
            label="Stream URL (HLS / YouTube / RTSP)" 
            size="small" 
            fullWidth 
            value={formData.stream_url} 
            onChange={(e) => setFormData({ ...formData, stream_url: e.target.value })} 
            required 
          />
          <Box sx={{ display: 'flex', gap: 2 }}>
            <TextField 
              label="Width" 
              type="number" 
              size="small" 
              fullWidth 
              value={formData.width} 
              onChange={(e) => setFormData({ ...formData, width: parseInt(e.target.value) })} 
            />
            <TextField 
              label="Height" 
              type="number" 
              size="small" 
              fullWidth 
              value={formData.height} 
              onChange={(e) => setFormData({ ...formData, height: parseInt(e.target.value) })} 
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDialog} color="inherit">Cancel</Button>
          <Button onClick={handleSubmit} variant="contained" disabled={!formData.id || !formData.name || !formData.stream_url}>
            {isEditing ? 'Save Changes' : 'Add Camera'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
