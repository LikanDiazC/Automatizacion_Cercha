import { useState, useContext } from 'react';
import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom';
import {
  Box, Typography, ThemeProvider, createTheme, CssBaseline,
  Button, Chip, Dialog, DialogTitle, DialogContent, DialogActions,
  TextField, Divider, Alert, Collapse, IconButton, Tooltip,
} from '@mui/material';

import Inventario from './pages/Inventario';
import Cortes from './pages/Cortes';
import Ordenes from './pages/Ordenes';
import Pendientes from './pages/Pendientes';
import Cotizador from './pages/Cotizador';
import CRM from './pages/CRM';
import Precios from './pages/Precios';
import AdminComparaciones from './pages/AdminComparaciones';
import { AdminContext } from './context/adminContext';

// ---------------------------------------------------------------------------
// Theme — HubSpot-inspired (#f6f9fc background, clean blues)
// ---------------------------------------------------------------------------

const theme = createTheme({
  palette: {
    mode: 'light',
    primary: { main: '#1f3a5f', dark: '#152a44', light: '#355980', contrastText: '#f6f4ef' },
    secondary: { main: '#c98c4a' },
    background: { default: '#f6f9fc', paper: '#ffffff' },
    text: { primary: '#1c232b', secondary: '#5f6b75' },
    divider: 'rgba(28, 35, 43, 0.10)',
  },
  shape: { borderRadius: 14 },
  typography: {
    fontFamily: '"Spline Sans", "Space Grotesk", sans-serif',
    h3: { fontFamily: '"Space Grotesk", "Spline Sans", sans-serif', fontWeight: 600, letterSpacing: -0.4 },
    h4: { fontFamily: '"Space Grotesk", "Spline Sans", sans-serif', fontWeight: 600, letterSpacing: -0.3 },
    h5: { fontFamily: '"Space Grotesk", "Spline Sans", sans-serif', fontWeight: 600 },
    button: { textTransform: 'none', fontWeight: 600 },
  },
  components: {
    MuiPaper: { styleOverrides: { root: { border: '1px solid rgba(28, 35, 43, 0.08)', backgroundImage: 'none', boxShadow: 'none' } } },
    MuiButton: { styleOverrides: { root: { borderRadius: 999 } } },
    MuiChip: { styleOverrides: { root: { fontWeight: 600, borderRadius: 999 } } },
    MuiTableCell: { styleOverrides: { head: { backgroundColor: 'rgba(31, 58, 95, 0.06)', color: '#3a4651', fontWeight: 600 } } },
    MuiOutlinedInput: { styleOverrides: { root: { borderRadius: 12, backgroundColor: 'rgba(255, 255, 255, 0.9)' } } },
  },
});

// ---------------------------------------------------------------------------
// Navigation config — grouped sections (HubSpot style)
// ---------------------------------------------------------------------------

const navSections = [
  {
    title: 'Produccion',
    icon: '🏭',
    items: [
      { to: '/',           label: 'Inventario',  caption: 'Materiales y stock',  icon: '📦' },
      { to: '/cortes',     label: 'Cortes',      caption: 'Optimizacion de corte', icon: '✂️' },
      { to: '/ordenes',    label: 'Ordenes',     caption: 'Trabajo y recursos',  icon: '📋' },
      { to: '/pendientes', label: 'Pendientes',  caption: 'Prioridades',         icon: '⏳' },
    ],
  },
  {
    title: 'Compras',
    icon: '🛒',
    items: [
      { to: '/cotizador',  label: 'Cotizador',   caption: 'Comparar proveedores', icon: '🔍' },
      { to: '/precios',    label: 'Precios',     caption: 'Historial y alertas',  icon: '📊' },
      { to: '/admin-ia',   label: 'Monitor IA',  caption: 'Diagnostico matching', icon: '🧠' },
    ],
  },
  {
    title: 'Ventas',
    icon: '💼',
    items: [
      { to: '/crm',        label: 'CRM',         caption: 'Deals y clientes',    icon: '🤝' },
    ],
  },
];

