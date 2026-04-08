/**
 * Cliente Axios centralizado para el ERP Cercha.
 *
 * Características de seguridad:
 *  - Una sola instancia con baseURL fija (no se acepta input del usuario).
 *  - withCredentials=true: cookies HttpOnly viajan automáticamente (refresh).
 *  - Interceptor request: añade Authorization: Bearer <jwt> si hay sesión.
 *  - Interceptor response: si recibe 401, intenta /auth/refresh UNA vez y
 *    reintenta la request original. Si el refresh falla, dispara logout.
 *  - El JWT se mantiene en MEMORIA (módulo cerrado), nunca en localStorage
 *    ni sessionStorage. Esto mitiga XSS exfiltration.
 */

import axios from 'axios';

export const API_BASE_URL =
  (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_URL) ||
  'http://localhost:8000';

// ── Token en memoria (no localStorage) ──────────────────────────────────────
let _accessToken = null;
let _onUnauthorized = null; // callback que el AuthContext registra

export function setAccessToken(token) {
  _accessToken = token || null;
}

export function getAccessToken() {
  return _accessToken;
}

export function registerUnauthorizedHandler(fn) {
  _onUnauthorized = typeof fn === 'function' ? fn : null;
}

// ── Instancia ───────────────────────────────────────────────────────────────
export const api = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true, // envía cookie de refresh
  timeout: 30000,
  headers: {
    'X-Requested-With': 'XMLHttpRequest',
  },
});

// ── Request interceptor: añadir Bearer ──────────────────────────────────────
api.interceptors.request.use(
  (config) => {
    if (_accessToken) {
      config.headers = config.headers || {};
      config.headers.Authorization = `Bearer ${_accessToken}`;
    }
    return config;
  },
  (error) => Promise.reject(error),
);

// ── Response interceptor: refresh automático en 401 ─────────────────────────
let _refreshing = null; // promesa en curso (single-flight)

async function tryRefresh() {
  if (_refreshing) return _refreshing;
  _refreshing = (async () => {
    try {
      const resp = await axios.post(
        `${API_BASE_URL}/api/auth/refresh`,
        {},
        { withCredentials: true, timeout: 15000 },
      );
      const token = resp.data?.access_token;
      if (token) {
        setAccessToken(token);
        return token;
      }
      return null;
    } catch (e) {
      return null;
    } finally {
      _refreshing = null;
    }
  })();
  return _refreshing;
}

api.interceptors.response.use(
  (resp) => resp,
  async (error) => {
    const original = error.config || {};
    const status = error.response?.status;
    const url = original.url || '';

    // No reintentar refresh sobre los propios endpoints de auth
    const isAuthEndpoint = url.includes('/api/auth/');

    if (status === 401 && !original.__isRetry && !isAuthEndpoint) {
      original.__isRetry = true;
      const newToken = await tryRefresh();
      if (newToken) {
        original.headers = original.headers || {};
        original.headers.Authorization = `Bearer ${newToken}`;
        return api.request(original);
      }
      // Refresh falló → expulsar
      setAccessToken(null);
      if (_onUnauthorized) _onUnauthorized();
    }
    return Promise.reject(error);
  },
);

// ── Helpers de auth ─────────────────────────────────────────────────────────
export const authApi = {
  /** GET /api/auth/providers — descubre qué métodos de login están activos */
  providers: () => api.get('/api/auth/providers').then((r) => r.data),

  /** GET /api/auth/session — recupera sesión a partir de cookie de refresh */
  session: () => api.get('/api/auth/session').then((r) => r.data),

  /** GET /api/auth/me — datos del usuario actual */
  me: () => api.get('/api/auth/me').then((r) => r.data),

  /** POST /api/auth/logout — limpia cookies en el server */
  logout: () => api.post('/api/auth/logout').then((r) => r.data),

  /** URL absoluta para iniciar OAuth (window.location.href = ...) */
  loginUrl: (provider) => `${API_BASE_URL}/api/auth/login/${provider}`,
};

// ── Helpers de Compras / Cotizador ──────────────────────────────────────────
export const comprasApi = {
  /** GET /api/compras/catalogo — catálogo cacheado (cache-first) */
  catalogo: (params = {}) =>
    api.get('/api/compras/catalogo', { params }).then((r) => r.data),

  /** POST /api/compras/catalogo/sync — dispara sync background */
  sync: () => api.post('/api/compras/catalogo/sync').then((r) => r.data),

  /** GET /api/compras/buscar — búsqueda live (scraping en tiempo real) */
  buscar: (query, params = {}) =>
    api.get('/api/compras/buscar', { params: { query, ...params } }).then((r) => r.data),

  /** POST /api/compras/comparar — fuerza comparación IA entre 2 productos */
  comparar: (producto_a_id, producto_b_id) =>
    api
      .post('/api/compras/comparar', { producto_a_id, producto_b_id })
      .then((r) => r.data),

  /** GET /api/compras/carrito/:sessionKey */
  getCarrito: (sessionKey) =>
    api.get(`/api/compras/carrito/${sessionKey}`).then((r) => r.data),

  /** POST /api/compras/carrito/:sessionKey/items */
  addItem: (sessionKey, body) =>
    api
      .post(`/api/compras/carrito/${sessionKey}/items`, body)
      .then((r) => r.data),

  /** DELETE /api/compras/carrito/:sessionKey/items/:itemId */
  removeItem: (sessionKey, itemId) =>
    api
      .delete(`/api/compras/carrito/${sessionKey}/items/${itemId}`)
      .then((r) => r.data),
};

// ── Helpers de Inbox CRM ─────────────────────────────────────────────────────
export const inboxApi = {
  /** GET /api/crm/inbox — lista mensajes con búsqueda opcional */
  listar: (params = {}) =>
    api.get('/api/crm/inbox', { params }).then((r) => r.data),

  /** GET /api/crm/inbox/{id} — detalle con body HTML sanitizado */
  obtener: (id) => api.get(`/api/crm/inbox/${id}`).then((r) => r.data),

  /** PATCH /api/crm/inbox/{id}/leido */
  marcarLeido: (id, leido = true) =>
    api.patch(`/api/crm/inbox/${id}/leido`, null, { params: { leido } }).then((r) => r.data),

  /** POST /api/crm/inbox/sync — fuerza sync del usuario actual */
  syncAhora: () => api.post('/api/crm/inbox/sync').then((r) => r.data),

  /** GET /api/crm/inbox/_meta/estado */
  estado: () => api.get('/api/crm/inbox/_meta/estado').then((r) => r.data),

  /** GET /api/crm/inbox/_meta/contactos-detectados */
  contactosDetectados: () =>
    api.get('/api/crm/inbox/_meta/contactos-detectados').then((r) => r.data),

  /** GET /api/crm/inbox/_meta/empresas-detectadas */
  empresasDetectadas: () =>
    api.get('/api/crm/inbox/_meta/empresas-detectadas').then((r) => r.data),
};
