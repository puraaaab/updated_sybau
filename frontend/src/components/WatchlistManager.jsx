import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Box, Typography, Grid, Paper, TextField, Button, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, IconButton, Alert, Dialog, DialogTitle, DialogContent, DialogActions, Avatar, Chip, Tooltip
} from '@mui/material';
import PersonAddIcon from '@mui/icons-material/PersonAdd';
import DeleteIcon from '@mui/icons-material/Delete';
import FileUploadIcon from '@mui/icons-material/FileUpload';
import AccountCircleIcon from '@mui/icons-material/AccountCircle';
import EditIcon from '@mui/icons-material/Edit';
import CheckIcon from '@mui/icons-material/Check';
import CloseIcon from '@mui/icons-material/Close';
import SearchIcon from '@mui/icons-material/Search';
import VideocamIcon from '@mui/icons-material/Videocam';

export default function WatchlistManager({ token }) {
  const [watchlist, setWatchlist] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [photoFile, setPhotoFile] = useState(null);
  const [photoPreview, setPhotoPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);
  const [poiToDelete, setPoiToDelete] = useState(null);
  const [editingPoiId, setEditingPoiId] = useState(null);
  const [editingName, setEditingName] = useState('');
  const fileInputRef = useRef(null);

  const loadWatchlist = useCallback(() => {
    if (!token) return;
    setLoading(true);
    fetch('/api/v1/watchlist', {
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(res => res.ok ? res.json() : [])
      .then(data => {
        setWatchlist(Array.isArray(data) ? data : []);
        setLoading(false);
      })
      .catch(err => {
        console.error("Failed to load watchlist:", err);
        setLoading(false);
      });
  }, [token]);

  useEffect(() => {
    loadWatchlist();
  }, [loadWatchlist]);

  const handleFileChange = (e) => {
    const f = e.target.files[0];
    if (!f) return;
    setPhotoFile(f);
    setSubmitError(null);
    if (photoPreview && photoPreview.startsWith('blob:')) {
      URL.revokeObjectURL(photoPreview);
    }
    setPhotoPreview(URL.createObjectURL(f));
  };

  const handleAddPOI = async (e) => {
    e.preventDefault();
    if (!name) return;
    if (!photoFile) {
      setSubmitError("A face photo is required. Upload a clear frontal image.");
      return;
    }

    setSubmitting(true);
    setSubmitError(null);

    const formData = new FormData();
    formData.append('name', name);
    formData.append('description', description);
    formData.append('file', photoFile);

    try {
      const res = await fetch('/api/v1/watchlist', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: formData
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to add target POI profile");
      }

      setName('');
      setDescription('');
      setPhotoFile(null);
      setPhotoPreview(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      loadWatchlist();
    } catch (err) {
      setSubmitError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const confirmDeletePOI = (id) => {
    fetch(`/api/v1/watchlist/${id}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(res => {
        if (!res.ok) throw new Error("Failed to delete POI profile");
        return res.json();
      })
      .then(() => loadWatchlist())
      .catch(err => alert(err.message));
  };

  const handleSaveRenamePOI = (poiId) => {
    if (!editingName.trim()) return;
    fetch(`/api/v1/watchlist/${poiId}`, {
      method: 'PUT',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ name: editingName.trim() })
    })
      .then(res => {
        if (!res.ok) throw new Error("Failed to update POI identity name");
        return res.json();
      })
      .then(() => {
        setEditingPoiId(null);
        setEditingName('');
        loadWatchlist();
      })
      .catch(err => alert(err.message));
  };

  const filteredWatchlist = watchlist.filter(poi => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      (poi.name && poi.name.toLowerCase().includes(q)) ||
      (poi.identity_uuid && poi.identity_uuid.toLowerCase().includes(q)) ||
      (poi.cams_seen && poi.cams_seen.some(c => c.toLowerCase().includes(q)))
    );
  });

  return (
    <Box sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column' }}>
      <Typography variant="h6" fontWeight="bold" sx={{ mb: 2 }}>POI Watchlist Registry</Typography>

      <Grid container spacing={3}>
        <Grid size={{ xs: 12, md: 4 }}>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Typography variant="subtitle2" fontWeight="bold" sx={{ mb: 2, borderBottom: '1px solid', borderColor: 'divider', pb: 1 }}>
              REGISTER TARGET PROFILE
            </Typography>

            <Box component="form" onSubmit={handleAddPOI} sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <TextField 
                label="Full Name / Identifier" 
                size="small" 
                required 
                value={name} 
                onChange={(e) => setName(e.target.value)} 
                placeholder="e.g. AGENT_POI_01" 
              />
              <TextField 
                label="POI Classification Metadata" 
                size="small" 
                multiline 
                rows={2} 
                value={description} 
                onChange={(e) => setDescription(e.target.value)} 
                placeholder="e.g. Retail loitering suspect" 
              />
              
              <Box>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>FACE PHOTO (REQUIRED):</Typography>
                {photoPreview ? (
                  <Box sx={{ position: 'relative', border: '1px solid', borderColor: 'divider', p: 1, backgroundColor: '#000', display: 'flex', justifyContent: 'center' }}>
                    <Box component="img" src={photoPreview} alt="POI preview" sx={{ height: 100, objectFit: 'contain' }} />
                    <Button 
                      size="small" 
                      color="error" 
                      variant="contained" 
                      sx={{ position: 'absolute', top: 4, right: 4 }}
                      onClick={() => {
                        setPhotoFile(null);
                        if (photoPreview && photoPreview.startsWith('blob:')) {
                          URL.revokeObjectURL(photoPreview);
                        }
                        setPhotoPreview(null);
                        if (fileInputRef.current) fileInputRef.current.value = '';
                      }}
                    >
                      Clear
                    </Button>
                  </Box>
                ) : (
                  <Button 
                    component="label" 
                    variant="outlined" 
                    sx={{ width: '100%', height: 100, borderStyle: 'dashed', display: 'flex', flexDirection: 'column' }}
                  >
                    <FileUploadIcon sx={{ mb: 1 }} />
                    <Typography variant="caption">CLICK TO SELECT IMAGE</Typography>
                    <input ref={fileInputRef} type="file" accept="image/*" hidden onChange={handleFileChange} />
                  </Button>
                )}
              </Box>

              {submitError && <Alert severity="error">{submitError}</Alert>}

              <Button 
                type="submit" 
                variant="contained" 
                disabled={submitting} 
                startIcon={<PersonAddIcon />} 
                sx={{ mt: 1 }}
              >
                {submitting ? 'PROCESSING EMBEDDING...' : 'COMMIT PROFILE'}
              </Button>
            </Box>

            <Box sx={{ mt: 2, p: 1.5, backgroundColor: 'background.default', border: '1px solid', borderColor: 'divider' }}>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                <strong>ENCODINGS:</strong> YuNet detects & SFace extracts 128-dimensional embedding from uploaded photo.
              </Typography>
              <Typography variant="caption" color="error.main" sx={{ display: 'block', fontWeight: 'bold' }}>
                <strong>DPDP ACT 2023 COMPLIANCE:</strong> Auto-purges vectors after 90 days legal retention window.
              </Typography>
            </Box>
          </Paper>
        </Grid>

        <Grid size={{ xs: 12, md: 8 }}>
          <Paper variant="outlined" sx={{ p: 2, height: '100%', display: 'flex', flexDirection: 'column' }}>
            <Typography variant="subtitle2" fontWeight="bold" sx={{ mb: 1.5, borderBottom: '1px solid', borderColor: 'divider', pb: 1, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 1 }}>
              <span>POI WATCHLIST LEDGER</span>
              <Typography variant="caption" color="primary.main" sx={{ border: '1px solid', borderColor: 'primary.main', px: 1, py: 0.25, borderRadius: 1 }}>
                DPDP 2023 PURGE PROTECTED
              </Typography>
            </Typography>

            <Box sx={{ mb: 2, display: 'flex', gap: 1 }}>
              <TextField
                size="small"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search POI by Name, ID, or Captured Camera..."
                fullWidth
                slotProps={{
                  input: {
                    startAdornment: <SearchIcon fontSize="small" sx={{ mr: 1, color: 'text.secondary' }} />
                  }
                }}
              />
              {searchQuery && (
                <Button size="small" variant="outlined" onClick={() => setSearchQuery('')}>Clear</Button>
              )}
            </Box>

            <TableContainer sx={{ flexGrow: 1, overflowY: 'auto', maxHeight: 'calc(100vh - 280px)' }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ fontWeight: 'bold' }}>FACE</TableCell>
                    <TableCell sx={{ fontWeight: 'bold' }}>ID</TableCell>
                    <TableCell sx={{ fontWeight: 'bold' }}>POI IDENTIFIER & NAME</TableCell>
                    <TableCell sx={{ fontWeight: 'bold' }}>CAPTURED CAMERAS HISTORY</TableCell>
                    <TableCell sx={{ fontWeight: 'bold' }}>REGISTERED</TableCell>
                    <TableCell align="center" sx={{ fontWeight: 'bold' }}>ACTION</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {loading ? (
                    <TableRow>
                      <TableCell colSpan={6} align="center" sx={{ py: 4, color: 'text.secondary' }}>LOADING REGISTRY...</TableCell>
                    </TableRow>
                  ) : filteredWatchlist.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={6} align="center" sx={{ py: 6 }}>
                        <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1 }}>
                          <AccountCircleIcon sx={{ fontSize: 40, color: 'text.secondary', opacity: 0.5 }} />
                          <Typography variant="subtitle2" fontWeight="bold" color="text.secondary">
                            {searchQuery ? "No POI target profiles match search query" : "No POI Target Profiles Enrolled"}
                          </Typography>
                          <Typography variant="caption" color="text.secondary">
                            Use the target registration form on the left to add suspect photos for real-time facial recognition.
                          </Typography>
                        </Box>
                      </TableCell>
                    </TableRow>
                  ) : (
                    filteredWatchlist.map((poi) => {
                      const isEditing = editingPoiId === poi.id;
                      return (
                        <TableRow key={poi.id} hover>
                          <TableCell>
                            <Avatar
                              src={poi.face_crop_url}
                              variant="rounded"
                              sx={{ width: 44, height: 44, border: '1.5px solid', borderColor: 'primary.main', backgroundColor: '#0a0f1d' }}
                            >
                              <AccountCircleIcon />
                            </Avatar>
                          </TableCell>
                          <TableCell sx={{ fontFamily: 'monospace', fontWeight: 'bold' }}>{poi.identity_uuid}</TableCell>
                          <TableCell>
                            {isEditing ? (
                              <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center' }}>
                                <TextField
                                  size="small"
                                  value={editingName}
                                  onChange={(e) => setEditingName(e.target.value)}
                                  autoFocus
                                  sx={{ width: 160 }}
                                />
                                <IconButton size="small" color="success" onClick={() => handleSaveRenamePOI(poi.id)}>
                                  <CheckIcon fontSize="small" />
                                </IconButton>
                                <IconButton size="small" color="inherit" onClick={() => setEditingPoiId(null)}>
                                  <CloseIcon fontSize="small" />
                                </IconButton>
                              </Box>
                            ) : (
                              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                <Typography variant="body2" fontWeight="bold">{poi.name}</Typography>
                                <Tooltip title="Edit Person Name">
                                  <IconButton
                                    size="small"
                                    onClick={() => {
                                      setEditingPoiId(poi.id);
                                      setEditingName(poi.name);
                                    }}
                                  >
                                    <EditIcon fontSize="small" sx={{ fontSize: 16, opacity: 0.7 }} />
                                  </IconButton>
                                </Tooltip>
                              </Box>
                            )}
                          </TableCell>
                          <TableCell>
                            <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', maxWidth: 220 }}>
                              {poi.cams_seen && poi.cams_seen.length > 0 ? (
                                poi.cams_seen.map((cam, idx) => (
                                  <Chip
                                    key={idx}
                                    icon={<VideocamIcon style={{ fontSize: 14 }} />}
                                    label={cam}
                                    size="small"
                                    color="info"
                                    variant="outlined"
                                  />
                                ))
                              ) : (
                                <Chip label="No Camera Detections Yet" size="small" variant="outlined" color="default" sx={{ opacity: 0.6 }} />
                              )}
                            </Box>
                          </TableCell>
                          <TableCell sx={{ color: 'text.secondary', fontSize: '0.8rem' }}>
                            {poi.first_seen ? poi.first_seen.substring(0, 10) : 'N/A'}
                          </TableCell>
                          <TableCell align="center">
                            <IconButton
                              size="small"
                              color="error"
                              aria-label={`Delete POI ${poi.name}`}
                              onClick={() => setPoiToDelete(poi)}
                            >
                              <DeleteIcon fontSize="small" />
                            </IconButton>
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

      {/* POI Deletion Confirmation Dialog (Issue 6) */}
      <Dialog open={Boolean(poiToDelete)} onClose={() => setPoiToDelete(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Confirm POI Removal</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            Are you sure you want to remove target POI <strong>"{poiToDelete?.name}"</strong> from the active watchlist registry? Facial recognition embeddings for this target will be purged.
          </Typography>
        </DialogContent>
        <DialogActions sx={{ p: 2 }}>
          <Button onClick={() => setPoiToDelete(null)} variant="outlined">Cancel</Button>
          <Button
            onClick={() => {
              if (poiToDelete) {
                confirmDeletePOI(poiToDelete.id);
                setPoiToDelete(null);
              }
            }}
            color="error"
            variant="contained"
          >
            Remove Target
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