// ---------------------------------------------------------------------------
// NavItem — individual link
// ---------------------------------------------------------------------------

const NavItem = ({ to, label, caption, icon }) => {
  const location = useLocation();
  const isActive = location.pathname === to;
  return (
    <Box
      component={Link} to={to}
      sx={{
        textDecoration: 'none', color: 'inherit',
        px: 1.5, py: 1, borderRadius: 2,
        display: 'flex', alignItems: 'center', gap: 1.2,
        backgroundColor: isActive ? 'rgba(31, 58, 95, 0.10)' : 'transparent',
        border: '1px solid',
        borderColor: isActive ? 'rgba(31, 58, 95, 0.18)' : 'transparent',
        transition: 'all 0.15s ease',
        '&:hover': {
          backgroundColor: isActive ? 'rgba(31, 58, 95, 0.12)' : 'rgba(31, 58, 95, 0.05)',
          borderColor: 'rgba(31, 58, 95, 0.12)',
        },
      }}
    >
      <Typography sx={{ fontSize: '1rem', lineHeight: 1, width: 22, textAlign: 'center' }}>{icon}</Typography>
      <Box sx={{ minWidth: 0 }}>
        <Typography variant="body2" sx={{ fontWeight: isActive ? 700 : 600, lineHeight: 1.3 }}>
          {label}
        </Typography>
        <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.63rem', lineHeight: 1.2 }}>
          {caption}
        </Typography>
      </Box>
    </Box>
  );
};

// ---------------------------------------------------------------------------
// NavSection — collapsible section group
// ---------------------------------------------------------------------------

const NavSection = ({ section, defaultOpen = true }) => {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Box>
      <Box
        onClick={() => setOpen(!open)}
        sx={{
          display: 'flex', alignItems: 'center', gap: 0.8,
          px: 1, py: 0.5, cursor: 'pointer', borderRadius: 1.5,
          userSelect: 'none',
          '&:hover': { backgroundColor: 'rgba(0,0,0,0.03)' },
        }}
      >
        <Typography sx={{ fontSize: '0.8rem' }}>{section.icon}</Typography>
        <Typography variant="caption" sx={{
          fontWeight: 700, letterSpacing: 0.8, textTransform: 'uppercase',
          color: 'text.secondary', fontSize: '0.65rem', flexGrow: 1,
        }}>
          {section.title}
        </Typography>
        <Typography sx={{
          fontSize: '0.6rem', color: 'text.disabled',
          transform: open ? 'rotate(0deg)' : 'rotate(-90deg)',
          transition: 'transform 0.2s',
        }}>
          ▼
        </Typography>
      </Box>
      <Collapse in={open}>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.3, mt: 0.5 }}>
          {section.items.map((item) => (
            <NavItem key={item.to} {...item} />
          ))}
        </Box>
      </Collapse>
    </Box>
  );
};

// ---------------------------------------------------------------------------
// CollapsedNavIcon — icon-only nav item for collapsed sidebar
// ---------------------------------------------------------------------------

const CollapsedNavIcon = ({ to, label, icon }) => {
  const location = useLocation();
  const isActive = location.pathname === to;
  return (
    <Tooltip title={label} placement="right">
      <Box
        component={Link} to={to}
        sx={{
          textDecoration: 'none', width: 38, height: 38,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          borderRadius: 2,
          backgroundColor: isActive ? 'rgba(31,58,95,0.10)' : 'transparent',
          '&:hover': { backgroundColor: 'rgba(31,58,95,0.08)' },
          transition: 'background-color 0.15s',
        }}
      >
        <Typography sx={{ fontSize: '1rem' }}>{icon}</Typography>
      </Box>
    </Tooltip>
  );
};

// ---------------------------------------------------------------------------
// AppMain — Layout with sidebar + content
// ---------------------------------------------------------------------------

