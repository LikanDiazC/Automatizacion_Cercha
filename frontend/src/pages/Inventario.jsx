import { useState, useEffect, useContext } from 'react';
import {
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  MenuItem,
  Box,
  Chip,
  Paper,
  Divider
} from '@mui/material';
import axios from 'axios';
import { AdminContext } from '../context/adminContext';

function Inventario() {
  const { adminSession, isAdmin } = useContext(AdminContext);
  const [articulos, setArticulos] = useState([]);
  const [openForm, setOpenForm] = useState(false);
  const [nuevoArticulo, setNuevoArticulo] = useState({
    codigo_sku: '',
    nombre: '',
    tipo: 'Plancha/Tablero',
    unidad_compra: '',
    unidad_almacenamiento: '',
    unidad_consumo: '',
    stock_actual: 0
  });

const cargarInventario = () => {
    axios.get('http://localhost:8000/api/inventario/articulos')
      .then((respuesta) => {
        // ESCUDO: Si la respuesta es una lista, úsala. Si no, usa una lista vacía [].
        setArticulos(Array.isArray(respuesta.data) ? respuesta.data : []);
      })
      .catch((error) => console.error("Error al cargar:", error));
  };

  useEffect(() => {
    cargarInventario();
  }, []);

  const handleAbrir = () => setOpenForm(true);
  const handleCerrar = () => setOpenForm(false);
  const handleChange = (e) => setNuevoArticulo({ ...nuevoArticulo, [e.target.name]: e.target.value });

  const handleGuardar = () => {
    axios
      .post('http://localhost:8000/api/inventario/articulos', nuevoArticulo)
      .then(() => {
        handleCerrar();
        cargarInventario();
        setNuevoArticulo({
          codigo_sku: '',
          nombre: '',
          tipo: 'Plancha/Tablero',
          unidad_compra: '',
          unidad_almacenamiento: '',
          unidad_consumo: '',
          stock_actual: 0
        });
      })
      .catch(() => alert('Error al guardar. Verifica que el SKU no esté repetido.'));
  };

  const handleEliminar = (articulo) => {
    if (!articulo) return;
    if (!adminSession.user || !adminSession.token) {
      alert('Debes iniciar sesión como admin para eliminar.');
      return;
    }
    axios
      .delete(`http://localhost:8000/api/inventario/articulos/${articulo.id}`, {
        headers: {
          'X-Admin-User': adminSession.user,
          'X-Admin-Token': adminSession.token
        }
      })
      .then(() => {
        cargarInventario();
      })
      .catch((error) => {
        const detalle = error?.response?.data?.detail || 'Error al eliminar el artículo.';
        alert(detalle);
      });
  };

  const totalArticulos = articulos.length;
  const conStock = articulos.filter((item) => Number(item.stock_actual) > 0).length;

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5, height: '100%', minHeight: 0 }}>
      <Box
        sx={{
          display: 'flex',
          flexDirection: { xs: 'column', md: 'row' },
          alignItems: { xs: 'flex-start', md: 'center' },
          justifyContent: 'space-between',
          gap: 2
        }}
      >
        <Box>
          <Typography variant="h4" sx={{ fontWeight: 600, mb: 0.6 }}>
            Registro de Inventario
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>
            Controla materias primas, retazos y unidades de consumo en un solo lugar.
          </Typography>
        </Box>

        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
          <Chip label={`${totalArticulos} materiales`} variant="outlined" />
          <Chip label={`${conStock} con stock`} variant="outlined" />
          <Button variant="contained" onClick={handleAbrir} sx={{ px: 2.6 }}>
            Nuevo material
          </Button>
        </Box>
      </Box>

      <TableContainer component={Paper} sx={{ borderRadius: 3, overflow: 'auto', flexGrow: 1, minHeight: 0 }}>
        <Table stickyHeader>
          <TableHead>
            <TableRow>
              <TableCell>SKU</TableCell>
              <TableCell>Descripción del material</TableCell>
              <TableCell>Tipo</TableCell>
              <TableCell align="center">Stock</TableCell>
              <TableCell>U. Almacén</TableCell>
              <TableCell align="right">Acciones</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {articulos.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} align="center" sx={{ py: 6, color: 'text.secondary' }}>
                  No hay materiales cargados aún.
                </TableCell>
              </TableRow>
            ) : (
              articulos.map((item) => {
                const tieneStock = Number(item.stock_actual) > 0;
                return (
                  <TableRow key={item.id} hover>
                    <TableCell sx={{ fontFamily: '"Space Grotesk", "Spline Sans", sans-serif', color: 'text.secondary' }}>
                      {item.codigo_sku}
                    </TableCell>
                    <TableCell sx={{ fontWeight: 600 }}>{item.nombre}</TableCell>
                    <TableCell>
                      <Chip
                        label={item.tipo}
                        size="small"
                        sx={{
                          backgroundColor: 'rgba(31, 58, 95, 0.08)',
                          color: 'text.primary',
                          fontWeight: 600
                        }}
                      />
                    </TableCell>
                    <TableCell align="center">
                      <Chip
                        label={item.stock_actual}
                        size="small"
                        sx={{
                          fontWeight: 700,
                          backgroundColor: tieneStock ? 'rgba(60, 207, 145, 0.2)' : 'rgba(226, 86, 86, 0.18)',
                          color: tieneStock ? '#1f6f4a' : '#9b2e2e',
                          minWidth: 64
                        }}
                      />
                    </TableCell>
                    <TableCell sx={{ color: 'text.secondary' }}>{item.unidad_almacenamiento}</TableCell>
                    <TableCell align="right">
                      <Button
                        color="error"
                        size="small"
                        variant="text"
                        onClick={() => handleEliminar(item)}
                        disabled={!isAdmin}
                        sx={{ fontWeight: 700, minWidth: 0, px: 1 }}
                      >
                        X
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </TableContainer>

      <Dialog
        open={openForm}
        onClose={handleCerrar}
        maxWidth="sm"
        fullWidth
        PaperProps={{
          sx: {
            borderRadius: 4,
            border: '1px solid rgba(28, 35, 43, 0.12)'
          }
        }}
      >
        <DialogTitle sx={{ fontWeight: 700 }}>Registrar nuevo material</DialogTitle>
        <Divider />
        <DialogContent sx={{ pt: 3 }}>
          <TextField
            margin="dense"
            name="codigo_sku"
            label="Código SKU"
            fullWidth
            value={nuevoArticulo.codigo_sku}
            onChange={handleChange}
            sx={{ mb: 2 }}
          />
          <TextField
            margin="dense"
            name="nombre"
            label="Nombre del material"
            fullWidth
            value={nuevoArticulo.nombre}
            onChange={handleChange}
            sx={{ mb: 2 }}
          />
          <TextField
            margin="dense"
            name="tipo"
            label="Tipo de material"
            select
            fullWidth
            value={nuevoArticulo.tipo}
            onChange={handleChange}
            sx={{ mb: 2 }}
          >
            <MenuItem value="Plancha/Tablero">Plancha/Tablero</MenuItem>
            <MenuItem value="Lineal">Lineal</MenuItem>
            <MenuItem value="Unidad">Unidad</MenuItem>
          </TextField>
          <Box sx={{ display: 'flex', gap: 1.5, mb: 2, flexDirection: { xs: 'column', sm: 'row' } }}>
            <TextField
              margin="dense"
              name="unidad_compra"
              label="Unidad de compra"
              fullWidth
              value={nuevoArticulo.unidad_compra}
              onChange={handleChange}
            />
            <TextField
              margin="dense"
              name="unidad_almacenamiento"
              label="Unidad de almacén"
              fullWidth
              value={nuevoArticulo.unidad_almacenamiento}
              onChange={handleChange}
            />
          </Box>
          <Box sx={{ display: 'flex', gap: 1.5, flexDirection: { xs: 'column', sm: 'row' } }}>
            <TextField
              margin="dense"
              name="unidad_consumo"
              label="Unidad de consumo"
              fullWidth
              value={nuevoArticulo.unidad_consumo}
              onChange={handleChange}
            />
            <TextField
              margin="dense"
              name="stock_actual"
              label="Stock inicial"
              type="number"
              fullWidth
              value={nuevoArticulo.stock_actual}
              onChange={handleChange}
            />
          </Box>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 3 }}>
          <Button onClick={handleCerrar} color="inherit">
            Cancelar
          </Button>
          <Button onClick={handleGuardar} variant="contained">
            Guardar material
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

export default Inventario;
