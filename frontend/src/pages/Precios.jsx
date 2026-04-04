import { useState, useEffect, useCallback } from 'react';
import {
  Box, Paper, Typography, Button, Chip, TextField,
  CircularProgress, Divider, Alert, Tooltip, Select,
  MenuItem, FormControl, InputLabel, Dialog, DialogTitle,
  DialogContent, IconButton,
} from '@mui/material';
import { motion, AnimatePresence } from 'framer-motion';
import axios from 'axios';

const API = 'http://127.0.0.1:8000/api/compras';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const formatCLP = (v) => v != null ? `$${Math.round(v).toLocaleString('es-CL')}` : '—';

const tiempoRelativo = (iso) => {
  if (!iso) return null;
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60)    return 'hace segundos';
  if (s < 3600)  return `hace ${Math.floor(s / 60)} min`;
  if (s < 86400) return `hace ${Math.floor(s / 3600)}h`;
  return `hace ${Math.floor(s / 86400)}d`;
};

const COLOR_SODIMAC = '#1f3a5f';
const COLOR_EASY    = '#10b981';

// ---------------------------------------------------------------------------
// MetricCard — tarjeta de métrica
// ---------------------------------------------------------------------------

function MetricCard({ label, value, subtitle, color = '#1f3a5f', icon }) {
  return (
    <Paper elevation={0} sx={{
      p: 2, borderRadius: 2, border: '1px solid rgba(28,35,43,0.08)',
      backgroundColor: `${color}06`,
    }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
        {icon && <Typography sx={{ fontSize: '1.2rem' }}>{icon}</Typography>}
        <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>
          {label}
        </Typography>
      </Box>
      <Typography variant="h5" sx={{ fontWeight: 800, color }}>{value}</Typography>
      {subtitle && (
        <Typography variant="caption" sx={{ color: 'text.disabled' }}>{subtitle}</Typography>
      )}
    </Paper>
  );
}

// ---------------------------------------------------------------------------
// PriceHistoryChart — mini gráfico de precios (SVG)
// ---------------------------------------------------------------------------

function PriceHistoryChart({ series, width = 300, height = 120 }) {
  if (!series || Object.keys(series).length === 0) {
    return (
      <Box sx={{ textAlign: 'center', py: 3 }}>
        <Typography variant="caption" sx={{ color: 'text.disabled' }}>
          Sin datos de historial aún
        </Typography>
      </Box>
    );
  }

  const allPoints = Object.values(series).flat();
  if (allPoints.length === 0) {
    return (
      <Box sx={{ textAlign: 'center', py: 3 }}>
        <Typography variant="caption" sx={{ color: 'text.disabled' }}>Sin datos</Typography>
      </Box>
    );
  }

  const allPrices = allPoints.map(p => p.precio_oferta || p.precio_normal).filter(Boolean);
  const minPrice = Math.min(...allPrices) * 0.95;
  const maxPrice = Math.max(...allPrices) * 1.05;
  const priceRange = maxPrice - minPrice || 1;

  const allDates = allPoints.map(p => new Date(p.fecha).getTime());
  const minDate = Math.min(...allDates);
  const maxDate = Math.max(...allDates);
  const dateRange = maxDate - minDate || 1;

  const margin = { top: 10, right: 10, bottom: 25, left: 50 };
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;

  const scaleX = (date) => margin.left + ((new Date(date).getTime() - minDate) / dateRange) * innerW;
  const scaleY = (price) => margin.top + innerH - ((price - minPrice) / priceRange) * innerH;

  const provColors = { Sodimac: COLOR_SODIMAC, Easy: COLOR_EASY };

  return (
    <svg width={width} height={height} style={{ display: 'block' }}>
      {/* Grid lines */}
      {[0, 0.25, 0.5, 0.75, 1].map((frac) => {
        const y = margin.top + innerH * (1 - frac);
        const price = minPrice + priceRange * frac;
        return (
          <g key={frac}>
            <line x1={margin.left} y1={y} x2={width - margin.right} y2={y}
              stroke="rgba(0,0,0,0.06)" strokeDasharray="3,3" />
            <text x={margin.left - 5} y={y + 3} textAnchor="end"
              fill="#999" fontSize="8" fontFamily="Space Grotesk">
              {formatCLP(price)}
            </text>
          </g>
        );
      })}

      {/* Lines per provider */}
      {Object.entries(series).map(([prov, points]) => {
        if (points.length < 2) return null;
        const sorted = [...points].sort((a, b) => new Date(a.fecha) - new Date(b.fecha));
        const color = provColors[prov] || '#888';

        const pathD = sorted.map((p, i) => {
          const x = scaleX(p.fecha);
          const y = scaleY(p.precio_oferta || p.precio_normal);
          return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
        }).join(' ');

        return (
          <g key={prov}>
            <path d={pathD} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" />
            {sorted.map((p, i) => (
              <circle key={i}
                cx={scaleX(p.fecha)}
                cy={scaleY(p.precio_oferta || p.precio_normal)}
                r="3" fill={color} stroke="#fff" strokeWidth="1"
              />
            ))}
          </g>
        );
      })}

      {/* Legend */}
      {Object.entries(series).map(([prov, _], i) => (
        <g key={prov} transform={`translate(${margin.left + i * 80}, ${height - 8})`}>
          <circle cx="4" cy="-2" r="4" fill={provColors[prov] || '#888'} />
          <text x="12" y="2" fill="#666" fontSize="9" fontFamily="Space Grotesk">{prov}</text>
        </g>
      ))}
    </svg>
  );
}

// ---------------------------------------------------------------------------
// AlertaRow — fila de alerta de precio
// ---------------------------------------------------------------------------

function AlertaRow({ alerta }) {
  const esGrande = Math.abs(alerta.cambio_pct) > 10;
  return (
    <Paper elevation={0} sx={{
      p: 1.5, borderRadius: 2, display: 'flex', alignItems: 'center', gap: 1.5,
      border: `1px solid ${esGrande ? 'rgba(16,185,129,0.3)' : 'rgba(28,35,43,0.06)'}`,
      backgroundColor: esGrande ? 'rgba(16,185,129,0.04)' : 'transparent',
    }}>
      <Typography sx={{ fontSize: '1.3rem' }}>
        {alerta.cambio_pct < -10 ? '🔥' : '📉'}
      </Typography>
      <Box sx={{ flexGrow: 1, minWidth: 0 }}>
        <Typography variant="body2" sx={{
          fontWeight: 700, whiteSpace: 'nowrap', overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}>
          {alerta.nombre}
        </Typography>
        <Typography variant="caption" sx={{ color: 'text.secondary' }}>
          {alerta.proveedor}
        </Typography>
      </Box>
      <Box sx={{ textAlign: 'right', flexShrink: 0 }}>
        <Typography variant="body2" sx={{
          fontWeight: 800,
          color: '#10b981',
        }}>
          {alerta.cambio_pct}%
        </Typography>
        <Typography variant="caption" sx={{ color: 'text.disabled', fontSize: '0.65rem' }}>
          {formatCLP(alerta.precio_anterior)} → {formatCLP(alerta.precio_actual)}
        </Typography>
      </Box>
    </Paper>
  );
}

// ---------------------------------------------------------------------------
// HistorialDialog — detalle de historial de un canonical
// ---------------------------------------------------------------------------

function HistorialDialog({ canonicalId, nombre, open, onClose }) {
  const [historial, setHistorial] = useState(null);
  const [loading, setLoading] = useState(false);
  const [dias, setDias] = useState(30);

  useEffect(() => {
    if (canonicalId && open) {
      setLoading(true);
      axios.get(`${API}/precios/historial/${canonicalId}?dias=${dias}`)
        .then(res => setHistorial(res.data))
        .catch(() => setHistorial(null))
        .finally(() => setLoading(false));
    }
  }, [canonicalId, open, dias]);

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth
      PaperProps={{ sx: { borderRadius: 4 } }}
    >
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Box sx={{ flexGrow: 1 }}>
          <Typography variant="h6" sx={{ fontWeight: 700 }}>Historial de Precios</Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>{nombre}</Typography>
        </Box>
        <FormControl size="small" sx={{ minWidth: 100 }}>
          <Select value={dias} onChange={(e) => setDias(e.target.value)} sx={{ borderRadius: 2 }}>
            <MenuItem value={7}>7 días</MenuItem>
            <MenuItem value={30}>30 días</MenuItem>
            <MenuItem value={90}>90 días</MenuItem>
          </Select>
        </FormControl>
        <IconButton onClick={onClose} size="small">
          <Typography>✕</Typography>
        </IconButton>
      </DialogTitle>
      <DialogContent>
        {loading ? (
          <Box sx={{ textAlign: 'center', py: 4 }}><CircularProgress size={30} /></Box>
        ) : historial ? (
          <Box>
            <PriceHistoryChart series={historial.series} width={480} height={200} />
            {/* Data table */}
            {Object.entries(historial.series || {}).map(([prov, points]) => (
              <Box key={prov} sx={{ mt: 2 }}>
                <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 0.5 }}>
                  {prov} ({points.length} registros)
                </Typography>
                <Box sx={{ maxHeight: 200, overflow: 'auto' }}>
                  {[...points].reverse().slice(0, 20).map((p, i) => (
                    <Box key={i} sx={{
                      display: 'flex', justifyContent: 'space-between', py: 0.5,
                      borderBottom: '1px solid rgba(0,0,0,0.04)',
                    }}>
                      <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                        {new Date(p.fecha).toLocaleDateString('es-CL')}
                      </Typography>
                      <Typography variant="caption" sx={{ fontWeight: 700 }}>
                        {formatCLP(p.precio_oferta || p.precio_normal)}
                        {p.precio_oferta && (
                          <Typography component="span" variant="caption" sx={{
                            color: 'text.disabled', textDecoration: 'line-through', ml: 0.5,
                          }}>
                            {formatCLP(p.precio_normal)}
                          </Typography>
                        )}
                      </Typography>
                    </Box>
                  ))}
                </Box>
              </Box>
            ))}
          </Box>
        ) : (
          <Typography variant="body2" sx={{ color: 'text.disabled', textAlign: 'center', py: 4 }}>
            Sin datos de historial
          </Typography>
        )}
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Precios — componente principal (Dashboard de precios)
// ---------------------------------------------------------------------------

function Precios() {
  const [catalogo, setCatalogo] = useState([]);
  const [alertas, setAlertas] = useState([]);
  const [estado, setEstado] = useState(null);
  const [schedulerEstado, setSchedulerEstado] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filtro, setFiltro] = useState('');
  const [historialOpen, setHistorialOpen] = useState(null);
  const [syncing, setSyncing] = useState(false);

  const cargar = useCallback(async () => {
    try {
      const [catR, estR, alertR, schR] = await Promise.all([
        axios.get(`${API}/catalogo`),
        axios.get(`${API}/catalogo/estado`),
        axios.get(`${API}/precios/alertas?limite=15`).catch(() => ({ data: [] })),
        axios.get(`${API}/scheduler/estado`).catch(() => ({ data: null })),
      ]);
      // Aplanar: el backend retorna agrupado por familia [{familia, variantes:[...]}]
      // pero Precios necesita lista plana de productos
      const agrupado = catR.data || [];
      const plano = agrupado.flatMap((f) =>
        (f.variantes || []).map((v) => ({ ...v, categoria: f.familia }))
      );
      setCatalogo(plano);
      setEstado(estR.data || null);
      setAlertas(alertR.data || []);
      setSchedulerEstado(schR.data || null);
    } catch (err) {
      console.error('Error cargando datos:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { cargar(); }, [cargar]);

  // Estadísticas
  const totalProductos = catalogo.length;
  const conAmbos = catalogo.filter(p => p.precio_sodimac != null && p.precio_easy != null).length;
  const ahorroTotal = catalogo.reduce((sum, p) => sum + (p.ahorro || 0), 0);
  const mejorSodimac = catalogo.filter(p => p.mejor_tienda === 'Sodimac').length;
  const mejorEasy = catalogo.filter(p => p.mejor_tienda === 'Easy').length;

  // Productos filtrados
  const productosFiltrados = catalogo.filter(p => {
    if (!filtro.trim()) return true;
    const t = filtro.toLowerCase();
    return p.nombre?.toLowerCase().includes(t)
      || (p.nombre_sodimac || '').toLowerCase().includes(t)
      || (p.nombre_easy || '').toLowerCase().includes(t);
  });

  const handleSync = async () => {
    setSyncing(true);
    try {
      await axios.post(`${API}/catalogo/sync`);
    } catch {}
    setTimeout(() => setSyncing(false), 5000);
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', gap: 2 }}>
        <CircularProgress size={36} />
        <Typography>Cargando dashboard...</Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5, height: '100%', minHeight: 0 }}>

      {/* Header */}
      <Paper sx={{ p: 2.5, borderRadius: 3 }}>
        <Box sx={{ display: 'flex', flexDirection: { xs: 'column', md: 'row' }, gap: 2, alignItems: { md: 'center' } }}>
          <Box sx={{ flexGrow: 1 }}>
            <Typography variant="h5" sx={{ fontWeight: 700 }}>Dashboard de Precios</Typography>
            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
              Monitoreo de precios Sodimac vs Easy
              {estado?.ultimo_scraping && ` · Actualizado ${tiempoRelativo(estado.ultimo_scraping)}`}
            </Typography>
          </Box>
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
            {schedulerEstado?.scheduler_activo && (
              <Chip label="Sync automático activo" size="small" color="success" variant="outlined"
                sx={{ fontSize: '0.65rem' }} />
            )}
            <Button variant="outlined" size="small" onClick={handleSync} disabled={syncing}
              sx={{ borderRadius: 2, textTransform: 'none', fontWeight: 700 }}>
              {syncing ? 'Sincronizando...' : 'Sync ahora'}
            </Button>
          </Box>
        </Box>
      </Paper>

      {/* Métricas */}
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr 1fr', sm: '1fr 1fr 1fr 1fr 1fr' }, gap: 1.5 }}>
        <MetricCard label="Total Productos" value={totalProductos} icon="📦" />
        <MetricCard label="Con ambas tiendas" value={conAmbos} icon="🔄" color="#3b82f6" />
        <MetricCard label="Ahorro posible" value={formatCLP(ahorroTotal)} icon="💰" color="#10b981" />
        <MetricCard
          label="Mejor Sodimac" value={mejorSodimac} icon="🏠" color={COLOR_SODIMAC}
          subtitle={`${mejorEasy} Easy`}
        />
        <MetricCard
          label="Alertas de precio" value={alertas.length} icon="📉" color="#f59e0b"
          subtitle="caídas recientes"
        />
      </Box>

      {/* Body: Alertas + Tabla */}
      <Box sx={{ flexGrow: 1, display: 'flex', gap: 2.5, minHeight: 0, overflow: 'hidden' }}>

        {/* Alertas sidebar */}
        <Paper elevation={0} sx={{
          width: 320, flexShrink: 0, borderRadius: 3, p: 2,
          border: '1px solid rgba(28,35,43,0.08)',
          display: { xs: 'none', lg: 'flex' }, flexDirection: 'column',
          overflow: 'hidden',
        }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1.5 }}>
            🔥 Caídas de Precio
          </Typography>
          <Box sx={{ flexGrow: 1, overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 1 }}>
            {alertas.length > 0 ? (
              alertas.map((a, i) => <AlertaRow key={i} alerta={a} />)
            ) : (
              <Typography variant="caption" sx={{ color: 'text.disabled', textAlign: 'center', py: 3 }}>
                Sin alertas de precio todavía.
                Los cambios se detectan en cada sync.
              </Typography>
            )}
          </Box>
        </Paper>

        {/* Tabla de productos */}
        <Box sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {/* Search */}
          <Box sx={{ mb: 1.5 }}>
            <TextField
              size="small" fullWidth
              placeholder="Buscar producto..."
              value={filtro}
              onChange={(e) => setFiltro(e.target.value)}
              sx={{ '& .MuiOutlinedInput-root': { borderRadius: 2, backgroundColor: '#fff' } }}
            />
          </Box>

          {/* Table header */}
          <Box sx={{
            display: 'grid',
            gridTemplateColumns: '2fr 1fr 1fr 1fr 80px',
            gap: 1, px: 1.5, py: 1,
            borderRadius: 2,
            backgroundColor: 'rgba(31,58,95,0.04)',
            mb: 0.5,
          }}>
            <Typography variant="caption" sx={{ fontWeight: 700 }}>Producto</Typography>
            <Typography variant="caption" sx={{ fontWeight: 700, textAlign: 'right' }}>Sodimac</Typography>
            <Typography variant="caption" sx={{ fontWeight: 700, textAlign: 'right' }}>Easy</Typography>
            <Typography variant="caption" sx={{ fontWeight: 700, textAlign: 'right' }}>Ahorro</Typography>
            <Typography variant="caption" sx={{ fontWeight: 700, textAlign: 'center' }}>Historial</Typography>
          </Box>

          {/* Rows */}
          <Box sx={{ flexGrow: 1, overflow: 'auto' }}>
            <AnimatePresence mode="popLayout">
              {productosFiltrados.map((p) => {
                const hayAmbos = p.precio_sodimac != null && p.precio_easy != null;
                const ahorro = hayAmbos ? Math.abs(p.precio_sodimac - p.precio_easy) : 0;
                const mejor = p.mejor_tienda;

                return (
                  <motion.div
                    key={p.id}
                    layout
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                  >
                    <Box sx={{
                      display: 'grid',
                      gridTemplateColumns: '2fr 1fr 1fr 1fr 80px',
                      gap: 1, px: 1.5, py: 1.2,
                      borderBottom: '1px solid rgba(28,35,43,0.04)',
                      alignItems: 'center',
                      '&:hover': { backgroundColor: 'rgba(31,58,95,0.02)' },
                      transition: 'background-color 0.1s',
                    }}>
                      {/* Nombre */}
                      <Box sx={{ minWidth: 0 }}>
                        <Typography variant="body2" sx={{
                          fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}>
                          {p.nombre}
                        </Typography>
                        {p.categoria && (
                          <Chip label={p.categoria} size="small" sx={{
                            fontSize: '0.55rem', height: 16, mt: 0.3,
                          }} />
                        )}
                      </Box>

                      {/* Sodimac */}
                      <Typography variant="body2" sx={{
                        textAlign: 'right', fontWeight: 700,
                        color: mejor === 'Sodimac' ? COLOR_SODIMAC : 'text.primary',
                      }}>
                        {p.precio_sodimac != null ? formatCLP(p.precio_sodimac) : '—'}
                        {mejor === 'Sodimac' && hayAmbos && (
                          <Typography component="span" sx={{ fontSize: '0.6rem', ml: 0.3 }}>⭐</Typography>
                        )}
                      </Typography>

                      {/* Easy */}
                      <Typography variant="body2" sx={{
                        textAlign: 'right', fontWeight: 700,
                        color: mejor === 'Easy' ? COLOR_EASY : 'text.primary',
                      }}>
                        {p.precio_easy != null ? formatCLP(p.precio_easy) : '—'}
                        {mejor === 'Easy' && hayAmbos && (
                          <Typography component="span" sx={{ fontSize: '0.6rem', ml: 0.3 }}>⭐</Typography>
                        )}
                      </Typography>

                      {/* Ahorro */}
                      <Typography variant="body2" sx={{
                        textAlign: 'right', fontWeight: 700,
                        color: ahorro > 0 ? '#10b981' : 'text.disabled',
                      }}>
                        {ahorro > 0 ? formatCLP(ahorro) : '—'}
                      </Typography>

                      {/* Historial button */}
                      <Box sx={{ textAlign: 'center' }}>
                        <Tooltip title="Ver historial de precios">
                          <IconButton
                            size="small"
                            onClick={() => setHistorialOpen({ id: p.id, nombre: p.nombre })}
                            sx={{ fontSize: '0.9rem' }}
                          >
                            📊
                          </IconButton>
                        </Tooltip>
                      </Box>
                    </Box>
                  </motion.div>
                );
              })}
            </AnimatePresence>

            {productosFiltrados.length === 0 && (
              <Box sx={{ textAlign: 'center', py: 4 }}>
                <Typography variant="body2" sx={{ color: 'text.disabled' }}>
                  No se encontraron productos
                </Typography>
              </Box>
            )}
          </Box>
        </Box>
      </Box>

      {/* Historial dialog */}
      <HistorialDialog
        canonicalId={historialOpen?.id}
        nombre={historialOpen?.nombre}
        open={!!historialOpen}
        onClose={() => setHistorialOpen(null)}
      />
    </Box>
  );
}

export default Precios;
