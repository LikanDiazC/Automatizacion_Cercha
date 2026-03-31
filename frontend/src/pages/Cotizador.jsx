import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Box,
  Paper,
  Typography,
  TextField,
  Button,
  Divider,
  Chip,
  Table,
  TableHead,
  TableRow,
  TableCell,
  TableBody,
  Alert,
  LinearProgress,
} from '@mui/material';
import { motion, AnimatePresence } from 'framer-motion';
import axios from 'axios';

// ---------------------------------------------------------------------------
// Constantes
// ---------------------------------------------------------------------------

const API = 'http://127.0.0.1:8000/api/compras';
const CARRITO_KEY_STORAGE = 'cercha_carrito_key';

const COLOR_SODIMAC = {
  bg:     'rgba(31, 58, 95, 0.07)',
  border: 'rgba(31, 58, 95, 0.25)',
  text:   '#1f3a5f',
};
const COLOR_EASY = {
  bg:     'rgba(60, 207, 145, 0.10)',
  border: 'rgba(60, 207, 145, 0.35)',
  text:   '#0f6e47',
};
const COLOR_WINNER = {
  bg:     'rgba(60, 207, 145, 0.18)',
  border: '#3ccf91',
};

// Fases semánticas que se muestran mientras el scraper trabaja
// duración en segundos aproximados de cada fase
const FASES_BUSQUEDA = [
  { id: 0, label: 'Conectando con Sodimac',      icono: '🏪', duracion: 3  },
  { id: 1, label: 'Analizando resultados',        icono: '🔍', duracion: 5  },
  { id: 2, label: 'Consultando Easy',             icono: '🛒', duracion: 8  },
  { id: 3, label: 'La IA está comparando',        icono: '🤖', duracion: 6  },
  { id: 4, label: 'Consolidando información',     icono: '✅', duracion: 3  },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const formatCLP = (valor) =>
  valor != null
    ? `$${Math.round(valor).toLocaleString('es-CL')}`
    : '—';

const colorConfianza = (score) => {
  if (score == null) return 'default';
  if (score >= 0.9)  return 'success';
  if (score >= 0.7)  return 'warning';
  return 'error';
};

const precioDeProveedor = (variantes, nombreProveedor) => {
  const v = variantes?.find((p) => p.proveedor === nombreProveedor);
  return v ? (v.precio_oferta ?? v.precio_clp) : null;
};

const imagenProducto = (variantes) =>
  variantes?.find((v) => v.imagen_url)?.imagen_url ?? null;

// ---------------------------------------------------------------------------
// Variantes de animación Framer Motion
// ---------------------------------------------------------------------------

const fadeSlideUp = {
  initial:  { opacity: 0, y: 18 },
  animate:  { opacity: 1, y: 0, transition: { duration: 0.35, ease: 'easeOut' } },
  exit:     { opacity: 0, y: -12, transition: { duration: 0.2 } },
};

const cardVariants = {
  initial:  { opacity: 0, scale: 0.96, y: 14 },
  animate:  { opacity: 1, scale: 1, y: 0 },
  exit:     { opacity: 0, scale: 0.94, y: -8, transition: { duration: 0.15 } },
};

const staggerContainer = {
  animate: { transition: { staggerChildren: 0.08 } },
};

// ---------------------------------------------------------------------------
// EstadoVacio
// ---------------------------------------------------------------------------

function EstadoVacio() {
  return (
    <motion.div key="vacio" {...fadeSlideUp} style={{ flexGrow: 1 }}>
      <Box
        sx={{
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 1.5,
          border: '1px dashed rgba(31, 58, 95, 0.2)',
          borderRadius: 3,
          p: 4,
          backgroundColor: 'rgba(255,255,255,0.4)',
        }}
      >
        <Typography variant="h3" sx={{ lineHeight: 1 }}>🔎</Typography>
        <Typography variant="h6" sx={{ fontWeight: 600, color: 'text.secondary' }}>
          Ingresa un material para cotizar
        </Typography>
        <Typography
          variant="body2"
          sx={{ color: 'text.secondary', textAlign: 'center', maxWidth: 360 }}
        >
          Busca "Tornillo 1/4 pulgada" o "Clavo 2 pulgadas" y compararemos
          precios en Sodimac y Easy en tiempo real con IA.
        </Typography>
      </Box>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// EstadoCargando — con progreso semántico por fases
// ---------------------------------------------------------------------------

function EstadoCargando({ query }) {
  const [faseActual, setFaseActual] = useState(0);
  const [progreso, setProgreso]     = useState(0);
  const intervalRef = useRef(null);
  const tiempoRef   = useRef(0);

  const duracionTotal = FASES_BUSQUEDA.reduce((acc, f) => acc + f.duracion, 0);

  useEffect(() => {
    // Avanzar el progreso cada 100ms
    intervalRef.current = setInterval(() => {
      tiempoRef.current += 0.1;
      const pct = Math.min((tiempoRef.current / duracionTotal) * 100, 96); // cap en 96% — nunca 100% hasta que llegue la respuesta
      setProgreso(pct);

      // Calcular en qué fase estamos por tiempo acumulado
      let acumulado = 0;
      for (let i = 0; i < FASES_BUSQUEDA.length; i++) {
        acumulado += FASES_BUSQUEDA[i].duracion;
        if (tiempoRef.current < acumulado) {
          setFaseActual(i);
          break;
        }
      }
    }, 100);

    return () => clearInterval(intervalRef.current);
  }, []);

  const fase = FASES_BUSQUEDA[faseActual] ?? FASES_BUSQUEDA[FASES_BUSQUEDA.length - 1];

  return (
    <motion.div key="cargando" {...fadeSlideUp} style={{ flexGrow: 1 }}>
      <Box
        sx={{
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 3,
          border: '1px dashed rgba(31, 58, 95, 0.2)',
          borderRadius: 3,
          p: 4,
          backgroundColor: 'rgba(255,255,255,0.4)',
        }}
      >
        {/* Ícono animado de la fase actual */}
        <AnimatePresence mode="wait">
          <motion.div
            key={fase.id}
            initial={{ scale: 0.5, opacity: 0 }}
            animate={{ scale: 1, opacity: 1, transition: { type: 'spring', stiffness: 260, damping: 20 } }}
            exit={{ scale: 0.5, opacity: 0, transition: { duration: 0.15 } }}
          >
            <Typography sx={{ fontSize: '2.8rem', lineHeight: 1 }}>{fase.icono}</Typography>
          </motion.div>
        </AnimatePresence>

        {/* Texto de fase con transición suave */}
        <Box sx={{ textAlign: 'center', minHeight: 48 }}>
          <AnimatePresence mode="wait">
            <motion.div
              key={fase.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0, transition: { duration: 0.3 } }}
              exit={{ opacity: 0, y: -8, transition: { duration: 0.15 } }}
            >
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                {fase.label}...
              </Typography>
              <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.3 }}>
                Cotizando "{query}"
              </Typography>
            </motion.div>
          </AnimatePresence>
        </Box>

        {/* Barra de progreso animada */}
        <Box sx={{ width: '100%', maxWidth: 360 }}>
          <LinearProgress
            variant="determinate"
            value={progreso}
            sx={{
              height: 6,
              borderRadius: 999,
              backgroundColor: 'rgba(31, 58, 95, 0.1)',
              '& .MuiLinearProgress-bar': {
                borderRadius: 999,
                background: 'linear-gradient(90deg, #1f3a5f 0%, #3ccf91 100%)',
                transition: 'transform 0.2s linear',
              },
            }}
          />
          <Typography
            variant="caption"
            sx={{ color: 'text.secondary', mt: 0.8, display: 'block', textAlign: 'right' }}
          >
            {Math.round(progreso)}%
          </Typography>
        </Box>

        {/* Indicadores de fases (puntos) */}
        <Box sx={{ display: 'flex', gap: 1 }}>
          {FASES_BUSQUEDA.map((f) => (
            <motion.div
              key={f.id}
              animate={{
                scale:           f.id === faseActual ? 1.3 : 1,
                backgroundColor: f.id <= faseActual ? '#1f3a5f' : 'rgba(31,58,95,0.15)',
              }}
              transition={{ duration: 0.2 }}
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                backgroundColor: 'rgba(31,58,95,0.15)',
              }}
            />
          ))}
        </Box>
      </Box>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// SkeletonTarjeta — placeholder mientras carga
