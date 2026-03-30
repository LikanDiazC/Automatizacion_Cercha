import { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Paper,
  Typography,
  TextField,
  Button,
  Divider,
  Chip,
  CircularProgress,
  Table,
  TableHead,
  TableRow,
  TableCell,
  TableBody,
  Alert,
} from '@mui/material';
import axios from 'axios';

// ---------------------------------------------------------------------------
// Constantes
// ---------------------------------------------------------------------------

const API = 'http://127.0.0.1:8000/api/compras';
const CARRITO_KEY_STORAGE = 'cercha_carrito_key';

// Colores semánticos alineados al tema existente del proyecto
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

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Formatea un número como precio CLP sin decimales. */
const formatCLP = (valor) =>
  valor != null
    ? `$${Math.round(valor).toLocaleString('es-CL')}`
    : '—';

/** Devuelve el color de badge según el confidence score. */
const colorConfianza = (score) => {
  if (score == null) return 'default';
  if (score >= 0.9)  return 'success';
  if (score >= 0.7)  return 'warning';
  return 'error';
};

/** Extrae el precio de un proveedor específico de las variantes. */
const precioDeProveedor = (variantes, nombreProveedor) => {
  const v = variantes?.find((p) => p.proveedor === nombreProveedor);
  return v ? (v.precio_oferta ?? v.precio_clp) : null;
};

/** Imagen de la variante disponible. */
const imagenProducto = (variantes) =>
  variantes?.find((v) => v.imagen_url)?.imagen_url ?? null;

// ---------------------------------------------------------------------------
// Sub-componentes
// ---------------------------------------------------------------------------

/** Estado vacío — sin búsqueda aún. */
function EstadoVacio() {
  return (
    <Box
      sx={{
        flexGrow: 1,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 1.5,
        border: '1px dashed rgba(31, 58, 95, 0.25)',
        borderRadius: 3,
        p: 4,
        backgroundColor: 'rgba(255,255,255,0.5)',
      }}
    >
      <Typography variant="h6" sx={{ fontWeight: 600, color: 'text.secondary' }}>
        Ingresa un material para cotizar
      </Typography>
      <Typography variant="body2" sx={{ color: 'text.secondary', textAlign: 'center' }}>
        Busca "Tornillo 1/4 pulgada" o "Clavo 2 pulgadas" y compararemos
        precios en Sodimac y Easy en tiempo real.
      </Typography>
    </Box>
  );
}

/** Estado de carga — el scraper puede demorar hasta 25s. */
function EstadoCargando({ query }) {
  return (
    <Box
      sx={{
        flexGrow: 1,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 2,
        border: '1px dashed rgba(31, 58, 95, 0.25)',
        borderRadius: 3,
        p: 4,
        backgroundColor: 'rgba(255,255,255,0.5)',
      }}
    >
      <CircularProgress size={32} thickness={4} sx={{ color: 'primary.main' }} />
      <Box sx={{ textAlign: 'center' }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
          Buscando "{query}"...
        </Typography>
        <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.5 }}>
          El scraper puede tardar hasta 25 segundos. Consultando Sodimac y Easy en paralelo.
        </Typography>
      </Box>
    </Box>
  );
}

