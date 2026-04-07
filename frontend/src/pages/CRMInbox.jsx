/**
 * CRMInbox — Bandeja de entrada OAuth multi-usuario.
 *
 * 3 pestañas:
 *   1. Bandeja      — lista de correos + preview (HTML sanitizado por backend)
 *   2. Contactos    — personas detectadas automáticamente vía email
 *   3. Empresas     — empresas detectadas por dominio corporativo
 *
 * Seguridad en cliente:
 *   - El HTML del body viene pre-sanitizado por bleach en backend.
 *   - Se renderiza dentro de un <iframe sandbox> para aislamiento adicional.
 *   - Ningún token se guarda en localStorage (vienen por axios en memoria).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Box,
  Tabs,
  Tab,
  Paper,
  Stack,
  Typography,
  TextField,
  InputAdornment,
  IconButton,
  List,
  ListItemButton,
  ListItemText,
  Divider,
  Chip,
  Button,
  CircularProgress,
  Alert,
  FormControlLabel,
  Switch,
  Table,
  TableHead,
  TableRow,
  TableCell,
  TableBody,
  Tooltip,
  Avatar,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import RefreshIcon from '@mui/icons-material/Refresh';
import MarkEmailUnreadIcon from '@mui/icons-material/MarkEmailUnread';
import MarkEmailReadIcon from '@mui/icons-material/MarkEmailRead';
import BusinessIcon from '@mui/icons-material/Business';
import PersonIcon from '@mui/icons-material/Person';

import { inboxApi } from '../services/api';
import { useAuth } from '../context/AuthContext';

function formatDate(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    const now = new Date();
    const sameDay =
      d.getFullYear() === now.getFullYear() &&
      d.getMonth() === now.getMonth() &&
      d.getDate() === now.getDate();
    if (sameDay) {
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
    return d.toLocaleDateString();
  } catch {
    return iso;
  }
}

function BandejaTab() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState('');
  const [soloNoLeidos, setSoloNoLeidos] = useState(false);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);
  const [estado, setEstado] = useState(null);

  const cargar = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await inboxApi.listar({
        q: q || undefined,
        solo_no_leidos: soloNoLeidos,
        limit: 100,
      });
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch (e) {
      setError('No se pudo cargar la bandeja');
    } finally {
      setLoading(false);
    }
  }, [q, soloNoLeidos]);

  const cargarEstado = useCallback(async () => {
    try {
      setEstado(await inboxApi.estado());
    } catch (e) {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    cargar();
    cargarEstado();
  }, [cargar, cargarEstado]);

  const abrir = async (mensaje) => {
    try {
      const full = await inboxApi.obtener(mensaje.id);
      setSelected(full);
      // Refrescar el estado leido en la lista
      setItems((prev) =>
        prev.map((m) => (m.id === mensaje.id ? { ...m, leido: true } : m)),
      );
    } catch (e) {
      setError('No se pudo abrir el mensaje');
    }
  };

  const sincronizar = async () => {
    setSyncing(true);
    setError(null);
    try {
      const r = await inboxApi.syncAhora();
      if (r.error) {
        setError(`Sync: ${r.error}`);
      }
      await cargar();
      await cargarEstado();
    } catch (e) {
      setError('Error al sincronizar');
    } finally {
      setSyncing(false);
    }
  };

  const toggleLeido = async (m) => {
    try {
      await inboxApi.marcarLeido(m.id, !m.leido);
      setItems((prev) =>
        prev.map((x) => (x.id === m.id ? { ...x, leido: !m.leido } : x)),
      );
      if (selected?.id === m.id) setSelected({ ...selected, leido: !m.leido });
    } catch (e) {
      /* ignore */
    }
  };

  return (
    <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mt: 2 }}>
      {/* Panel izquierdo: lista */}
      <Paper sx={{ flex: 1, minWidth: 340, maxWidth: { md: 460 }, p: 0 }}>
        <Box sx={{ p: 2, borderBottom: '1px solid #e0e0e0' }}>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
            <TextField
              size="small"
              fullWidth
              placeholder="Buscar asunto o remitente"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && cargar()}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon fontSize="small" />
                  </InputAdornment>
                ),
              }}
            />
            <Tooltip title="Sincronizar ahora">
              <span>
                <IconButton onClick={sincronizar} disabled={syncing}>
                  {syncing ? <CircularProgress size={20} /> : <RefreshIcon />}
                </IconButton>
              </span>
            </Tooltip>
          </Stack>
          <FormControlLabel
            control={
              <Switch
                size="small"
                checked={soloNoLeidos}
                onChange={(e) => setSoloNoLeidos(e.target.checked)}
              />
            }
            label="Solo no leídos"
          />
          {estado && (
            <Typography variant="caption" display="block" color="text.secondary">
              {estado.email} · {estado.total} correos ·{' '}
              <strong>{estado.no_leidos} sin leer</strong>
            </Typography>
          )}
        </Box>

        {error && <Alert severity="error" sx={{ m: 1 }}>{error}</Alert>}

        {loading ? (
          <Box sx={{ p: 4, textAlign: 'center' }}>
            <CircularProgress size={24} />
          </Box>
        ) : items.length === 0 ? (
          <Box sx={{ p: 4, textAlign: 'center' }}>
            <Typography variant="body2" color="text.secondary">
              No hay correos. Pulsa el botón de refresco para sincronizar.
            </Typography>
          </Box>
        ) : (
          <List dense sx={{ maxHeight: '70vh', overflow: 'auto' }}>
            {items.map((m) => (
              <Box key={m.id}>
                <ListItemButton
                  selected={selected?.id === m.id}
                  onClick={() => abrir(m)}
                  sx={{
                    bgcolor: m.leido ? 'transparent' : '#f0f7ff',
                  }}
                >
                  <ListItemText
                    primary={
                      <Stack direction="row" spacing={1} alignItems="center">
                        <Typography
                          variant="body2"
                          fontWeight={m.leido ? 400 : 700}
                          noWrap
                          sx={{ flex: 1 }}
                        >
                          {m.remitente_nombre || m.remitente_email}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {formatDate(m.recibido_at)}
                        </Typography>
                      </Stack>
                    }
                    secondary={
                      <>
                        <Typography
                          variant="body2"
                          fontWeight={m.leido ? 400 : 600}
                          noWrap
                        >
                          {m.asunto || '(sin asunto)'}
                        </Typography>
                        <Typography
                          variant="caption"
                          color="text.secondary"
                          noWrap
                        >
                          {m.snippet}
                        </Typography>
                      </>
                    }
                  />
                </ListItemButton>
                <Divider component="li" />
              </Box>
            ))}
          </List>
        )}
      </Paper>

      {/* Panel derecho: preview */}
      <Paper sx={{ flex: 2, p: 2, minHeight: 400 }}>
        {!selected ? (
          <Box sx={{ p: 4, textAlign: 'center' }}>
            <Typography color="text.secondary">
              Selecciona un mensaje para ver su contenido
            </Typography>
          </Box>
        ) : (
          <Stack spacing={2}>
            <Stack direction="row" justifyContent="space-between" alignItems="center">
              <Typography variant="h6" sx={{ flex: 1 }}>
                {selected.asunto || '(sin asunto)'}
              </Typography>
              <Tooltip title={selected.leido ? 'Marcar no leído' : 'Marcar leído'}>
                <IconButton onClick={() => toggleLeido(selected)}>
                  {selected.leido ? <MarkEmailUnreadIcon /> : <MarkEmailReadIcon />}
                </IconButton>
              </Tooltip>
            </Stack>
            <Box>
              <Typography variant="body2">
                <strong>De:</strong>{' '}
                {selected.remitente_nombre
                  ? `${selected.remitente_nombre} <${selected.remitente_email}>`
                  : selected.remitente_email}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {formatDate(selected.recibido_at)} · {selected.proveedor}
              </Typography>
            </Box>
            <Divider />
            {selected.body_html_safe ? (
              <iframe
                title="Email content"
                sandbox=""
                srcDoc={selected.body_html_safe}
                style={{
                  width: '100%',
                  minHeight: 500,
                  border: 0,
                  background: '#fff',
                }}
              />
            ) : (
              <Box
                component="pre"
                sx={{
                  whiteSpace: 'pre-wrap',
                  fontFamily: 'inherit',
                  fontSize: 14,
                  p: 1,
                }}
              >
                {selected.body_text || selected.snippet || '(sin contenido)'}
              </Box>
            )}
          </Stack>
        )}
      </Paper>
    </Stack>
  );
}