// ---------------------------------------------------------------------------

function SkeletonTarjeta() {
  return (
    <Paper
      sx={{
        p: 2,
        borderRadius: 3,
        display: 'flex',
        flexDirection: 'column',
        gap: 1.5,
        overflow: 'hidden',
        position: 'relative',
      }}
    >
      <Box sx={{ display: 'flex', gap: 1.5 }}>
        <Box
          sx={{
            width: 56, height: 56, borderRadius: 2,
            background: 'linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%)',
            backgroundSize: '200% 100%',
            animation: 'shimmer 1.4s infinite',
            flexShrink: 0,
          }}
        />
        <Box sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column', gap: 1 }}>
          <Box sx={{ height: 16, borderRadius: 1, background: 'linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%)', backgroundSize: '200% 100%', animation: 'shimmer 1.4s infinite', width: '80%' }} />
          <Box sx={{ height: 12, borderRadius: 1, background: 'linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%)', backgroundSize: '200% 100%', animation: 'shimmer 1.4s infinite 0.1s', width: '50%' }} />
        </Box>
      </Box>
      <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1 }}>
        {[0, 1].map((i) => (
          <Box
            key={i}
            sx={{
              height: 60, borderRadius: 2,
              background: 'linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%)',
              backgroundSize: '200% 100%',
              animation: `shimmer 1.4s infinite ${i * 0.1}s`,
            }}
          />
        ))}
      </Box>
      <style>{`
        @keyframes shimmer {
          0%   { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
      `}</style>
    </Paper>
  );
}

