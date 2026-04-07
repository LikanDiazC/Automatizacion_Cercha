/**
 * AuthSuccess — landing tras callback OAuth.
 * Llama a /api/auth/session para canjear la cookie de refresh por un access
 * token y luego redirige a la página principal.
 */

import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Box, CircularProgress, Stack, Typography } from '@mui/material';
import { authApi, setAccessToken } from '../services/api';
import { useAuth } from '../context/AuthContext';

export default function AuthSuccess() {
  const navigate = useNavigate();
  const { refreshUser } = useAuth();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await authApi.session();
        if (cancelled) return;
        setAccessToken(data.access_token);
        await refreshUser();
        navigate('/', { replace: true });
      } catch (e) {
        navigate('/login?error=exchange_failed', { replace: true });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [navigate, refreshUser]);

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
      <Stack alignItems="center" spacing={2}>
        <CircularProgress />
        <Typography variant="body1" color="text.secondary">
          Completando inicio de sesión…
        </Typography>
      </Stack>
    </Box>
  );
}
