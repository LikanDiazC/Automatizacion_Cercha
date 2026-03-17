import { useState, useEffect } from 'react';
import { 
  Typography, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, 
  Button, Dialog, DialogTitle, DialogContent, DialogActions, TextField, MenuItem, Box, Chip 
} from '@mui/material';
import axios from 'axios';

function Inventario() {
  const [articulos, setArticulos] = useState([]);
  const [openForm, setOpenForm] = useState(false);
  const [nuevoArticulo, setNuevoArticulo] = useState({
    codigo_sku: '', nombre: '', tipo: 'Plancha/Tablero', 
    unidad_compra: '', unidad_almacenamiento: '', unidad_consumo: '', stock_actual: 0
  });

  const cargarInventario = () => {
    axios.get('http://localhost:8000/api/inventario/articulos')
      .then((respuesta) => setArticulos(respuesta.data))
      .catch((error) => console.error("Error al cargar:", error));
  };

  useEffect(() => { cargarInventario(); }, []);

  const handleAbrir = () => setOpenForm(true);
  const handleCerrar = () => setOpenForm(false);
  const handleChange = (e) => setNuevoArticulo({ ...nuevoArticulo, [e.target.name]: e.target.value });

  const handleGuardar = () => {
    axios.post('http://localhost:8000/api/inventario/articulos', nuevoArticulo)
      .then(() => {
        handleCerrar();
        cargarInventario();
        setNuevoArticulo({codigo_sku: '', nombre: '', tipo: 'Plancha/Tablero', unidad_compra: '', unidad_almacenamiento: '', unidad_consumo: '', stock_actual: 0});
      })
      .catch(() => alert("Error al guardar. Verifica que el SKU no esté repetido."));
  };

  return (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column', p: 3, boxSizing: 'border-box' }}>
      
      {/* CABECERA DE LA PÁGINA */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <div>
          <Typography variant="h5" sx={{ fontWeight: 'bold', color: '#0f172a' }}>
            Registro Maestro de Artículos
          </Typography>
          <Typography variant="body2" sx={{ color: '#64748b' }}>
            Gestión centralizada de materias primas y retazos del taller.
          </Typography>
        </div>
        <Button 
          variant="contained" 
          disableElevation
          onClick={handleAbrir}
          sx={{ backgroundColor: '#0284c7', textTransform: 'none', fontWeight: 'bold', borderRadius: '8px', px: 3, py: 1, '&:hover': { backgroundColor: '#0369a1' } }}
        >
          + Nuevo Material
        </Button>
      </Box>
      
      {/* TABLA DE DATOS (DATA GRID) FULL-WIDTH */}
      <TableContainer sx={{ flexGrow: 1, backgroundColor: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '12px', overflow: 'auto' }}>
        <Table stickyHeader>
          <TableHead>
            <TableRow>
              <TableCell sx={{ backgroundColor: '#f8fafc', fontWeight: '600', color: '#475569', borderBottom: '2px solid #e2e8f0' }}>SKU</TableCell>
              <TableCell sx={{ backgroundColor: '#f8fafc', fontWeight: '600', color: '#475569', borderBottom: '2px solid #e2e8f0' }}>Descripción del Material</TableCell>
              <TableCell sx={{ backgroundColor: '#f8fafc', fontWeight: '600', color: '#475569', borderBottom: '2px solid #e2e8f0' }}>Tipo</TableCell>
              <TableCell align="center" sx={{ backgroundColor: '#f8fafc', fontWeight: '600', color: '#475569', borderBottom: '2px solid #e2e8f0' }}>Stock</TableCell>
              <TableCell sx={{ backgroundColor: '#f8fafc', fontWeight: '600', color: '#475569', borderBottom: '2px solid #e2e8f0' }}>U. Almacén</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {articulos.map((item) => (
              <TableRow key={item.id} hover sx={{ '&:last-child td, &:last-child th': { border: 0 } }}>
                <TableCell sx={{ fontFamily: 'monospace', color: '#64748b' }}>{item.codigo_sku}</TableCell>
                <TableCell sx={{ fontWeight: '500', color: '#0f172a' }}>{item.nombre}</TableCell>
                <TableCell>
                  <Chip 
                    label={item.tipo} 
                    size="small" 
                    sx={{ backgroundColor: item.tipo === 'Plancha/Tablero' ? '#f1f5f9' : '#f0fdf4', color: '#475569', fontWeight: '500', borderRadius: '6px' }} 
                  />
                </TableCell>
                <TableCell align="center">
                  <Chip 
                    label={item.stock_actual} 
                    size="small"
                    sx={{ 
                      fontWeight: 'bold', 
                      borderRadius: '6px',
                      backgroundColor: item.stock_actual > 0 ? '#dcfce7' : '#fee2e2', 
                      color: item.stock_actual > 0 ? '#166534' : '#991b1b',
                      minWidth: '50px'
                    }} 
                  />
                </TableCell>
                <TableCell sx={{ color: '#64748b' }}>{item.unidad_almacenamiento}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      {/* MODAL FORMULARIO */}
      <Dialog open={openForm} onClose={handleCerrar} maxWidth="sm" fullWidth PaperProps={{ sx: { borderRadius: '12px' } }}>
        <DialogTitle sx={{ fontWeight: 'bold', color: '#0f172a', borderBottom: '1px solid #e2e8f0', pb: 2 }}>Registrar Nuevo Material</DialogTitle>
        <DialogContent sx={{ pt: '20px !important' }}>
          <TextField margin="dense" name="codigo_sku" label="Código SKU" fullWidth variant="outlined" value={nuevoArticulo.codigo_sku} onChange={handleChange} size="small" sx={{ mb: 2 }} />
          <TextField margin="dense" name="nombre" label="Nombre del Material" fullWidth variant="outlined" value={nuevoArticulo.nombre} onChange={handleChange} size="small" sx={{ mb: 2 }} />
          <TextField margin="dense" name="tipo" label="Tipo de Material" select fullWidth variant="outlined" value={nuevoArticulo.tipo} onChange={handleChange} size="small" sx={{ mb: 2 }}>
            <MenuItem value="Plancha/Tablero">Plancha/Tablero</MenuItem>
            <MenuItem value="Lineal">Lineal</MenuItem>
            <MenuItem value="Unidad">Unidad</MenuItem>
          </TextField>
          <Box sx={{ display: 'flex', gap: '10px', mb: 2 }}>
            <TextField margin="dense" name="unidad_compra" label="U. Compra" fullWidth variant="outlined" value={nuevoArticulo.unidad_compra} onChange={handleChange} size="small" />
            <TextField margin="dense" name="unidad_almacenamiento" label="U. Almacén" fullWidth variant="outlined" value={nuevoArticulo.unidad_almacenamiento} onChange={handleChange} size="small" />
          </Box>
          <Box sx={{ display: 'flex', gap: '10px' }}>
            <TextField margin="dense" name="unidad_consumo" label="U. Consumo" fullWidth variant="outlined" value={nuevoArticulo.unidad_consumo} onChange={handleChange} size="small" />
            <TextField margin="dense" name="stock_actual" label="Stock Inicial" type="number" fullWidth variant="outlined" value={nuevoArticulo.stock_actual} onChange={handleChange} size="small" />
          </Box>
        </DialogContent>
        <DialogActions sx={{ p: 3, borderTop: '1px solid #e2e8f0' }}>
          <Button onClick={handleCerrar} sx={{ color: '#64748b', fontWeight: 'bold', textTransform: 'none' }}>Cancelar</Button>
          <Button onClick={handleGuardar} variant="contained" disableElevation sx={{ backgroundColor: '#0f172a', fontWeight: 'bold', textTransform: 'none', borderRadius: '8px', '&:hover': { backgroundColor: '#334155' } }}>Guardar Material</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

export default Inventario;