/** Tarjeta de un producto con comparación de precios. */
function TarjetaProducto({ resultado, onAgregar, cargandoCarrito }) {
  const { canonical, variantes, confidence_score } = resultado;
  const nombre = canonical?.nombre_normalizado || variantes?.[0]?.nombre_raw || 'Producto';
  const imagen = imagenProducto(variantes);

  const precioSodimac = precioDeProveedor(variantes, 'Sodimac');
  const precioEasy    = precioDeProveedor(variantes, 'Easy');

  const hayAmbos    = precioSodimac != null && precioEasy != null;
  const masBarato   = hayAmbos
    ? (precioSodimac <= precioEasy ? 'Sodimac' : 'Easy')
    : null;
  const ahorro      = hayAmbos ? Math.abs(precioSodimac - precioEasy) : null;

  return (
    <Paper
      sx={{
        p: 2,
        borderRadius: 3,
        display: 'flex',
        flexDirection: 'column',
        gap: 1.5,
        transition: 'box-shadow 0.15s',
        '&:hover': { boxShadow: '0 4px 16px rgba(31,35,40,0.10)' },
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
              width: 56,
              height: 56,
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
              fontWeight: 600,
              lineHeight: 1.3,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
            }}
          >
            {nombre}
          </Typography>
          {confidence_score != null && (
            <Chip
              label={`Confianza: ${Math.round(confidence_score * 100)}%`}
              size="small"
              color={colorConfianza(confidence_score)}
              variant="outlined"
              sx={{ mt: 0.5, fontWeight: 700 }}
            />
          )}
        </Box>
      </Box>

      {/* Precios por proveedor */}
      <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1 }}>
        {/* Sodimac */}
        <Box
          sx={{
            p: 1.2,
            borderRadius: 2,
            backgroundColor: masBarato === 'Sodimac' ? COLOR_WINNER.bg : COLOR_SODIMAC.bg,
            border: `1px solid ${masBarato === 'Sodimac' ? COLOR_WINNER.border : COLOR_SODIMAC.border}`,
          }}
        >
          <Typography variant="caption" sx={{ color: COLOR_SODIMAC.text, fontWeight: 700, display: 'block' }}>
            Sodimac
          </Typography>
          <Typography variant="h6" sx={{ fontWeight: 700, color: COLOR_SODIMAC.text, lineHeight: 1.2 }}>
            {formatCLP(precioSodimac)}
          </Typography>
          {masBarato === 'Sodimac' && (
            <Typography variant="caption" sx={{ color: COLOR_EASY.text, fontWeight: 700 }}>
              más barato
            </Typography>
          )}
        </Box>

        {/* Easy */}
        <Box
          sx={{
            p: 1.2,
            borderRadius: 2,
            backgroundColor: masBarato === 'Easy' ? COLOR_WINNER.bg : COLOR_EASY.bg,
            border: `1px solid ${masBarato === 'Easy' ? COLOR_WINNER.border : COLOR_EASY.border}`,
          }}
        >
          <Typography variant="caption" sx={{ color: COLOR_EASY.text, fontWeight: 700, display: 'block' }}>
            Easy
          </Typography>
          <Typography variant="h6" sx={{ fontWeight: 700, color: COLOR_EASY.text, lineHeight: 1.2 }}>
            {formatCLP(precioEasy)}
          </Typography>
          {masBarato === 'Easy' && (
            <Typography variant="caption" sx={{ color: COLOR_EASY.text, fontWeight: 700 }}>
              más barato
            </Typography>
          )}
        </Box>
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

      {/* Acción */}
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
  );
}

