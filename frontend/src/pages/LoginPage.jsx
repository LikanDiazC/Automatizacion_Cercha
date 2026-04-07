/**
 * LoginPage — pantalla pública para iniciar sesión OAuth.
 * Botones Google / Microsoft (sólo se muestran los configurados en backend).
 */

import { useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import {
  Box,
  Card,
  CardContent,
  Stack,
  Typography,
  Button,
  Divider,
  Alert,
  CircularProgress,
} from '@mui/material';
import { useAuth } from '../context/AuthContext';

const ERROR_MESSAGES = {
  oauth_error: 'El proveedor de identidad rechazó la autorización.',
  invalid_state: 'Sesión OAuth inválida (posible CSRF). Intenta de nuevo.',
  missing_params: 'Faltan parámetros de OAuth. Reintenta.',
  missing_verifier: 'Sesión OAuth expirada. Reintenta.',
  provider_mismatch: 'No coincide el proveedor. Reintenta.',
  exchange_failed: 'Fallo al validar credenciales con el proveedor.',
  user_disabled: 'Tu cuenta está deshabilitada. Contacta al administrador.',
  upsert_failed: 'Error interno creando tu usuario. Reintenta o contacta soporte.',
};

export default function LoginPage() {
  const { providers, status, loginWith } = useAuth();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const errorCode = params.get('error');

  useEffect(() => {
    if (status === 'authenticated') {
      navigate('/', { replace: true });
    }
  }, [status, navigate]);

  if (status === 'loading') {
    return (
      <Box
        sx={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          bgcolor: '#f6f9fc',
        }}
      >
        <CircularProgress />
      </Box>
    );
  }

  const noProviders = !providers.google && !providers.microsoft;

  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        bgcolor: '#f6f9fc',
        p: 2,
      }}
    >
      <Card sx={{ maxWidth: 440, width: '100%', borderRadius: 3, boxShadow: 8 }}>
        <CardContent sx={{ p: 4 }}>
          <Stack spacing={3}>
            <Box textAlign="center">
              <Typography variant="h5" fontWeight={700} sx={{ color: '#1f3a5f' }}>
                CERCHA — ERP + MRP + CRM
              </Typography>
              <Typography variant="body2" sx={{ mt: 1, color: 'text.secondary' }}>
                Inicia sesión con tu cuenta corporativa o personal
              </Typography>
            </Box>

            {errorCode && ERROR_MESSAGES[errorCode] && (
              <Alert severity="error">{ERROR_MESSAGES[errorCode]}</Alert>
            )}

            {noProviders && (
              <Alert severity="warning">
                No hay proveedores OAuth configurados en el servidor. Contacta
                al administrador para configurar Google y/o Microsoft en el
                archivo <code>.env</code>.
              </Alert>
            )}

            {providers.google && (
              <Button
                variant="outlined"
                size="large"
                fullWidth
                onClick={() => loginWith('google')}
                sx={{
                  textTransform: 'none',
                  borderColor: '#dadce0',
                  color: '#3c4043',
                  fontWeight: 600,
                  py: 1.4,
                  '&:hover': { borderColor: '#1a73e8', bgcolor: '#f8faff' },
                }}
                startIcon={<GoogleIcon />}
              >
                Continuar con Google
              </Button>
            )}

            {providers.microsoft && (
              <Button
                variant="outlined"
                size="large"
                fullWidth
                onClick={() => loginWith('microsoft')}
                sx={{
                  textTransform: 'none',
                  borderColor: '#dadce0',
                  color: '#3c4043',
                  fontWeight: 600,
                  py: 1.4,
                  '&:hover': { borderColor: '#0078d4', bgcolor: '#f3f9ff' },
                }}
                startIcon={<MicrosoftIcon />}
              >
                Continuar con Microsoft
              </Button>
            )}

            <Divider />
            <Typography variant="caption" textAlign="center" color="text.secondary">
              Al iniciar sesión aceptas que el ERP lea tu correo electrónico
              para detectar contactos automáticamente. Tus credenciales nunca
              se almacenan, sólo tokens OAuth encriptados.
            </Typography>
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
}

// SVG inline para no agregar dependencias
function GoogleIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 48 48">
      <path
        fill="#FFC107"
        d="M43.6 20.5H42V20H24v8h11.3c-1.6 4.7-6.1 8-11.3 8-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20c11 0 19.7-8 19.7-20 0-1.3-.1-2.3-.3-3.5z"
      />
      <path
        fill="#FF3D00"
        d="M6.3 14.7l6.6 4.8C14.6 16 18.9 13 24 13c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.4 6.3 14.7z"
      />
      <path
        fill="#4CAF50"
        d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2c-2 1.4-4.5 2.3-7.2 2.3-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z"
      />
      <path
        fill="#1976D2"
        d="M43.6 20.5H42V20H24v8h11.3c-.8 2.3-2.3 4.2-4.2 5.6l6.2 5.2c-.4.4 6.7-4.9 6.7-14.8 0-1.3-.1-2.3-.4-3.5z"
      />
    </svg>
  );
}

function MicrosoftIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 23 23">
      <path fill="#f3f3f3" d="M0 0h23v23H0z" />
      <path fill="#f35325" d="M1 1h10v10H1z" />
      <path fill="#81bc06" d="M12 1h10v10H12z" />
      <path fill="#05a6f0" d="M1 12h10v10H1z" />
      <path fill="#ffba08" d="M12 12h10v10H12z" />
    </svg>
  );
}
