import { useState, useContext } from 'react';
import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom';
import {
  Box,
  Typography,
  ThemeProvider,
  createTheme,
  CssBaseline,
  Button,
  Chip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Divider
} from '@mui/material';

import Inventario from './pages/Inventario';
import Cortes from './pages/Cortes';
import Ordenes from './pages/Ordenes';
import { AdminContext } from './context/adminContext';

const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#1f3a5f',
      dark: '#152a44',
      light: '#355980',
      contrastText: '#f6f4ef'
    },
    secondary: {
      main: '#c98c4a'
    },
    background: {
      default: '#f6f2eb',
      paper: '#ffffff'
    },
    text: {
      primary: '#1c232b',
      secondary: '#5f6b75'
    },
    divider: 'rgba(28, 35, 43, 0.12)'
  },
  shape: {
    borderRadius: 14
  },
  typography: {
    fontFamily: '"Spline Sans", "Space Grotesk", sans-serif',
    h3: {
      fontFamily: '"Space Grotesk", "Spline Sans", sans-serif',
      fontWeight: 600,
      letterSpacing: -0.4
    },
    h4: {
      fontFamily: '"Space Grotesk", "Spline Sans", sans-serif',
      fontWeight: 600,
      letterSpacing: -0.3
    },
    h5: {
      fontFamily: '"Space Grotesk", "Spline Sans", sans-serif',
      fontWeight: 600
    },
    button: {
      textTransform: 'none',
      fontWeight: 600
    }
  },
  components: {
    MuiPaper: {
      styleOverrides: {
        root: {
          border: '1px solid rgba(28, 35, 43, 0.08)',
          backgroundImage: 'none',
          boxShadow: 'none'
        }
      }
    },
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 999
        }
      }
    },
    MuiChip: {
      styleOverrides: {
        root: {
          fontWeight: 600,
          borderRadius: 999
        }
      }
    },
    MuiTableCell: {
      styleOverrides: {
        head: {
          backgroundColor: 'rgba(31, 58, 95, 0.06)',
          color: '#3a4651',
          fontWeight: 600
        }
      }
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          borderRadius: 12,
          backgroundColor: 'rgba(255, 255, 255, 0.9)'
        }
      }
    }
  }
});

const navItems = [
  {
    to: '/',
    label: 'Inventario',
    caption: 'Materiales, retazos y stock'
  },
  {
    to: '/cortes',
    label: 'Cortes',
    caption: 'Optimización y planos'
  },
  {
    to: '/ordenes',
    label: 'Órdenes',
    caption: 'Trabajo y recursos'
  }
];

const NavItem = ({ to, label, caption }) => {
  const location = useLocation();
  const isActive = location.pathname === to;

  return (
    <Box
      component={Link}
      to={to}
      sx={{
        textDecoration: 'none',
        color: 'inherit',
        px: 2,
        py: 1.6,
        borderRadius: 3,
        border: '1px solid',
        borderColor: isActive ? 'primary.main' : 'divider',
        backgroundColor: isActive ? 'rgba(31, 58, 95, 0.12)' : 'rgba(255, 255, 255, 0.65)',
        boxShadow: isActive ? '0 14px 30px rgba(31, 58, 95, 0.15)' : 'none',
        transition: 'all 0.2s ease',
        display: 'flex',
        flexDirection: 'column',
        gap: 0.4,
        minWidth: { xs: '0', md: 'auto' },
        '&:hover': {
          borderColor: 'primary.main',
          backgroundColor: 'rgba(31, 58, 95, 0.08)',
          transform: 'translateY(-1px)'
        }
      }}
    >
      <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
        {label}
      </Typography>
      <Typography variant="caption" sx={{ color: 'text.secondary' }}>
        {caption}
      </Typography>
    </Box>
  );
};

