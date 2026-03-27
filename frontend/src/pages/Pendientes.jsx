import { useEffect, useMemo, useState } from 'react';
import {
  Box, Paper, Typography, Table, TableBody, TableCell, TableHead,
  TableRow, Divider, Chip, Button, TextField, MenuItem
} from '@mui/material';
import axios from 'axios';

const API = 'http://localhost:8000';

const PRIORIDADES = [
  { value: 5, label: '5 — Alta' },
  { value: 4, label: '4' },
  { value: 3, label: '3 — Media' },
  { value: 2, label: '2' },
  { value: 1, label: '1 — Baja' },
];

const ESTADOS = ['Pendiente', 'En progreso', 'Completado', 'Cancelado'];

const ESTADO_COLOR = {
  'Pendiente': 'default',
  'En progreso': 'warning',
  'Completado': 'success',
  'Cancelado': 'error',
};

function Pendientes() {
  const [ordenes, setOrdenes] = useState([]);
  const [muebles, setMuebles] = useState([]);
  const [ordenSeleccionadaId, setOrdenSeleccionadaId] = useState(null);

  const cargarOrdenes = () => {
    axios.get(`${API}/api/ordenes`)
      .then((r) => {
        const lista = r.data || [];
        setOrdenes(lista);
        if (!ordenSeleccionadaId && lista.length) setOrdenSeleccionadaId(lista[0].id);
      })
      .catch((e) => console.error('Error al cargar ordenes:', e));
  };

  const cargarMuebles = () => {
    axios.get(`${API}/api/ordenes/muebles`)
      .then((r) => setMuebles(r.data || []))
      .catch((e) => console.error('Error al cargar muebles:', e));
  };

  useEffect(() => {
    cargarOrdenes();
    cargarMuebles();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const ordenesPendientes = useMemo(() => {
    return ordenes
      .filter((o) => ['Pendiente', 'En progreso'].includes(o.estado || 'Pendiente'))
      .sort((a, b) => {
        const pa = Number(a.prioridad ?? 3), pb = Number(b.prioridad ?? 3);
        if (pa !== pb) return pb - pa;
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      });
  }, [ordenes]);

  useEffect(() => {
    if (!ordenesPendientes.length) { setOrdenSeleccionadaId(null); return; }
    const existe = ordenesPendientes.some((o) => Number(o.id) === Number(ordenSeleccionadaId));
    if (!existe) setOrdenSeleccionadaId(ordenesPendientes[0].id);
  }, [ordenesPendientes, ordenSeleccionadaId]);

  const ordenSeleccionada = useMemo(
    () => ordenesPendientes.find((o) => Number(o.id) === Number(ordenSeleccionadaId)),
    [ordenesPendientes, ordenSeleccionadaId]
  );

  const muebleSeleccionado = useMemo(
    () => muebles.find((m) => Number(m.id) === Number(ordenSeleccionada?.mueble_id)),
    [muebles, ordenSeleccionada]
  );

  const piezasMueble = useMemo(() => {
    if (!muebleSeleccionado || !ordenSeleccionada) return [];
    return (muebleSeleccionado.piezas || []).map((p) => ({
      ...p,
      cantidad: Number(p.cantidad || 0) * Number(ordenSeleccionada.cantidad || 1),
    }));
  }, [muebleSeleccionado, ordenSeleccionada]);

  const handlePrioridad = (ordenId, prioridad) => {
    axios.put(`${API}/api/ordenes/${ordenId}/prioridad`, { prioridad })
      .then(() => cargarOrdenes())
      .catch((e) => console.error('Error prioridad:', e));
  };

  const handleEstado = (ordenId, estado) => {
    axios.put(`${API}/api/ordenes/${ordenId}/estado`, { estado })
      .then(() => cargarOrdenes())
      .catch((e) => console.error('Error estado:', e));
  };

  const handleEliminar = (ordenId) => {
    if (!window.confirm('¿Eliminar esta orden? Esta acción no se puede deshacer.')) return;
    axios.delete(`${API}/api/ordenes/${ordenId}`)
      .then(() => cargarOrdenes())
      .catch((e) => {
        const msg = e?.response?.data?.detail || 'Error al eliminar la orden.';
        alert(msg);
      });
  };

  return (
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: '360px 1fr' }, gap: 2.5, alignItems: 'stretch', height: '100%', minHeight: 0 }}>
      {/* Left — orders list */}
      <Paper sx={{ p: 2.5, borderRadius: 3, display: 'flex', flexDirection: 'column', gap: 2, minHeight: 0 }}>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 600, mb: 0.4 }}>Órdenes activas</Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>Pendientes y en progreso, por prioridad.</Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
          <Chip label={`Activas: ${ordenesPendientes.length}`} variant="outlined" />
          <Button size="small" variant="outlined" onClick={cargarOrdenes}>Actualizar</Button>
        </Box>
        <Divider />
        <Box sx={{ flexGrow: 1, overflow: 'auto' }}>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                <TableCell>Orden</TableCell>
                <TableCell align="center">Prio.</TableCell>
                <TableCell align="center">Estado</TableCell>
                <TableCell align="center"></TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {ordenesPendientes.length === 0 ? (
                <TableRow><TableCell colSpan={4} align="center" sx={{ py: 4, color: 'text.secondary' }}>No hay órdenes activas.</TableCell></TableRow>
              ) : ordenesPendientes.map((orden) => (
                <TableRow
                  key={orden.id} hover
                  selected={Number(orden.id) === Number(ordenSeleccionadaId)}
                  onClick={() => setOrdenSeleccionadaId(orden.id)}
                  sx={{ cursor: 'pointer' }}
                >
                  <TableCell>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>{orden.mueble_nombre}</Typography>
                    <Typography variant="caption" sx={{ color: 'text.secondary' }}>×{orden.cantidad}</Typography>
                  </TableCell>
                  <TableCell align="center" onClick={(e) => e.stopPropagation()}>
                    <TextField
                      select size="small" value={orden.prioridad ?? 3}
                      onChange={(e) => handlePrioridad(orden.id, Number(e.target.value))}
                      sx={{ minWidth: 90 }}
                    >
                      {PRIORIDADES.map((op) => <MenuItem key={op.value} value={op.value}>{op.value}</MenuItem>)}
                    </TextField>
                  </TableCell>
                  <TableCell align="center" onClick={(e) => e.stopPropagation()}>
                    <TextField
                      select size="small" value={orden.estado || 'Pendiente'}
                      onChange={(e) => handleEstado(orden.id, e.target.value)}
                      sx={{ minWidth: 120 }}
                    >
                      {ESTADOS.map((s) => <MenuItem key={s} value={s}>{s}</MenuItem>)}
                    </TextField>
                  </TableCell>
                  <TableCell align="center" onClick={(e) => e.stopPropagation()}>
                    <Button size="small" color="error" variant="text" onClick={() => handleEliminar(orden.id)} sx={{ minWidth: 0, px: 1 }}>✕</Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Box>
      </Paper>

      {/* Right — materials detail */}
      <Paper sx={{ p: 2.5, borderRadius: 3, display: 'flex', flexDirection: 'column', gap: 2, minHeight: 0 }}>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 600, mb: 0.4 }}>Materiales del mueble</Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>
            {ordenSeleccionada
              ? `${ordenSeleccionada.mueble_nombre} — ${ordenSeleccionada.estado || 'Pendiente'}`
              : 'Selecciona una orden para ver materiales.'}
          </Typography>
        </Box>

        {ordenSeleccionada && (
          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
            <Chip label={`Estado: ${ordenSeleccionada.estado || 'Pendiente'}`} size="small" color={ESTADO_COLOR[ordenSeleccionada.estado] || 'default'} variant="outlined" />
            <Chip label={`Prioridad: ${ordenSeleccionada.prioridad ?? 3}`} size="small" variant="outlined" />
          </Box>
        )}

        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          <Chip label={`Tornillos: ${ordenSeleccionada?.total_tornillos ?? 0}`} variant="outlined" />
          <Chip label={`Pegamento: ${ordenSeleccionada?.total_pegamento_ml ?? 0} ml`} variant="outlined" />
          <Chip label={`Pintura: ${ordenSeleccionada?.total_pintura_ml ?? 0} ml`} variant="outlined" />
          <Chip label={`Perfiles: ${ordenSeleccionada?.total_perfiles_m ?? 0} m`} variant="outlined" />
        </Box>

        <Divider />

        <Typography variant="subtitle2" sx={{ color: 'text.secondary', letterSpacing: 1, textTransform: 'uppercase' }}>Lista de piezas</Typography>

        <Box sx={{ flexGrow: 1, overflow: 'auto' }}>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                <TableCell>Pieza</TableCell>
                <TableCell align="center">Largo (mm)</TableCell>
                <TableCell align="center">Ancho (mm)</TableCell>
                <TableCell align="center">Cant.</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {piezasMueble.length === 0 ? (
                <TableRow><TableCell colSpan={4} align="center" sx={{ py: 4, color: 'text.secondary' }}>Sin piezas registradas.</TableCell></TableRow>
              ) : piezasMueble.map((pieza, i) => (
                <TableRow key={i} hover>
                  <TableCell>{pieza.id_pieza}</TableCell>
                  <TableCell align="center">{pieza.largo}</TableCell>
                  <TableCell align="center">{pieza.ancho}</TableCell>
                  <TableCell align="center">{pieza.cantidad}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Box>
      </Paper>
    </Box>
  );
}

export default Pendientes;
