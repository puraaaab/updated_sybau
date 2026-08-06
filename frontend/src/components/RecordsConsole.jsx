import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Paper,
  Tabs,
  Tab,
  Grid,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Button,
  Chip,
  IconButton,
  CircularProgress,
  Pagination,
  FormControl,
  Select,
  MenuItem,
  Dialog,
  DialogContent
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import RefreshIcon from '@mui/icons-material/Refresh';
import DownloadIcon from '@mui/icons-material/Download';
import FaceIcon from '@mui/icons-material/Face';
import DirectionsCarIcon from '@mui/icons-material/DirectionsCar';
import ConfirmationNumberIcon from '@mui/icons-material/ConfirmationNumber';
import SubtitlesIcon from '@mui/icons-material/Subtitles';
import SortIcon from '@mui/icons-material/Sort';
import CloseIcon from '@mui/icons-material/Close';
import CameraAltIcon from '@mui/icons-material/CameraAlt';


export default function RecordsConsole({ token }) {
  const [activeTab, setActiveTab] = useState(0);
  const [loading, setLoading] = useState(false);
  const [sortOrder, setSortOrder] = useState('desc');
  const [stats, setStats] = useState({
    faces_count: 0,
    vehicles_count: 0,
    plates_count: 0,
    captions_count: 0,
    identities_count: 0
  });

  const [facesData, setFacesData] = useState({ total: 0, items: [] });
  const [vehiclesData, setVehiclesData] = useState({ total: 0, items: [] });
  const [platesData, setPlatesData] = useState({ total: 0, items: [] });
  const [captionsData, setCaptionsData] = useState({ total: 0, items: [] });

  const [searchQuery, setSearchQuery] = useState('');
  const [page, setPage] = useState(1);
  const [previewImage, setPreviewImage] = useState(null);
  const limit = 20;


  const authHeaders = token ? { 'Authorization': `Bearer ${token}` } : {};

  const fetchStats = async () => {
    try {
      const res = await fetch('/api/v1/records/stats', { headers: authHeaders });
      if (res.ok) {
        const data = await res.json();
        setStats(data);
      }
    } catch (err) {
      console.error("Error fetching record stats:", err);
    }
  };

  const fetchTabData = async () => {
    setLoading(true);
    const offset = (page - 1) * limit;
    const qParam = searchQuery ? `&search=${encodeURIComponent(searchQuery)}` : '';
    const sParam = `&sort=${sortOrder}`;

    try {
      if (activeTab === 0) {
        // Faces
        const res = await fetch(`/api/v1/records/faces?limit=${limit}&offset=${offset}${qParam}${sParam}`, { headers: authHeaders });
        if (res.ok) setFacesData(await res.json());
      } else if (activeTab === 1) {
        // Vehicles
        const res = await fetch(`/api/v1/records/vehicles?limit=${limit}&offset=${offset}${qParam}${sParam}`, { headers: authHeaders });
        if (res.ok) setVehiclesData(await res.json());
      } else if (activeTab === 2) {
        // Number Plates
        const res = await fetch(`/api/v1/records/plates?limit=${limit}&offset=${offset}${qParam}${sParam}`, { headers: authHeaders });
        if (res.ok) setPlatesData(await res.json());
      } else if (activeTab === 3) {
        // Captions
        const res = await fetch(`/api/v1/records/captions?limit=${limit}&offset=${offset}${qParam}${sParam}`, { headers: authHeaders });
        if (res.ok) setCaptionsData(await res.json());
      }
    } catch (err) {
      console.error("Error fetching records:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStats();
    fetchTabData();
  }, [activeTab, page, sortOrder, token]);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    setPage(1);
    fetchTabData();
  };

  const handleExportCSV = async () => {
    setLoading(true);
    const qParam = searchQuery ? `&search=${encodeURIComponent(searchQuery)}` : '';
    const sParam = `&sort=${sortOrder}`;

    let endpoint = '';
    if (activeTab === 0) endpoint = '/api/v1/records/faces';
    else if (activeTab === 1) endpoint = '/api/v1/records/vehicles';
    else if (activeTab === 2) endpoint = '/api/v1/records/plates';
    else if (activeTab === 3) endpoint = '/api/v1/records/captions';

    let itemsToExport = [];
    try {
      const res = await fetch(`${endpoint}?limit=50000&offset=0${qParam}${sParam}`, { headers: authHeaders });
      if (res.ok) {
        const data = await res.json();
        itemsToExport = data.items || [];
      }
    } catch (err) {
      console.error("Export fetch error:", err);
    } finally {
      setLoading(false);
    }

    if (!itemsToExport.length) return;

    let csvLines = [];
    if (activeTab === 0) {
      csvLines.push("ID,Track UUID,Label,Confidence,Timestamp,Snapshot URL");
      itemsToExport.forEach(item => {
        csvLines.push(`${item.id},${item.track_uuid},"${item.label}",${item.confidence},${item.timestamp},"${item.snapshot_url || ''}"`);
      });
    } else if (activeTab === 1) {
      csvLines.push("ID,Camera ID,Track UUID,Type,Color,Plate,Timestamp,Snapshot URL");
      itemsToExport.forEach(item => {
        csvLines.push(`${item.id},${item.camera_id},${item.track_uuid},${item.vehicle_type},${item.vehicle_color},${item.license_plate || 'N/A'},${item.timestamp},"${item.snapshot_url || ''}"`);
      });
    } else if (activeTab === 2) {
      csvLines.push("ID,Camera ID,License Plate,Confidence,Vehicle Type,Timestamp,Snapshot URL");
      itemsToExport.forEach(item => {
        csvLines.push(`${item.id},${item.camera_id},${item.license_plate},${item.ocr_confidence},${item.vehicle_type || 'car'},${item.timestamp},"${item.snapshot_url || ''}"`);
      });
    } else if (activeTab === 3) {
      csvLines.push("ID,Camera ID,Generated Scene Caption,Timestamp,Snapshot URL");
      itemsToExport.forEach(item => {
        csvLines.push(`${item.id},${item.camera_id},"${(item.caption || '').replace(/"/g, '""')}",${item.timestamp},"${item.snapshot_url || ''}"`);
      });
    }

    const blob = new Blob([csvLines.join("\n")], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", `VMS_Full_Records_Export_Tab_${activeTab}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <Box sx={{ p: 3 }}>
      {/* Header Title */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 800, letterSpacing: '0.5px', color: 'primary.main' }}>
            CAPTURED RECORDS LEDGER
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Central audit directory logging all faces, vehicle tracks, OCR license plates, and AI scene captions.
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button
            variant="outlined"
            startIcon={<RefreshIcon />}
            onClick={() => { fetchStats(); fetchTabData(); }}
            size="small"
          >
            Refresh
          </Button>
          <Button
            variant="contained"
            color="primary"
            startIcon={<DownloadIcon />}
            onClick={handleExportCSV}
            size="small"
          >
            Export CSV
          </Button>
        </Box>
      </Box>

      {/* Top Metric Cards */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid xs={12} sm={6} md={3}>
          <Paper sx={{ p: 2, display: 'flex', alignItems: 'center', gap: 2, borderLeft: '4px solid #00e676' }}>
            <FaceIcon sx={{ fontSize: 36, color: '#00e676' }} />
            <Box>
              <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
                CAPTURED FACES
              </Typography>
              <Typography variant="h5" sx={{ fontWeight: 700 }}>
                {stats.faces_count.toLocaleString()}
              </Typography>
            </Box>
          </Paper>
        </Grid>

        <Grid xs={12} sm={6} md={3}>
          <Paper sx={{ p: 2, display: 'flex', alignItems: 'center', gap: 2, borderLeft: '4px solid #29b6f6' }}>
            <DirectionsCarIcon sx={{ fontSize: 36, color: '#29b6f6' }} />
            <Box>
              <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
                CAPTURED VEHICLES
              </Typography>
              <Typography variant="h5" sx={{ fontWeight: 700 }}>
                {stats.vehicles_count.toLocaleString()}
              </Typography>
            </Box>
          </Paper>
        </Grid>

        <Grid xs={12} sm={6} md={3}>
          <Paper sx={{ p: 2, display: 'flex', alignItems: 'center', gap: 2, borderLeft: '4px solid #ab47bc' }}>
            <ConfirmationNumberIcon sx={{ fontSize: 36, color: '#ab47bc' }} />
            <Box>
              <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
                NUMBER PLATES (OCR)
              </Typography>
              <Typography variant="h5" sx={{ fontWeight: 700 }}>
                {stats.plates_count.toLocaleString()}
              </Typography>
            </Box>
          </Paper>
        </Grid>

        <Grid xs={12} sm={6} md={3}>
          <Paper sx={{ p: 2, display: 'flex', alignItems: 'center', gap: 2, borderLeft: '4px solid #ff7043' }}>
            <SubtitlesIcon sx={{ fontSize: 36, color: '#ff7043' }} />
            <Box>
              <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
                AI SCENE CAPTIONS
              </Typography>
              <Typography variant="h5" sx={{ fontWeight: 700 }}>
                {stats.captions_count.toLocaleString()}
              </Typography>
            </Box>
          </Paper>
        </Grid>
      </Grid>

      {/* Main Tabs Navigation */}
      <Paper sx={{ width: '100%', mb: 2 }}>
        <Box sx={{ borderBottom: 1, borderColor: 'divider', display: 'flex', justifyContent: 'space-between', alignItems: 'center', pr: 2 }}>
          <Tabs
            value={activeTab}
            onChange={(e, newVal) => { setActiveTab(newVal); setPage(1); setSearchQuery(''); }}
            textColor="primary"
            indicatorColor="primary"
          >
            <Tab icon={<FaceIcon />} iconPosition="start" label={`Faces (${stats.faces_count})`} />
            <Tab icon={<DirectionsCarIcon />} iconPosition="start" label={`Vehicles (${stats.vehicles_count})`} />
            <Tab icon={<ConfirmationNumberIcon />} iconPosition="start" label={`Number Plates (${stats.plates_count})`} />
            <Tab icon={<SubtitlesIcon />} iconPosition="start" label={`AI Captions (${stats.captions_count})`} />
          </Tabs>

          <Box component="form" onSubmit={handleSearchSubmit} sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
            <FormControl size="small" sx={{ minWidth: 160 }}>
              <Select
                value={sortOrder}
                onChange={(e) => { setSortOrder(e.target.value); setPage(1); }}
                displayEmpty
                startAdornment={<SortIcon fontSize="small" sx={{ mr: 1, color: 'text.secondary' }} />}
                sx={{ fontSize: '0.85rem' }}
              >
                <MenuItem value="desc">⚡ Newest First</MenuItem>
                <MenuItem value="asc">⏳ Oldest First</MenuItem>
              </Select>
            </FormControl>

            <TextField
              size="small"
              placeholder="Search records..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              slotProps={{
                input: {
                  endAdornment: (
                    <IconButton size="small" type="submit">
                      <SearchIcon fontSize="small" />
                    </IconButton>
                  )
                }
              }}
            />
          </Box>
        </Box>


        {loading ? (
          <Box sx={{ p: 4, textAlign: 'center' }}>
            <CircularProgress size={32} />
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              Querying database records...
            </Typography>
          </Box>
        ) : (
          <Box sx={{ p: 2 }}>
            {/* Tab 0: Faces */}
            {activeTab === 0 && (
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell sx={{ fontWeight: 'bold' }}>Snapshot</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }}>Track UUID</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }}>Resolved Identity</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }}>Confidence</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }}>Timestamp</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {facesData.items.length === 0 ? (
                      <TableRow><TableCell colSpan={5} align="center">No face detection records found.</TableCell></TableRow>
                    ) : (
                      facesData.items.map((row) => (
                        <TableRow key={row.id} hover>
                          <TableCell>
                            {row.snapshot_url ? (
                              <Box
                                component="img"
                                src={row.snapshot_url}
                                alt="Face"
                                sx={{ width: 48, height: 48, borderRadius: 1, objectFit: 'cover', border: '1px solid #444' }}
                              />
                            ) : (
                              <FaceIcon color="action" />
                            )}
                          </TableCell>
                          <TableCell><Chip label={row.track_uuid} size="small" variant="outlined" /></TableCell>
                          <TableCell sx={{ fontWeight: 600 }}>{row.label}</TableCell>
                          <TableCell>{(row.confidence * 100).toFixed(0)}%</TableCell>
                          <TableCell color="text.secondary">{row.timestamp}</TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </TableContainer>
            )}

            {/* Tab 1: Vehicles */}
            {activeTab === 1 && (
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell sx={{ fontWeight: 'bold', width: '90px' }}>Snapshot</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }}>Camera ID</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }}>Track UUID</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }}>Vehicle Type</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }}>Paint Color</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }}>License Plate</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }}>Timestamp</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {vehiclesData.items.length === 0 ? (
                      <TableRow><TableCell colSpan={7} align="center">No vehicle detection records found.</TableCell></TableRow>
                    ) : (
                      vehiclesData.items.map((row) => (
                        <TableRow key={row.id} hover>
                          <TableCell>
                            {row.snapshot_url ? (
                              <Box
                                component="img"
                                src={row.snapshot_url}
                                alt="Vehicle Snapshot"
                                onClick={() => setPreviewImage(row.snapshot_url)}
                                sx={{
                                  width: 72,
                                  height: 48,
                                  objectFit: 'cover',
                                  borderRadius: 1,
                                  border: '1px solid rgba(255,255,255,0.2)',
                                  cursor: 'pointer',
                                  transition: 'transform 0.15s ease-in-out',
                                  '&:hover': { transform: 'scale(1.1)', borderColor: 'primary.main' }
                                }}
                              />
                            ) : (
                              <Box sx={{ width: 72, height: 48, borderRadius: 1, bgcolor: 'action.disabledBackground', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                <CameraAltIcon sx={{ fontSize: 20, opacity: 0.5 }} />
                              </Box>
                            )}
                          </TableCell>
                          <TableCell sx={{ fontWeight: 600 }}>{row.camera_id}</TableCell>
                          <TableCell><Chip label={row.track_uuid} size="small" variant="outlined" /></TableCell>
                          <TableCell sx={{ textTransform: 'capitalize' }}>{row.vehicle_type}</TableCell>
                          <TableCell>
                            <Chip
                              label={row.vehicle_color}
                              size="small"
                              color={row.vehicle_color === 'black' ? 'default' : row.vehicle_color === 'white' ? 'secondary' : 'primary'}
                              sx={{ textTransform: 'uppercase', fontSize: '0.65rem' }}
                            />
                          </TableCell>
                          <TableCell>
                            {row.license_plate ? (
                              <Typography variant="body2" sx={{ fontWeight: 700, color: '#00e676', fontFamily: 'monospace' }}>
                                {row.license_plate}
                              </Typography>
                            ) : (
                              <Typography variant="caption" color="text.secondary">N/A</Typography>
                            )}
                          </TableCell>
                          <TableCell color="text.secondary">{row.timestamp}</TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </TableContainer>
            )}

            {/* Tab 2: Number Plates */}
            {activeTab === 2 && (
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell sx={{ fontWeight: 'bold', width: '90px' }}>Snapshot</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }}>License Plate</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }}>Camera ID</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }}>Track UUID</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }}>OCR Confidence</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }}>Timestamp</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {platesData.items.length === 0 ? (
                      <TableRow><TableCell colSpan={6} align="center">No license plate OCR records found.</TableCell></TableRow>
                    ) : (
                      platesData.items.map((row) => (
                        <TableRow key={row.id} hover>
                          <TableCell>
                            {row.snapshot_url ? (
                              <Box
                                component="img"
                                src={row.snapshot_url}
                                alt="Plate Snapshot"
                                onClick={() => setPreviewImage(row.snapshot_url)}
                                sx={{
                                  width: 72,
                                  height: 48,
                                  objectFit: 'cover',
                                  borderRadius: 1,
                                  border: '1px solid rgba(255,255,255,0.2)',
                                  cursor: 'pointer',
                                  transition: 'transform 0.15s ease-in-out',
                                  '&:hover': { transform: 'scale(1.1)', borderColor: 'primary.main' }
                                }}
                              />
                            ) : (
                              <Box sx={{ width: 72, height: 48, borderRadius: 1, bgcolor: 'action.disabledBackground', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                <CameraAltIcon sx={{ fontSize: 20, opacity: 0.5 }} />
                              </Box>
                            )}
                          </TableCell>
                          <TableCell>
                            <Chip
                              label={row.license_plate}
                              color="success"
                              sx={{ fontWeight: 'bold', fontSize: '0.85rem', fontFamily: 'monospace' }}
                            />
                          </TableCell>
                          <TableCell sx={{ fontWeight: 600 }}>{row.camera_id}</TableCell>
                          <TableCell><Chip label={row.track_uuid} size="small" variant="outlined" /></TableCell>
                          <TableCell>{(row.ocr_confidence * 100).toFixed(0)}%</TableCell>
                          <TableCell color="text.secondary">{row.timestamp}</TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </TableContainer>
            )}

            {/* Tab 3: AI Scene Captions Log */}
            {activeTab === 3 && (
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell sx={{ fontWeight: 'bold', width: '90px' }}>Snapshot</TableCell>
                      <TableCell sx={{ fontWeight: 'bold', width: '120px' }}>Camera ID</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }}>Generated AI Scene Caption</TableCell>
                      <TableCell sx={{ fontWeight: 'bold', width: '180px' }}>Timestamp</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {captionsData.items.length === 0 ? (
                      <TableRow><TableCell colSpan={4} align="center">No generated scene captions logged yet.</TableCell></TableRow>
                    ) : (
                      captionsData.items.map((row) => (
                        <TableRow key={row.id} hover>
                          <TableCell>
                            {row.snapshot_url ? (
                              <Box
                                component="img"
                                src={row.snapshot_url}
                                alt="AI Scene Frame"
                                onClick={() => setPreviewImage({ url: row.snapshot_url, caption: row.caption, camera_id: row.camera_id, timestamp: row.timestamp })}
                                sx={{
                                  width: 64,
                                  height: 44,
                                  borderRadius: 1,
                                  objectFit: 'cover',
                                  border: '1px solid #38bdf8',
                                  cursor: 'pointer',
                                  transition: 'transform 0.2s',
                                  '&:hover': { transform: 'scale(1.08)', boxShadow: '0 0 8px rgba(56, 189, 248, 0.6)' }
                                }}
                              />
                            ) : (
                              <CameraAltIcon color="action" />
                            )}
                          </TableCell>
                          <TableCell sx={{ fontWeight: 700, color: 'primary.main' }}>{row.camera_id}</TableCell>
                          <TableCell>
                            <Typography
                              variant="body2"
                              onClick={() => row.snapshot_url && setPreviewImage({ url: row.snapshot_url, caption: row.caption, camera_id: row.camera_id, timestamp: row.timestamp })}
                              sx={{
                                fontFamily: 'monospace',
                                color: '#e0e0e0',
                                backgroundColor: 'rgba(0,0,0,0.3)',
                                p: 1,
                                borderRadius: 1,
                                cursor: row.snapshot_url ? 'pointer' : 'default',
                                '&:hover': row.snapshot_url ? { backgroundColor: 'rgba(56, 189, 248, 0.1)', color: '#38bdf8' } : {}
                              }}
                            >
                              {row.caption}
                            </Typography>
                          </TableCell>
                          <TableCell color="text.secondary">{row.timestamp}</TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </TableContainer>
            )}

            {/* Snapshot Preview Dialog */}
            <Dialog
              open={Boolean(previewImage)}
              onClose={() => setPreviewImage(null)}
              maxWidth="lg"
              fullWidth
              PaperProps={{
                sx: { backgroundColor: '#0f172a', color: '#fff', border: '1px solid #334155' }
              }}
            >
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', p: 2, borderBottom: '1px solid #334155' }}>
                <Typography variant="h6" fontWeight="bold" color="primary.main">
                  AI Caption Snapshot — {previewImage?.camera_id} ({previewImage?.timestamp})
                </Typography>
                <IconButton onClick={() => setPreviewImage(null)} sx={{ color: '#94a3b8' }}>
                  <CloseIcon />
                </IconButton>
              </Box>
              <DialogContent sx={{ p: 2, textAlign: 'center' }}>
                {previewImage?.url && (
                  <Box
                    component="img"
                    src={previewImage.url}
                    alt="Full AI Snapshot"
                    sx={{ width: '100%', maxHeight: '70vh', objectFit: 'contain', borderRadius: 1, border: '1px solid #334155', mb: 2 }}
                  />
                )}
                <Typography variant="body1" sx={{ fontFamily: 'monospace', backgroundColor: 'rgba(0,0,0,0.5)', p: 2, borderRadius: 1, color: '#38bdf8', textAlign: 'left' }}>
                  {previewImage?.caption}
                </Typography>
              </DialogContent>
            </Dialog>


            {/* Pagination Controls */}
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mt: 2, pt: 2, borderTop: '1px solid', borderColor: 'divider' }}>
              <Typography variant="caption" color="text.secondary">
                Showing {Math.min(limit, (activeTab === 0 ? facesData : activeTab === 1 ? vehiclesData : activeTab === 2 ? platesData : captionsData).items.length)} of {(activeTab === 0 ? facesData : activeTab === 1 ? vehiclesData : activeTab === 2 ? platesData : captionsData).total} records
              </Typography>
              <Pagination
                count={Math.ceil(((activeTab === 0 ? facesData : activeTab === 1 ? vehiclesData : activeTab === 2 ? platesData : captionsData).total || 1) / limit)}
                page={page}
                onChange={(e, val) => setPage(val)}
                color="primary"
                size="small"
              />
            </Box>
          </Box>
        )}
      </Paper>
    </Box>
  );
}