function AppMain() {
  const { isAdmin, openAdminDialog, logoutAdmin } = useContext(AdminContext);

  return (
    <Box
      sx={{
        minHeight: '100vh',
        height: '100vh',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: { xs: 'column', md: 'row' },
        gap: { xs: 2, md: 0 }
      }}
    >
      <Box
        sx={{
          width: { xs: '100%', md: 280 },
          px: { xs: 2, md: 3 },
          py: { xs: 2.5, md: 3 },
          borderRight: { md: '1px solid' },
          borderColor: { md: 'divider' },
          backgroundColor: 'rgba(255, 255, 255, 0.6)',
          backdropFilter: 'blur(10px)'
        }}
      >
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5, height: '100%' }}>
          <Box>
            <Typography variant="h5" sx={{ fontWeight: 700, letterSpacing: 0.6 }}>
              CERCHA
            </Typography>
            <Typography variant="caption" sx={{ color: 'text.secondary', letterSpacing: 1.6, textTransform: 'uppercase' }}>
              ERP + MRP Workshop
            </Typography>
          </Box>

          <Box
            sx={{
              display: 'grid',
              gap: 1.5,
              gridTemplateColumns: { xs: '1fr 1fr', md: '1fr' }
            }}
          >
            {navItems.map((item) => (
              <NavItem key={item.to} {...item} />
            ))}
          </Box>

          <Box sx={{ mt: { xs: 1, md: 'auto' }, display: 'flex', flexDirection: 'column', gap: 1.5 }}>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, alignItems: 'center' }}>
              <Chip size="small" label={isAdmin ? 'Modo: Admin' : 'Modo: Usuario'} variant="outlined" />
              {isAdmin ? (
                <Button size="small" color="inherit" onClick={logoutAdmin}>
                  Cerrar sesión
                </Button>
              ) : (
                <Button size="small" variant="outlined" onClick={openAdminDialog}>
                  Iniciar sesión
                </Button>
              )}
            </Box>

            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Box sx={{ width: 8, height: 8, borderRadius: 999, backgroundColor: '#3ccf91' }} />
              <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                API local activa
              </Typography>
            </Box>
          </Box>
        </Box>
      </Box>

      <Box
        sx={{
          flexGrow: 1,
          minHeight: 0,
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          boxSizing: 'border-box',
          px: { xs: 2, md: 4 },
          py: { xs: 2, md: 4 }
        }}
      >
        <Routes>
          <Route path="/" element={<Inventario />} />
          <Route path="/cortes" element={<Cortes />} />
          <Route path="/ordenes" element={<Ordenes />} />
        </Routes>
      </Box>
    </Box>
  );
}

function App() {
  const [adminSession, setAdminSession] = useState(() => {
    const user = localStorage.getItem('cercha_admin_user') || '';
    const token = localStorage.getItem('cercha_admin_token') || '';
    return { user, token };
  });
  const [openAdmin, setOpenAdmin] = useState(false);
  const [adminUserInput, setAdminUserInput] = useState('Admin2046');
  const [adminTokenInput, setAdminTokenInput] = useState('Admin2046');

  const isAdmin = Boolean(adminSession.user && adminSession.token);

  const openAdminDialog = () => {
    setAdminUserInput(adminSession.user || 'Admin2046');
    setAdminTokenInput(adminSession.token || 'Admin2046');
    setOpenAdmin(true);
  };
  const closeAdminDialog = () => setOpenAdmin(false);

  const loginAdmin = () => {
    const nextSession = { user: adminUserInput.trim(), token: adminTokenInput.trim() };
    setAdminSession(nextSession);
    localStorage.setItem('cercha_admin_user', nextSession.user);
    localStorage.setItem('cercha_admin_token', nextSession.token);
    setOpenAdmin(false);
  };

  const logoutAdmin = () => {
    setAdminSession({ user: '', token: '' });
    localStorage.removeItem('cercha_admin_user');
    localStorage.removeItem('cercha_admin_token');
  };

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <AdminContext.Provider
        value={{
          adminSession,
          isAdmin,
          openAdminDialog,
          closeAdminDialog,
          loginAdmin,
          logoutAdmin
        }}
      >
        <Router>
          <AppMain />
        </Router>

        <Dialog
          open={openAdmin}
          onClose={closeAdminDialog}
          maxWidth="xs"
          fullWidth
          PaperProps={{
            sx: {
              borderRadius: 4,
              border: '1px solid rgba(28, 35, 43, 0.12)'
            }
          }}
        >
          <DialogTitle sx={{ fontWeight: 700 }}>Iniciar sesión admin</DialogTitle>
          <Divider />
          <DialogContent sx={{ pt: 3 }}>
            <Typography variant="body2" sx={{ color: 'text.secondary', mb: 2 }}>
              Ingresa las credenciales para habilitar eliminación de inventario.
            </Typography>
            <TextField
              label="Usuario admin"
              fullWidth
              value={adminUserInput}
              onChange={(e) => setAdminUserInput(e.target.value)}
              sx={{ mb: 2 }}
            />
            <TextField
              label="Token admin"
              type="password"
              fullWidth
              value={adminTokenInput}
              onChange={(e) => setAdminTokenInput(e.target.value)}
            />
          </DialogContent>
          <DialogActions sx={{ px: 3, pb: 3 }}>
            <Button onClick={closeAdminDialog} color="inherit">
              Cancelar
            </Button>
            <Button
              onClick={loginAdmin}
              variant="contained"
              disabled={!adminUserInput || !adminTokenInput}
            >
              Iniciar sesión
            </Button>
          </DialogActions>
        </Dialog>
      </AdminContext.Provider>
    </ThemeProvider>
  );
}

export default App;
