import { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Paper, Chip, Button, TextField, Select, MenuItem,
  FormControl, InputLabel, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, IconButton, Tooltip, LinearProgress, Alert,
  Dialog, DialogTitle, DialogContent, DialogActions, Divider, Grid,
  Card, CardContent, Switch, FormControlLabel, Tabs, Tab, Collapse,
  CircularProgress, Skeleton,
} from '@mui/material';

const API = 'http://localhost:8000/api/compras';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const fmtPrecio = (v) => v != null ? `$${Math.round(v).toLocaleString('es-CL')}` : '—';
const fmtPct = (v) => v != null ? `${v.toFixed(1)}%` : '—';
const fmtScore = (v) => v != null ? v.toFixed(4) : '—';

const METODO_COLORS = {
  vectorial: '#3b82f6',
  llm_coem: '#8b5cf6',
  llm: '#8b5cf6',
  texto_jaccard: '#f59e0b',
  texto_jaccard_rechazo: '#ef4444',
  rechazo_directo: '#ef4444',
  unidad_rechazo: '#dc2626',
  etim_rechazo: '#991b1b',
  vectorial_fallback_textual: '#f97316',
  desconocido: '#6b7280',
};

const CONFIDENCE_COLOR = (score) => {
  if (score >= 0.85) return '#10b981';
  if (score >= 0.6) return '#f59e0b';
  if (score >= 0.3) return '#f97316';
  return '#ef4444';
};

// ---------------------------------------------------------------------------
// StatsCards — resumen global
// ---------------------------------------------------------------------------

function StatsCards({ stats, loading }) {
  if (loading) return <Skeleton variant="rectangular" height={120} sx={{ borderRadius: 3 }} />;
  if (!stats) return null;

  const cards = [
    { label: 'Comparaciones', value: stats.total_comparaciones, icon: '🔀', color: '#6366f1' },
    { label: 'Productos', value: stats.total_productos, icon: '📦', color: '#3b82f6' },
    { label: 'Canonicals', value: stats.total_canonicals, icon: '🎯', color: '#10b981' },
    { label: 'Con Embedding', value: stats.productos_con_embedding, icon: '🧠', color: '#8b5cf6' },
    { label: 'Con ETIM', value: stats.productos_con_etim || 0, icon: '🏷️', color: '#0ea5e9' },
    { label: 'Costo IA', value: `$${(stats.total_ai_cost_usd || 0).toFixed(4)}`, icon: '💰', color: '#f59e0b' },
  ];

  return (
    <Grid container spacing={2}>
      {cards.map((c) => (
        <Grid item xs={6} sm={4} md={2} key={c.label}>
          <Card sx={{ borderRadius: 3, border: `2px solid ${c.color}20` }}>
            <CardContent sx={{ py: 1.5, px: 2, '&:last-child': { pb: 1.5 } }}>
              <Typography sx={{ fontSize: '1.2rem', mb: 0.3 }}>{c.icon}</Typography>
              <Typography variant="h5" sx={{ fontWeight: 800, color: c.color }}>{c.value}</Typography>
              <Typography variant="caption" sx={{ color: 'text.secondary' }}>{c.label}</Typography>
            </CardContent>
          </Card>
        </Grid>
      ))}
    </Grid>
  );
}

// ---------------------------------------------------------------------------
// DistributionChart — barras simples de distribución
// ---------------------------------------------------------------------------

function DistributionChart({ title, data, colorMap }) {
  if (!data || Object.keys(data).length === 0) return null;
  const total = Object.values(data).reduce((a, b) => a + b, 0);
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);

  return (
    <Paper sx={{ p: 2, borderRadius: 3 }}>
      <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1.5 }}>{title}</Typography>
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        {entries.map(([key, count]) => {
          const pct = total > 0 ? (count / total) * 100 : 0;
          const color = colorMap?.[key] || '#6b7280';
          return (
            <Box key={key}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.3 }}>
                <Typography variant="caption" sx={{ fontWeight: 600 }}>{key}</Typography>
                <Typography variant="caption" sx={{ color: 'text.secondary' }}>{count} ({pct.toFixed(0)}%)</Typography>
              </Box>
              <Box sx={{ height: 8, borderRadius: 4, backgroundColor: '#f1f5f9', overflow: 'hidden' }}>
                <Box sx={{ height: '100%', width: `${pct}%`, backgroundColor: color, borderRadius: 4, transition: 'width 0.5s ease' }} />
              </Box>
            </Box>
          );
        })}
      </Box>
    </Paper>
  );
}

