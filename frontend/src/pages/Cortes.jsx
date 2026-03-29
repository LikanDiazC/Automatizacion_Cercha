import { useEffect, useMemo, useState } from 'react';
import {
  Box, Paper, Typography, Table, TableBody, TableCell, TableHead,
  TableRow, Divider, Chip, Button
} from '@mui/material';
import axios from 'axios';

const API = 'http://127.0.0.1:8000';

// Status chip colors
const ESTADO_COLOR = {
  'Pendiente': 'default',
  'En progreso': 'warning',
  'Completado': 'success',
  'Cancelado': 'error',
};

function Cortes() {
  const [ordenes, setOrdenes] = useState([]);
  const [ordenSeleccionadaId, setOrdenSeleccionadaId] = useState(null);
  const [detalleOrden, setDetalleOrden] = useState(null);
  const [cargandoDetalle, setCargandoDetalle] = useState(false);

  const cargarOrdenes = () => {
    axios.get(`${API}/api/ordenes`)
      .then((r) => {
        const lista = r.data || [];
        setOrdenes(lista);
        if (lista.length > 0) {
          setOrdenSeleccionadaId((prev) => {
            const existe = lista.some((o) => Number(o.id) === Number(prev));
            return existe ? prev : lista[0].id;
          });
        } else {
          setOrdenSeleccionadaId(null);
        }
      })
      .catch((e) => console.error('Error al cargar órdenes:', e));
  };

  useEffect(() => { cargarOrdenes(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!ordenSeleccionadaId) { setDetalleOrden(null); return; }
    setCargandoDetalle(true);
    axios.get(`${API}/api/ordenes/${ordenSeleccionadaId}/cortes`)
      .then((r) => setDetalleOrden(r.data))
      .catch((e) => console.error('Error al cargar cortes:', e))
      .finally(() => setCargandoDetalle(false));
  }, [ordenSeleccionadaId]);

  const ordenSeleccionada = useMemo(
    () => ordenes.find((o) => Number(o.id) === Number(ordenSeleccionadaId)),
    [ordenes, ordenSeleccionadaId]
  );

  const planchaLargo = Number(detalleOrden?.largo_plancha ?? ordenSeleccionada?.largo_plancha ?? 2440);
  const planchaAncho = Number(detalleOrden?.ancho_plancha ?? ordenSeleccionada?.ancho_plancha ?? 1220);
  const totalTableros = detalleOrden?.planchas_usadas ?? ordenSeleccionada?.planchas_usadas ?? 0;
  const totalRetazos = detalleOrden?.retazos_total ?? ordenSeleccionada?.retazos_total ?? 0;
  const totalCortes = detalleOrden?.cortes_total ?? ordenSeleccionada?.cortes_total ?? 0;

  return (
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: '360px 1fr' }, gap: 2.5, alignItems: 'stretch', height: '100%', minHeight: 0 }}>
      {/* Left panel */}
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5, minHeight: 0 }}>
        <Paper sx={{ p: 2.5, borderRadius: 3, display: 'flex', flexDirection: 'column', gap: 2, minHeight: 0 }}>
          <Box>
            <Typography variant="h5" sx={{ fontWeight: 600, mb: 0.4 }}>Cortes por órdenes</Typography>
            <Typography variant="body2" sx={{ color: 'text.secondary' }}>Selecciona una orden y revisa sus planchas optimizadas.</Typography>
          </Box>
          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
            <Chip label={`Órdenes: ${ordenes.length}`} variant="outlined" />
            <Button size="small" variant="outlined" onClick={cargarOrdenes}>Actualizar</Button>
          </Box>
          <Divider />
          <Box sx={{ flexGrow: 1, overflow: 'auto' }}>
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow>
                  <TableCell>Orden</TableCell>
                  <TableCell align="center">Cant.</TableCell>
                  <TableCell align="center">Estado</TableCell>
                  <TableCell align="center">Planchas</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {ordenes.length === 0 ? (
                  <TableRow><TableCell colSpan={4} align="center" sx={{ py: 4, color: 'text.secondary' }}>Aún no hay órdenes creadas.</TableCell></TableRow>
                ) : ordenes.map((orden) => (
                  <TableRow
                    key={orden.id} hover
                    selected={Number(orden.id) === Number(ordenSeleccionadaId)}
                    onClick={() => setOrdenSeleccionadaId(orden.id)}
                    sx={{ cursor: 'pointer' }}
                  >
                    <TableCell>{orden.mueble_nombre}</TableCell>
                    <TableCell align="center">{orden.cantidad}</TableCell>
                    <TableCell align="center">
                      <Chip label={orden.estado || 'Pendiente'} size="small" color={ESTADO_COLOR[orden.estado] || 'default'} variant="outlined" />
                    </TableCell>
                    <TableCell align="center">{orden.planchas_usadas}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>
        </Paper>
      </Box>

      {/* Right panel — cut plan SVG */}
      <Paper sx={{ borderRadius: 3, p: 2.5, display: 'flex', flexDirection: 'column', gap: 2, minHeight: { lg: '70vh' } }}>
        <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 1 }}>
          <Box>
            <Typography variant="h5" sx={{ fontWeight: 600, mb: 0.4 }}>Plano de producción</Typography>
            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
              {detalleOrden?.mueble_nombre || ordenSeleccionada?.mueble_nombre
                ? `Orden: ${detalleOrden?.mueble_nombre || ordenSeleccionada?.mueble_nombre}`
                : 'Selecciona una orden para visualizar los cortes.'}
            </Typography>
          </Box>
          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
            <Chip label={`Cortes: ${totalCortes}`} variant="outlined" />
            <Chip label={`Planchas: ${totalTableros}`} variant="outlined" />
            <Chip label={`Retazos: ${totalRetazos}`} variant="outlined" />
          </Box>
        </Box>

        <Divider />

        {/* Legend */}
        <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', alignItems: 'center' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.7 }}>
            <Box sx={{ width: 14, height: 14, borderRadius: 1, backgroundColor: 'rgba(240, 190, 99, 0.75)', border: '2px solid #a06a32' }} />
            <Typography variant="caption" sx={{ color: 'text.secondary' }}>Pieza</Typography>
          </Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.7 }}>
            <Box sx={{ width: 14, height: 14, borderRadius: 1, backgroundColor: 'rgba(240, 190, 99, 0.45)', border: '2px dashed #a06a32' }} />
            <Typography variant="caption" sx={{ color: 'text.secondary' }}>Pieza rotada</Typography>
          </Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.7 }}>
            <Box sx={{ width: 14, height: 14, borderRadius: 1, backgroundColor: 'rgba(69, 160, 125, 0.32)', border: '2px solid #2f6f57' }} />
            <Typography variant="caption" sx={{ color: 'text.secondary' }}>Retazo útil</Typography>
          </Box>
        </Box>

        <Box sx={{ flexGrow: 1, overflowY: 'auto' }}>
          {!ordenSeleccionadaId ? (
            <EmptyState text="No hay orden seleccionada. Crea una orden y selecciónala." />
          ) : cargandoDetalle ? (
            <EmptyState text="Cargando cortes de la orden seleccionada..." />
          ) : (detalleOrden?.cortes || []).length === 0 ? (
            <EmptyState text="Esta orden no tiene cortes generados." />
          ) : (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {(detalleOrden?.cortes || []).map((planchaData, index) => (
                <PlanchaSVG
                  key={index}
                  index={index}
                  planchaData={planchaData}
                  planchaLargo={planchaLargo}
                  planchaAncho={planchaAncho}
                />
              ))}
            </Box>
          )}
        </Box>
      </Paper>
    </Box>
  );
}

