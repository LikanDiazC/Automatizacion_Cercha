import { useEffect, useMemo, useState } from 'react';
import {
  Box,
  Paper,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Divider,
  Chip,
  Button
} from '@mui/material';
import axios from 'axios';

function Cortes() {
  const [ordenes, setOrdenes] = useState([]);
  const [ordenSeleccionadaId, setOrdenSeleccionadaId] = useState(null);
  const [detalleOrden, setDetalleOrden] = useState(null);
  const [cargandoDetalle, setCargandoDetalle] = useState(false);

  const cargarOrdenes = () => {
    axios
      .get('http://localhost:8000/api/ordenes')
      .then((respuesta) => {
        const lista = respuesta.data || [];
        setOrdenes(lista);
        if (lista.length === 0) {
          setOrdenSeleccionadaId(null);
          return;
        }
        const existe = lista.some((orden) => Number(orden.id) === Number(ordenSeleccionadaId));
        if (!existe) {
          setOrdenSeleccionadaId(lista[0].id);
        }
      })
      .catch((error) => console.error('Error al cargar órdenes:', error));
  };

  useEffect(() => {
    cargarOrdenes();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!ordenSeleccionadaId) {
      setDetalleOrden(null);
      return;
    }
    setCargandoDetalle(true);
    axios
      .get(`http://localhost:8000/api/ordenes/${ordenSeleccionadaId}/cortes`)
      .then((respuesta) => setDetalleOrden(respuesta.data))
      .catch((error) => console.error('Error al cargar cortes:', error))
      .finally(() => setCargandoDetalle(false));
  }, [ordenSeleccionadaId]);

  const ordenSeleccionada = useMemo(() => {
    return ordenes.find((orden) => Number(orden.id) === Number(ordenSeleccionadaId));
  }, [ordenes, ordenSeleccionadaId]);

  const planchaLargo = Number(detalleOrden?.largo_plancha ?? ordenSeleccionada?.largo_plancha ?? 2440);
  const planchaAncho = Number(detalleOrden?.ancho_plancha ?? ordenSeleccionada?.ancho_plancha ?? 1220);
  const totalTableros = detalleOrden?.planchas_usadas ?? ordenSeleccionada?.planchas_usadas ?? 0;
  const totalRetazos = detalleOrden?.retazos_total ?? ordenSeleccionada?.retazos_total ?? 0;
  const totalCortes = detalleOrden?.cortes_total ?? ordenSeleccionada?.cortes_total ?? 0;

  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: '1fr', lg: '360px 1fr' },
        gap: 2.5,
        alignItems: 'stretch',
        height: '100%',
        minHeight: 0
      }}
    >
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5, minHeight: 0 }}>
        <Paper sx={{ p: 2.5, borderRadius: 3, display: 'flex', flexDirection: 'column', gap: 2, minHeight: 0 }}>
          <Box>
            <Typography variant="h5" sx={{ fontWeight: 600, mb: 0.4 }}>
              Cortes por órdenes
            </Typography>
            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
              Selecciona una orden de trabajo y revisa sus planchas optimizadas.
            </Typography>
          </Box>

          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
            <Chip label={`Órdenes: ${ordenes.length}`} variant="outlined" />
            <Button size="small" variant="outlined" onClick={cargarOrdenes}>
              Actualizar listado
            </Button>
          </Box>

          <Divider />

          <Typography variant="subtitle2" sx={{ color: 'text.secondary', letterSpacing: 1, textTransform: 'uppercase' }}>
            Órdenes registradas
          </Typography>

          <Box sx={{ flexGrow: 1, overflow: 'auto' }}>
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow>
                  <TableCell>Orden</TableCell>
                  <TableCell align="center">Cant.</TableCell>
                  <TableCell align="center">Cortes</TableCell>
                  <TableCell align="center">Planchas</TableCell>
                  <TableCell align="center">Retazos</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {ordenes.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                      Aún no hay órdenes creadas.
                    </TableCell>
                  </TableRow>
                ) : (
                  ordenes.map((orden) => (
                    <TableRow
                      key={orden.id}
                      hover
                      selected={Number(orden.id) === Number(ordenSeleccionadaId)}
                      onClick={() => setOrdenSeleccionadaId(orden.id)}
                      sx={{ cursor: 'pointer' }}
                    >
                      <TableCell>{orden.mueble_nombre}</TableCell>
                      <TableCell align="center">{orden.cantidad}</TableCell>
                      <TableCell align="center">{orden.cortes_total}</TableCell>
                      <TableCell align="center">{orden.planchas_usadas}</TableCell>
                      <TableCell align="center">{orden.retazos_total}</TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </Box>
        </Paper>
      </Box>

      <Paper
        sx={{
          borderRadius: 3,
          p: 2.5,
          display: 'flex',
          flexDirection: 'column',
          gap: 2,
          minHeight: { lg: '70vh' }
        }}
      >
        <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 1 }}>
          <Box>
            <Typography variant="h5" sx={{ fontWeight: 600, mb: 0.4 }}>
              Plano de producción
            </Typography>
            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
              {detalleOrden?.mueble_nombre || ordenSeleccionada?.mueble_nombre
                ? `Orden seleccionada: ${detalleOrden?.mueble_nombre || ordenSeleccionada?.mueble_nombre}`
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

        <Box sx={{ flexGrow: 1, overflowY: 'auto' }}>
          {!ordenSeleccionadaId ? (
            <Box
              sx={{
                height: '100%',
                minHeight: 260,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                border: '1px dashed rgba(31, 58, 95, 0.3)',
                borderRadius: 3,
                backgroundColor: 'rgba(255, 255, 255, 0.6)'
              }}
            >
              <Typography sx={{ color: 'text.secondary' }}>
                No hay órdenes seleccionadas. Crea una orden y selecciónala.
              </Typography>
            </Box>
          ) : cargandoDetalle ? (
            <Box
              sx={{
                height: '100%',
                minHeight: 260,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                border: '1px dashed rgba(31, 58, 95, 0.3)',
                borderRadius: 3,
                backgroundColor: 'rgba(255, 255, 255, 0.6)'
              }}
            >
              <Typography sx={{ color: 'text.secondary' }}>
                Cargando cortes de la orden seleccionada...
              </Typography>
            </Box>
          ) : (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {(detalleOrden?.cortes || []).length === 0 ? (
                <Box
                  sx={{
                    height: '100%',
                    minHeight: 260,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    border: '1px dashed rgba(31, 58, 95, 0.3)',
                    borderRadius: 3,
                    backgroundColor: 'rgba(255, 255, 255, 0.6)'
                  }}
                >
                  <Typography sx={{ color: 'text.secondary' }}>
                    Esta orden no tiene cortes generados.
                  </Typography>
                </Box>
              ) : (
                (detalleOrden?.cortes || []).map((planchaData, index) => (
                  <Box
                    key={index}
                    sx={{
                      backgroundColor: 'rgba(255, 255, 255, 0.85)',
                      borderRadius: 3,
                      border: '1px solid rgba(28, 35, 43, 0.1)',
                      p: 2
                    }}
                  >
                    <Typography variant="subtitle1" sx={{ mb: 1.5, fontWeight: 600, color: 'text.secondary' }}>
                      Tablero #{index + 1}
                    </Typography>
                    <svg
                      viewBox={`0 0 ${planchaLargo} ${planchaAncho}`}
                      style={{
                        width: '100%',
                        height: 'auto',
                        background: 'linear-gradient(180deg, #f1d7ad 0%, #e8c897 100%)',
                        border: '3px solid #b07a3d',
                        borderRadius: '6px'
                      }}
                    >
                      {(planchaData.retazos_utiles || []).map((retazo, i) => {
                        const rX = retazo.x;
                        const rY = retazo.y;
                        const rAncho = retazo.largo || retazo.width || 0;
                        const rAlto = retazo.ancho || retazo.height || 0;
                        const rMin = Math.min(rAncho, rAlto);
                        const rLabelSize = Math.max(8, Math.min(18, rMin / 7));
                        const rDimsSize = Math.max(7, rLabelSize - 3);
                        const rPadding = Math.max(4, Math.min(10, rMin / 10));
                        const rSku = retazo.sku || retazo.id_pieza || 'RETAZO';
                        const showRetazoLabel = rMin > 28;

                        if (rX === undefined || rY === undefined) return null;

                        return (
                          <g key={`retazo-${i}`}>
                            <rect x={rX} y={rY} width={rAncho} height={rAlto} fill="rgba(69, 160, 125, 0.32)" stroke="#2f6f57" strokeWidth="3" />
                            {showRetazoLabel && (
                              <>
                                <text
                                  x={rX + rPadding}
                                  y={rY + rPadding}
                                  fill="#1f513e"
                                  fontSize={rLabelSize}
                                  fontWeight="600"
                                  dominantBaseline="hanging"
                                  opacity="0.8"
                                >
                                  {rSku}
                                </text>
                                <text
                                  x={rX + rPadding}
                                  y={rY + rPadding + rLabelSize + 3}
                                  fill="#1f513e"
                                  fontSize={rDimsSize}
                                  dominantBaseline="hanging"
                                  opacity="0.65"
                                >
                                  {Math.round(rAncho)} x {Math.round(rAlto)}
                                </text>
                              </>
                            )}
                          </g>
                        );
                      })}

                      {(planchaData.piezas || []).map((pieza, i) => {
                        const pX = pieza.x || 0;
                        const pY = pieza.y || 0;
                        const pAncho = pieza.largo || 0;
                        const pAlto = pieza.ancho || 0;

                        const minDim = Math.min(pAncho, pAlto);
                        const labelSize = Math.max(8, Math.min(22, minDim / 6));
                        const dimsSize = Math.max(7, labelSize - 3);
                        const labelPadding = Math.max(4, Math.min(10, minDim / 10));

                        return (
                          <g key={`pieza-${i}`}>
                            <rect
                              x={pX}
                              y={pY}
                              width={pAncho}
                              height={pAlto}
                              fill="rgba(240, 190, 99, 0.75)"
                              stroke="#a06a32"
                              strokeWidth="4"
                            />
                            <>
                              <text
                                x={pX + labelPadding}
                                y={pY + labelPadding}
                                fill="#1c232b"
                                fontSize={labelSize}
                                fontWeight="600"
                                dominantBaseline="hanging"
                                opacity="0.8"
                              >
                                {pieza.id_pieza}
                              </text>
                              <text
                                x={pX + labelPadding}
                                y={pY + labelPadding + labelSize + 3}
                                fill="#1c232b"
                                fontSize={dimsSize}
                                dominantBaseline="hanging"
                                opacity="0.65"
                              >
                                {Math.round(pAncho)} x {Math.round(pAlto)}
                              </text>
                            </>
                          </g>
                        );
                      })}
                    </svg>
                  </Box>
                ))
              )}
            </Box>
          )}
        </Box>
      </Paper>
    </Box>
  );
}

export default Cortes;