function AppMain() {
  const { isAdmin, openAdminDialog, logoutAdmin } = useContext(AdminContext);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  return (
    <Box sx={{
      minHeight: '100vh', height: '100vh', overflow: 'hidden',
      display: 'flex', flexDirection: { xs: 'column', md: 'row' },
    }}>
      {/* ---- SIDEBAR ---- */}
      <Box sx={{
        width: { xs: '100%', md: sidebarCollapsed ? 60 : 260 },
        minWidth: { md: sidebarCollapsed ? 60 : 260 },
        transition: 'width 0.25s ease, min-width 0.25s ease',
        px: { xs: 2, md: sidebarCollapsed ? 0.8 : 2 },
        py: { xs: 2, md: 2.5 },
        borderRight: { md: '1px solid' },
        borderColor: { md: 'divider' },
        backgroundColor: '#ffffff',
        display: 'flex', flexDirection: 'column',
        overflow: 'hidden',
      }}>
        {/* Logo + collapse */}
        <Box sx={{
          display: 'flex', alignItems: 'center', gap: 1,
          mb: 2, px: sidebarCollapsed ? 0 : 0.5,
          justifyContent: sidebarCollapsed ? 'center' : 'flex-start',
        }}>
          {!sidebarCollapsed && (
            <Box sx={{ flexGrow: 1 }}>
              <Typography variant="h5" sx={{ fontWeight: 800, letterSpacing: 0.8, fontSize: '1.2rem' }}>
                CERCHA
              </Typography>
              <Typography variant="caption" sx={{
                color: 'text.secondary', letterSpacing: 1.2, textTransform: 'uppercase',
                fontSize: '0.55rem',
              }}>
                ERP + MRP + CRM
              </Typography>
            </Box>
          )}
          <Tooltip title={sidebarCollapsed ? 'Expandir menu' : 'Colapsar menu'}>
            <IconButton
              size="small"
              onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
              sx={{
                width: 28, height: 28, borderRadius: 1.5,
                backgroundColor: 'rgba(31,58,95,0.06)',
                '&:hover': { backgroundColor: 'rgba(31,58,95,0.12)' },
              }}
            >
              <Typography sx={{ fontSize: '0.7rem', transform: sidebarCollapsed ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}>
                ◀
              </Typography>
            </IconButton>
          </Tooltip>
        </Box>

        {/* Nav sections */}
        {!sidebarCollapsed ? (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, flexGrow: 1, overflow: 'auto' }}>
            {navSections.map((section) => (
              <NavSection key={section.title} section={section} />
            ))}
          </Box>
        ) : (
          /* Collapsed: show only icons */
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5, flexGrow: 1, alignItems: 'center', pt: 1 }}>
            {navSections.flatMap(s => s.items).map((item) => (
              <CollapsedNavIcon key={item.to} {...item} />
            ))}
          </Box>
        )}

        {/* Footer */}
        {!sidebarCollapsed && (
          <Box sx={{ mt: 'auto', pt: 2, display: 'flex', flexDirection: 'column', gap: 1 }}>
            <Divider />
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.8, alignItems: 'center', pt: 0.5 }}>
              <Chip
                size="small"
                label={isAdmin ? 'Admin' : 'Usuario'}
                variant="outlined"
                color={isAdmin ? 'primary' : 'default'}
                sx={{ fontSize: '0.65rem', height: 22 }}
              />
              {isAdmin
                ? <Button size="small" color="inherit" onClick={logoutAdmin}
                    sx={{ fontSize: '0.7rem', minWidth: 0, px: 1 }}>
                    Salir
                  </Button>
                : <Button size="small" variant="outlined" onClick={openAdminDialog}
                    sx={{ fontSize: '0.7rem', minWidth: 0, px: 1.5 }}>
                    Login
                  </Button>
              }
            </Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.8 }}>
              <Box sx={{ width: 6, height: 6, borderRadius: 999, backgroundColor: '#3ccf91' }} />
              <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.63rem' }}>
                API activa
              </Typography>
            </Box>
          </Box>
        )}
      </Box>

      {/* ---- CONTENT AREA ---- */}
      <Box sx={{
        flexGrow: 1, minHeight: 0, height: '100%',
        display: 'flex', flexDirection: 'column', overflow: 'hidden',
        px: { xs: 2, md: 3 }, py: { xs: 2, md: 3 },
        backgroundColor: '#f6f9fc',
      }}>
        <Routes>
          <Route path="/" element={<Inventario />} />
          <Route path="/cortes" element={<Cortes />} />
          <Route path="/ordenes" element={<Ordenes />} />
          <Route path="/pendientes" element={<Pendientes />} />
          <Route path="/cotizador" element={<Cotizador />} />
          <Route path="/precios" element={<Precios />} />
          <Route path="/admin-ia" element={<AdminComparaciones />} />
          <Route path="/crm" element={<CRM />} />
        </Routes>
      </Box>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// App — root with providers