function ContactosTab() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    inboxApi
      .contactosDetectados()
      .then((data) => setRows(data || []))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <Box sx={{ p: 4, textAlign: 'center' }}>
        <CircularProgress size={24} />
      </Box>
    );
  }

  return (
    <Paper sx={{ mt: 2, p: 2 }}>
      <Typography variant="h6" sx={{ mb: 2 }}>
        Contactos detectados automáticamente ({rows.length})
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 2 }}>
        Personas con las que has intercambiado emails. Dominios personales
        (gmail, outlook…) → contacto personal. Dominios corporativos → vinculados
        a su empresa.
      </Typography>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell></TableCell>
            <TableCell>Nombre</TableCell>
            <TableCell>Email</TableCell>
            <TableCell>Tipo</TableCell>
            <TableCell align="right">Emails</TableCell>
            <TableCell>Último contacto</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((c) => (
            <TableRow key={c.id}>
              <TableCell>
                <Avatar sx={{ width: 28, height: 28, bgcolor: c.es_personal ? '#9c27b0' : '#1976d2' }}>
                  <PersonIcon fontSize="small" />
                </Avatar>
              </TableCell>
              <TableCell>
                {[c.nombre, c.apellido].filter(Boolean).join(' ') || '—'}
              </TableCell>
              <TableCell>{c.email}</TableCell>
              <TableCell>
                <Chip
                  size="small"
                  label={c.es_personal ? 'Personal' : 'Corporativo'}
                  color={c.es_personal ? 'secondary' : 'primary'}
                  variant="outlined"
                />
              </TableCell>
              <TableCell align="right">{c.frecuencia_emails}</TableCell>
              <TableCell>{formatDate(c.ultimo_email_at)}</TableCell>
            </TableRow>
          ))}
          {rows.length === 0 && (
            <TableRow>
              <TableCell colSpan={6} align="center">
                <Typography variant="body2" color="text.secondary" sx={{ py: 3 }}>
                  Aún no hay contactos detectados. Sincroniza tu bandeja.
                </Typography>
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </Paper>
  );
}

