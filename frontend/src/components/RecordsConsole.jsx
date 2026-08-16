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
  TablePagination,
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
import TextFieldsIcon from '@mui/icons-material/TextFields';
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
    ocr_count: 0,
    captions_count: 0,
    identities_count: 0
  });

  const [facesData, setFacesData] = useState({ total: 0, items: [] });
  const [vehiclesData, setVehiclesData] = useState({ total: 0, items: [] });
  const [platesData, setPlatesData] = useState({ total: 0, items: [] });
  const [ocrData, setOcrData] = useState({ total: 0, items: [] });
  const [captionsData, setCaptionsData] = useState({ total: 0, items: [] });

  const [searchQuery, setSearchQuery] = useState('');
  const [page, setPage] = useState(1);
  const [rowsPerPage, setRowsPerPage] = useState(20);
  const [previewImage, setPreviewImage] = useState(null);


  const authHeaders = token ? { 'Authorization': `Bearer ${token}` } : {};

  const authUrl = (url) => {
    if (!url) return null;
    if (token && !url.includes('token=')) {
      return url.includes('?') ? `${url}&token=${encodeURIComponent(token)}` : `${url}?token=${encodeURIComponent(token)}`;
    }
    return url;
  };

  const fetchStats = async () => {
    try {
      const res = await fetch('/api/v1/records/stats', { headers: authHeaders });
      if (res.ok) {
        const data = await res.json();
        setStats({
          faces_count: data.faces_count || 0,
          vehicles_count: data.vehicles_count || 0,
          plates_count: data.plates_count || 0,
          ocr_count: data.ocr_count || 0,
          captions_count: data.captions_count || 0,
          identities_count: data.identities_count || 0,
        });
      }
    } catch (err) {
      console.error("Error fetching record stats:", err);
    }
  };

  const fetchTabData = async () => {
    setLoading(true);
    const offset = (page - 1) * rowsPerPage;
    const qParam = searchQuery ? `&search=${encodeURIComponent(searchQuery)}` : '';
    const sParam = `&sort=${sortOrder}`;

    try {
      if (activeTab === 0) {
        // Faces
        const res = await fetch(`/api/v1/records/faces?limit=${rowsPerPage}&offset=${offset}${qParam}${sParam}`, { headers: authHeaders });
        if (res.ok) {
          const data = await res.json();
          setFacesData(data);
          if (typeof data.total === 'number') {
            setStats(prev => ({ ...prev, faces_count: data.total }));
          }
        }
      } else if (activeTab === 1) {
        // Vehicles
        const res = await fetch(`/api/v1/records/vehicles?limit=${rowsPerPage}&offset=${offset}${qParam}${sParam}`, { headers: authHeaders });
        if (res.ok) {
          const data = await res.json();
          setVehiclesData(data);
          if (typeof data.total === 'number') {
            setStats(prev => ({ ...prev, vehicles_count: data.total }));
          }
        }
      } else if (activeTab === 2) {
        // Number Plates
        const res = await fetch(`/api/v1/records/plates?limit=${rowsPerPage}&offset=${offset}${qParam}${sParam}`, { headers: authHeaders });
        if (res.ok) {
          const data = await res.json();
          setPlatesData(data);
          if (typeof data.total === 'number') {
            setStats(prev => ({ ...prev, plates_count: data.total }));
          }
        }
      } else if (activeTab === 3) {
        // Raw OCR
        const res = await fetch(`/api/v1/records/ocr?limit=${rowsPerPage}&offset=${offset}${qParam}${sParam}`, { headers: authHeaders });
        if (res.ok) {
          const data = await res.json();
          setOcrData(data);
          if (typeof data.total === 'number') {
            setStats(prev => ({ ...prev, ocr_count: data.total }));
          }
        }
      } else if (activeTab === 4) {
        // Captions
        const res = await fetch(`/api/v1/records/captions?limit=${rowsPerPage}&offset=${offset}${qParam}${sParam}`, { headers: authHeaders });
        if (res.ok) {
          const data = await res.json();
          setCaptionsData(data);
          if (typeof data.total === 'number') {
            setStats(prev => ({ ...prev, captions_count: data.total }));
          }
        }
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
  }, [activeTab, page, rowsPerPage, sortOrder, token, searchQuery]);

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
    else if (activeTab === 3) endpoint = '/api/v1/records/ocr';
    else if (activeTab === 4) endpoint = '/api/v1/records/captions';

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
      csvLines.push("ID,Camera ID,Track UUID,Detected Text,Raw OCR,Confidence,Timestamp,Snapshot URL");
      itemsToExport.forEach(item => {
        csvLines.push(`${item.id},${item.camera_id},${item.track_uuid},"${item.detected_text}","${item.raw_text}",${item.ocr_confidence},${item.timestamp},"${item.snapshot_url || ''}"`);
      });
    } else if (activeTab === 4) {
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

  const facesCount = stats.faces_count || 0;
  const vehiclesCount = stats.vehicles_count || 0;
  const platesCount = stats.plates_count || 0;
  const ocrCount = stats.ocr_count || 0;
  const captionsCount = stats.captions_count || 0;

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 85px)', overflow: 'hidden', p: 2 }}>
      {/* Header Title */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.5 }}>
        <Box>
          <Typography variant="h6" sx={{ fontWeight: 800, letterSpacing: '0.5px', color: 'primary.main' }}>
            CAPTURED RECORDS LEDGER
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Central audit directory logging all faces, vehicle tracks, OCR license plates, raw frame OCR text, and AI scene captions.
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
      <Grid container spacing={2} sx={{ mb: 1.5 }}>
        <Grid size={{ xs: 12, sm: 6, md: 2.4 }}>
          <Paper sx={{ p: 1.5, display: 'flex', alignItems: 'center', gap: 1.5, borderLeft: '4px solid #00e676' }}>
            <FaceIcon sx={{ fontSize: 28, color: '#00e676' }} />
            <Box>
              <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
                FACES
              </Typography>
              <Typography variant="h6" sx={{ fontWeight: 700 }}>
                {facesCount.toLocaleString()}
              </Typography>
            </Box>
          </Paper>
        </Grid>

        <Grid size={{ xs: 12, sm: 6, md: 2.4 }}>
          <Paper sx={{ p: 1.5, display: 'flex', alignItems: 'center', gap: 1.5, borderLeft: '4px solid #29b6f6' }}>
            <DirectionsCarIcon sx={{ fontSize: 28, color: '#29b6f6' }} />
            <Box>
              <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
                VEHICLES
              </Typography>
              <Typography variant="h6" sx={{ fontWeight: 700 }}>
                {vehiclesCount.toLocaleString()}
              </Typography>
            </Box>
          </Paper>
        </Grid>

        <Grid size={{ xs: 12, sm: 6, md: 2.4 }}>
          <Paper sx={{ p: 1.5, display: 'flex', alignItems: 'center', gap: 1.5, borderLeft: '4px solid #ab47bc' }}>
            <ConfirmationNumberIcon sx={{ fontSize: 28, color: '#ab47bc' }} />
            <Box>
              <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
                NUMBER PLATES
              </Typography>
              <Typography variant="h6" sx={{ fontWeight: 700 }}>
                {platesCount.toLocaleString()}
              </Typography>
            </Box>
          </Paper>
        </Grid>

        <Grid size={{ xs: 12, sm: 6, md: 2.4 }}>
          <Paper sx={{ p: 1.5, display: 'flex', alignItems: 'center', gap: 1.5, borderLeft: '4px solid #ffb74d' }}>
            <TextFieldsIcon sx={{ fontSize: 28, color: '#ffb74d' }} />
            <Box>
              <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
                RAW OCR TEXT
              </Typography>
              <Typography variant="h6" sx={{ fontWeight: 700 }}>
                {ocrCount.toLocaleString()}
              </Typography>
            </Box>
          </Paper>
        </Grid>

        <Grid size={{ xs: 12, sm: 6, md: 2.4 }}>
          <Paper sx={{ p: 1.5, display: 'flex', alignItems: 'center', gap: 1.5, borderLeft: '4px solid #ff7043' }}>
            <SubtitlesIcon sx={{ fontSize: 28, color: '#ff7043' }} />
            <Box>
              <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
                AI CAPTIONS
              </Typography>
              <Typography variant="h6" sx={{ fontWeight: 700 }}>
                {captionsCount.toLocaleString()}
              </Typography>
            </Box>
          </Paper>
        </Grid>
      </Grid>

      {/* Main Tabs Navigation */}
      <Paper sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minHeight: 0 }}>
        <Box sx={{ borderBottom: 1, borderColor: 'divider', display: 'flex', justifyContent: 'space-between', alignItems: 'center', pr: 2 }}>
          <Tabs
            value={activeTab}
            onChange={(e, newVal) => { setActiveTab(newVal); setPage(1); setSearchQuery(''); }}
            textColor="primary"
            indicatorColor="primary"
          >
            <Tab icon={<FaceIcon />} iconPosition="start" label={`Faces (${facesCount})`} />
            <Tab icon={<DirectionsCarIcon />} iconPosition="start" label={`Vehicles (${vehiclesCount})`} />
            <Tab icon={<ConfirmationNumberIcon />} iconPosition="start" label={`Number Plates (${platesCount})`} />
            <Tab icon={<TextFieldsIcon />} iconPosition="start" label={`OCR (${ocrCount})`} />
            <Tab icon={<SubtitlesIcon />} iconPosition="start" label={`AI Captions (${captionsCount})`} />
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
          <Box sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minHeight: 0, p: 1.5 }}>
            {/* Tab 0: Faces */}
            {activeTab === 0 && (
              <TableContainer sx={{ flexGrow: 1, overflowY: 'auto', maxHeight: 'calc(100vh - 380px)' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell sx={{ fontWeight: 'bold' }}>Snapshot</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }}>Resolved Identity (POI)</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }}>Camera Occurrences</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }}>Total Sightings</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }}>Confidence</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }}>Latest Timestamp</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {facesData.items.length === 0 ? (
                      <TableRow><TableCell colSpan={6} align="center">No face detection records found.</TableCell></TableRow>
                    ) : (
                      facesData.items.map((row) => (
                        <TableRow key={row.id} hover>
                          <TableCell>
                            {row.snapshot_url ? (
                              <Box
                                component="img"
                                src={authUrl(row.snapshot_url)}
                                alt="Face Crop"
                                onError={(e) => { e.target.onerror = null; e.target.src = '/api/v1/playback/snapshot/default'; }}
                                onClick={() => setPreviewImage(row.snapshot_url)}
                                sx={{
                                  width: 52,
                                  height: 52,
                                  borderRadius: '50%',
                                  objectFit: 'cover',
                                  border: '2px solid #00e676',
                                  cursor: 'pointer',
                                  transition: 'transform 0.15s ease-in-out',
                                  '&:hover': { transform: 'scale(1.2)', borderColor: '#38bdf8', boxShadow: '0 0 10px rgba(0, 230, 118, 0.5)' }
                                }}
                              />
                            ) : (
                              <FaceIcon color="action" />
                            )}
                          </TableCell>
                          <TableCell sx={{ fontWeight: 700, color: 'primary.main' }}>{row.label}</TableCell>
                          <TableCell><Chip label={row.cameras || 'Live Grid'} size="small" variant="outlined" color="secondary" /></TableCell>
                          <TableCell><Chip label={`${row.sightings || 1} sighting(s)`} size="small" color="success" sx={{ fontWeight: 'bold' }} /></TableCell>
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
              <TableContainer sx={{ flexGrow: 1, overflowY: 'auto', maxHeight: 'calc(100vh - 380px)' }}>
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
                                src={authUrl(row.snapshot_url)}
                                alt="Vehicle Snapshot"
                                onError={(e) => { e.target.onerror = null; e.target.src = '/api/v1/playback/snapshot/default'; }}
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
              <TableContainer sx={{ flexGrow: 1, overflowY: 'auto', maxHeight: 'calc(100vh - 380px)' }}>
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
                                src={authUrl(row.snapshot_url)}
                                alt="Plate Snapshot"
                                onError={(e) => { e.target.onerror = null; e.target.src = '/api/v1/playback/snapshot/default'; }}
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

            {/* Tab 3: Raw OCR Text Log */}
            {activeTab === 3 && (
              <TableContainer sx={{ flexGrow: 1, overflowY: 'auto', maxHeight: 'calc(100vh - 380px)' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell sx={{ fontWeight: 'bold', width: '90px' }}>Snapshot</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }}>Detected Raw OCR Text</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }}>Camera ID</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }}>Track UUID</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }}>OCR Confidence</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }}>Timestamp</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {ocrData.items.length === 0 ? (
                      <TableRow><TableCell colSpan={6} align="center">No raw OCR text records found.</TableCell></TableRow>
                    ) : (
                      ocrData.items.map((row) => (
                        <TableRow key={row.id} hover>
                          <TableCell>
                            {row.snapshot_url ? (
                              <Box
                                component="img"
                                src={authUrl(row.snapshot_url)}
                                alt="OCR Snapshot"
                                onError={(e) => { e.target.onerror = null; e.target.src = '/api/v1/playback/snapshot/default'; }}
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
                              label={row.raw_text || row.detected_text}
                              color="warning"
                              variant="outlined"
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

            {/* Tab 4: AI Scene Captions Log */}
            {activeTab === 4 && (() => {
              // ── Timestamp helpers (scoped to this tab) ─────────────────────
              // Parse ts= field from stored caption string. Returns Date or null.
              const parseCaptureTsRC = (caption) => {
                try {
                  const m = caption?.match(/\bts=(\S+)/);
                  if (!m) return null;  // No ts= in caption → show only DB time
                  const d = new Date(m[1]);
                  return isNaN(d.getTime()) ? null : d;  // Invalid date → fallback
                } catch { return null; }
              };

              // Strip ts= field from the displayed caption text (keep it clean).
              const stripTs = (caption) => {
                try { return caption?.replace(/\s*\|\s*ts=\S+/, '').trim() || '[No caption]'; }
                catch { return caption || '[No caption]'; }
              };

              // Format a Date into HH:MM:SS IST string for display.
              const fmtTime = (d) => {
                try {
                  return d.toLocaleTimeString('en-IN', { hour12: false, timeZone: 'Asia/Kolkata' });
                } catch { return null; }
              };

              // Human-readable processing lag between capture time and DB stored time.
              const getLag = (capturedAt, storedAtStr) => {
                try {
                  if (!capturedAt || !storedAtStr) return null;
                  const storedAt = new Date(storedAtStr);
                  if (isNaN(storedAt.getTime())) return null;
                  const lagSeconds = Math.round((storedAt - capturedAt) / 1000);
                  if (lagSeconds < 0) return null;      // Clock skew → hide
                  if (lagSeconds > 3600) return null;   // >1 hr → too old to be useful
                  if (lagSeconds < 60) return { label: `⚡ ${lagSeconds}s`, ok: true };
                  return { label: `⚠ ${Math.floor(lagSeconds / 60)}m ${lagSeconds % 60}s`, ok: false };
                } catch { return null; }
              };
              // ────────────────────────────────────────────────────────────────

              return (
                <TableContainer sx={{ flexGrow: 1, overflowY: 'auto', maxHeight: 'calc(100vh - 380px)' }}>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell sx={{ fontWeight: 'bold', width: '90px' }}>Snapshot</TableCell>
                        <TableCell sx={{ fontWeight: 'bold', width: '120px' }}>Camera</TableCell>
                        <TableCell sx={{ fontWeight: 'bold' }}>AI Scene Caption</TableCell>
                        <TableCell sx={{ fontWeight: 'bold', width: '210px' }}>Timestamps</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {(captionsData.items || []).length === 0 ? (
                        <TableRow><TableCell colSpan={4} align="center">No generated scene captions logged yet.</TableCell></TableRow>
                      ) : (
                        captionsData.items.map((row) => {
                          const capturedAt = parseCaptureTsRC(row.caption);
                          const capturedTime = capturedAt ? fmtTime(capturedAt) : null;
                          const lag = getLag(capturedAt, row.timestamp);
                          const cleanCaption = stripTs(row.caption);

                          return (
                            <TableRow key={row.id} hover>
                              <TableCell>
                                {row.snapshot_url ? (
                                  <Box
                                    component="img"
                                    src={authUrl(row.snapshot_url)}
                                    alt="AI Scene Frame"
                                    onClick={() => setPreviewImage({ url: row.snapshot_url, caption: cleanCaption, camera_id: row.camera_id, timestamp: row.timestamp })}
                                    sx={{
                                      width: 64, height: 44, borderRadius: 1, objectFit: 'cover',
                                      border: '1px solid #38bdf8', cursor: 'pointer',
                                      transition: 'transform 0.2s',
                                      '&:hover': { transform: 'scale(1.08)', boxShadow: '0 0 8px rgba(56,189,248,0.6)' }
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
                                  onClick={() => row.snapshot_url && setPreviewImage({ url: row.snapshot_url, caption: cleanCaption, camera_id: row.camera_id, timestamp: row.timestamp })}
                                  sx={{
                                    fontFamily: 'monospace', color: '#e0e0e0',
                                    backgroundColor: 'rgba(0,0,0,0.3)', p: 1, borderRadius: 1,
                                    cursor: row.snapshot_url ? 'pointer' : 'default',
                                    '&:hover': row.snapshot_url ? { backgroundColor: 'rgba(56,189,248,0.1)', color: '#38bdf8' } : {}
                                  }}
                                >
                                  {cleanCaption}
                                </Typography>
                              </TableCell>
                              <TableCell>
                                {/* Frame captured at — from ts= embedded in caption */}
                                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.4 }}>
                                  {capturedTime ? (
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                      <Typography variant="caption" sx={{ color: '#94a3b8', minWidth: 58 }}>📷 captured</Typography>
                                      <Typography variant="caption" sx={{ fontFamily: 'monospace', color: '#e2e8f0', fontWeight: 600 }}>
                                        {capturedTime}
                                      </Typography>
                                    </Box>
                                  ) : null}
                                  {/* Stored at — from DB timestamp column */}
                                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                    <Typography variant="caption" sx={{ color: '#94a3b8', minWidth: 58 }}>
                                      {capturedTime ? '💾 stored' : '🕒 time'}
                                    </Typography>
                                    <Typography variant="caption" sx={{ fontFamily: 'monospace', color: '#94a3b8' }}>
                                      {row.timestamp
                                        ? (() => { try { return fmtTime(new Date(row.timestamp)) || row.timestamp; } catch { return row.timestamp; } })()
                                        : 'unknown'}
                                    </Typography>
                                  </Box>
                                  {/* Processing lag badge */}
                                  {lag && (
                                    <Chip
                                      label={lag.label}
                                      size="small"
                                      sx={{
                                        height: 16, fontSize: '0.6rem', fontFamily: 'monospace',
                                        alignSelf: 'flex-start',
                                        backgroundColor: lag.ok ? 'rgba(34,197,94,0.15)' : 'rgba(245,158,11,0.15)',
                                        color: lag.ok ? '#22c55e' : '#f59e0b',
                                        border: `1px solid ${lag.ok ? 'rgba(34,197,94,0.4)' : 'rgba(245,158,11,0.4)'}`,
                                      }}
                                    />
                                  )}
                                </Box>
                              </TableCell>
                            </TableRow>
                          );
                        })
                      )}
                    </TableBody>
                  </Table>
                </TableContainer>
              );
            })()}


            {/* Snapshot Preview Dialog */}
            <Dialog
              open={Boolean(previewImage)}
              onClose={() => setPreviewImage(null)}
              maxWidth="lg"
              fullWidth
              slotProps={{
                paper: {
                  sx: { backgroundColor: '#0f172a', color: '#fff', border: '1px solid #334155' }
                }
              }}
            >
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', p: 2, borderBottom: '1px solid #334155' }}>
                <Typography variant="h6" fontWeight="bold" color="primary.main">
                  Snapshot Preview {previewImage?.camera_id ? `— ${previewImage.camera_id} (${previewImage?.timestamp || ''})` : ''}
                </Typography>
                <IconButton onClick={() => setPreviewImage(null)} sx={{ color: '#94a3b8' }}>
                  <CloseIcon />
                </IconButton>
              </Box>
              <DialogContent sx={{ p: 2, textAlign: 'center' }}>
                {(typeof previewImage === 'string' ? previewImage : previewImage?.url) && (
                  <Box
                    component="img"
                    src={authUrl(typeof previewImage === 'string' ? previewImage : previewImage.url)}
                    alt="Snapshot Preview"
                    sx={{ width: '100%', maxHeight: '70vh', objectFit: 'contain', borderRadius: 1, border: '1px solid #334155', mb: previewImage?.caption ? 2 : 0 }}
                  />
                )}
                {previewImage?.caption && (
                  <Typography variant="body1" sx={{ fontFamily: 'monospace', backgroundColor: 'rgba(0,0,0,0.5)', p: 2, borderRadius: 1, color: '#38bdf8', textAlign: 'left' }}>
                    {previewImage.caption}
                  </Typography>
                )}
              </DialogContent>
            </Dialog>


            {/* Pagination Controls */}
            <Box sx={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', mt: 2, pt: 1, borderTop: '1px solid', borderColor: 'divider' }}>
              <TablePagination
                component="div"
                count={(activeTab === 0 ? facesData : activeTab === 1 ? vehiclesData : activeTab === 2 ? platesData : activeTab === 3 ? ocrData : captionsData).total || 0}
                page={page - 1}
                onPageChange={(e, newPage) => setPage(newPage + 1)}
                rowsPerPage={rowsPerPage}
                onRowsPerPageChange={(e) => {
                  setRowsPerPage(parseInt(e.target.value, 10));
                  setPage(1);
                }}
                rowsPerPageOptions={[10, 20, 50, 100]}
                sx={{ borderBottom: 'none' }}
              />
            </Box>
          </Box>
        )}
      </Paper>
    </Box>
  );
}