// ---------------------------------------------------------------------------
// ProductoMini — tarjeta compacta de producto
// ---------------------------------------------------------------------------

function ProductoMini({ prod, label }) {
  if (!prod) return <Typography color="text.secondary" variant="caption">Producto eliminado</Typography>;
  return (
    <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}>
      {prod.imagen_url && (
        <Box
          component="img" src={prod.imagen_url} alt=""
          sx={{ width: 48, height: 48, borderRadius: 1.5, objectFit: 'contain', backgroundColor: '#f8fafc', flexShrink: 0 }}
          onError={(e) => { e.target.style.display = 'none'; }}
        />
      )}
      <Box sx={{ minWidth: 0 }}>
        <Chip label={label} size="small" sx={{ mb: 0.3, height: 18, fontSize: '0.6rem', fontWeight: 700 }} />
        <Typography variant="body2" sx={{ fontWeight: 600, fontSize: '0.75rem', lineHeight: 1.3, overflow: 'hidden', textOverflow: 'ellipsis', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
          {prod.nombre}
        </Typography>
        <Box sx={{ display: 'flex', gap: 0.5, mt: 0.3, flexWrap: 'wrap' }}>
          <Chip label={prod.proveedor} size="small" variant="outlined" sx={{ height: 18, fontSize: '0.6rem' }} />
          <Chip label={fmtPrecio(prod.precio)} size="small" sx={{ height: 18, fontSize: '0.6rem', backgroundColor: '#e0f2fe' }} />
          {prod.unidad && <Chip label={prod.unidad} size="small" color="warning" variant="outlined" sx={{ height: 18, fontSize: '0.6rem' }} />}
          {prod.tiene_embedding && <Chip label="EMB" size="small" sx={{ height: 18, fontSize: '0.55rem', backgroundColor: '#ddd6fe', color: '#6d28d9' }} />}
        </Box>
      </Box>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// EmbeddingViewer — dialog para ver embedding de un producto
// ---------------------------------------------------------------------------

function EmbeddingViewer({ open, onClose, productoId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !productoId) return;
    setLoading(true);
    fetch(`${API}/admin/embedding/${productoId}`)
      .then(r => r.json())
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [open, productoId]);

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth PaperProps={{ sx: { borderRadius: 4 } }}>
      <DialogTitle sx={{ fontWeight: 700 }}>Embedding — Producto #{productoId}</DialogTitle>
      <Divider />
      <DialogContent>
        {loading && <LinearProgress sx={{ mb: 2 }} />}
        {data && (
          <Box>
            <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>Texto usado para embedding:</Typography>
            <Paper sx={{ p: 1.5, mb: 2, backgroundColor: '#f8fafc', borderRadius: 2 }}>
              <Typography variant="body2" sx={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>{data.texto_embedding}</Typography>
            </Paper>

            {data.tiene_embedding ? (
              <>
                <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>Estadisticas del vector:</Typography>
                <Grid container spacing={1} sx={{ mb: 2 }}>
                  {Object.entries(data.stats || {}).map(([k, v]) => (
                    <Grid item xs={4} sm={2} key={k}>
                      <Paper sx={{ p: 1, textAlign: 'center', borderRadius: 2 }}>
                        <Typography variant="caption" sx={{ color: 'text.secondary' }}>{k}</Typography>
                        <Typography variant="body2" sx={{ fontWeight: 700, fontFamily: 'monospace' }}>{typeof v === 'number' ? v.toFixed(4) : v}</Typography>
                      </Paper>
                    </Grid>
                  ))}
                </Grid>

                <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
                  Preview del vector (primeros {data.vector_preview?.length || 0} de {data.vector_full_length} dimensiones):
                </Typography>
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.3, maxHeight: 200, overflow: 'auto' }}>
                  {(data.vector_preview || []).map((v, i) => {
                    const intensity = Math.min(Math.abs(v) * 5, 1);
                    const bg = v > 0
                      ? `rgba(16, 185, 129, ${intensity})`
                      : `rgba(239, 68, 68, ${intensity})`;
                    return (
                      <Tooltip key={i} title={`[${i}] = ${v.toFixed(6)}`}>
                        <Box sx={{
                          width: 16, height: 16, borderRadius: 0.5,
                          backgroundColor: bg, border: '1px solid rgba(0,0,0,0.06)',
                          cursor: 'pointer',
                        }} />
                      </Tooltip>
                    );
                  })}
                </Box>
              </>
            ) : (
              <Alert severity="warning">Este producto no tiene embedding generado.</Alert>
            )}
          </Box>
        )}
        {!loading && !data && <Alert severity="error">No se pudo cargar el embedding.</Alert>}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cerrar</Button>
      </DialogActions>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// ComparacionRow — fila de la tabla de comparaciones
// ---------------------------------------------------------------------------

function ComparacionRow({ comp, onViewEmbedding, onReComparar }) {
  const [expanded, setExpanded] = useState(false);
  const metodoColor = METODO_COLORS[comp.metodo] || '#6b7280';
  const confColor = CONFIDENCE_COLOR(comp.confidence_score);

  return (
    <>
      <TableRow
        hover
        onClick={() => setExpanded(!expanded)}
        sx={{ cursor: 'pointer', '& td': { py: 1 }, backgroundColor: comp.es_match ? 'rgba(16,185,129,0.03)' : 'transparent' }}
      >
        <TableCell sx={{ width: 40 }}>
          <Typography sx={{ fontSize: '0.7rem', color: 'text.secondary' }}>#{comp.id}</Typography>
        </TableCell>
        <TableCell>
          <ProductoMini prod={comp.producto_a} label="A" />
        </TableCell>
        <TableCell>
          <ProductoMini prod={comp.producto_b} label="B" />
        </TableCell>
        <TableCell align="center">
          <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 0.3 }}>
            <Box sx={{
              width: 44, height: 44, borderRadius: 999, border: `3px solid ${confColor}`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <Typography sx={{ fontWeight: 800, fontSize: '0.7rem', color: confColor }}>
                {(comp.confidence_score * 100).toFixed(0)}
              </Typography>
            </Box>
            <Chip
              label={comp.es_match ? 'MATCH' : 'NO'}
              size="small"
              sx={{
                height: 18, fontSize: '0.55rem', fontWeight: 800,
                backgroundColor: comp.es_match ? '#d1fae5' : '#fee2e2',
                color: comp.es_match ? '#065f46' : '#991b1b',
              }}
            />
          </Box>
        </TableCell>
        <TableCell align="center">
          <Chip
            label={comp.metodo}
            size="small"
            sx={{ height: 20, fontSize: '0.6rem', fontWeight: 700, backgroundColor: `${metodoColor}18`, color: metodoColor, border: `1px solid ${metodoColor}40` }}
          />
        </TableCell>
        <TableCell align="center">
          <Typography variant="caption">{fmtPct(comp.precio_diff_pct)}</Typography>
        </TableCell>
      </TableRow>
      <TableRow>
        <TableCell colSpan={6} sx={{ py: 0, border: 0 }}>
          <Collapse in={expanded}>
            <Box sx={{ py: 2, px: 1 }}>
              <Paper sx={{ p: 2, borderRadius: 2, backgroundColor: '#f8fafc' }}>
                <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>Razon IA:</Typography>
                <Typography variant="body2" sx={{ mb: 1, fontStyle: 'italic' }}>
                  "{comp.razon || 'Sin razon registrada'}"
                </Typography>

                {/* Observabilidad v2 */}
                <Box sx={{ display: 'flex', gap: 1, mb: 2, flexWrap: 'wrap' }}>
                  {comp.prompt_version && <Chip label={`Prompt: ${comp.prompt_version}`} size="small" variant="outlined" sx={{ height: 20, fontSize: '0.6rem' }} />}
                  {comp.modelo_usado && <Chip label={comp.modelo_usado} size="small" variant="outlined" sx={{ height: 20, fontSize: '0.6rem' }} />}
                  {comp.latencia_total_ms != null && <Chip label={`${Math.round(comp.latencia_total_ms)}ms`} size="small" sx={{ height: 20, fontSize: '0.6rem', backgroundColor: '#dbeafe' }} />}
                  {comp.tokens_totales != null && <Chip label={`${comp.tokens_totales} tokens`} size="small" sx={{ height: 20, fontSize: '0.6rem', backgroundColor: '#fef3c7' }} />}
                  {comp.costo_usd != null && comp.costo_usd > 0 && <Chip label={`$${comp.costo_usd.toFixed(6)}`} size="small" sx={{ height: 20, fontSize: '0.6rem', backgroundColor: '#d1fae5' }} />}
                  {comp.tiene_lineage && <Chip label="LINEAGE" size="small" color="info" sx={{ height: 20, fontSize: '0.55rem', fontWeight: 700 }} />}
                </Box>

                <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                  {comp.producto_a && (
                    <Button
                      size="small" variant="outlined"
                      onClick={(e) => { e.stopPropagation(); onViewEmbedding(comp.producto_a.id); }}
                    >
                      Embedding A
                    </Button>
                  )}
                  {comp.producto_b && (
                    <Button
                      size="small" variant="outlined"
                      onClick={(e) => { e.stopPropagation(); onViewEmbedding(comp.producto_b.id); }}
                    >
                      Embedding B
                    </Button>
                  )}
                  <Button
                    size="small" variant="contained" color="secondary"
                    onClick={(e) => { e.stopPropagation(); onReComparar(comp.id); }}
                  >
                    Re-comparar
                  </Button>
                  {comp.producto_a?.url && (
                    <Button size="small" variant="text" href={comp.producto_a.url} target="_blank" rel="noopener">
                      Ver en tienda A
                    </Button>
                  )}
                  {comp.producto_b?.url && (
                    <Button size="small" variant="text" href={comp.producto_b.url} target="_blank" rel="noopener">
                      Ver en tienda B
                    </Button>
                  )}
                </Box>
              </Paper>
            </Box>
          </Collapse>
        </TableCell>
      </TableRow>
    </>
  );
}

// ---------------------------------------------------------------------------
// AILogsTab — Logs de llamadas IA
// ---------------------------------------------------------------------------

function AILogsTab() {
  const [logs, setLogs] = useState([]);
  const [aiStats, setAiStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filterType, setFilterType] = useState('');

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const params = new URLSearchParams({ limite: '100' });
        if (filterType) params.set('call_type', filterType);
        const [logsR, statsR] = await Promise.all([
          fetch(`${API}/admin/ai-logs?${params}`).then(r => r.json()),
          fetch(`${API}/admin/ai-stats`).then(r => r.json()),
        ]);
        setLogs(logsR.logs || []);
        setAiStats(statsR);
      } catch (e) { console.error(e); }
      finally { setLoading(false); }
    };
    load();
  }, [filterType]);

  const typeColors = { embedding: '#3b82f6', llm: '#8b5cf6', unit_parse: '#f59e0b', etim_classify: '#10b981' };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      {/* AI Stats summary */}
      {aiStats && (
        <Grid container spacing={2}>
          {(aiStats.por_tipo || []).map((t) => (
            <Grid item xs={6} sm={3} key={t.tipo}>
              <Card sx={{ borderRadius: 3, border: `2px solid ${(typeColors[t.tipo] || '#6b7280')}20` }}>
                <CardContent sx={{ py: 1.5, '&:last-child': { pb: 1.5 } }}>
                  <Chip label={t.tipo} size="small" sx={{ mb: 0.5, backgroundColor: `${typeColors[t.tipo] || '#6b7280'}18`, color: typeColors[t.tipo] || '#6b7280', fontWeight: 700, fontSize: '0.6rem' }} />
                  <Typography variant="body2"><b>{t.total}</b> llamadas</Typography>
                  <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                    Avg: {t.avg_latencia_ms}ms | ${t.total_costo_usd.toFixed(6)}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}

      {/* Filter + Table */}
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
        <FormControl size="small" sx={{ minWidth: 140 }}>
          <InputLabel>Tipo</InputLabel>
          <Select value={filterType} onChange={(e) => setFilterType(e.target.value)} label="Tipo">
            <MenuItem value="">Todos</MenuItem>
            <MenuItem value="embedding">Embedding</MenuItem>
            <MenuItem value="llm">LLM</MenuItem>
            <MenuItem value="unit_parse">Unit Parse</MenuItem>
            <MenuItem value="etim_classify">ETIM Classify</MenuItem>
          </Select>
        </FormControl>
        <Typography variant="caption" sx={{ color: 'text.secondary' }}>{logs.length} logs</Typography>
      </Box>

      {loading && <LinearProgress />}

      <TableContainer component={Paper} sx={{ borderRadius: 3, maxHeight: 'calc(100vh - 400px)' }}>
        <Table stickyHeader size="small">
          <TableHead>
            <TableRow>
              <TableCell>Tipo</TableCell>
              <TableCell>Modelo</TableCell>
              <TableCell align="right">Latencia</TableCell>
              <TableCell align="right">Tokens In</TableCell>
              <TableCell align="right">Tokens Out</TableCell>
              <TableCell align="right">Costo</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Fecha</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {logs.map((l) => (
              <TableRow key={l.id} hover>
                <TableCell>
                  <Chip label={l.call_type} size="small" sx={{ height: 20, fontSize: '0.6rem', fontWeight: 700, backgroundColor: `${typeColors[l.call_type] || '#6b7280'}18`, color: typeColors[l.call_type] || '#6b7280' }} />
                </TableCell>
                <TableCell><Typography variant="caption">{l.modelo || '-'}</Typography></TableCell>
                <TableCell align="right"><Typography variant="caption" sx={{ fontFamily: 'monospace' }}>{Math.round(l.latencia_ms)}ms</Typography></TableCell>
                <TableCell align="right"><Typography variant="caption">{l.tokens_input}</Typography></TableCell>
                <TableCell align="right"><Typography variant="caption">{l.tokens_output}</Typography></TableCell>
                <TableCell align="right"><Typography variant="caption" sx={{ fontFamily: 'monospace' }}>${(l.costo_usd || 0).toFixed(6)}</Typography></TableCell>
                <TableCell>{l.exitoso ? <Chip label="OK" size="small" sx={{ height: 18, fontSize: '0.55rem', backgroundColor: '#d1fae5', color: '#065f46' }} /> : <Chip label="ERR" size="small" sx={{ height: 18, fontSize: '0.55rem', backgroundColor: '#fee2e2', color: '#991b1b' }} />}</TableCell>
                <TableCell><Typography variant="caption" sx={{ color: 'text.secondary' }}>{l.created_at ? new Date(l.created_at).toLocaleString('es-CL') : '-'}</Typography></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
}


// ---------------------------------------------------------------------------
// AdminComparaciones — Pagina principal
// ---------------------------------------------------------------------------

export default function AdminComparaciones() {
  const [tab, setTab] = useState(0);
  const [stats, setStats] = useState(null);
  const [comparaciones, setComparaciones] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Filtros
  const [filtroMetodo, setFiltroMetodo] = useState('');
  const [filtroMatch, setFiltroMatch] = useState('');
  const [filtroMinConf, setFiltroMinConf] = useState('');
  const [filtroMaxConf, setFiltroMaxConf] = useState('');
  const [pagina, setPagina] = useState(0);
  const LIMITE = 50;

  // Embedding viewer
  const [embeddingOpen, setEmbeddingOpen] = useState(false);
  const [embeddingProdId, setEmbeddingProdId] = useState(null);

  // Re-comparar
  const [reCompResult, setReCompResult] = useState(null);
  const [reCompOpen, setReCompOpen] = useState(false);
  const [reCompLoading, setReCompLoading] = useState(false);

  const cargarStats = useCallback(async () => {
    try {
      const r = await fetch(`${API}/admin/comparaciones/stats`);
      const data = await r.json();
      setStats(data);
    } catch (e) {
      console.error('Error cargando stats:', e);
    }
  }, []);

  const cargarComparaciones = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams({ limite: LIMITE, offset: pagina * LIMITE });
      if (filtroMetodo) params.set('metodo', filtroMetodo);
      if (filtroMatch === 'si') params.set('solo_matches', 'true');
      if (filtroMatch === 'no') params.set('solo_matches', 'false');
      if (filtroMinConf) params.set('min_confidence', filtroMinConf);
      if (filtroMaxConf) params.set('max_confidence', filtroMaxConf);

      const r = await fetch(`${API}/admin/comparaciones?${params}`);
      const data = await r.json();
      setComparaciones(data.comparaciones || []);
      setTotal(data.total || 0);
    } catch (e) {
      setError('Error cargando comparaciones');
    } finally {
      setLoading(false);
    }
  }, [pagina, filtroMetodo, filtroMatch, filtroMinConf, filtroMaxConf]);

  useEffect(() => { cargarStats(); }, [cargarStats]);
  useEffect(() => { cargarComparaciones(); }, [cargarComparaciones]);

  const handleViewEmbedding = (prodId) => {
    setEmbeddingProdId(prodId);
    setEmbeddingOpen(true);
  };

  const handleReComparar = async (compId) => {
    setReCompLoading(true);
    setReCompOpen(true);
    setReCompResult(null);
    try {
      const r = await fetch(`${API}/admin/re-comparar/${compId}`, { method: 'POST' });
      const data = await r.json();
      setReCompResult(data);
      cargarComparaciones();
      cargarStats();
    } catch (e) {
      setReCompResult({ error: 'Error al re-comparar' });
    } finally {
      setReCompLoading(false);
    }
  };

  return (
    <Box sx={{ height: '100%', overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 2 }}>
      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
        <Typography variant="h4">Monitor de Comparaciones IA</Typography>
        <Chip label="Admin" color="error" size="small" sx={{ fontWeight: 700 }} />
        <Box sx={{ flexGrow: 1 }} />
        <Button variant="outlined" size="small" onClick={() => { cargarStats(); cargarComparaciones(); }}>
          Actualizar
        </Button>
      </Box>

      {/* Stats */}
      <StatsCards stats={stats} loading={!stats} />

      {/* Tabs */}
      <Paper sx={{ borderRadius: 3 }}>
        <Tabs value={tab} onChange={(_, v) => setTab(v)} variant="scrollable" scrollButtons="auto">
          <Tab label="Comparaciones" />
          <Tab label="Distribuciones" />
          <Tab label="AI Logs" />
        </Tabs>
      </Paper>

      {/* Tab 0: Comparaciones */}
      {tab === 0 && (
        <>
          {/* Filtros */}
          <Paper sx={{ p: 2, borderRadius: 3 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>Filtros</Typography>
            <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap', alignItems: 'center' }}>
              <FormControl size="small" sx={{ minWidth: 140 }}>
                <InputLabel>Metodo</InputLabel>
                <Select value={filtroMetodo} onChange={(e) => { setFiltroMetodo(e.target.value); setPagina(0); }} label="Metodo">
                  <MenuItem value="">Todos</MenuItem>
                  <MenuItem value="vectorial">Vectorial</MenuItem>
                  <MenuItem value="llm">LLM</MenuItem>
                  <MenuItem value="texto_jaccard">Texto Jaccard</MenuItem>
                  <MenuItem value="texto_jaccard_rechazo">Jaccard Rechazo</MenuItem>
                  <MenuItem value="rechazo_directo">Rechazo Directo</MenuItem>
                  <MenuItem value="unidad_rechazo">Unidad Rechazo</MenuItem>
                  <MenuItem value="etim_rechazo">ETIM Rechazo</MenuItem>
                  <MenuItem value="llm_coem">LLM CoEM</MenuItem>
                </Select>
              </FormControl>

              <FormControl size="small" sx={{ minWidth: 120 }}>
                <InputLabel>Match</InputLabel>
                <Select value={filtroMatch} onChange={(e) => { setFiltroMatch(e.target.value); setPagina(0); }} label="Match">
                  <MenuItem value="">Todos</MenuItem>
                  <MenuItem value="si">Solo matches</MenuItem>
                  <MenuItem value="no">Solo rechazos</MenuItem>
                </Select>
              </FormControl>

              <TextField
                size="small" label="Conf. min" type="number"
                inputProps={{ min: 0, max: 1, step: 0.1 }}
                value={filtroMinConf}
                onChange={(e) => { setFiltroMinConf(e.target.value); setPagina(0); }}
                sx={{ width: 100 }}
              />

              <TextField
                size="small" label="Conf. max" type="number"
                inputProps={{ min: 0, max: 1, step: 0.1 }}
                value={filtroMaxConf}
                onChange={(e) => { setFiltroMaxConf(e.target.value); setPagina(0); }}
                sx={{ width: 100 }}
              />

              <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                {total} resultados
              </Typography>
            </Box>
          </Paper>

          {/* Tabla */}
          {loading && <LinearProgress />}
          {error && <Alert severity="error">{error}</Alert>}

          <TableContainer component={Paper} sx={{ borderRadius: 3, maxHeight: 'calc(100vh - 450px)' }}>
            <Table stickyHeader size="small">
              <TableHead>
                <TableRow>
                  <TableCell sx={{ width: 40 }}>#</TableCell>
                  <TableCell>Producto A</TableCell>
                  <TableCell>Producto B</TableCell>
                  <TableCell align="center" sx={{ width: 80 }}>Score</TableCell>
                  <TableCell align="center" sx={{ width: 120 }}>Metodo</TableCell>
                  <TableCell align="center" sx={{ width: 80 }}>Diff %</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {comparaciones.length === 0 && !loading && (
                  <TableRow>
                    <TableCell colSpan={6} align="center" sx={{ py: 4 }}>
                      <Typography color="text.secondary">
                        No hay comparaciones registradas. Usa el Cotizador para generar comparaciones.
                      </Typography>
                    </TableCell>
                  </TableRow>
                )}
                {comparaciones.map((c) => (
                  <ComparacionRow
                    key={c.id}
                    comp={c}
                    onViewEmbedding={handleViewEmbedding}
                    onReComparar={handleReComparar}
                  />
                ))}
              </TableBody>
            </Table>
          </TableContainer>

          {/* Paginacion */}
          {total > LIMITE && (
            <Box sx={{ display: 'flex', justifyContent: 'center', gap: 1 }}>
              <Button disabled={pagina === 0} onClick={() => setPagina(p => p - 1)} size="small">Anterior</Button>
              <Chip label={`Pagina ${pagina + 1} de ${Math.ceil(total / LIMITE)}`} size="small" />
              <Button disabled={(pagina + 1) * LIMITE >= total} onClick={() => setPagina(p => p + 1)} size="small">Siguiente</Button>
            </Box>
          )}
        </>
      )}

      {/* Tab 1: Distribuciones */}
      {tab === 1 && stats && (
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <DistributionChart
              title="Distribucion por Confidence Score"
              data={stats.distribucion_confidence}
              colorMap={{
                'alta_0.9_1.0': '#10b981',
                'media_0.6_0.9': '#f59e0b',
                'baja_0.3_0.6': '#f97316',
                'rechazo_0_0.3': '#ef4444',
              }}
            />
          </Grid>
          <Grid item xs={12} md={6}>
            <DistributionChart
              title="Distribucion por Metodo"
              data={stats.distribucion_metodos}
              colorMap={METODO_COLORS}
            />
          </Grid>
          <Grid item xs={12}>
            <Paper sx={{ p: 3, borderRadius: 3 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 2 }}>Guia de Metodos</Typography>
              <Grid container spacing={1}>
                {[
                  { metodo: 'etim_rechazo', desc: 'Capa 0: Clases ETIM diferentes (ej: tornillo vs perno) — rechazo sin IA' },
                  { metodo: 'unidad_rechazo', desc: 'Capa 1: quantulum3+pint detecta unidades incompatibles (pack vs unit, kg vs un)' },
                  { metodo: 'vectorial', desc: 'Capa 2: Similitud coseno alta (>0.92) — match directo por embeddings' },
                  { metodo: 'rechazo_directo', desc: 'Capa 2: Similitud coseno muy baja (<0.60) — rechazo sin LLM' },
                  { metodo: 'llm_coem', desc: 'Capa 3: Chain-of-Thought 3 pasos (ComEM) en zona gris (0.60-0.92)' },
                  { metodo: 'texto_jaccard', desc: 'Capa 4: Fallback sin API — similitud Jaccard bigramas' },
                  { metodo: 'texto_jaccard_rechazo', desc: 'Capa 4: Rechazo por baja similitud textual (sin API)' },
                  { metodo: 'vectorial_fallback_textual', desc: 'LLM fallo en zona gris, degradacion a texto' },
                ].map(({ metodo, desc }) => (
                  <Grid item xs={12} sm={6} key={metodo}>
                    <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
                      <Chip
                        label={metodo} size="small"
                        sx={{
                          height: 22, fontSize: '0.6rem', fontWeight: 700, flexShrink: 0,
                          backgroundColor: `${METODO_COLORS[metodo]}18`,
                          color: METODO_COLORS[metodo],
                        }}
                      />
                      <Typography variant="caption" sx={{ color: 'text.secondary' }}>{desc}</Typography>
                    </Box>
                  </Grid>
                ))}
              </Grid>
            </Paper>
          </Grid>
        </Grid>
      )}

      {/* Tab 2: AI Logs */}
      {tab === 2 && <AILogsTab />}

      {/* Embedding Viewer Dialog */}
      <EmbeddingViewer
        open={embeddingOpen}
        onClose={() => setEmbeddingOpen(false)}
        productoId={embeddingProdId}
      />

      {/* Re-comparar Dialog */}
      <Dialog open={reCompOpen} onClose={() => setReCompOpen(false)} maxWidth="sm" fullWidth PaperProps={{ sx: { borderRadius: 4 } }}>
        <DialogTitle sx={{ fontWeight: 700 }}>Resultado de Re-comparacion</DialogTitle>
        <Divider />
        <DialogContent>
          {reCompLoading && <Box sx={{ textAlign: 'center', py: 3 }}><CircularProgress /><Typography variant="body2" sx={{ mt: 1 }}>Re-evaluando con matcher mejorado...</Typography></Box>}
          {reCompResult && !reCompResult.error && (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: 1 }}>
              <Paper sx={{ p: 2, borderRadius: 2, backgroundColor: '#fef3c7' }}>
                <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>Resultado anterior:</Typography>
                <Typography variant="body2">Confidence: {fmtScore(reCompResult.resultado_anterior?.confidence)}</Typography>
              </Paper>
              <Paper sx={{ p: 2, borderRadius: 2, backgroundColor: '#d1fae5' }}>
                <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>Resultado nuevo:</Typography>
                <Typography variant="body2">Match: {reCompResult.resultado_nuevo?.es_match ? 'SI' : 'NO'}</Typography>
                <Typography variant="body2">Confidence: {fmtScore(reCompResult.resultado_nuevo?.confidence)}</Typography>
                <Typography variant="body2">Metodo: {reCompResult.resultado_nuevo?.metodo}</Typography>
                <Typography variant="body2">Similitud coseno: {fmtScore(reCompResult.resultado_nuevo?.similitud_coseno)}</Typography>
                <Typography variant="body2" sx={{ mt: 1, fontStyle: 'italic' }}>"{reCompResult.resultado_nuevo?.razon}"</Typography>
              </Paper>
            </Box>
          )}
          {reCompResult?.error && <Alert severity="error">{reCompResult.error}</Alert>}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setReCompOpen(false)}>Cerrar</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