/** Dashboard de resumen del carrito procesado. */
function ResumenCotizacion({ resumen, onNuevaCotizacion }) {
  const esSodimac = resumen.proveedor_optimo === 'Sodimac';

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5, flexGrow: 1 }}>
      {/* KPIs */}
      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 1.5 }}>
        {[
          { label: 'Total Sodimac', valor: resumen.total_sodimac, color: COLOR_SODIMAC },
          { label: 'Total Easy',    valor: resumen.total_easy,    color: COLOR_EASY    },
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
              p: 1.5,
              borderRadius: 2,
              backgroundColor: color.bg,
              border: `1px solid ${color.border}`,
              display: 'flex',
              flexDirection: 'column',
              gap: 0.3,
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

      {/* Recomendación */}
      <Alert
        severity="success"
        sx={{ borderRadius: 2, fontWeight: 600 }}
      >
        Conviene comprar en <strong>{resumen.proveedor_optimo}</strong> — ahorras{' '}
        {formatCLP(resumen.ahorro_potencial)} ({resumen.ahorro_porcentaje?.toFixed(1)}%)
        sobre el precio del otro proveedor.
      </Alert>

      {/* Advertencias */}
      {resumen.advertencias?.length > 0 && (
        <Alert severity="warning" sx={{ borderRadius: 2 }}>
          {resumen.advertencias.join(' ')}
        </Alert>
      )}

      {/* Detalle por ítem */}
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
              const ps = item.precio_sodimac;
              const pe = item.precio_easy;
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
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

function Cotizador() {
  // Estado de búsqueda
  const [query, setQuery]           = useState('');
  const [buscando, setBuscando]     = useState(false);
  const [resultados, setResultados] = useState([]);
  const [errorBusqueda, setError]   = useState('');

  // Estado de carrito
  const [carritoKey, setCarritoKey]         = useState(() => localStorage.getItem(CARRITO_KEY_STORAGE) || null);
  const [carritoItems, setCarritoItems]     = useState([]);
  const [cargandoCarrito, setCargandoCarrito] = useState(false);

  // Estado del resumen
  const [resumen, setResumen]     = useState(null);
  const [vista, setVista]         = useState('resultados'); // 'resultados' | 'resumen'

  // ---------------------------------------------------------------------------
  // Cargar carrito existente al montar
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (!carritoKey) return;
    axios
      .get(`${API}/carrito/${carritoKey}`)
      .then((r) => setCarritoItems(r.data?.items || []))
      .catch(() => {
        // El carrito expiró o fue procesado — limpiar localStorage
        localStorage.removeItem(CARRITO_KEY_STORAGE);
        setCarritoKey(null);
        setCarritoItems([]);
      });
  }, [carritoKey]);

  // ---------------------------------------------------------------------------
  // Búsqueda principal (scraping en vivo)
  // ---------------------------------------------------------------------------
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
        { timeout: 40_000 }, // 40s — el scraper puede demorar
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

  // ---------------------------------------------------------------------------
  // Búsqueda en caché (instantánea — sin scraping)
  // ---------------------------------------------------------------------------
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

  // ---------------------------------------------------------------------------
  // Crear carrito si no existe
  // ---------------------------------------------------------------------------
  const obtenerOCrearCarrito = useCallback(async () => {
    if (carritoKey) return carritoKey;

    const resp = await axios.post(`${API}/carrito`);
    const key  = resp.data.session_key;
    localStorage.setItem(CARRITO_KEY_STORAGE, key);
    setCarritoKey(key);
    return key;
  }, [carritoKey]);

  // ---------------------------------------------------------------------------
  // Agregar producto al carrito
  // ---------------------------------------------------------------------------
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

  // ---------------------------------------------------------------------------
  // Eliminar ítem del carrito
  // ---------------------------------------------------------------------------
  const handleEliminarItem = useCallback(async (itemId) => {
    if (!carritoKey) return;
    try {
      const resp = await axios.delete(`${API}/carrito/${carritoKey}/items/${itemId}`);
      setCarritoItems(resp.data?.items || []);
    } catch (err) {
      alert(err?.response?.data?.detail || 'Error al eliminar ítem.');
    }
  }, [carritoKey]);

  // ---------------------------------------------------------------------------
  // Procesar carrito → resumen
  // ---------------------------------------------------------------------------
  const handleProcesar = useCallback(async () => {
    if (!carritoKey || carritoItems.length === 0) return;
    setCargandoCarrito(true);
    try {
      const resp = await axios.post(`${API}/carrito/${carritoKey}/procesar`);
      setResumen(resp.data);
      setVista('resumen');
      // El carrito queda como PROCESADO — limpiar localStorage para el próximo
      localStorage.removeItem(CARRITO_KEY_STORAGE);
      setCarritoKey(null);
    } catch (err) {
      alert(err?.response?.data?.detail || 'Error al procesar el carrito.');
    } finally {
      setCargandoCarrito(false);
    }
  }, [carritoKey, carritoItems]);

  // ---------------------------------------------------------------------------
  // Nueva cotización — resetear todo
  // ---------------------------------------------------------------------------
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

  // ---------------------------------------------------------------------------
  // Enter en el TextField
  // ---------------------------------------------------------------------------
  const handleKeyDown = (e) => {
    if (e.key === 'Enter') handleBuscar();
  };

  // ---------------------------------------------------------------------------
  // Totales del carrito (preview antes de procesar)
  // ---------------------------------------------------------------------------
  const totalSodimacPreview = carritoItems.reduce(
    (acc, i) => acc + (i.precio_sodimac ?? 0) * i.cantidad, 0
  );
  const totalEasyPreview = carritoItems.reduce(
    (acc, i) => acc + (i.precio_easy ?? 0) * i.cantidad, 0
  );

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
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
      {/* ------------------------------------------------------------------ */}
      {/* PANEL IZQUIERDO — Búsqueda + Carrito                               */}
      {/* ------------------------------------------------------------------ */}
      <Paper
        sx={{
          p: 2.5,
          borderRadius: 3,
          display: 'flex',
          flexDirection: 'column',
          gap: 2,
          overflow: 'auto',
        }}
      >
        {/* Encabezado */}
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 600, mb: 0.6 }}>
            Cotizador inteligente
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>
            Compara precios de materiales entre Sodimac y Easy en tiempo real.
          </Typography>
        </Box>

        <Divider />

        {/* Búsqueda */}
        <Typography variant="subtitle2" sx={{ color: 'text.secondary', letterSpacing: 1, textTransform: 'uppercase' }}>
          Buscar material
        </Typography>

        <TextField
          label="Ej: Tornillo hexagonal 1/4 pulgada"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
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
            {buscando ? <CircularProgress size={16} sx={{ color: 'inherit' }} /> : 'Buscar en vivo'}
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

        {/* Carrito */}
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
            {carritoItems.map((item) => (
              <Box
                key={item.id}
                sx={{
                  p: 1.2,
                  borderRadius: 2,
                  border: '1px solid rgba(28,35,43,0.10)',
                  backgroundColor: 'rgba(255,255,255,0.7)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 0.5,
                }}
              >
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <Typography variant="caption" sx={{ fontWeight: 600, lineHeight: 1.3, flex: 1, mr: 1 }}>
                    {item.query_original || `Ítem ${item.canonical_id}`}
                  </Typography>
                  <Button
                    size="small"
                    color="error"
                    variant="text"
                    onClick={() => handleEliminarItem(item.id)}
                    sx={{ minWidth: 0, px: 0.8, py: 0, fontWeight: 700, fontSize: '0.7rem' }}
                  >
                    X
                  </Button>
                </Box>
                <Box sx={{ display: 'flex', gap: 1 }}>
                  <Chip
                    label={`SOD: ${formatCLP(item.precio_sodimac)}`}
                    size="small"
                    variant="outlined"
                    sx={{ fontSize: '0.68rem', height: 20, fontWeight: 600, color: COLOR_SODIMAC.text }}
                  />
                  <Chip
                    label={`EASY: ${formatCLP(item.precio_easy)}`}
                    size="small"
                    variant="outlined"
                    sx={{ fontSize: '0.68rem', height: 20, fontWeight: 600, color: COLOR_EASY.text }}
                  />
                </Box>
              </Box>
            ))}
          </Box>
        )}

        {/* Preview totales */}
        {carritoItems.length > 0 && (
          <>
            <Divider />
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.6 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                <Typography variant="caption" sx={{ color: COLOR_SODIMAC.text, fontWeight: 700 }}>
                  Total Sodimac (preview)
                </Typography>
                <Typography variant="caption" sx={{ fontWeight: 700 }}>
                  {formatCLP(totalSodimacPreview)}
                </Typography>
              </Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                <Typography variant="caption" sx={{ color: COLOR_EASY.text, fontWeight: 700 }}>
                  Total Easy (preview)
                </Typography>
                <Typography variant="caption" sx={{ fontWeight: 700 }}>
                  {formatCLP(totalEasyPreview)}
                </Typography>
              </Box>
            </Box>

            <Button
              variant="contained"
              onClick={handleProcesar}
              disabled={cargandoCarrito}
              sx={{ py: 1.3, borderRadius: 999 }}
            >
              {cargandoCarrito ? <CircularProgress size={16} sx={{ color: 'inherit' }} /> : 'Procesar cotización'}
            </Button>
          </>
        )}
      </Paper>

      {/* ------------------------------------------------------------------ */}
      {/* PANEL DERECHO — Resultados o Resumen                               */}
      {/* ------------------------------------------------------------------ */}
      <Paper
        sx={{
          p: 2.5,
          borderRadius: 3,
          display: 'flex',
          flexDirection: 'column',
          gap: 2,
          minHeight: 0,
          overflow: 'hidden',
        }}
      >
        {/* Encabezado dinámico */}
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
        {errorBusqueda && !buscando && (
          <Alert severity="warning" onClose={() => setError('')} sx={{ borderRadius: 2 }}>
            {errorBusqueda}
          </Alert>
        )}

        {/* Contenido principal */}
        <Box sx={{ flexGrow: 1, overflow: 'auto', display: 'flex', flexDirection: 'column' }}>
          {vista === 'resumen' && resumen ? (
            <ResumenCotizacion resumen={resumen} onNuevaCotizacion={handleNuevaCotizacion} />
          ) : buscando ? (
            <EstadoCargando query={query} />
          ) : resultados.length === 0 ? (
            <EstadoVacio />
          ) : (
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
          )}
        </Box>
      </Paper>
    </Box>
  );
}

export default Cotizador;