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
  Button,
  TextField,
  MenuItem
} from '@mui/material';
import axios from 'axios';

const PRIORIDADES = [
  { value: 5, label: '5 - Alta' },
  { value: 4, label: '4' },
  { value: 3, label: '3 - Media' },
  { value: 2, label: '2' },
  { value: 1, label: '1 - Baja' }
];

function Pendientes() {
  const [ordenes, setOrdenes] = useState([]);
  const [muebles, setMuebles] = useState([]);
  const [ordenSeleccionadaId, setOrdenSeleccionadaId] = useState(null);

  const cargarOrdenes = () => {
    axios
      .get('https://automatizacion-cercha.onrender.com/api/ordenes')
      .then((respuesta) => {
        const lista = respuesta.data || [];
        setOrdenes(lista);
        if (!ordenSeleccionadaId && lista.length) {
          setOrdenSeleccionadaId(lista[0].id);
        }
      })
      .catch((error) => console.error('Error al cargar ordenes:', error));
  };

  const cargarMuebles = () => {
    axios
      .get('https://automatizacion-cercha.onrender.com/api/ordenes/muebles')
      .then((respuesta) => setMuebles(respuesta.data || []))
      .catch((error) => console.error('Error al cargar muebles:', error));
  };

  useEffect(() => {
    cargarOrdenes();
    cargarMuebles();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const ordenesPendientes = useMemo(() => {
    return ordenes
      .filter((orden) => (orden.estado || 'Pendiente') === 'Pendiente')
      .sort((a, b) => {
        const prioA = Number(a.prioridad ?? 3);
        const prioB = Number(b.prioridad ?? 3);
        if (prioA !== prioB) {
          return prioB - prioA;
        }
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      });
  }, [ordenes]);

  useEffect(() => {
    if (ordenesPendientes.length === 0) {
      setOrdenSeleccionadaId(null);
      return;
    }
    const existe = ordenesPendientes.some((orden) => Number(orden.id) === Number(ordenSeleccionadaId));
    if (!existe) {
      setOrdenSeleccionadaId(ordenesPendientes[0].id);
    }
  }, [ordenesPendientes, ordenSeleccionadaId]);

  const ordenSeleccionada = useMemo(() => {
    return ordenesPendientes.find((orden) => Number(orden.id) === Number(ordenSeleccionadaId));
  }, [ordenesPendientes, ordenSeleccionadaId]);

  const muebleSeleccionado = useMemo(() => {
    return muebles.find((mueble) => Number(mueble.id) === Number(ordenSeleccionada?.mueble_id));
  }, [muebles, ordenSeleccionada]);

  const piezasMueble = useMemo(() => {
    if (!muebleSeleccionado || !ordenSeleccionada) return [];
    return (muebleSeleccionado.piezas || []).map((pieza) => ({
      ...pieza,
      cantidad: Number(pieza.cantidad || 0) * Number(ordenSeleccionada.cantidad || 1)
    }));
  }, [muebleSeleccionado, ordenSeleccionada]);

  const handlePrioridadChange = (ordenId, prioridad) => {
    axios
      .put(`https://automatizacion-cercha.onrender.com/api/ordenes/${ordenId}/prioridad`, { prioridad })
      .then(() => cargarOrdenes())
      .catch((error) => console.error('Error al actualizar prioridad:', error));
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
      <Paper sx={{ p: 2.5, borderRadius: 3, display: 'flex', flexDirection: 'column', gap: 2, minHeight: 0 }}>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 600, mb: 0.4 }}>
            Ordenes pendientes
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>
            Ajusta la prioridad y revisa los materiales requeridos por mueble.
          </Typography>
        </Box>

        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
          <Chip label={`Pendientes: ${ordenesPendientes.length}`} variant="outlined" />
          <Button size="small" variant="outlined" onClick={cargarOrdenes}>
            Actualizar listado
          </Button>
        </Box>

        <Divider />

        <Box sx={{ flexGrow: 1, overflow: 'auto' }}>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                <TableCell>Orden</TableCell>
                <TableCell align="center">Cant.</TableCell>
                <TableCell align="center">Prioridad</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {ordenesPendientes.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={3} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                    No hay ordenes pendientes.
                  </TableCell>
                </TableRow>
              ) : (
                ordenesPendientes.map((orden) => (
                  <TableRow
                    key={orden.id}
                    hover
                    selected={Number(orden.id) === Number(ordenSeleccionadaId)}
                    onClick={() => setOrdenSeleccionadaId(orden.id)}
                    sx={{ cursor: 'pointer' }}
                  >
                    <TableCell>{orden.mueble_nombre}</TableCell>
                    <TableCell align="center">{orden.cantidad}</TableCell>
                    <TableCell align="center">
                      <TextField
                        select
                        size="small"
                        value={orden.prioridad ?? 3}
                        onChange={(e) => handlePrioridadChange(orden.id, Number(e.target.value))}
                        sx={{ minWidth: 120 }}
                      >
                        {PRIORIDADES.map((opcion) => (
                          <MenuItem key={opcion.value} value={opcion.value}>
                            {opcion.label}
                          </MenuItem>
                        ))}
                      </TextField>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </Box>
      </Paper>

      <Paper sx={{ p: 2.5, borderRadius: 3, display: 'flex', flexDirection: 'column', gap: 2, minHeight: 0 }}>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 600, mb: 0.4 }}>
            Materiales del mueble
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>
            {ordenSeleccionada
              ? `Orden seleccionada: ${ordenSeleccionada.mueble_nombre}`
              : 'Selecciona una orden para ver su lista de materiales.'}
          </Typography>
        </Box>

        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          <Chip label={`Tornillos: ${ordenSeleccionada?.total_tornillos ?? 0}`} variant="outlined" />
          <Chip label={`Pegamento: ${ordenSeleccionada?.total_pegamento_ml ?? 0} ml`} variant="outlined" />
          <Chip label={`Pintura: ${ordenSeleccionada?.total_pintura_ml ?? 0} ml`} variant="outlined" />
          <Chip label={`Perfiles: ${ordenSeleccionada?.total_perfiles_m ?? 0} m`} variant="outlined" />
        </Box>

        <Divider />

        <Typography variant="subtitle2" sx={{ color: 'text.secondary', letterSpacing: 1, textTransform: 'uppercase' }}>
          Lista de piezas
        </Typography>

        <Box sx={{ flexGrow: 1, overflow: 'auto' }}>
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
                  <TableCell colSpan={4} align="center" sx={{ py: 4, color: 'text.secondary' }}>
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
      </Paper>
    </Box>
  );
}

export default Pendientes;

