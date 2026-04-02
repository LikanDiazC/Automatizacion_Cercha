import { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Paper,
  Typography,
  TextField,
  Button,
  Divider,
  Chip,
  Alert,
  CircularProgress,
  Dialog,
  DialogTitle,
  DialogContent,
  IconButton,
  Tooltip,
} from '@mui/material';
import { motion, AnimatePresence } from 'framer-motion';
import axios from 'axios';

// ---------------------------------------------------------------------------
// Constantes
// ---------------------------------------------------------------------------

const API = 'http://127.0.0.1:8000/api/compras';

const COLOR_SODIMAC = { bg: 'rgba(31,58,95,0.06)', border: 'rgba(31,58,95,0.22)', text: '#1f3a5f' };
const COLOR_EASY    = { bg: 'rgba(60,207,145,0.08)', border: 'rgba(60,207,145,0.30)', text: '#0f6e47' };

const ICONOS_FAMILIA = {
  'Tornillos': '\uD83D\uDD29', 'Clavos': '\uD83D\uDCCC', 'Pernos': '\u2699\uFE0F',
  'Tuercas y Golillas': '\uD83D\uDD27', 'Tirafondos': '\uD83E\uDE9B',
  'Placas y Conectores': '\uD83D\uDEE0\uFE0F', 'Adhesivos y Sellantes': '\uD83E\uDEAF',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const formatCLP = (v) => v != null ? `$${Math.round(v).toLocaleString('es-CL')}` : null;

const tiempoRelativo = (iso) => {
  if (!iso) return null;
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60)    return 'hace segundos';
  if (s < 3600)  return `hace ${Math.floor(s / 60)} min`;
  if (s < 86400) return `hace ${Math.floor(s / 3600)}h`;
  return `hace ${Math.floor(s / 86400)}d`;
};

const mejorPrecio = (p) => {
  const s = p.precio_sodimac, e = p.precio_easy;
  if (s != null && e != null) return s <= e ? s : e;
  return s ?? e ?? null;
};

const mejorTienda = (p) => {
  const s = p.precio_sodimac, e = p.precio_easy;
  if (s != null && e != null) return s <= e ? 'Sodimac' : 'Easy';
  if (s != null) return 'Sodimac';
  if (e != null) return 'Easy';
  return null;
};

const mejorImagen = (p) => p.imagen_sodimac || p.imagen_easy || null;

// ---------------------------------------------------------------------------
// TarjetaProducto — card visual con mejor precio e imagen
// ---------------------------------------------------------------------------

