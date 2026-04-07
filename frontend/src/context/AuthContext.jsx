/**
 * AuthContext — sesión OAuth2 multi-usuario.
 *
 * Provee:
 *  - user: objeto UserPublic o null
 *  - status: 'loading' | 'authenticated' | 'anonymous'
 *  - providers: { google: bool, microsoft: bool }
 *  - loginWith(provider): redirige a /api/auth/login/{provider}
 *  - logout(): cierra sesión y redirige a /login
 *  - refreshUser(): re-fetch /me
 */

import { createContext, useContext, useEffect, useState, useCallback } from 'react';
import {
  api,
  authApi,
  setAccessToken,
  registerUnauthorizedHandler,
} from '../services/api';

const AuthContext = createContext({
  user: null,
  status: 'loading',
  providers: { google: false, microsoft: false },
  loginWith: () => {},
  logout: () => {},
  refreshUser: async () => {},
});

export function useAuth() {
  return useContext(AuthContext);
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [status, setStatus] = useState('loading');
  const [providers, setProviders] = useState({ google: false, microsoft: false });

  // Bootstrap inicial: intentar recuperar sesión a partir de la cookie de refresh
  const bootstrap = useCallback(async () => {
    setStatus('loading');
    try {
      const data = await authApi.session();
      setAccessToken(data.access_token);
      setUser(data.user);
      setStatus('authenticated');
    } catch (e) {
      setAccessToken(null);
      setUser(null);
      setStatus('anonymous');
    }
  }, []);

  const refreshUser = useCallback(async () => {
    try {
      const me = await authApi.me();
      setUser(me);
    } catch (e) {
      // ignore — el interceptor se encarga del 401
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch (e) {
      // ignore
    }
    setAccessToken(null);
    setUser(null);
    setStatus('anonymous');
    window.location.href = '/login';
  }, []);

  const loginWith = useCallback((provider) => {
    if (provider !== 'google' && provider !== 'microsoft') return;
    window.location.href = authApi.loginUrl(provider);
  }, []);

  // Registrar callback global para que el interceptor pueda forzar logout
  useEffect(() => {
    registerUnauthorizedHandler(() => {
      setUser(null);
      setStatus('anonymous');
      // Sólo redirigir si NO estamos ya en /login
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login';
      }
    });
    return () => registerUnauthorizedHandler(null);
  }, []);

  // Cargar lista de providers disponibles + sesión
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const p = await authApi.providers();
        if (!cancelled) setProviders(p);
      } catch (e) {
        // si /providers falla, asumimos ninguno
      }
      await bootstrap();
    })();
    return () => {
      cancelled = true;
    };
  }, [bootstrap]);

  return (
    <AuthContext.Provider
      value={{ user, status, providers, loginWith, logout, refreshUser }}
    >
      {children}
    </AuthContext.Provider>
  );
}
