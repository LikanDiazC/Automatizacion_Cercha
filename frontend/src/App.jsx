import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom';
import { AppBar, Toolbar, Typography, Button, Box } from '@mui/material';

import Inventario from './pages/Inventario';
import Cortes from './pages/Cortes';

const MenuButton = ({ to, label, icon }) => {
  const location = useLocation();
  const isActive = location.pathname === to;
  return (
    <Button 
      component={Link} to={to} 
      disableElevation
      sx={{ 
        mx: 0.5, 
        px: 2.5,
        textTransform: 'none', 
        fontSize: '0.95rem',
        fontWeight: isActive ? '600' : '400',
        backgroundColor: isActive ? '#f1f5f9' : 'transparent',
        color: isActive ? '#0f172a' : '#94a3b8',
        borderRadius: '6px',
        '&:hover': { backgroundColor: isActive ? '#e2e8f0' : '#1e293b', color: '#0f172a' } 
      }}
    >
      <span style={{ marginRight: '8px', fontSize: '1.1rem' }}>{icon}</span> {label}
    </Button>
  );
};

function AppMain() {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100vh', backgroundColor: '#f8fafc', overflow: 'hidden' }}>
      
      {/* BARRA SUPERIOR ULTRA MINIMALISTA */}
      <AppBar position="static" elevation={0} sx={{ backgroundColor: '#ffffff', borderBottom: '1px solid #e2e8f0', py: 0.5 }}>
        <Toolbar>
          <Typography variant="h6" component="div" sx={{ flexGrow: 1, fontWeight: '800', letterSpacing: 0.5, color: '#0f172a' }}>
            ERP CERCHA <span style={{ color: '#0284c7', fontWeight: '400' }}>// CORE</span>
          </Typography>
          <Box sx={{ backgroundColor: '#0f172a', p: 0.5, borderRadius: '8px', display: 'flex' }}>
            <MenuButton to="/" label="Inventario" icon="📦" />
            <MenuButton to="/cortes" label="Motor de Cortes" icon="📐" />
          </Box>
        </Toolbar>
      </AppBar>

      {/* CONTENEDOR 100% FLUIDO SIN MÁRGENES MUERTOS */}
      <Box sx={{ flexGrow: 1, width: '100%', height: 'calc(100vh - 64px)', overflow: 'hidden' }}>
        <Routes>
          <Route path="/" element={<Inventario />} />
          <Route path="/cortes" element={<Cortes />} />
        </Routes>
      </Box>

    </Box>
  );
}

function App() {
  return (
    <Router>
      <AppMain />
    </Router>
  );
}

export default App;