function EmpresasTab() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    inboxApi
      .empresasDetectadas()
      .then((data) => setRows(data || []))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <Box sx={{ p: 4, textAlign: 'center' }}>
        <CircularProgress size={24} />
      </Box>
    );
  }

  return (
    <Paper sx={{ mt: 2, p: 2 }}>
      <Typography variant="h6" sx={{ mb: 2 }}>
        Empresas detectadas por dominio ({rows.length})
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 2 }}>
        Creadas automáticamente al recibir correos con dominios corporativos.
      </Typography>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell></TableCell>
            <TableCell>Nombre</TableCell>
            <TableCell>Dominio</TableCell>
            <TableCell align="right">Contactos</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((e) => (
            <TableRow key={e.id}>
              <TableCell>
                <Avatar sx={{ width: 28, height: 28, bgcolor: '#1f3a5f' }}>
                  <BusinessIcon fontSize="small" />
                </Avatar>
              </TableCell>
              <TableCell>{e.nombre}</TableCell>
              <TableCell>
                <Chip size="small" label={e.dominio_email} variant="outlined" />
              </TableCell>
              <TableCell align="right">{e.contactos_count}</TableCell>
            </TableRow>
          ))}
          {rows.length === 0 && (
            <TableRow>
              <TableCell colSpan={4} align="center">
                <Typography variant="body2" color="text.secondary" sx={{ py: 3 }}>
                  Aún no hay empresas detectadas.
                </Typography>
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </Paper>
  );
}

export default function CRMInbox() {
  const [tab, setTab] = useState(0);
  const { user } = useAuth();

  return (
    <Box sx={{ p: 3 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Box>
          <Typography variant="h4" fontWeight={700} sx={{ color: '#1f3a5f' }}>
            Bandeja de entrada
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Sincronización OAuth con {user?.email || 'tu cuenta'}
          </Typography>
        </Box>
      </Stack>

      <Paper sx={{ mt: 2 }}>
        <Tabs value={tab} onChange={(_, v) => setTab(v)}>
          <Tab label="Bandeja" />
          <Tab label="Contactos detectados" />
          <Tab label="Empresas detectadas" />
        </Tabs>
      </Paper>

      {tab === 0 && <BandejaTab />}
      {tab === 1 && <ContactosTab />}
      {tab === 2 && <EmpresasTab />}
    </Box>
  );
}