function TarjetaProducto({ producto, color, familia, onClick }) {
  const precio = mejorPrecio(producto);
  const tienda = mejorTienda(producto);
  const imagen = mejorImagen(producto);
  const hayAmbos = producto.precio_sodimac != null && producto.precio_easy != null;
  const ahorro = hayAmbos ? Math.abs(producto.precio_sodimac - producto.precio_easy) : null;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.94 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.94 }}
      transition={{ duration: 0.2 }}
    >
      <Paper
        elevation={0}
        onClick={onClick}
        sx={{
          border: '1px solid rgba(28,35,43,0.10)',
          borderRadius: 3,
          overflow: 'hidden',
          cursor: 'pointer',
          display: 'flex',
          flexDirection: 'column',
          height: '100%',
          transition: 'box-shadow 0.18s, transform 0.18s, border-color 0.18s',
          '&:hover': {
            boxShadow: '0 8px 28px rgba(31,35,40,0.13)',
            transform: 'translateY(-3px)',
            borderColor: color,
          },
        }}
      >
        {/* Imagen */}
        <Box sx={{
          height: 120,
          background: imagen ? '#fff' : `linear-gradient(135deg, ${color}10 0%, ${color}05 100%)`,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          borderBottom: '1px solid rgba(28,35,43,0.06)',
        }}>
          {imagen ? (
            <Box
              component="img" src={imagen} alt={producto.nombre}
              sx={{ height: 100, maxWidth: '85%', objectFit: 'contain' }}
              onError={(e) => {
                e.target.onerror = null;
                e.target.style.display = 'none';
                e.target.parentElement.innerHTML = `<span style="font-size:2.5rem">${ICONOS_FAMILIA[familia] || '\uD83D\uDCE6'}</span>`;
              }}
            />
          ) : (
            <Typography sx={{ fontSize: '2.5rem', opacity: 0.5 }}>{ICONOS_FAMILIA[familia] || '\uD83D\uDCE6'}</Typography>
          )}
        </Box>

        {/* Info */}
        <Box sx={{ p: 1.5, display: 'flex', flexDirection: 'column', gap: 0.6, flexGrow: 1 }}>
          {/* Categoria */}
          <Chip label={familia} size="small" sx={{
            alignSelf: 'flex-start', fontWeight: 700, fontSize: '0.6rem', height: 18,
            backgroundColor: `${color}15`, color, border: `1px solid ${color}30`,
          }} />

          {/* Nombre */}
          <Typography variant="body2" sx={{
            fontWeight: 700, lineHeight: 1.3, color: '#1c232b', minHeight: 36,
            display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden',
          }}>
            {producto.nombre_sodimac || producto.nombre_easy || producto.nombre}
          </Typography>

          {/* Specs */}
          {producto.specs?.length > 0 && (
            <Box sx={{ display: 'flex', gap: 0.4, flexWrap: 'wrap' }}>
              {producto.specs.map((s, i) => (
                <Typography key={i} variant="caption" sx={{
                  fontSize: '0.62rem', color: 'text.secondary',
                  backgroundColor: 'rgba(0,0,0,0.04)', borderRadius: 0.8, px: 0.5,
                }}>{s}</Typography>
              ))}
            </Box>
          )}

          <Box sx={{ flexGrow: 1 }} />

          {/* Precio */}
          {precio != null ? (
            <Box sx={{ mt: 0.5 }}>
              <Typography variant="h6" sx={{ fontWeight: 800, color: '#1c232b', lineHeight: 1 }}>
                {formatCLP(precio)}
              </Typography>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 0.3 }}>
                <Box sx={{ width: 7, height: 7, borderRadius: '50%', backgroundColor: tienda === 'Sodimac' ? COLOR_SODIMAC.text : COLOR_EASY.text }} />
                <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.68rem' }}>
                  {tienda}
                  {hayAmbos && ahorro > 0 && (
                    <Typography component="span" variant="caption" sx={{ color: '#10b981', fontWeight: 700, ml: 0.5 }}>
                      (ahorras {formatCLP(ahorro)})
                    </Typography>
                  )}
                </Typography>
              </Box>
              {hayAmbos && (
                <Typography variant="caption" sx={{ color: 'text.disabled', fontSize: '0.6rem' }}>
                  {producto.precio_sodimac <= producto.precio_easy
                    ? `Easy: ${formatCLP(producto.precio_easy)}`
                    : `Sodimac: ${formatCLP(producto.precio_sodimac)}`
                  }
                </Typography>
              )}
            </Box>
          ) : (
            <Typography variant="caption" sx={{ color: 'text.disabled', mt: 0.5 }}>
              Sin precio aun
            </Typography>
          )}
        </Box>
      </Paper>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// DetalleProducto — Dialog que muestra el producto en cada tienda
// ---------------------------------------------------------------------------

