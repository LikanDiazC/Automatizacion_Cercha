import { useState } from 'react';
import { 
  Card, CardContent, Typography, TextField, Button, Grid, 
  Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Box, Divider 
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

    if (isNaN(l) || isNaN(a) || isNaN(c) || c <= 0) return;
    if (l > plancha.largo || a > plancha.ancho) {
      alert(`La pieza excede las dimensiones de la plancha.`);
      return;
    }

    setPiezas([...piezas, { id_pieza: nuevaPieza.id_pieza, largo: l, ancho: a, cantidad: c }]);
    setNuevaPieza({ id_pieza: '', largo: '', ancho: '', cantidad: 1 });
  };

  const handleOptimizar = () => {
    if (piezas.length === 0) return;
    const payload = { largo_plancha: plancha.largo, ancho_plancha: plancha.ancho, grosor_sierra: plancha.grosor_sierra, piezas };

    axios.post('http://localhost:8000/api/mrp/optimizar-cortes', payload)
      .then((respuesta) => setResultadoCorte(respuesta.data))
      .catch((error) => console.error(error));
  };

  return (
    <Grid container spacing={3} sx={{ height: 'calc(100vh - 100px)' }}>
      
      {/* -------------------------------------------------------------
          COLUMNA IZQUIERDA: CONTROLES (30% DEL ANCHO)
      ------------------------------------------------------------- */}
      <Grid item xs={12} lg={3} sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        
        {/* PANEL DE CONFIGURACIÓN */}
        <Card sx={{ borderRadius: '12px', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}>
          <CardContent>
            <Typography variant="subtitle2" sx={{ color: '#64748b', fontWeight: 'bold', mb: 2, textTransform: 'uppercase' }}>
              Parámetros del Tablero
            </Typography>
            <Grid container spacing={1.5}>
              <Grid item xs={6}><TextField size="small" fullWidth label="Largo (mm)" name="largo" type="number" value={plancha.largo} onChange={handlePlanchaChange} /></Grid>
              <Grid item xs={6}><TextField size="small" fullWidth label="Ancho (mm)" name="ancho" type="number" value={plancha.ancho} onChange={handlePlanchaChange} /></Grid>
              <Grid item xs={12}><TextField size="small" fullWidth label="Grosor Sierra / Kerf (mm)" name="grosor_sierra" type="number" value={plancha.grosor_sierra} onChange={handlePlanchaChange} /></Grid>
            </Grid>
          </CardContent>
        </Card>

        {/* PANEL DE INGRESO DE PIEZAS */}
        <Card sx={{ borderRadius: '12px', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)', flexGrow: 1, display: 'flex', flexDirection: 'column' }}>
          <CardContent sx={{ display: 'flex', flexDirection: 'column', height: '100%', p: 0 }}>
            <Box sx={{ p: 2 }}>
              <Typography variant="subtitle2" sx={{ color: '#64748b', fontWeight: 'bold', mb: 2, textTransform: 'uppercase' }}>
                Lista de Componentes
              </Typography>
              <Grid container spacing={1.5}>
                <Grid item xs={12}><TextField size="small" fullWidth label="ID / Nombre Pieza" name="id_pieza" value={nuevaPieza.id_pieza} onChange={handlePiezaChange} /></Grid>
                <Grid item xs={4}><TextField size="small" fullWidth label="Largo" name="largo" type="number" value={nuevaPieza.largo} onChange={handlePiezaChange} /></Grid>
                <Grid item xs={4}><TextField size="small" fullWidth label="Ancho" name="ancho" type="number" value={nuevaPieza.ancho} onChange={handlePiezaChange} /></Grid>
                <Grid item xs={4}><TextField size="small" fullWidth label="Cant." name="cantidad" type="number" value={nuevaPieza.cantidad} onChange={handlePiezaChange} /></Grid>
                <Grid item xs={12}>
                  <Button fullWidth variant="outlined" sx={{ borderRadius: '8px', fontWeight: 'bold' }} onClick={handleAgregarPieza}>
                    + Agregar Componente
                  </Button>
                </Grid>
              </Grid>
            </Box>

            <Divider />

            {/* TABLA DE PIEZAS CON SCROLL INTERNO */}
            <Box sx={{ flexGrow: 1, overflow: 'auto', maxHeight: '250px' }}>
              <Table size="small" stickyHeader>
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ backgroundColor: '#f8fafc', fontWeight: 'bold' }}>Pieza</TableCell>
                    <TableCell sx={{ backgroundColor: '#f8fafc', fontWeight: 'bold' }}>Medidas</TableCell>
                    <TableCell sx={{ backgroundColor: '#f8fafc', fontWeight: 'bold', textAlign: 'center' }}>Q</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {piezas.map((p, index) => (
                    <TableRow key={index} hover>
                      <TableCell sx={{ fontSize: '0.85rem' }}>{p.id_pieza}</TableCell>
                      <TableCell sx={{ fontSize: '0.85rem', color: '#64748b' }}>{p.largo} × {p.ancho}</TableCell>
                      <TableCell sx={{ fontSize: '0.85rem', textAlign: 'center', fontWeight: 'bold' }}>{p.cantidad}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Box>

            <Box sx={{ p: 2, backgroundColor: '#f8fafc', borderTop: '1px solid #e2e8f0' }}>
              <Button fullWidth variant="contained" onClick={handleOptimizar} sx={{ py: 1.5, borderRadius: '8px', backgroundColor: '#0f172a', fontWeight: 'bold', fontSize: '1rem', '&:hover': { backgroundColor: '#334155' } }}>
                EJECUTAR ALGORITMO
              </Button>
            </Box>
          </CardContent>
        </Card>

      </Grid>

      {/* -------------------------------------------------------------
          COLUMNA DERECHA: VISUALIZADOR CAD (70% DEL ANCHO)
      ------------------------------------------------------------- */}
      <Grid item xs={12} lg={9} sx={{ height: '100%' }}>
        <Card sx={{ height: '100%', borderRadius: '12px', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)', display: 'flex', flexDirection: 'column' }}>
          
          <Box sx={{ p: 2, borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="h6" sx={{ fontWeight: 'bold', color: '#0f172a' }}>
              Plano de Producción SVG
            </Typography>
            {resultadoCorte && (
              <Typography sx={{ backgroundColor: '#dcfce7', color: '#166534', px: 2, py: 0.5, borderRadius: '20px', fontWeight: 'bold', fontSize: '0.9rem' }}>
                Tableros requeridos: {resultadoCorte.planchas_usadas || 0}
              </Typography>
            )}
          </Box>

          <CardContent sx={{ flexGrow: 1, overflowY: 'auto', backgroundColor: '#f1f5f9', p: 4 }}>
            {!resultadoCorte ? (
              <Box sx={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', border: '2px dashed #cbd5e1', borderRadius: '12px' }}>
                <Typography sx={{ color: '#94a3b8', fontWeight: '500' }}>El lienzo está vacío. Ingresa piezas y ejecuta el algoritmo.</Typography>
              </Box>
            ) : (
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {(resultadoCorte.cortes || []).map((planchaData, index) => (
                  <Box key={index} sx={{ backgroundColor: '#ffffff', p: 3, borderRadius: '12px', boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1)' }}>
                    <Typography variant="h6" sx={{ mb: 2, fontWeight: 'bold', color: '#334155' }}>
                      TABLERO #{index + 1}
                    </Typography>
                    
                    {/* LIENZO SVG FULL WIDTH */}
                    <svg 
                      viewBox={`0 0 ${plancha.largo} ${plancha.ancho}`} 
                      style={{ width: '100%', height: 'auto', backgroundColor: '#fde68a', border: '4px solid #b45309', borderRadius: '4px' }}
                    >
                      {/* 1. Dibujamos los Retazos Primero (Para que queden al fondo si hay solapamiento) */}
                      {(planchaData.retazos_utiles || []).map((retazo, i) => {
                        const rX = retazo.x; const rY = retazo.y;
                        const rAncho = retazo.largo || retazo.width || 0;
                        const rAlto = retazo.ancho || retazo.height || 0;
                        
                        // DEFENSA: Si el retazo no tiene coordenadas válidas X/Y, no lo dibujamos
                        if (rX === undefined || rY === undefined) return null;
                        
                        return (
                          <g key={`retazo-${i}`}>
                            <rect x={rX} y={rY} width={rAncho} height={rAlto} fill="rgba(34, 197, 94, 0.4)" stroke="#15803d" strokeWidth="3" />
                            {(rAncho > 200 && rAlto > 200) && (
                              <text x={rX + rAncho / 2} y={rY + rAlto / 2} fill="#14532d" fontSize="40" fontWeight="bold" textAnchor="middle" alignmentBaseline="middle">
                                RETAZO
                              </text>
                            )}
                          </g>
                        );
                      })}

                      {/* 2. Dibujamos las Piezas de Producción por encima */}
                      {(planchaData.piezas || []).map((pieza, i) => {
                        const pX = pieza.x || 0; const pY = pieza.y || 0;
                        const pAncho = pieza.largo || 0; const pAlto = pieza.ancho || 0;

                        return (
                          <g key={`pieza-${i}`}>
                            <rect x={pX} y={pY} width={pAncho} height={pAlto} fill="#fcd34d" stroke="#b45309" strokeWidth="4" />
                            {(pAncho > 150 && pAlto > 150) && (
                              <>
                                <text x={pX + pAncho / 2} y={pY + pAlto / 2 - 15} fill="#0f172a" fontSize="45" fontWeight="bold" textAnchor="middle" alignmentBaseline="middle">
                                  {pieza.id_pieza}
                                </text>
                                <text x={pX + pAncho / 2} y={pY + pAlto / 2 + 45} fill="#334155" fontSize="35" textAnchor="middle" alignmentBaseline="middle">
                                  {Math.round(pAncho)} × {Math.round(pAlto)}
                                </text>
                              </>
                            )}
                          </g>
                        );
                      })}
                    </svg>

                  </Box>
                ))}
              </Box>
            )}
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );
}

export default Cortes;