function EmptyState({ text }) {
  return (
    <Box sx={{ height: '100%', minHeight: 260, display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px dashed rgba(31, 58, 95, 0.3)', borderRadius: 3, backgroundColor: 'rgba(255, 255, 255, 0.6)' }}>
      <Typography sx={{ color: 'text.secondary' }}>{text}</Typography>
    </Box>
  );
}

function PlanchaSVG({ index, planchaData, planchaLargo, planchaAncho }) {
  return (
    <Box sx={{ backgroundColor: 'rgba(255, 255, 255, 0.85)', borderRadius: 3, border: '1px solid rgba(28, 35, 43, 0.1)', p: 2 }}>
      <Typography variant="subtitle1" sx={{ mb: 1.5, fontWeight: 600, color: 'text.secondary' }}>
        Tablero #{index + 1}
        {planchaData.piezas?.some(p => p.rotada) && (
          <Typography component="span" variant="caption" sx={{ ml: 1.5, color: 'text.secondary', fontWeight: 400 }}>
            (contiene piezas rotadas para mejor aprovechamiento)
          </Typography>
        )}
      </Typography>
      <svg
        viewBox={`0 0 ${planchaLargo} ${planchaAncho}`}
        style={{ width: '100%', height: 'auto', background: 'linear-gradient(180deg, #f1d7ad 0%, #e8c897 100%)', border: '3px solid #b07a3d', borderRadius: '6px' }}
      >
        {/* Retazos útiles */}
        {(planchaData.retazos_utiles || []).map((retazo, i) => {
          const rX = retazo.x ?? 0;
          const rY = retazo.y ?? 0;
          const rW = retazo.largo ?? 0;
          const rH = retazo.ancho ?? 0;
          if (rW <= 0 || rH <= 0) return null;
          const rMin = Math.min(rW, rH);
          const rLabelSize = Math.max(8, Math.min(18, rMin / 7));
          const rDimsSize = Math.max(7, rLabelSize - 3);
          const rPad = Math.max(4, Math.min(10, rMin / 10));
          const showLabel = rMin > 100;
          const sku = retazo.sku || 'RETAZO';
          return (
            <g key={`retazo-${i}`}>
              <rect x={rX} y={rY} width={rW} height={rH} fill="rgba(69, 160, 125, 0.32)" stroke="#2f6f57" strokeWidth="3" />
              {showLabel && (
                <>
                  <text x={rX + rPad} y={rY + rPad} fill="#1f513e" fontSize={rLabelSize} fontWeight="600" dominantBaseline="hanging" opacity="0.8">{sku}</text>
                  <text x={rX + rPad} y={rY + rPad + rLabelSize + 3} fill="#1f513e" fontSize={rDimsSize} dominantBaseline="hanging" opacity="0.65">{Math.round(rW)} × {Math.round(rH)}</text>
                </>
              )}
            </g>
          );
        })}

        {/* Piezas */}
        {(planchaData.piezas || []).map((pieza, i) => {
          const pX = pieza.x ?? 0;
          const pY = pieza.y ?? 0;
          // svg_w/svg_h: tamaño real del rectángulo en el SVG (lo que ocupa en la plancha)
          // Si el backend es viejo y no tiene svg_w, usar largo/ancho como fallback
          const pW = pieza.svg_w ?? pieza.largo ?? 0;
          const pH = pieza.svg_h ?? pieza.ancho ?? 0;
          // largo/ancho: dimensiones originales de diseño para el label
          const labelLargo = Math.round(pieza.largo ?? pW);
          const labelAncho = Math.round(pieza.ancho ?? pH);
          const minDim = Math.min(pW, pH);
          const labelSize = Math.max(8, Math.min(22, minDim / 6));
          const dimsSize = Math.max(7, labelSize - 3);
          const pad = Math.max(4, Math.min(10, minDim / 10));
          const isRotated = pieza.rotada === true;

          return (
            <g key={`pieza-${i}`}>
              <rect
                x={pX} y={pY} width={pW} height={pH}
                fill={isRotated ? 'rgba(240, 190, 99, 0.45)' : 'rgba(240, 190, 99, 0.75)'}
                stroke="#a06a32" strokeWidth="4"
                strokeDasharray={isRotated ? '12 6' : 'none'}
              />
              <text x={pX + pad} y={pY + pad} fill="#1c232b" fontSize={labelSize} fontWeight="600" dominantBaseline="hanging" opacity="0.8">
                {pieza.id_pieza}{isRotated ? ' ↺' : ''}
              </text>
              <text x={pX + pad} y={pY + pad + labelSize + 3} fill="#1c232b" fontSize={dimsSize} dominantBaseline="hanging" opacity="0.65">
                {labelLargo} × {labelAncho}
              </text>
            </g>
          );
        })}
      </svg>
    </Box>
  );
}

export default Cortes;