function DetalleProducto({ producto, open, onClose }) {
  if (!producto) return null;

  const tiendas = [
    {
      nombre: 'Sodimac', color: COLOR_SODIMAC,
      precio: producto.precio_sodimac, nombreProd: producto.nombre_sodimac,
      imagen: producto.imagen_sodimac, sku: producto.sku_sodimac, url: producto.url_sodimac,
    },
    {
      nombre: 'Easy', color: COLOR_EASY,
      precio: producto.precio_easy, nombreProd: producto.nombre_easy,
      imagen: producto.imagen_easy, sku: producto.sku_easy, url: producto.url_easy,
    },
  ];

  const hayAmbos = producto.precio_sodimac != null && producto.precio_easy != null;
  const mejor    = mejorTienda(producto);
  const ahorro   = hayAmbos ? Math.abs(producto.precio_sodimac - producto.precio_easy) : 0;

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth
      PaperProps={{ sx: { borderRadius: 4, overflow: 'hidden' } }}
    >
      {/* Header */}
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1.5, pb: 1 }}>
        <Box sx={{ flexGrow: 1 }}>
          <Typography variant="h6" sx={{ fontWeight: 700, lineHeight: 1.3 }}>
            {producto.nombre}
          </Typography>
          {producto.specs?.length > 0 && (
            <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', mt: 0.5 }}>
              {producto.specs.map((s, i) => (
                <Chip key={i} label={s} size="small" variant="outlined" sx={{ fontSize: '0.65rem', height: 20 }} />
              ))}
            </Box>
          )}
        </Box>
        <IconButton onClick={onClose} sx={{ alignSelf: 'flex-start' }}>
          <Typography sx={{ fontSize: '1.2rem' }}>{'\u2715'}</Typography>
        </IconButton>
      </DialogTitle>

      <DialogContent sx={{ pt: 0 }}>
        {/* Ahorro banner */}
        {hayAmbos && ahorro > 0 && (
          <Alert severity="success" icon={false} sx={{ mb: 2, borderRadius: 2, fontWeight: 700 }}>
            Ahorras {formatCLP(ahorro)} comprando en {mejor}
          </Alert>
        )}

        {/* Cards de tienda */}
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' }, gap: 2 }}>
          {tiendas.map((t) => {
            const esMejor = mejor === t.nombre;
            return (
              <Paper
                key={t.nombre}
                elevation={0}
                sx={{
                  border: `2px solid ${esMejor ? '#3ccf91' : t.color.border}`,
                  borderRadius: 3,
                  overflow: 'hidden',
                  position: 'relative',
                  backgroundColor: esMejor ? 'rgba(60,207,145,0.05)' : '#fff',
                }}
              >
                {/* Badge mejor precio */}
                {esMejor && hayAmbos && (
                  <Box sx={{
                    position: 'absolute', top: 8, right: 8, zIndex: 1,
                    backgroundColor: '#10b981', color: '#fff', borderRadius: 2,
                    px: 1, py: 0.3, fontSize: '0.65rem', fontWeight: 800,
                  }}>
                    MEJOR PRECIO
                  </Box>
                )}

                {/* Imagen */}
                <Box sx={{
                  height: 140, backgroundColor: '#fafafa',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  borderBottom: `1px solid ${t.color.border}`,
                }}>
                  {t.imagen ? (
                    <Box component="img" src={t.imagen} alt={t.nombreProd}
                      sx={{ height: 120, maxWidth: '90%', objectFit: 'contain' }}
                      onError={(e) => { e.target.style.display = 'none'; }}
                    />
                  ) : (
                    <Typography sx={{ color: 'text.disabled', fontSize: '0.85rem' }}>
                      {t.precio != null ? 'Sin imagen' : 'No disponible'}
                    </Typography>
                  )}
                </Box>

                {/* Info */}
                <Box sx={{ p: 2 }}>
                  {/* Logo tienda */}
                  <Chip label={t.nombre} size="small" sx={{
                    fontWeight: 800, fontSize: '0.7rem', height: 22, mb: 1,
                    backgroundColor: t.color.text, color: '#fff',
                  }} />

                  {/* Nombre producto real */}
                  <Typography variant="body2" sx={{
                    fontWeight: 600, lineHeight: 1.3, mb: 0.5, minHeight: 38,
                    display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden',
                    color: t.precio != null ? '#1c232b' : 'text.disabled',
                  }}>
                    {t.nombreProd || 'Producto no encontrado'}
                  </Typography>

                  {/* SKU */}
                  {t.sku && (
                    <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', mb: 1 }}>
                      SKU: {t.sku}
                    </Typography>
                  )}

                  {/* Precio */}
                  {t.precio != null ? (
                    <Typography variant="h5" sx={{ fontWeight: 800, color: t.color.text }}>
                      {formatCLP(t.precio)}
                    </Typography>
                  ) : (
                    <Typography variant="body2" sx={{ color: 'text.disabled', fontStyle: 'italic' }}>
                      No encontrado en esta tienda
                    </Typography>
                  )}

                  {/* Link a tienda */}
                  {t.url && (
                    <Button
                      component="a" href={t.url} target="_blank" rel="noopener noreferrer"
                      size="small" variant="outlined" fullWidth
                      sx={{
                        mt: 1.5, borderRadius: 2, textTransform: 'none', fontWeight: 700,
                        borderColor: t.color.text, color: t.color.text,
                        '&:hover': { backgroundColor: `${t.color.text}08` },
                      }}
                    >
                      Ver en {t.nombre}
                    </Button>
                  )}
                </Box>
              </Paper>
            );
          })}
        </Box>

        {/* Timestamp */}
        {producto.scraped_at && (
          <Typography variant="caption" sx={{ color: 'text.disabled', display: 'block', textAlign: 'center', mt: 2 }}>
            Precios actualizados {tiempoRelativo(producto.scraped_at)}
          </Typography>
        )}
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Componente principal — Cotizador
// ---------------------------------------------------------------------------