// ---------------------------------------------------------------------------

function App() {
  const [adminSession, setAdminSession] = useState(() => ({
    user: sessionStorage.getItem('cercha_admin_user') || '',
    token: sessionStorage.getItem('cercha_admin_token') || '',
  }));
  const [openAdmin, setOpenAdmin] = useState(false);
  const [adminUserInput, setAdminUserInput] = useState('');
  const [adminTokenInput, setAdminTokenInput] = useState('');
  const [loginError, setLoginError] = useState('');

  const isAdmin = Boolean(adminSession.user && adminSession.token);

  const openAdminDialog = () => {
    setAdminUserInput('');
    setAdminTokenInput('');
    setLoginError('');
    setOpenAdmin(true);
  };

  const loginAdmin = () => {
    const user = adminUserInput.trim();
    const token = adminTokenInput.trim();
    if (!user || !token) { setLoginError('Completa ambos campos.'); return; }
    const next = { user, token };
    setAdminSession(next);
    sessionStorage.setItem('cercha_admin_user', next.user);
    sessionStorage.setItem('cercha_admin_token', next.token);
    setOpenAdmin(false);
    setLoginError('');
  };

  const logoutAdmin = () => {
    setAdminSession({ user: '', token: '' });
    sessionStorage.removeItem('cercha_admin_user');
    sessionStorage.removeItem('cercha_admin_token');
  };

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <AdminContext.Provider value={{
        adminSession, isAdmin, openAdminDialog,
        closeAdminDialog: () => setOpenAdmin(false),
        loginAdmin, logoutAdmin,
      }}>
        <Router>
          <AppMain />
        </Router>

        <Dialog open={openAdmin} onClose={() => setOpenAdmin(false)} maxWidth="xs" fullWidth
          PaperProps={{ sx: { borderRadius: 4, border: '1px solid rgba(28, 35, 43, 0.12)' } }}>
          <DialogTitle sx={{ fontWeight: 700 }}>Iniciar sesion admin</DialogTitle>
          <Divider />
          <DialogContent sx={{ pt: 3 }}>
            <Typography variant="body2" sx={{ color: 'text.secondary', mb: 2 }}>
              Las credenciales se borran al cerrar la pestana.
            </Typography>
            {loginError && <Alert severity="error" sx={{ mb: 2 }}>{loginError}</Alert>}
            <TextField label="Usuario admin" fullWidth value={adminUserInput}
              onChange={(e) => setAdminUserInput(e.target.value)} sx={{ mb: 2 }} autoComplete="off" />
            <TextField label="Token admin" type="password" fullWidth value={adminTokenInput}
              onChange={(e) => setAdminTokenInput(e.target.value)} autoComplete="new-password"
              onKeyDown={(e) => e.key === 'Enter' && loginAdmin()} />
          </DialogContent>
          <DialogActions sx={{ px: 3, pb: 3 }}>
            <Button onClick={() => setOpenAdmin(false)} color="inherit">Cancelar</Button>
            <Button onClick={loginAdmin} variant="contained" disabled={!adminUserInput || !adminTokenInput}>
              Iniciar sesion
            </Button>
          </DialogActions>
        </Dialog>
      </AdminContext.Provider>
    </ThemeProvider>
  );
}

export default App;
