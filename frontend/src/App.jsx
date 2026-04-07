import { useState, useContext } from 'react';
import {
  BrowserRouter as Router,
  Routes,
  Route,
  Link,
  useLocation,
  Navigate,
} from 'react-router-dom';
import {
  Box, Typography, ThemeProvider, createTheme, CssBaseline,
  Button, Chip, Divider, Collapse, IconButton, Tooltip, Avatar,
  CircularProgress, Menu, MenuItem,
} from '@mui/material';

import Inventario from './pages/Inventario';
import Cortes from './pages/Cortes';
import Ordenes from './pages/Ordenes';
import Pendientes from './pages/Pendientes';
import Cotizador from './pages/Cotizador';
import CRM from './pages/CRM';
import CRMInbox from './pages/CRMInbox';
import Precios from './pages/Precios';
import AdminComparaciones from './pages/AdminComparaciones';
import LoginPage from './pages/LoginPage';
import AuthSuccess from './pages/AuthSuccess';
import { AdminContext } from './context/adminContext';
import { AuthProvider, useAuth } from './context/AuthContext';

// ---------------------------------------------------------------------------
// Theme — HubSpot-inspired
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
// Navigation config
// ---------------------------------------------------------------------------
const navSections = [
  {
    title: 'Produccion', icon: '🏭',
    items: [
      { to: '/',           label: 'Inventario',  caption: 'Materiales y stock',     icon: '📦' },
      { to: '/cortes',     label: 'Cortes',      caption: 'Optimizacion de corte',  icon: '✂️' },
      { to: '/ordenes',    label: 'Ordenes',     caption: 'Trabajo y recursos',     icon: '📋' },
      { to: '/pendientes', label: 'Pendientes',  caption: 'Prioridades',            icon: '⏳' },
    ],
  },
  {
    title: 'Compras', icon: '🛒',
    items: [
      { to: '/cotizador',  label: 'Cotizador',   caption: 'Comparar proveedores',  icon: '🔍' },
      { to: '/precios',    label: 'Precios',     caption: 'Historial y alertas',   icon: '📊' },
      { to: '/admin-ia',   label: 'Monitor IA',  caption: 'Diagnostico matching',  icon: '🧠' },
    ],
  },
  {
    title: 'Ventas', icon: '💼',
    items: [
      { to: '/crm',        label: 'CRM',         caption: 'Deals y clientes',      icon: '🤝' },
      { to: '/crm/inbox',  label: 'Bandeja',     caption: 'Correo y contactos',    icon: '📬' },
    ],
  },
];

// ---------------------------------------------------------------------------
// NavItem
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
// UserMenu — avatar + nombre + dropdown con logout
// ---------------------------------------------------------------------------
function UserMenu({ collapsed }) {
  const { user, logout } = useAuth();
  const [anchor, setAnchor] = useState(null);
  if (!user) return null;

  const initials = (user.nombre || user.email || '?')
    .split(' ')
    .map((p) => p[0])
    .filter(Boolean)
    .slice(0, 2)
    .join('')
    .toUpperCase();

  return (
    <>
      <Box
        onClick={(e) => setAnchor(e.currentTarget)}
        sx={{
          display: 'flex', alignItems: 'center', gap: 1.2,
          p: 1, borderRadius: 2, cursor: 'pointer',
          '&:hover': { backgroundColor: 'rgba(31,58,95,0.06)' },
          justifyContent: collapsed ? 'center' : 'flex-start',
        }}
      >
        <Avatar
          src={user.avatar_url || undefined}
          sx={{ width: 32, height: 32, bgcolor: 'primary.main', fontSize: '0.85rem' }}
        >
          {initials}
        </Avatar>
        {!collapsed && (
          <Box sx={{ minWidth: 0, flexGrow: 1 }}>
            <Typography variant="body2" sx={{ fontWeight: 600, lineHeight: 1.2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {user.nombre || user.email}
            </Typography>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.62rem', lineHeight: 1.1 }}>
              {user.is_admin ? 'Administrador' : user.email}
            </Typography>
          </Box>
        )}
      </Box>
      <Menu
        anchorEl={anchor}
        open={Boolean(anchor)}
        onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: 'top', horizontal: 'right' }}
      >
        <MenuItem disabled>
          <Box>
            <Typography variant="body2" fontWeight={600}>{user.nombre}</Typography>
            <Typography variant="caption" color="text.secondary">{user.email}</Typography>
          </Box>
        </MenuItem>
        <Divider />
        <MenuItem onClick={() => { setAnchor(null); logout(); }}>
          Cerrar sesión
        </MenuItem>
      </Menu>
    </>
  );
}

// ---------------------------------------------------------------------------
// AppMain — Layout autenticado
// ---------------------------------------------------------------------------
function AppMain() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  return (
    <Box sx={{
      minHeight: '100vh', height: '100vh', overflow: 'hidden',
      display: 'flex', flexDirection: { xs: 'column', md: 'row' },
    }}>
      {/* SIDEBAR */}
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

        {!sidebarCollapsed ? (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, flexGrow: 1, overflow: 'auto' }}>
            {navSections.map((section) => (
              <NavSection key={section.title} section={section} />
            ))}
          </Box>
        ) : (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5, flexGrow: 1, alignItems: 'center', pt: 1 }}>
            {navSections.flatMap((s) => s.items).map((item) => (
              <CollapsedNavIcon key={item.to} {...item} />
            ))}
          </Box>
        )}

        {/* Footer: user menu */}
        <Box sx={{ mt: 'auto', pt: 2 }}>
          <Divider sx={{ mb: 1 }} />
          <UserMenu collapsed={sidebarCollapsed} />
          {!sidebarCollapsed && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.8, mt: 1, px: 1 }}>
              <Box sx={{ width: 6, height: 6, borderRadius: 999, backgroundColor: '#3ccf91' }} />
              <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.63rem' }}>
                API activa
              </Typography>
            </Box>
          )}
        </Box>
      </Box>

      {/* CONTENT */}
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
          <Route path="/crm/inbox" element={<CRMInbox />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Box>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// AuthGate — bloquea contenido si no hay sesión
// ---------------------------------------------------------------------------
function AuthGate() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === 'loading') {
    return (
      <Box sx={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <CircularProgress />
      </Box>
    );
  }

  if (status === 'anonymous') {
    if (location.pathname === '/login' || location.pathname === '/auth/success') {
      return (
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/auth/success" element={<AuthSuccess />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      );
    }
    return <Navigate to="/login" replace />;
  }

  // Authenticated: rutas privadas + redirect /login → /
  if (location.pathname === '/login') {
    return <Navigate to="/" replace />;
  }
  if (location.pathname === '/auth/success') {
    return <AuthSuccess />;
  }
  return <AppMain />;
}

// ---------------------------------------------------------------------------
// App — root
// ---------------------------------------------------------------------------
function App() {
  // El AdminContext viejo se mantiene en stub para compatibilidad con páginas
  // que lo importan (Inventario, etc). No hace nada útil — la auth real ahora
  // viene de AuthContext (OAuth2). Se eliminará tras migrar las páginas.
  const adminStub = {
    adminSession: { user: '', token: '' },
    isAdmin: false,
    openAdminDialog: () => {},
    closeAdminDialog: () => {},
    loginAdmin: () => {},
    logoutAdmin: () => {},
  };

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <AdminContext.Provider value={adminStub}>
        <Router>
          <AuthProvider>
            <AuthGate />
          </AuthProvider>
        </Router>
      </AdminContext.Provider>
    </ThemeProvider>
  );
}

export default App;
