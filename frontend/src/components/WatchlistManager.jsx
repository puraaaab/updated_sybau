import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Box, Typography, Grid, Paper, TextField, Button, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, IconButton, Alert
} from '@mui/material';
import PersonAddIcon from '@mui/icons-material/PersonAdd';
import DeleteIcon from '@mui/icons-material/Delete';
import FileUploadIcon from '@mui/icons-material/FileUpload';

export default function WatchlistManager({ token }) {
  const [watchlist, setWatchlist] = useState([]);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [photoFile, setPhotoFile] = useState(null);
  const [photoPreview, setPhotoPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);
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
    const reader = new FileReader();
    reader.onloadend = () => setPhotoPreview(reader.result);
    reader.readAsDataURL(f);
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

  const handleDeletePOI = (id) => {
    if (!window.confirm("Confirm deletion of this target POI from live watchlist?")) return;

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
                      onClick={() => { setPhotoFile(null); setPhotoPreview(null); if (fileInputRef.current) fileInputRef.current.value = ''; }}
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
            <Typography variant="subtitle2" fontWeight="bold" sx={{ mb: 2, borderBottom: '1px solid', borderColor: 'divider', pb: 1, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>POI WATCHLIST LEDGER</span>
              <Typography variant="caption" color="primary.main" sx={{ border: '1px solid', borderColor: 'primary.main', px: 1, py: 0.25, borderRadius: 1 }}>
                DPDP 2023 PURGE PROTECTED
              </Typography>
            </Typography>

            <TableContainer sx={{ flexGrow: 1 }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ fontWeight: 'bold' }}>ID</TableCell>
                    <TableCell sx={{ fontWeight: 'bold' }}>POI IDENTIFIER</TableCell>
                    <TableCell sx={{ fontWeight: 'bold' }}>REGISTERED</TableCell>
                    <TableCell sx={{ fontWeight: 'bold' }}>RETENTION STATUS</TableCell>
                    <TableCell align="center" sx={{ fontWeight: 'bold' }}>ACTION</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {loading ? (
                    <TableRow>
                      <TableCell colSpan={5} align="center" sx={{ py: 4, color: 'text.secondary' }}>LOADING REGISTRY...</TableCell>
                    </TableRow>
                  ) : watchlist.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5} align="center" sx={{ py: 6, color: 'text.secondary' }}>[ NO TARGET POI PROFILES ENROLLED ]</TableCell>
                    </TableRow>
                  ) : (
                    watchlist.map((poi) => (
                      <TableRow key={poi.id} hover>
                        <TableCell sx={{ fontFamily: 'monospace' }}>{poi.identity_uuid}</TableCell>
                        <TableCell sx={{ fontWeight: 'bold' }}>{poi.name}</TableCell>
                        <TableCell sx={{ color: 'text.secondary' }}>{poi.first_seen ? poi.first_seen.substring(0, 10) : 'N/A'}</TableCell>
                        <TableCell>
                          <Typography variant="caption" color="success.main" sx={{ fontWeight: 'bold', fontFamily: 'monospace' }}>
                            {poi.dpdp_status || 'DPDP_VERIFIED_ACTIVE'}
                          </Typography>
                        </TableCell>
                        <TableCell align="center">
                          <IconButton size="small" color="error" onClick={() => handleDeletePOI(poi.id)}>
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
        </Grid>
      </Grid>
    </Box>
  );
}