// ---------------------------------------------------------------------------
// TarjetaProducto
// ---------------------------------------------------------------------------

function TarjetaProducto({ resultado, onAgregar, cargandoCarrito }) {
  const { canonical, variantes, confidence_score } = resultado;
  const nombre   = variantes?.[0]?.nombre_raw || canonical?.nombre_normalizado || 'Producto';
  const imagen   = imagenProducto(variantes);

  const precioSodimac = precioDeProveedor(variantes, 'Sodimac');
  const precioEasy    = precioDeProveedor(variantes, 'Easy');

  const hayAmbos  = precioSodimac != null && precioEasy != null;
  const masBarato = hayAmbos
    ? (precioSodimac <= precioEasy ? 'Sodimac' : 'Easy')
    : null;
  const ahorro    = hayAmbos ? Math.abs(precioSodimac - precioEasy) : null;

  return (
    <motion.div variants={cardVariants}>
      <Paper
        sx={{
          p: 2,
          borderRadius: 3,
          display: 'flex',
          flexDirection: 'column',
          gap: 1.5,
          transition: 'box-shadow 0.18s, transform 0.18s',
          '&:hover': {
            boxShadow: '0 6px 24px rgba(31,35,40,0.12)',
            transform: 'translateY(-2px)',
          },
        }}
      >
        {/* Cabecera */}
        <Box sx={{ display: 'flex', gap: 1.5, alignItems: 'flex-start' }}>
          {imagen && (
            <Box
              component="img"
              src={imagen}
              alt={nombre}
              sx={{
                width: 56, height: 56,
                objectFit: 'contain',
                borderRadius: 2,
                border: '1px solid rgba(28,35,43,0.08)',
                flexShrink: 0,
                backgroundColor: '#fafafa',
              }}
              onError={(e) => { e.target.style.display = 'none'; }}
            />
          )}
          <Box sx={{ flexGrow: 1, minWidth: 0 }}>
            <Typography
              variant="subtitle1"
              sx={{
                fontWeight: 600, lineHeight: 1.3,
                overflow: 'hidden', textOverflow: 'ellipsis',
                display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
              }}
            >
              {nombre}
            </Typography>
            {confidence_score != null && (
              <Chip
                label={`Confianza IA: ${Math.round(confidence_score * 100)}%`}
                size="small"
                color={colorConfianza(confidence_score)}
                variant="outlined"
                sx={{ mt: 0.5, fontWeight: 700 }}
              />
            )}
          </Box>
        </Box>

        {/* Precios */}
        <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1 }}>
          {[
            { nombre: 'Sodimac', precio: precioSodimac, color: COLOR_SODIMAC },
            { nombre: 'Easy',    precio: precioEasy,    color: COLOR_EASY    },
          ].map(({ nombre: prov, precio, color }) => (
            <Box
              key={prov}
              sx={{
                p: 1.2, borderRadius: 2,
                backgroundColor: masBarato === prov ? COLOR_WINNER.bg : color.bg,
                border: `1px solid ${masBarato === prov ? COLOR_WINNER.border : color.border}`,
              }}
            >
              <Typography variant="caption" sx={{ color: color.text, fontWeight: 700, display: 'block' }}>
                {prov}
              </Typography>
              <Typography variant="h6" sx={{ fontWeight: 700, color: color.text, lineHeight: 1.2 }}>
                {formatCLP(precio)}
              </Typography>
              {masBarato === prov && (
                <Typography variant="caption" sx={{ color: COLOR_EASY.text, fontWeight: 700 }}>
                  más barato
                </Typography>
              )}
            </Box>
          ))}
        </Box>

        {/* Diferencia */}
        {hayAmbos && ahorro > 0 && (
          <Typography variant="caption" sx={{ color: 'text.secondary' }}>
            Diferencia: {formatCLP(ahorro)} — ahorra comprando en {masBarato}
          </Typography>
        )}
        {!hayAmbos && (
          <Typography variant="caption" sx={{ color: 'text.secondary' }}>
            {precioSodimac == null ? 'Sin precio en Sodimac.' : 'Sin precio en Easy.'}
          </Typography>
        )}

        <Button
          variant="outlined"
          size="small"
          disabled={cargandoCarrito || canonical?.id == null || canonical?.id === 0}
          onClick={() => onAgregar(resultado)}
          sx={{ alignSelf: 'flex-end', borderRadius: 999 }}
        >
          Agregar al carrito
        </Button>
      </Paper>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// ResumenCotizacion
