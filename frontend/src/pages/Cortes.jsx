import { useState } from 'react';
import {
  Box,
  Paper,
  Typography,
  TextField,
  Button,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Divider,
  Chip
} from '@mui/material';
import axios from 'axios';

function Cortes() {
  const [plancha, setPlancha] = useState({ largo: 2440, ancho: 1220, grosor_sierra: 4 });
  const [piezas, setPiezas] = useState([]);
  const [nuevaPieza, setNuevaPieza] = useState({ id_pieza: '', largo: '', ancho: '', cantidad: 1 });
  const [resultadoCorte, setResultadoCorte] = useState(null);

  const handlePlanchaChange = (e) => setPlancha({ ...plancha, [e.target.name]: Number(e.target.value) });
  const handlePiezaChange = (e) => setNuevaPieza({ ...nuevaPieza, [e.target.name]: e.target.value });

  const handleAgregarPieza = () => {
    if (!nuevaPieza.id_pieza || !nuevaPieza.largo || !nuevaPieza.ancho || !nuevaPieza.cantidad) return;
    const l = parseFloat(nuevaPieza.largo);
    const a = parseFloat(nuevaPieza.ancho);
    const c = parseInt(nuevaPieza.cantidad, 10);

    if (Number.isNaN(l) || Number.isNaN(a) || Number.isNaN(c) || c <= 0) return;
    if (l > plancha.largo || a > plancha.ancho) {
      alert('La pieza excede las dimensiones de la plancha.');
      return;
    }

    setPiezas([...piezas, { id_pieza: nuevaPieza.id_pieza, largo: l, ancho: a, cantidad: c }]);
    setNuevaPieza({ id_pieza: '', largo: '', ancho: '', cantidad: 1 });
  };

  const handleEliminarPieza = (index) => {
    setPiezas((prev) => prev.filter((_, i) => i !== index));
  };

  const handleOptimizar = () => {
    if (piezas.length === 0) return;
    const payload = {
      largo_plancha: plancha.largo,
      ancho_plancha: plancha.ancho,
      grosor_sierra: plancha.grosor_sierra,
      piezas
    };

    axios
      .post('http://localhost:8000/api/mrp/optimizar-cortes', payload)
      .then((respuesta) => setResultadoCorte(respuesta.data))
      .catch((error) => console.error(error));
  };

  const totalPiezas = piezas.reduce((acc, pieza) => acc + pieza.cantidad, 0);
  const totalTableros = resultadoCorte?.planchas_usadas || 0;
  const totalRetazos = resultadoCorte
    ? (resultadoCorte.cortes || []).reduce((acc, planchaData) => acc + (planchaData.retazos_utiles || []).length, 0)
    : 0;

  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: '1fr', lg: '340px 1fr' },
        gap: 2.5,
        alignItems: 'stretch',
        height: '100%',
        minHeight: 0
      }}
    >
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5 }}>
        <Paper sx={{ p: 2.5, borderRadius: 3 }}>
          <Typography variant="subtitle2" sx={{ color: 'text.secondary', fontWeight: 700, letterSpacing: 1, textTransform: 'uppercase', mb: 2 }}>
            Parámetros del tablero
          </Typography>
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(0, 1fr))' },
              gap: 1.5
            }}
          >
            <TextField label="Largo (mm)" name="largo" type="number" value={plancha.largo} onChange={handlePlanchaChange} />
            <TextField label="Ancho (mm)" name="ancho" type="number" value={plancha.ancho} onChange={handlePlanchaChange} />
            <TextField
              label="Kerf / Grosor de sierra (mm)"
              name="grosor_sierra"
              type="number"
              value={plancha.grosor_sierra}
              onChange={handlePlanchaChange}
              sx={{ gridColumn: '1 / -1' }}
            />
          </Box>
        </Paper>

        <Paper sx={{ p: 2.5, borderRadius: 3, display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Box>
            <Typography variant="subtitle2" sx={{ color: 'text.secondary', fontWeight: 700, letterSpacing: 1, textTransform: 'uppercase' }}>
              Componentes a cortar
            </Typography>
            <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.5 }}>
              Agrega cada pieza con su cantidad. Total actual: {totalPiezas}.
            </Typography>
          </Box>

          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(12, 1fr)', gap: 1.5 }}>
            <TextField
              label="Nombre de pieza"
              name="id_pieza"
              value={nuevaPieza.id_pieza}
              onChange={handlePiezaChange}
              sx={{ gridColumn: 'span 12' }}
            />
            <TextField
              label="Largo"
              name="largo"
              type="number"
              value={nuevaPieza.largo}
              onChange={handlePiezaChange}
              sx={{ gridColumn: { xs: 'span 12', sm: 'span 4' } }}
            />
            <TextField
              label="Ancho"
              name="ancho"
              type="number"
              value={nuevaPieza.ancho}
              onChange={handlePiezaChange}
              sx={{ gridColumn: { xs: 'span 12', sm: 'span 4' } }}
            />
            <TextField
              label="Cantidad"
              name="cantidad"
              type="number"
              value={nuevaPieza.cantidad}
              onChange={handlePiezaChange}
              sx={{ gridColumn: { xs: 'span 12', sm: 'span 4' } }}
            />
            <Button variant="outlined" onClick={handleAgregarPieza} sx={{ gridColumn: 'span 12', borderRadius: 2 }}>
              Agregar componente
            </Button>
          </Box>

          <Divider />

          <Box sx={{ maxHeight: 220, overflow: 'auto' }}>
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow>
                  <TableCell>Pieza</TableCell>
                  <TableCell>Medidas</TableCell>
                  <TableCell align="center">Cant.</TableCell>
                  <TableCell align="right">Acciones</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {piezas.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={4} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                      Aún no hay piezas agregadas.
                    </TableCell>
                  </TableRow>
                ) : (
                  piezas.map((p, index) => (
                    <TableRow key={index} hover>
                      <TableCell sx={{ fontSize: '0.85rem' }}>{p.id_pieza}</TableCell>
                      <TableCell sx={{ fontSize: '0.85rem', color: 'text.secondary' }}>
                        {p.largo} x {p.ancho}
                      </TableCell>
                      <TableCell sx={{ fontSize: '0.85rem', textAlign: 'center', fontWeight: 700 }}>{p.cantidad}</TableCell>
                      <TableCell align="right">
                        <Button
                          color="error"
                          size="small"
                          variant="text"
                          onClick={() => handleEliminarPieza(index)}
                          sx={{ fontWeight: 700, minWidth: 0, px: 1 }}
                        >
                          X
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </Box>

          <Button
            variant="contained"
            onClick={handleOptimizar}
            disabled={piezas.length === 0}
            sx={{ py: 1.4 }}
          >
            Optimizar cortes
          </Button>
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
              Visualiza el patrón optimizado y registra retazos utilizables.
            </Typography>
          </Box>
          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
            <Chip label={`Tableros: ${totalTableros}`} variant="outlined" />
            <Chip label={`Retazos: ${totalRetazos}`} variant="outlined" />
          </Box>
        </Box>

        <Divider />

        <Box sx={{ flexGrow: 1, overflowY: 'auto' }}>
          {!resultadoCorte ? (
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
                El lienzo está listo. Ingresa piezas y ejecuta el algoritmo.
              </Typography>
            </Box>
          ) : (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {(resultadoCorte.cortes || []).map((planchaData, index) => (
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
                    viewBox={`0 0 ${plancha.largo} ${plancha.ancho}`}
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
              ))}
            </Box>
          )}
        </Box>
      </Paper>
    </Box>
  );
}

export default Cortes;