function Cotizador() {
  const [catalogo, setCatalogo]           = useState([]);
  const [cargando, setCargando]           = useState(true);
  const [estado, setEstado]               = useState(null);
  const [familiaActiva, setFamiliaActiva] = useState('Todos');
  const [filtro, setFiltro]               = useState('');
  const [productoDetalle, setDetalle]     = useState(null);
  const [syncing, setSyncing]             = useState(false);
  const [syncMsg, setSyncMsg]             = useState('');

  // Cargar catalogo
  const cargarCatalogo = useCallback(async () => {
    try {
      const [catR, estR] = await Promise.all([
        axios.get(`${API}/catalogo`),
        axios.get(`${API}/catalogo/estado`),
      ]);
      setCatalogo(catR.data || []);
      setEstado(estR.data || null);
    } catch (err) {
      console.error('Error cargando catalogo:', err);
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => { cargarCatalogo(); }, [cargarCatalogo]);

  // Lista plana
  const todosProductos = catalogo.flatMap((f) =>
    (f.variantes || []).map((v) => ({ ...v, familia: f.familia, color: f.color }))
  );

  const productosFiltrados = todosProductos.filter((p) => {
    const mF = familiaActiva === 'Todos' || p.familia === familiaActiva;
    const mT = !filtro.trim() || p.nombre.toLowerCase().includes(filtro.toLowerCase())
      || (p.nombre_sodimac || '').toLowerCase().includes(filtro.toLowerCase())
      || (p.nombre_easy || '').toLowerCase().includes(filtro.toLowerCase());
    return mF && mT;
  });

  // Contadores
  const conPrecio = productosFiltrados.filter((p) => p.precio_sodimac != null || p.precio_easy != null).length;
  const sinPrecio = productosFiltrados.length - conPrecio;

  // Sync
  const handleSync = async () => {
    if (syncing) return;
    setSyncing(true);
    setSyncMsg('Sincronizacion iniciada... esto toma varios minutos.');
    try {
      await axios.post(`${API}/catalogo/sync`);
      setSyncMsg('Sync en proceso. Recarga la pagina en unos minutos para ver precios actualizados.');
    } catch { setSyncMsg('Error al iniciar sync.'); }
    setTimeout(() => { setSyncing(false); setSyncMsg(''); }, 8000);
  };

  // Sync de un solo item
  const handleSyncItem = async (query) => {
    try {
      await axios.post(`${API}/catalogo/sync-item`, {
        query, proveedores: ['Sodimac', 'Easy'], max_resultados: 5,
      }, { timeout: 90_000 });
      await cargarCatalogo();
    } catch (err) {
      console.error('Error syncing:', err);
    }
  };

  if (cargando) {
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', gap: 2 }}>
        <CircularProgress size={36} />
        <Typography variant="body1" sx={{ color: 'text.secondary' }}>Cargando catalogo...</Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5, height: '100%', minHeight: 0 }}>

      {/* ---- HEADER ---- */}
      <Paper sx={{ p: 2.5, borderRadius: 3, display: 'flex', flexDirection: { xs: 'column', md: 'row' }, gap: 2, alignItems: { md: 'center' } }}>
        <Box sx={{ flexGrow: 1 }}>
          <Typography variant="h5" sx={{ fontWeight: 700 }}>Catalogo de Materiales</Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>
            {conPrecio} productos con precio
            {sinPrecio > 0 ? ` \u2022 ${sinPrecio} pendientes de sync` : ''}
            {estado?.ultimo_scraping && ` \u2022 Actualizado ${tiempoRelativo(estado.ultimo_scraping)}`}
          </Typography>
        </Box>

        {/* Busqueda */}
        <TextField
          size="small"
          placeholder="Filtrar productos..."
          value={filtro}
          onChange={(e) => setFiltro(e.target.value)}
          sx={{
            width: { xs: '100%', md: 280 },
            '& .MuiOutlinedInput-root': { borderRadius: 2, backgroundColor: '#fff' },
          }}
        />

        {/* Sync */}
        <Tooltip title="Escanea todos los productos en Sodimac y Easy">
          <Button
            variant="outlined" size="small"
            onClick={handleSync} disabled={syncing}
            sx={{ borderRadius: 2, textTransform: 'none', fontWeight: 700, whiteSpace: 'nowrap' }}
          >
            {syncing ? 'Sincronizando...' : 'Actualizar precios'}
          </Button>
        </Tooltip>
      </Paper>

      {syncMsg && (
        <Alert severity="info" onClose={() => setSyncMsg('')} sx={{ borderRadius: 2 }}>{syncMsg}</Alert>
      )}

      {/* ---- CHIPS DE FAMILIA ---- */}
      <Box sx={{ display: 'flex', gap: 0.8, flexWrap: 'wrap', px: 0.5 }}>
        <Chip
          label={`Todos (${todosProductos.length})`}
          size="small"
          onClick={() => setFamiliaActiva('Todos')}
          sx={{
            fontWeight: 700, fontSize: '0.75rem', borderRadius: 2, cursor: 'pointer',
            backgroundColor: familiaActiva === 'Todos' ? '#1f3a5f' : 'rgba(31,58,95,0.08)',
            color: familiaActiva === 'Todos' ? '#fff' : '#1f3a5f',
            '&:hover': { opacity: 0.85 },
          }}
        />
        {catalogo.map((fam) => {
          const cnt = fam.variantes?.length || 0;
          return (
            <Chip
              key={fam.familia}
              label={`${fam.familia} (${cnt})`}
              size="small"
              onClick={() => setFamiliaActiva(fam.familia)}
              sx={{
                fontWeight: 600, fontSize: '0.72rem', borderRadius: 2, cursor: 'pointer',
                backgroundColor: familiaActiva === fam.familia ? fam.color : `${fam.color}15`,
                color: familiaActiva === fam.familia ? '#fff' : fam.color,
                border: `1px solid ${familiaActiva === fam.familia ? fam.color : `${fam.color}40`}`,
                '&:hover': { opacity: 0.85 },
              }}
            />
          );
        })}
      </Box>

      {/* ---- GRID DE PRODUCTOS ---- */}
      <Box sx={{ flexGrow: 1, overflow: 'auto', pb: 2 }}>
        <Box sx={{
          display: 'grid',
          gridTemplateColumns: {
            xs: 'repeat(2, 1fr)',
            sm: 'repeat(3, 1fr)',
            md: 'repeat(4, 1fr)',
            lg: 'repeat(5, 1fr)',
            xl: 'repeat(6, 1fr)',
          },
          gap: 2,
          alignContent: 'start',
        }}>
          <AnimatePresence mode="popLayout">
            {productosFiltrados.map((p) => (
              <TarjetaProducto
                key={p.query}
                producto={p}
                color={p.color}
                familia={p.familia}
                onClick={() => setDetalle(p)}
              />
            ))}
          </AnimatePresence>
        </Box>

        {productosFiltrados.length === 0 && (
          <Box sx={{ textAlign: 'center', py: 6 }}>
            <Typography variant="h6" sx={{ color: 'text.secondary', mb: 1 }}>No se encontraron productos</Typography>
            <Typography variant="body2" sx={{ color: 'text.disabled' }}>Cambia el filtro o la categoria</Typography>
          </Box>
        )}
      </Box>

      {/* ---- DIALOG DETALLE ---- */}
      <DetalleProducto
        producto={productoDetalle}
        open={!!productoDetalle}
        onClose={() => setDetalle(null)}
      />
    </Box>
  );
}

export default Cotizador;