// ---------------------------------------------------------------------------

function ResumenCotizacion({ resumen, onNuevaCotizacion }) {
  return (
    <motion.div key="resumen" {...fadeSlideUp} style={{ display: 'flex', flexDirection: 'column', gap: 20, flexGrow: 1 }}>
      {/* KPIs */}
      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 1.5 }}>
        {[
          { label: 'Total Sodimac',     valor: resumen.total_sodimac, color: COLOR_SODIMAC },
          { label: 'Total Easy',        valor: resumen.total_easy,    color: COLOR_EASY    },
          {
            label: 'Ahorro potencial',
            valor: resumen.ahorro_potencial,
            color: { bg: 'rgba(60,207,145,0.15)', border: '#3ccf91', text: '#0f6e47' },
            extra: `${resumen.ahorro_porcentaje?.toFixed(1) ?? 0}%`,
          },
        ].map(({ label, valor, color, extra }) => (
          <Box
            key={label}
            sx={{
              p: 1.5, borderRadius: 2,
              backgroundColor: color.bg,
              border: `1px solid ${color.border}`,
              display: 'flex', flexDirection: 'column', gap: 0.3,
            }}
          >
            <Typography variant="caption" sx={{ color: color.text, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.8 }}>
              {label}
            </Typography>
            <Typography variant="h5" sx={{ fontWeight: 700, color: color.text }}>
              {formatCLP(valor)}
            </Typography>
            {extra && (
              <Typography variant="caption" sx={{ color: color.text, fontWeight: 600 }}>
                {extra} de ahorro
              </Typography>
            )}
          </Box>
        ))}
      </Box>

      <Alert severity="success" sx={{ borderRadius: 2, fontWeight: 600 }}>
        Conviene comprar en <strong>{resumen.proveedor_optimo}</strong> — ahorras{' '}
        {formatCLP(resumen.ahorro_potencial)} ({resumen.ahorro_porcentaje?.toFixed(1)}%)
        sobre el precio del otro proveedor.
      </Alert>

      {resumen.advertencias?.length > 0 && (
        <Alert severity="warning" sx={{ borderRadius: 2 }}>
          {resumen.advertencias.join(' ')}
        </Alert>
      )}

      <Typography variant="subtitle2" sx={{ color: 'text.secondary', letterSpacing: 1, textTransform: 'uppercase' }}>
        Detalle por ítem
      </Typography>

      <Box sx={{ overflow: 'auto', flexGrow: 1 }}>
        <Table size="small" stickyHeader>
          <TableHead>
            <TableRow>
              <TableCell>Producto</TableCell>
              <TableCell align="center">Cant.</TableCell>
              <TableCell align="right">Sodimac</TableCell>
              <TableCell align="right">Easy</TableCell>
              <TableCell align="right">Mejor</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {resumen.detalle?.map((item, i) => {
              const ps  = item.precio_sodimac;
              const pe  = item.precio_easy;
              const mejor = ps != null && pe != null
                ? (ps <= pe ? { precio: ps, prov: 'Sodimac' } : { precio: pe, prov: 'Easy' })
                : null;
              return (
                <TableRow key={i} hover>
                  <TableCell sx={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {item.query_original || `Producto ${item.canonical_id}`}
                  </TableCell>
                  <TableCell align="center">{item.cantidad}</TableCell>
                  <TableCell align="right">{formatCLP(ps ? ps * item.cantidad : null)}</TableCell>
                  <TableCell align="right">{formatCLP(pe ? pe * item.cantidad : null)}</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700, color: '#0f6e47' }}>
                    {mejor ? `${formatCLP(mejor.precio * item.cantidad)} (${mejor.prov})` : '—'}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </Box>

      <Button variant="outlined" onClick={onNuevaCotizacion} sx={{ alignSelf: 'flex-start', borderRadius: 999 }}>
        Nueva cotización
      </Button>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

function Cotizador() {
  const [query, setQuery]                     = useState('');
  const [buscando, setBuscando]               = useState(false);
  const [resultados, setResultados]           = useState([]);
  const [errorBusqueda, setError]             = useState('');
  const [carritoKey, setCarritoKey]           = useState(() => localStorage.getItem(CARRITO_KEY_STORAGE) || null);
  const [carritoItems, setCarritoItems]       = useState([]);
  const [cargandoCarrito, setCargandoCarrito] = useState(false);
  const [resumen, setResumen]                 = useState(null);
  const [vista, setVista]                     = useState('resultados');

  // Cargar carrito existente al montar
  useEffect(() => {
    if (!carritoKey) return;
    axios
      .get(`${API}/carrito/${carritoKey}`)
      .then((r) => setCarritoItems(r.data?.items || []))
      .catch(() => {
        localStorage.removeItem(CARRITO_KEY_STORAGE);
        setCarritoKey(null);
        setCarritoItems([]);
      });
  }, [carritoKey]);

  const handleBuscar = useCallback(async () => {
    const q = query.trim();
    if (!q || buscando) return;

    setBuscando(true);
    setError('');
    setResultados([]);
    setResumen(null);
    setVista('resultados');

    try {
      const resp = await axios.post(
        `${API}/buscar`,
        { query: q, proveedores: ['Sodimac', 'Easy'], max_resultados: 10 },
        { timeout: 45_000 },
      );
      setResultados(resp.data || []);
      if (!resp.data?.length) {
        setError('No se encontraron productos. Intenta con términos más específicos o usa el caché.');
      }
    } catch (err) {
      const msg = err?.response?.data?.detail || err?.message || 'Error al conectar con los proveedores.';
      setError(msg);
    } finally {
      setBuscando(false);
    }
  }, [query, buscando]);

  const handleBuscarCache = useCallback(async () => {
    const q = query.trim();
    if (!q || buscando) return;

    setBuscando(true);
    setError('');
    setResultados([]);
    setVista('resultados');

    try {
      const resp = await axios.get(`${API}/buscar/cache`, {
        params: { query: q, max_resultados: 10 },
      });
      setResultados(resp.data || []);
      if (!resp.data?.length) {
        setError('Sin resultados en caché. Usa "Buscar en vivo" para scrapear los proveedores.');
      }
    } catch (err) {
      setError(err?.response?.data?.detail || 'Error consultando el caché.');
    } finally {
      setBuscando(false);
    }
  }, [query, buscando]);

  const obtenerOCrearCarrito = useCallback(async () => {
    if (carritoKey) return carritoKey;
    const resp = await axios.post(`${API}/carrito`);
    const key  = resp.data.session_key;
    localStorage.setItem(CARRITO_KEY_STORAGE, key);
    setCarritoKey(key);
    return key;
  }, [carritoKey]);

  const handleAgregar = useCallback(async (resultado) => {
    const canonicalId = resultado?.canonical?.id;
    if (!canonicalId || canonicalId === 0) return;

    setCargandoCarrito(true);
    try {
      const key  = await obtenerOCrearCarrito();
      const resp = await axios.post(`${API}/carrito/${key}/items`, {
        canonical_id:   canonicalId,
        cantidad:       1,
        query_original: resultado.canonical?.nombre_normalizado || query,
      });
      setCarritoItems(resp.data?.items || []);
    } catch (err) {
      alert(err?.response?.data?.detail || 'Error al agregar al carrito.');
    } finally {
      setCargandoCarrito(false);
    }
  }, [obtenerOCrearCarrito, query]);

  const handleEliminarItem = useCallback(async (itemId) => {
    if (!carritoKey) return;
    try {
      const resp = await axios.delete(`${API}/carrito/${carritoKey}/items/${itemId}`);
      setCarritoItems(resp.data?.items || []);
    } catch (err) {
      alert(err?.response?.data?.detail || 'Error al eliminar ítem.');
    }
  }, [carritoKey]);

  const handleProcesar = useCallback(async () => {
    if (!carritoKey || carritoItems.length === 0) return;
    setCargandoCarrito(true);
    try {
      const resp = await axios.post(`${API}/carrito/${carritoKey}/procesar`);
      setResumen(resp.data);
      setVista('resumen');
      localStorage.removeItem(CARRITO_KEY_STORAGE);
      setCarritoKey(null);
    } catch (err) {
      alert(err?.response?.data?.detail || 'Error al procesar el carrito.');
    } finally {
      setCargandoCarrito(false);
    }
  }, [carritoKey, carritoItems]);

  const handleNuevaCotizacion = () => {
    setQuery('');
    setResultados([]);
    setCarritoItems([]);
    setCarritoKey(null);
    setResumen(null);
    setVista('resultados');
    setError('');
    localStorage.removeItem(CARRITO_KEY_STORAGE);
  };

  const totalSodimacPreview = carritoItems.reduce((acc, i) => acc + (i.precio_sodimac ?? 0) * i.cantidad, 0);
  const totalEasyPreview    = carritoItems.reduce((acc, i) => acc + (i.precio_easy ?? 0) * i.cantidad, 0);

  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: '1fr', lg: '360px 1fr' },
        gap: 2.5,
        alignItems: 'stretch',
        height: '100%',
        minHeight: 0,
      }}
    >
      {/* ---------------------------------------------------------------- */}
      {/* PANEL IZQUIERDO — Búsqueda + Carrito                             */}
      {/* ---------------------------------------------------------------- */}
      <Paper
        sx={{
          p: 2.5, borderRadius: 3,
          display: 'flex', flexDirection: 'column', gap: 2,
          overflow: 'auto',
        }}
      >
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 600, mb: 0.6 }}>
            Cotizador inteligente
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>
            Compara precios de materiales entre Sodimac y Easy en tiempo real.
          </Typography>
        </Box>

        <Divider />

        <Typography variant="subtitle2" sx={{ color: 'text.secondary', letterSpacing: 1, textTransform: 'uppercase' }}>
          Buscar material
        </Typography>

        <TextField
          label="Ej: Tornillo hexagonal 1/4 pulgada"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') handleBuscar(); }}
          disabled={buscando}
          size="small"
          fullWidth
        />

        <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1 }}>
          <Button
            variant="contained"
            onClick={handleBuscar}
            disabled={buscando || !query.trim()}
            sx={{ py: 1.2, borderRadius: 999 }}
          >
            {buscando ? '...' : 'Buscar en vivo'}
          </Button>
          <Button
            variant="outlined"
            onClick={handleBuscarCache}
            disabled={buscando || !query.trim()}
            sx={{ py: 1.2, borderRadius: 999 }}
          >
            Ver caché
          </Button>
        </Box>

        <Divider />

        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Typography variant="subtitle2" sx={{ color: 'text.secondary', letterSpacing: 1, textTransform: 'uppercase' }}>
            Carrito de cotización
          </Typography>
          <Chip label={`${carritoItems.length} ítems`} size="small" variant="outlined" />
        </Box>

        {carritoItems.length === 0 ? (
          <Typography variant="body2" sx={{ color: 'text.secondary', textAlign: 'center', py: 2 }}>
            Agrega productos desde los resultados de búsqueda.
          </Typography>
        ) : (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, flexGrow: 1, overflow: 'auto' }}>
            <AnimatePresence>
              {carritoItems.map((item) => (
                <motion.div
                  key={item.id}
                  layout
                  initial={{ opacity: 0, x: -16 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 16, transition: { duration: 0.15 } }}
                  transition={{ duration: 0.25 }}
                >
                  <Box
                    sx={{
                      p: 1.2, borderRadius: 2,
                      border: '1px solid rgba(28,35,43,0.10)',
                      backgroundColor: 'rgba(255,255,255,0.7)',
                      display: 'flex', flexDirection: 'column', gap: 0.5,
                    }}
                  >
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <Typography variant="caption" sx={{ fontWeight: 600, lineHeight: 1.3, flex: 1, mr: 1 }}>
                        {item.query_original || `Ítem ${item.canonical_id}`}
                      </Typography>
                      <Button
                        size="small" color="error" variant="text"
                        onClick={() => handleEliminarItem(item.id)}
                        sx={{ minWidth: 0, px: 0.8, py: 0, fontWeight: 700, fontSize: '0.7rem' }}
                      >
                        ✕
                      </Button>
                    </Box>
                    <Box sx={{ display: 'flex', gap: 1 }}>
                      <Chip label={`SOD: ${formatCLP(item.precio_sodimac)}`} size="small" variant="outlined" sx={{ fontSize: '0.68rem', height: 20, fontWeight: 600, color: COLOR_SODIMAC.text }} />
                      <Chip label={`EASY: ${formatCLP(item.precio_easy)}`}   size="small" variant="outlined" sx={{ fontSize: '0.68rem', height: 20, fontWeight: 600, color: COLOR_EASY.text }} />
                    </Box>
                  </Box>
                </motion.div>
              ))}
            </AnimatePresence>
          </Box>
        )}

        {carritoItems.length > 0 && (
          <>
            <Divider />
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.6 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                <Typography variant="caption" sx={{ color: COLOR_SODIMAC.text, fontWeight: 700 }}>Total Sodimac (preview)</Typography>
                <Typography variant="caption" sx={{ fontWeight: 700 }}>{formatCLP(totalSodimacPreview)}</Typography>
              </Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                <Typography variant="caption" sx={{ color: COLOR_EASY.text, fontWeight: 700 }}>Total Easy (preview)</Typography>
                <Typography variant="caption" sx={{ fontWeight: 700 }}>{formatCLP(totalEasyPreview)}</Typography>
              </Box>
            </Box>
            <Button
              variant="contained"
              onClick={handleProcesar}
              disabled={cargandoCarrito}
              sx={{ py: 1.3, borderRadius: 999 }}
            >
              {cargandoCarrito ? 'Procesando...' : 'Procesar cotización'}
            </Button>
          </>
        )}
      </Paper>

      {/* ---------------------------------------------------------------- */}
      {/* PANEL DERECHO — Resultados o Resumen                             */}
      {/* ---------------------------------------------------------------- */}
      <Paper
        sx={{
          p: 2.5, borderRadius: 3,
          display: 'flex', flexDirection: 'column', gap: 2,
          minHeight: 0, overflow: 'hidden',
        }}
      >
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 600, mb: 0.4 }}>
            {vista === 'resumen' ? 'Resumen de cotización' : 'Resultados de búsqueda'}
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>
            {vista === 'resumen'
              ? 'Comparación final de precios por proveedor.'
              : buscando
              ? `Consultando proveedores para "${query}"...`
              : resultados.length > 0
              ? `${resultados.length} resultado${resultados.length !== 1 ? 's' : ''} encontrado${resultados.length !== 1 ? 's' : ''}.`
              : 'Usa la búsqueda para comparar materiales en tiempo real.'}
          </Typography>
        </Box>

        {/* Error */}
        <AnimatePresence>
          {errorBusqueda && !buscando && (
            <motion.div key="error" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}>
              <Alert severity="warning" onClose={() => setError('')} sx={{ borderRadius: 2 }}>
                {errorBusqueda}
              </Alert>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Contenido principal */}
        <Box sx={{ flexGrow: 1, overflow: 'auto', display: 'flex', flexDirection: 'column' }}>
          <AnimatePresence mode="wait">
            {vista === 'resumen' && resumen ? (
              <ResumenCotizacion key="resumen" resumen={resumen} onNuevaCotizacion={handleNuevaCotizacion} />
            ) : buscando ? (
              <EstadoCargando key="cargando" query={query} />
            ) : resultados.length === 0 ? (
              <EstadoVacio key="vacio" />
            ) : (
              <motion.div
                key="resultados"
                variants={staggerContainer}
                initial="initial"
                animate="animate"
              >
                <Box
                  sx={{
                    display: 'grid',
                    gridTemplateColumns: { xs: '1fr', md: 'repeat(2, 1fr)', xl: 'repeat(3, 1fr)' },
                    gap: 2,
                    alignContent: 'start',
                  }}
                >
                  {resultados.map((resultado, i) => (
                    <TarjetaProducto
                      key={resultado.canonical?.id ?? i}
                      resultado={resultado}
                      onAgregar={handleAgregar}
                      cargandoCarrito={cargandoCarrito}
                    />
                  ))}
                </Box>
              </motion.div>
            )}
          </AnimatePresence>
        </Box>
      </Paper>
    </Box>
  );
}

export default Cotizador;
