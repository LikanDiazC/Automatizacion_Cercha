import { useEffect, useMemo, useState } from 'react';
import {
  Box,
  Paper,
  Typography,
  TextField,
  MenuItem,
  Button,
  Divider,
  Chip,
  Table,
  TableHead,
  TableRow,
  TableCell,
  TableBody
} from '@mui/material';
import axios from 'axios';

function Ordenes() {
  const [muebles, setMuebles] = useState([]);
  const [muebleId, setMuebleId] = useState('');
  const [cantidad, setCantidad] = useState(1);
  const [notas, setNotas] = useState('');
  const [plancha, setPlancha] = useState({ largo: 2440, ancho: 1220, grosor_sierra: 4 });
  const [resumen, setResumen] = useState(null);
  const [ordenes, setOrdenes] = useState([]);

  const cargarMuebles = () => {
    axios
      .get('http://127.0.0.1:8000/api/ordenes/muebles')
      .then((respuesta) => {
        setMuebles(respuesta.data || []);
        if (respuesta.data?.length && !muebleId) {
          setMuebleId(respuesta.data[0].id);
        }
      })
      .catch((error) => console.error('Error al cargar muebles:', error));
  };

  const cargarOrdenes = () => {
    axios
      .get('http://127.0.0.1:8000/api/ordenes')
      .then((respuesta) => setOrdenes(respuesta.data || []))
      .catch((error) => console.error('Error al cargar órdenes:', error));
  };

  useEffect(() => {
    cargarMuebles();
    cargarOrdenes();
  }, []);

  const muebleSeleccionado = useMemo(() => {
    return muebles.find((mueble) => Number(mueble.id) === Number(muebleId));
  }, [muebles, muebleId]);

  const piezasMueble = muebleSeleccionado?.piezas || [];

  const cortesPorMueble = piezasMueble.reduce((acc, pieza) => acc + Number(pieza.cantidad || 0), 0);
  const cortesPreview = cortesPorMueble * Number(cantidad || 1);

  const totalesPreview = {
    tornillos: Number(muebleSeleccionado?.tornillos || 0) * Number(cantidad || 1),
    pegamento: Number(muebleSeleccionado?.pegamento_ml || 0) * Number(cantidad || 1),
    pintura: Number(muebleSeleccionado?.pintura_ml || 0) * Number(cantidad || 1),
    perfiles: Number(muebleSeleccionado?.perfiles_m || 0) * Number(cantidad || 1)
  };

  const handleSeleccion = (e) => {
    const nextId = Number(e.target.value);
    setMuebleId(nextId);
    setResumen(null);
  };

  const handleCrearOrden = () => {
    if (!muebleId) return;
    axios
      .post('http://127.0.0.1:8000/api/ordenes', {
        mueble_id: Number(muebleId),
        cantidad: Number(cantidad || 1),
        notas,
        largo_plancha: Number(plancha.largo),
        ancho_plancha: Number(plancha.ancho),
        grosor_sierra: Number(plancha.grosor_sierra)
      })
      .then((respuesta) => {
        setResumen(respuesta.data);
        cargarOrdenes();
      })
      .catch((error) => {
        const detalle = error?.response?.data?.detail || 'Error al crear la orden.';
        alert(detalle);
      });
  };

  const handlePlanchaChange = (e) => {
    setPlancha((prev) => ({ ...prev, [e.target.name]: Number(e.target.value) }));
  };

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
      <Paper sx={{ p: 2.5, borderRadius: 3, display: 'flex', flexDirection: 'column', gap: 2, overflow: 'auto' }}>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 600, mb: 0.6 }}>
            Órdenes de trabajo
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>
            Selecciona el mueble con materiales y cortes predefinidos.
          </Typography>
        </Box>

        <Divider />

        <TextField label="Seleccionar mueble" value={muebleId} onChange={handleSeleccion} select>
          {muebles.map((item) => (
            <MenuItem key={item.id} value={item.id}>
              {item.nombre}
            </MenuItem>
          ))}
        </TextField>

        <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 1.5 }}>
          <TextField label="Largo (mm)" value={muebleSeleccionado?.largo || ''} disabled />
          <TextField label="Ancho (mm)" value={muebleSeleccionado?.ancho || ''} disabled />
          <TextField label="Alto (mm)" value={muebleSeleccionado?.alto || ''} disabled />
        </Box>

        <Divider />

        <Typography variant="subtitle2" sx={{ color: 'text.secondary', letterSpacing: 1, textTransform: 'uppercase' }}>
          Insumos por unidad
        </Typography>

        <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 1.5 }}>
          <TextField label="Tornillos (unid.)" value={muebleSeleccionado?.tornillos || 0} disabled />
          <TextField label="Pegamento (ml)" value={muebleSeleccionado?.pegamento_ml || 0} disabled />
          <TextField label="Pintura (ml)" value={muebleSeleccionado?.pintura_ml || 0} disabled />
          <TextField label="Perfiles metálicos (m)" value={muebleSeleccionado?.perfiles_m || 0} disabled />
        </Box>

        <Divider />

        <Typography variant="subtitle2" sx={{ color: 'text.secondary', letterSpacing: 1, textTransform: 'uppercase' }}>
          Parámetros de plancha
        </Typography>

        <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 1.5 }}>
          <TextField label="Largo" name="largo" type="number" value={plancha.largo} onChange={handlePlanchaChange} />
          <TextField label="Ancho" name="ancho" type="number" value={plancha.ancho} onChange={handlePlanchaChange} />
          <TextField label="Kerf" name="grosor_sierra" type="number" value={plancha.grosor_sierra} onChange={handlePlanchaChange} />
        </Box>

        <TextField
          label="Cantidad"
          type="number"
          value={cantidad}
          onChange={(e) => setCantidad(Number(e.target.value))}
        />

        <TextField
          label="Notas"
          multiline
          minRows={2}
          value={notas}
          onChange={(e) => setNotas(e.target.value)}
        />

        <Button variant="contained" onClick={handleCrearOrden} sx={{ py: 1.3 }} disabled={!muebleId}>
          Crear orden
        </Button>
      </Paper>

      <Paper sx={{ p: 2.5, borderRadius: 3, display: 'flex', flexDirection: 'column', gap: 2, minHeight: 0 }}>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 600, mb: 0.4 }}>
            Resumen de producción
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>
            Totales por orden y cortes estimados.
          </Typography>
        </Box>

        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          <Chip label={`Tornillos: ${resumen?.total_tornillos ?? totalesPreview.tornillos}`} variant="outlined" />
          <Chip label={`Pegamento: ${resumen?.total_pegamento_ml ?? totalesPreview.pegamento} ml`} variant="outlined" />
          <Chip label={`Pintura: ${resumen?.total_pintura_ml ?? totalesPreview.pintura} ml`} variant="outlined" />
          <Chip label={`Perfiles: ${resumen?.total_perfiles_m ?? totalesPreview.perfiles} m`} variant="outlined" />
        </Box>

        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          <Chip label={`Cortes totales: ${resumen?.cortes_total ?? cortesPreview}`} variant="outlined" />
          <Chip label={`Planchas: ${resumen?.planchas_usadas ?? '--'}`} variant="outlined" />
          <Chip label={`Retazos: ${resumen?.retazos_total ?? '--'}`} variant="outlined" />
        </Box>

        {resumen?.retazos_por_plancha?.length ? (
          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
            {resumen.retazos_por_plancha.map((cantidadRetazo, index) => (
              <Chip key={index} label={`Plancha ${index + 1}: ${cantidadRetazo} retazos`} size="small" variant="outlined" />
            ))}
          </Box>
        ) : null}

        <Divider />

        <Typography variant="subtitle2" sx={{ color: 'text.secondary', letterSpacing: 1, textTransform: 'uppercase' }}>
          Lista de cortes
        </Typography>

        <Box sx={{ maxHeight: 220, overflow: 'auto' }}>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                <TableCell>Pieza</TableCell>
                <TableCell align="center">Largo</TableCell>
                <TableCell align="center">Ancho</TableCell>
                <TableCell align="center">Cant.</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {piezasMueble.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={4} align="center" sx={{ py: 3, color: 'text.secondary' }}>
                    Sin piezas registradas.
                  </TableCell>
                </TableRow>
              ) : (
                piezasMueble.map((pieza, index) => (
                  <TableRow key={index} hover>
                    <TableCell>{pieza.id_pieza}</TableCell>
                    <TableCell align="center">{pieza.largo}</TableCell>
                    <TableCell align="center">{pieza.ancho}</TableCell>
                    <TableCell align="center">{pieza.cantidad}</TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
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
                  <TableRow key={orden.id} hover>
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
  );
}

export default Ordenes;
