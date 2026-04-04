import { useState, useEffect, useCallback } from 'react';
import {
  Box, Paper, Typography, Button, Chip, TextField,
  Dialog, DialogTitle, DialogContent, DialogActions,
  Divider, Alert, IconButton, Tooltip, Tab, Tabs,
  CircularProgress, Select, MenuItem, FormControl,
  InputLabel,
} from '@mui/material';
import { motion, AnimatePresence } from 'framer-motion';
import axios from 'axios';

const API = 'http://127.0.0.1:8000/api/crm';

// ---------------------------------------------------------------------------
// Colores del pipeline
// ---------------------------------------------------------------------------

const PIPELINE_CONFIG = {
  prospecto:   { label: 'Prospecto',   color: '#6366f1', bg: 'rgba(99,102,241,0.08)', icon: '🎯' },
  cotizacion:  { label: 'Cotización',  color: '#f59e0b', bg: 'rgba(245,158,11,0.08)',  icon: '📋' },
  negociacion: { label: 'Negociación', color: '#3b82f6', bg: 'rgba(59,130,246,0.08)',  icon: '🤝' },
  ganado:      { label: 'Ganado',      color: '#10b981', bg: 'rgba(16,185,129,0.08)',   icon: '✅' },
  perdido:     { label: 'Perdido',     color: '#ef4444', bg: 'rgba(239,68,68,0.08)',    icon: '❌' },
};

const TIPO_ACTIVIDAD_ICONS = {
  nota: '📝', email: '📧', llamada: '📞', reunion: '📅',
  cotizacion: '💰', orden: '📦', cambio_estado: '🔄', sistema: '⚙️',
};

const formatCLP = (v) => v != null ? `$${Math.round(v).toLocaleString('es-CL')}` : '$0';

const tiempoRelativo = (iso) => {
  if (!iso) return '';
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60)    return 'hace segundos';
  if (s < 3600)  return `hace ${Math.floor(s / 60)} min`;
  if (s < 86400) return `hace ${Math.floor(s / 3600)}h`;
  return `hace ${Math.floor(s / 86400)}d`;
};

// ---------------------------------------------------------------------------
// DealCard — tarjeta individual dentro del Kanban
// ---------------------------------------------------------------------------

function DealCard({ deal, onClick }) {
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.15 }}
    >
      <Paper
        elevation={0}
        onClick={() => onClick(deal)}
        sx={{
          p: 1.5, borderRadius: 2, cursor: 'pointer',
          border: '1px solid rgba(28,35,43,0.08)',
          transition: 'all 0.15s',
          '&:hover': {
            borderColor: PIPELINE_CONFIG[deal.estado]?.color || '#1f3a5f',
            boxShadow: '0 4px 16px rgba(31,35,40,0.10)',
            transform: 'translateY(-1px)',
          },
        }}
      >
        <Typography variant="body2" sx={{ fontWeight: 700, lineHeight: 1.3, mb: 0.5 }}>
          {deal.titulo}
        </Typography>

        {deal.empresa_nombre && (
          <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', mb: 0.5 }}>
            🏢 {deal.empresa_nombre}
          </Typography>
        )}

        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mt: 0.5 }}>
          <Typography variant="body2" sx={{ fontWeight: 800, color: '#1c232b' }}>
            {formatCLP(deal.valor)}
          </Typography>
          <Typography variant="caption" sx={{ color: 'text.disabled', fontSize: '0.65rem' }}>
            {tiempoRelativo(deal.updated_at)}
          </Typography>
        </Box>

        {deal.contacto_nombre && (
          <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.65rem' }}>
            👤 {deal.contacto_nombre}
          </Typography>
        )}
      </Paper>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// KanbanColumn — columna del pipeline
// ---------------------------------------------------------------------------

function KanbanColumn({ config, deals, valorTotal, onDealClick }) {
  return (
    <Box sx={{
      minWidth: 260, maxWidth: 320, flexShrink: 0, flexGrow: 1,
      display: 'flex', flexDirection: 'column', height: '100%',
    }}>
      {/* Header */}
      <Box sx={{
        display: 'flex', alignItems: 'center', gap: 1,
        p: 1.5, borderRadius: 2, mb: 1,
        backgroundColor: config.bg,
        border: `1px solid ${config.color}20`,
      }}>
        <Typography sx={{ fontSize: '1.1rem' }}>{config.icon}</Typography>
        <Box sx={{ flexGrow: 1 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 700, color: config.color }}>
            {config.label}
          </Typography>
          <Typography variant="caption" sx={{ color: 'text.secondary' }}>
            {deals.length} deal{deals.length !== 1 ? 's' : ''} · {formatCLP(valorTotal)}
          </Typography>
        </Box>
        <Chip
          label={deals.length}
          size="small"
          sx={{
            fontWeight: 800, fontSize: '0.7rem', height: 22,
            backgroundColor: config.color, color: '#fff',
          }}
        />
      </Box>

      {/* Cards */}
      <Box sx={{
        flexGrow: 1, overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 1,
        pr: 0.5,
      }}>
        <AnimatePresence mode="popLayout">
          {deals.map((deal) => (
            <DealCard key={deal.id} deal={deal} onClick={onDealClick} />
          ))}
        </AnimatePresence>

        {deals.length === 0 && (
          <Box sx={{ textAlign: 'center', py: 3, opacity: 0.4 }}>
            <Typography variant="caption">Sin deals</Typography>
          </Box>
        )}
      </Box>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// DealDetailDialog — detalle + timeline de un deal
// ---------------------------------------------------------------------------

function DealDetailDialog({ deal, open, onClose, onUpdate, onAddActivity }) {
  const [timeline, setTimeline] = useState([]);
  const [loadingTimeline, setLoadingTimeline] = useState(false);
  const [newNote, setNewNote] = useState('');
  const [editEstado, setEditEstado] = useState('');

  useEffect(() => {
    if (deal && open) {
      setEditEstado(deal.estado);
      loadTimeline(deal.id);
    }
  }, [deal, open]);

  const loadTimeline = async (dealId) => {
    setLoadingTimeline(true);
    try {
      const res = await axios.get(`${API}/deals/${dealId}/timeline`);
      setTimeline(res.data || []);
    } catch { setTimeline([]); }
    setLoadingTimeline(false);
  };

  const handleAddNote = async () => {
    if (!newNote.trim() || !deal) return;
    try {
      await axios.post(`${API}/deals/${deal.id}/timeline`, {
        deal_id: deal.id,
        tipo: 'nota',
        titulo: 'Nota',
        contenido: newNote.trim(),
        usuario: 'usuario',
      });
      setNewNote('');
      loadTimeline(deal.id);
      onAddActivity?.();
    } catch (err) {
      console.error('Error adding note:', err);
    }
  };

  const handleEstadoChange = async (nuevoEstado) => {
    if (!deal || nuevoEstado === deal.estado) return;
    try {
      await axios.patch(`${API}/deals/${deal.id}`, { estado: nuevoEstado });
      setEditEstado(nuevoEstado);
      onUpdate?.();
      loadTimeline(deal.id);
    } catch (err) {
      console.error('Error updating estado:', err);
    }
  };

  if (!deal) return null;
  const cfg = PIPELINE_CONFIG[deal.estado] || PIPELINE_CONFIG.prospecto;

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth
      PaperProps={{ sx: { borderRadius: 4, maxHeight: '85vh' } }}
    >
      <DialogTitle sx={{ pb: 1 }}>
        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
          <Box sx={{ flexGrow: 1 }}>
            <Typography variant="h6" sx={{ fontWeight: 700, lineHeight: 1.3 }}>
              {deal.titulo}
            </Typography>
            {deal.empresa_nombre && (
              <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                🏢 {deal.empresa_nombre}
                {deal.contacto_nombre && ` · 👤 ${deal.contacto_nombre}`}
              </Typography>
            )}
          </Box>
          <IconButton onClick={onClose} size="small">
            <Typography>✕</Typography>
          </IconButton>
        </Box>
      </DialogTitle>

      <DialogContent sx={{ pt: 0 }}>
        {/* Valor + Estado */}
        <Box sx={{ display: 'flex', gap: 2, mb: 2, alignItems: 'center' }}>
          <Paper elevation={0} sx={{
            p: 1.5, borderRadius: 2, flexGrow: 1,
            backgroundColor: 'rgba(31,58,95,0.04)',
            border: '1px solid rgba(31,58,95,0.08)',
          }}>
            <Typography variant="caption" sx={{ color: 'text.secondary' }}>Valor</Typography>
            <Typography variant="h5" sx={{ fontWeight: 800 }}>{formatCLP(deal.valor)}</Typography>
          </Paper>

          <FormControl size="small" sx={{ minWidth: 150 }}>
            <InputLabel>Estado</InputLabel>
            <Select
              value={editEstado}
              label="Estado"
              onChange={(e) => handleEstadoChange(e.target.value)}
              sx={{ borderRadius: 2 }}
            >
              {Object.entries(PIPELINE_CONFIG).map(([key, cfg]) => (
                <MenuItem key={key} value={key}>
                  {cfg.icon} {cfg.label}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Box>

        {deal.descripcion && (
          <Typography variant="body2" sx={{ color: 'text.secondary', mb: 2 }}>
            {deal.descripcion}
          </Typography>
        )}

        <Divider sx={{ mb: 2 }} />

        {/* Add note */}
        <Box sx={{ display: 'flex', gap: 1, mb: 2 }}>
          <TextField
            size="small" fullWidth
            placeholder="Agregar nota..."
            value={newNote}
            onChange={(e) => setNewNote(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleAddNote()}
            sx={{ '& .MuiOutlinedInput-root': { borderRadius: 2 } }}
          />
          <Button
            variant="contained" size="small"
            onClick={handleAddNote}
            disabled={!newNote.trim()}
            sx={{ borderRadius: 2, minWidth: 80, textTransform: 'none' }}
          >
            Agregar
          </Button>
        </Box>

        {/* Timeline */}
        <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
          Timeline
        </Typography>

        {loadingTimeline ? (
          <Box sx={{ textAlign: 'center', py: 2 }}>
            <CircularProgress size={24} />
          </Box>
        ) : (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
            {timeline.map((act) => (
              <Paper key={act.id} elevation={0} sx={{
                p: 1.5, borderRadius: 2,
                border: '1px solid rgba(28,35,43,0.06)',
                backgroundColor: 'rgba(0,0,0,0.015)',
              }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                  <Typography sx={{ fontSize: '0.9rem' }}>
                    {TIPO_ACTIVIDAD_ICONS[act.tipo] || '📌'}
                  </Typography>
                  <Typography variant="body2" sx={{ fontWeight: 700, flexGrow: 1 }}>
                    {act.titulo || act.tipo}
                  </Typography>
                  <Typography variant="caption" sx={{ color: 'text.disabled', fontSize: '0.65rem' }}>
                    {tiempoRelativo(act.created_at)}
                  </Typography>
                </Box>
                {act.contenido && (
                  <Typography variant="body2" sx={{ color: 'text.secondary', pl: 3.5, lineHeight: 1.4 }}>
                    {act.contenido}
                  </Typography>
                )}
                {act.estado_anterior && act.estado_nuevo && (
                  <Box sx={{ pl: 3.5, display: 'flex', gap: 0.5, alignItems: 'center' }}>
                    <Chip label={PIPELINE_CONFIG[act.estado_anterior]?.label || act.estado_anterior} size="small"
                      sx={{ fontSize: '0.6rem', height: 18 }} />
                    <Typography variant="caption">→</Typography>
                    <Chip label={PIPELINE_CONFIG[act.estado_nuevo]?.label || act.estado_nuevo} size="small"
                      sx={{
                        fontSize: '0.6rem', height: 18,
                        backgroundColor: PIPELINE_CONFIG[act.estado_nuevo]?.color || '#888',
                        color: '#fff',
                      }} />
                  </Box>
                )}
              </Paper>
            ))}
            {timeline.length === 0 && (
              <Typography variant="caption" sx={{ color: 'text.disabled', textAlign: 'center', py: 2 }}>
                Sin actividades aún
              </Typography>
            )}
          </Box>
        )}
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// NewDealDialog — crear nuevo deal
// ---------------------------------------------------------------------------

function NewDealDialog({ open, onClose, onCreated, empresas, contactos }) {
  const [form, setForm] = useState({
    titulo: '', descripcion: '', valor: '', estado: 'prospecto',
    empresa_id: '', contacto_id: '',
  });

  const handleCreate = async () => {
    if (!form.titulo.trim()) return;
    try {
      await axios.post(`${API}/deals`, {
        titulo: form.titulo,
        descripcion: form.descripcion || null,
        valor: parseFloat(form.valor) || 0,
        estado: form.estado,
        empresa_id: form.empresa_id || null,
        contacto_id: form.contacto_id || null,
      });
      setForm({ titulo: '', descripcion: '', valor: '', estado: 'prospecto', empresa_id: '', contacto_id: '' });
      onCreated?.();
      onClose();
    } catch (err) {
      console.error('Error creating deal:', err);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth
      PaperProps={{ sx: { borderRadius: 4 } }}
    >
      <DialogTitle sx={{ fontWeight: 700 }}>Nuevo Deal</DialogTitle>
      <Divider />
      <DialogContent sx={{ pt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
        <TextField
          label="Título" fullWidth required
          value={form.titulo}
          onChange={(e) => setForm({ ...form, titulo: e.target.value })}
        />
        <TextField
          label="Descripción" fullWidth multiline rows={2}
          value={form.descripcion}
          onChange={(e) => setForm({ ...form, descripcion: e.target.value })}
        />
        <TextField
          label="Valor estimado (CLP)" fullWidth type="number"
          value={form.valor}
          onChange={(e) => setForm({ ...form, valor: e.target.value })}
        />
        <FormControl fullWidth size="small">
          <InputLabel>Empresa</InputLabel>
          <Select
            value={form.empresa_id}
            label="Empresa"
            onChange={(e) => setForm({ ...form, empresa_id: e.target.value })}
          >
            <MenuItem value="">Sin empresa</MenuItem>
            {empresas.map((e) => (
              <MenuItem key={e.id} value={e.id}>{e.nombre}</MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl fullWidth size="small">
          <InputLabel>Contacto</InputLabel>
          <Select
            value={form.contacto_id}
            label="Contacto"
            onChange={(e) => setForm({ ...form, contacto_id: e.target.value })}
          >
            <MenuItem value="">Sin contacto</MenuItem>
            {contactos.map((c) => (
              <MenuItem key={c.id} value={c.id}>{c.nombre} {c.apellido || ''}</MenuItem>
            ))}
          </Select>
        </FormControl>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 3 }}>
        <Button onClick={onClose} color="inherit">Cancelar</Button>
        <Button onClick={handleCreate} variant="contained" disabled={!form.titulo.trim()}>
          Crear Deal
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// EmpresasContactosTab — vista de empresas y contactos
// ---------------------------------------------------------------------------

function EmpresasContactosTab() {
  const [empresas, setEmpresas] = useState([]);
  const [contactos, setContactos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialogEmpresa, setDialogEmpresa] = useState(false);
  const [dialogContacto, setDialogContacto] = useState(false);
  const [formEmpresa, setFormEmpresa] = useState({ nombre: '', rut: '', giro: '', email: '', telefono: '' });
  const [formContacto, setFormContacto] = useState({ nombre: '', apellido: '', email: '', telefono: '', cargo: '', empresa_id: '' });

  const cargar = useCallback(async () => {
    setLoading(true);
    try {
      const [empR, contR] = await Promise.all([
        axios.get(`${API}/empresas`),
        axios.get(`${API}/contactos`),
      ]);
      setEmpresas(empR.data || []);
      setContactos(contR.data || []);
    } catch (err) { console.error(err); }
    setLoading(false);
  }, []);

  useEffect(() => { cargar(); }, [cargar]);

  const crearEmpresa = async () => {
    if (!formEmpresa.nombre.trim()) return;
    try {
      await axios.post(`${API}/empresas`, formEmpresa);
      setDialogEmpresa(false);
      setFormEmpresa({ nombre: '', rut: '', giro: '', email: '', telefono: '' });
      cargar();
    } catch (err) { console.error(err); }
  };

  const crearContacto = async () => {
    if (!formContacto.nombre.trim()) return;
    try {
      await axios.post(`${API}/contactos`, {
        ...formContacto,
        empresa_id: formContacto.empresa_id || null,
      });
      setDialogContacto(false);
      setFormContacto({ nombre: '', apellido: '', email: '', telefono: '', cargo: '', empresa_id: '' });
      cargar();
    } catch (err) { console.error(err); }
  };

  if (loading) return <Box sx={{ textAlign: 'center', py: 4 }}><CircularProgress size={30} /></Box>;

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      {/* Empresas */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 700, flexGrow: 1 }}>
          🏢 Empresas ({empresas.length})
        </Typography>
        <Button size="small" variant="outlined" onClick={() => setDialogEmpresa(true)}
          sx={{ borderRadius: 2, textTransform: 'none' }}>
          + Empresa
        </Button>
      </Box>

      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr', md: '1fr 1fr 1fr' }, gap: 1.5 }}>
        {empresas.map((e) => (
          <Paper key={e.id} elevation={0} sx={{
            p: 2, borderRadius: 2, border: '1px solid rgba(28,35,43,0.08)',
            '&:hover': { borderColor: '#1f3a5f', boxShadow: '0 4px 12px rgba(0,0,0,0.06)' },
            transition: 'all 0.15s',
          }}>
            <Typography variant="body2" sx={{ fontWeight: 700 }}>{e.nombre}</Typography>
            {e.rut && <Typography variant="caption" sx={{ color: 'text.secondary' }}>RUT: {e.rut}</Typography>}
            {e.giro && <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>{e.giro}</Typography>}
            <Box sx={{ display: 'flex', gap: 0.5, mt: 1 }}>
              <Chip label={`${e.n_contactos || 0} contactos`} size="small" sx={{ fontSize: '0.6rem', height: 18 }} />
              <Chip label={`${e.n_deals || 0} deals`} size="small" sx={{ fontSize: '0.6rem', height: 18 }} />
            </Box>
          </Paper>
        ))}
        {empresas.length === 0 && (
          <Typography variant="caption" sx={{ color: 'text.disabled', py: 2 }}>
            No hay empresas registradas
          </Typography>
        )}
      </Box>

      <Divider sx={{ my: 1 }} />

      {/* Contactos */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 700, flexGrow: 1 }}>
          👤 Contactos ({contactos.length})
        </Typography>
        <Button size="small" variant="outlined" onClick={() => setDialogContacto(true)}
          sx={{ borderRadius: 2, textTransform: 'none' }}>
          + Contacto
        </Button>
      </Box>

      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr', md: '1fr 1fr 1fr' }, gap: 1.5 }}>
        {contactos.map((c) => (
          <Paper key={c.id} elevation={0} sx={{
            p: 2, borderRadius: 2, border: '1px solid rgba(28,35,43,0.08)',
            transition: 'all 0.15s',
            '&:hover': { borderColor: '#c98c4a', boxShadow: '0 4px 12px rgba(0,0,0,0.06)' },
          }}>
            <Typography variant="body2" sx={{ fontWeight: 700 }}>
              {c.nombre} {c.apellido || ''}
            </Typography>
            {c.cargo && <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>{c.cargo}</Typography>}
            {c.empresa_nombre && <Typography variant="caption" sx={{ color: 'text.secondary' }}>🏢 {c.empresa_nombre}</Typography>}
            <Box sx={{ display: 'flex', gap: 0.5, mt: 0.5, flexWrap: 'wrap' }}>
              {c.email && <Chip label={c.email} size="small" sx={{ fontSize: '0.58rem', height: 18 }} />}
              {c.telefono && <Chip label={c.telefono} size="small" sx={{ fontSize: '0.58rem', height: 18 }} />}
            </Box>
          </Paper>
        ))}
        {contactos.length === 0 && (
          <Typography variant="caption" sx={{ color: 'text.disabled', py: 2 }}>
            No hay contactos registrados
          </Typography>
        )}
      </Box>

      {/* Dialog Empresa */}
      <Dialog open={dialogEmpresa} onClose={() => setDialogEmpresa(false)} maxWidth="xs" fullWidth
        PaperProps={{ sx: { borderRadius: 4 } }}>
        <DialogTitle sx={{ fontWeight: 700 }}>Nueva Empresa</DialogTitle>
        <Divider />
        <DialogContent sx={{ pt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
          <TextField label="Nombre" required fullWidth value={formEmpresa.nombre}
            onChange={(e) => setFormEmpresa({ ...formEmpresa, nombre: e.target.value })} />
          <TextField label="RUT" fullWidth value={formEmpresa.rut}
            onChange={(e) => setFormEmpresa({ ...formEmpresa, rut: e.target.value })} />
          <TextField label="Giro" fullWidth value={formEmpresa.giro}
            onChange={(e) => setFormEmpresa({ ...formEmpresa, giro: e.target.value })} />
          <TextField label="Email" fullWidth value={formEmpresa.email}
            onChange={(e) => setFormEmpresa({ ...formEmpresa, email: e.target.value })} />
          <TextField label="Teléfono" fullWidth value={formEmpresa.telefono}
            onChange={(e) => setFormEmpresa({ ...formEmpresa, telefono: e.target.value })} />
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 3 }}>
          <Button onClick={() => setDialogEmpresa(false)} color="inherit">Cancelar</Button>
          <Button onClick={crearEmpresa} variant="contained" disabled={!formEmpresa.nombre.trim()}>Crear</Button>
        </DialogActions>
      </Dialog>

      {/* Dialog Contacto */}
      <Dialog open={dialogContacto} onClose={() => setDialogContacto(false)} maxWidth="xs" fullWidth
        PaperProps={{ sx: { borderRadius: 4 } }}>
        <DialogTitle sx={{ fontWeight: 700 }}>Nuevo Contacto</DialogTitle>
        <Divider />
        <DialogContent sx={{ pt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
          <TextField label="Nombre" required fullWidth value={formContacto.nombre}
            onChange={(e) => setFormContacto({ ...formContacto, nombre: e.target.value })} />
          <TextField label="Apellido" fullWidth value={formContacto.apellido}
            onChange={(e) => setFormContacto({ ...formContacto, apellido: e.target.value })} />
          <TextField label="Email" fullWidth value={formContacto.email}
            onChange={(e) => setFormContacto({ ...formContacto, email: e.target.value })} />
          <TextField label="Teléfono" fullWidth value={formContacto.telefono}
            onChange={(e) => setFormContacto({ ...formContacto, telefono: e.target.value })} />
          <TextField label="Cargo" fullWidth value={formContacto.cargo}
            onChange={(e) => setFormContacto({ ...formContacto, cargo: e.target.value })} />
          <FormControl fullWidth size="small">
            <InputLabel>Empresa</InputLabel>
            <Select
              value={formContacto.empresa_id} label="Empresa"
              onChange={(e) => setFormContacto({ ...formContacto, empresa_id: e.target.value })}
            >
              <MenuItem value="">Sin empresa</MenuItem>
              {empresas.map((emp) => (
                <MenuItem key={emp.id} value={emp.id}>{emp.nombre}</MenuItem>
              ))}
            </Select>
          </FormControl>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 3 }}>
          <Button onClick={() => setDialogContacto(false)} color="inherit">Cancelar</Button>
          <Button onClick={crearContacto} variant="contained" disabled={!formContacto.nombre.trim()}>Crear</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// EmailTab — Vista de correos electrónicos
// ---------------------------------------------------------------------------

const ESTADO_EMAIL_CONFIG = {
  borrador:  { label: 'Borrador',  color: '#94a3b8', icon: '📝' },
  enviado:   { label: 'Enviado',   color: '#3b82f6', icon: '📤' },
  entregado: { label: 'Entregado', color: '#6366f1', icon: '✅' },
  abierto:   { label: 'Abierto',   color: '#10b981', icon: '👁️' },
  clicked:   { label: 'Clicked',   color: '#f59e0b', icon: '🖱️' },
  rebotado:  { label: 'Rebotado',  color: '#ef4444', icon: '🔴' },
  error:     { label: 'Error',     color: '#ef4444', icon: '❌' },
};

function ComposeEmailDialog({ open, onClose, onSent, contactos, deals }) {
  const [form, setForm] = useState({
    para_email: '', para_nombre: '', asunto: '', cuerpo_html: '', cuerpo_texto: '',
    cc: '', deal_id: '', contacto_id: '',
  });
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState('');
  const [modo, setModo] = useState('enviar'); // 'enviar' | 'borrador'

  const handleSubmit = async () => {
    if (!form.para_email.trim() || !form.asunto.trim()) {
      setError('Email destinatario y asunto son requeridos');
      return;
    }
    setEnviando(true);
    setError('');

    const endpoint = modo === 'borrador' ? '/email/borrador' : '/email/enviar';
    try {
      // Si solo hay texto plano, generar HTML simple
      let html = form.cuerpo_html;
      if (!html && form.cuerpo_texto) {
        html = form.cuerpo_texto
          .split('\n')
          .map(line => `<p>${line || '&nbsp;'}</p>`)
          .join('');
        html = `<html><body style="font-family:Arial,sans-serif;font-size:14px;color:#333;">${html}</body></html>`;
      }

      await axios.post(`${API}${endpoint}`, {
        para_email: form.para_email,
        para_nombre: form.para_nombre,
        asunto: form.asunto,
        cuerpo_html: html,
        cuerpo_texto: form.cuerpo_texto,
        cc: form.cc || null,
        deal_id: form.deal_id || null,
        contacto_id: form.contacto_id || null,
      });

      setForm({ para_email: '', para_nombre: '', asunto: '', cuerpo_html: '', cuerpo_texto: '', cc: '', deal_id: '', contacto_id: '' });
      onSent?.();
      onClose();
    } catch (err) {
      setError(err.response?.data?.detail || 'Error al enviar email');
    }
    setEnviando(false);
  };

  // Auto-fill para_email cuando se selecciona un contacto
  const handleContactoChange = (contactoId) => {
    setForm(prev => {
      const c = contactos.find(c => c.id === contactoId);
      return {
        ...prev,
        contacto_id: contactoId,
        para_email: c?.email || prev.para_email,
        para_nombre: c ? `${c.nombre} ${c.apellido || ''}`.trim() : prev.para_nombre,
      };
    });
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth
      PaperProps={{ sx: { borderRadius: 4, maxHeight: '90vh' } }}>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1, pb: 1 }}>
        <Typography sx={{ fontSize: '1.3rem' }}>✉️</Typography>
        <Typography variant="h6" sx={{ fontWeight: 700, flexGrow: 1 }}>Nuevo Email</Typography>
        <IconButton onClick={onClose} size="small"><Typography>✕</Typography></IconButton>
      </DialogTitle>
      <Divider />
      <DialogContent sx={{ pt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
        {error && <Alert severity="error" onClose={() => setError('')}>{error}</Alert>}

        {/* Vincular a contacto/deal */}
        <Box sx={{ display: 'flex', gap: 2 }}>
          <FormControl size="small" sx={{ minWidth: 200 }}>
            <InputLabel>Contacto</InputLabel>
            <Select value={form.contacto_id} label="Contacto"
              onChange={(e) => handleContactoChange(e.target.value)}>
              <MenuItem value="">Sin vincular</MenuItem>
              {contactos.filter(c => c.email).map(c => (
                <MenuItem key={c.id} value={c.id}>
                  {c.nombre} {c.apellido || ''} ({c.email})
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 180 }}>
            <InputLabel>Deal</InputLabel>
            <Select value={form.deal_id} label="Deal"
              onChange={(e) => setForm({ ...form, deal_id: e.target.value })}>
              <MenuItem value="">Sin vincular</MenuItem>
              {deals.map(d => (
                <MenuItem key={d.id} value={d.id}>{d.titulo}</MenuItem>
              ))}
            </Select>
          </FormControl>
        </Box>

        <TextField label="Para" required fullWidth size="small" value={form.para_email}
          onChange={(e) => setForm({ ...form, para_email: e.target.value })}
          placeholder="email@ejemplo.com" />

        <TextField label="CC" fullWidth size="small" value={form.cc}
          onChange={(e) => setForm({ ...form, cc: e.target.value })}
          placeholder="cc1@ejemplo.com, cc2@ejemplo.com" />

        <TextField label="Asunto" required fullWidth size="small" value={form.asunto}
          onChange={(e) => setForm({ ...form, asunto: e.target.value })} />

        <TextField
          label="Mensaje"
          fullWidth multiline rows={10}
          value={form.cuerpo_texto}
          onChange={(e) => setForm({ ...form, cuerpo_texto: e.target.value })}
          placeholder="Escribe tu mensaje aqui..."
          sx={{ '& .MuiOutlinedInput-root': { fontFamily: '"Spline Sans", sans-serif', fontSize: '0.9rem' } }}
        />
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 3, gap: 1 }}>
        <Button onClick={onClose} color="inherit">Cancelar</Button>
        <Button
          onClick={() => { setModo('borrador'); handleSubmit(); }}
          variant="outlined" disabled={enviando}
          sx={{ borderRadius: 2, textTransform: 'none' }}>
          Guardar borrador
        </Button>
        <Button
          onClick={() => { setModo('enviar'); handleSubmit(); }}
          variant="contained" disabled={enviando || !form.para_email || !form.asunto}
          sx={{ borderRadius: 2, textTransform: 'none', fontWeight: 700 }}>
          {enviando ? 'Enviando...' : 'Enviar'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function EmailDetailDialog({ email, open, onClose }) {
  if (!email) return null;
  const cfg = ESTADO_EMAIL_CONFIG[email.estado] || ESTADO_EMAIL_CONFIG.borrador;

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth
      PaperProps={{ sx: { borderRadius: 4, maxHeight: '85vh' } }}>
      <DialogTitle sx={{ pb: 1 }}>
        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
          <Box sx={{ flexGrow: 1 }}>
            <Typography variant="h6" sx={{ fontWeight: 700, lineHeight: 1.3 }}>
              {email.asunto}
            </Typography>
            <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.3 }}>
              De: {email.de_nombre || email.de_email} &lt;{email.de_email}&gt;
            </Typography>
            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
              Para: {email.para_nombre || email.para_email} &lt;{email.para_email}&gt;
              {email.cc && ` · CC: ${email.cc}`}
            </Typography>
          </Box>
          <IconButton onClick={onClose} size="small"><Typography>✕</Typography></IconButton>
        </Box>
      </DialogTitle>
      <DialogContent sx={{ pt: 0 }}>
        {/* Estado + Tracking */}
        <Box sx={{ display: 'flex', gap: 1.5, mb: 2, flexWrap: 'wrap', alignItems: 'center' }}>
          <Chip label={`${cfg.icon} ${cfg.label}`} size="small"
            sx={{ fontWeight: 700, backgroundColor: `${cfg.color}15`, color: cfg.color, border: `1px solid ${cfg.color}30` }} />

          {email.enviado_at && (
            <Typography variant="caption" sx={{ color: 'text.secondary' }}>
              Enviado: {new Date(email.enviado_at).toLocaleString('es-CL')}
            </Typography>
          )}

          {email.email_abierto && (
            <Chip label={`Abierto ${email.veces_abierto}x`} size="small" color="success" variant="outlined"
              sx={{ fontSize: '0.65rem', height: 22 }} />
          )}

          {email.email_clicked && (
            <Chip label={`Click ${email.veces_clicked}x`} size="small" color="warning" variant="outlined"
              sx={{ fontSize: '0.65rem', height: 22 }} />
          )}
        </Box>

        {email.error_mensaje && (
          <Alert severity="error" sx={{ mb: 2, borderRadius: 2 }}>
            Error: {email.error_mensaje}
          </Alert>
        )}

        <Divider sx={{ mb: 2 }} />

        {/* Cuerpo del email */}
        {email.cuerpo_html ? (
          <Paper elevation={0} sx={{
            p: 2, borderRadius: 2, border: '1px solid rgba(28,35,43,0.06)',
            backgroundColor: '#fff', minHeight: 200,
          }}>
            <div dangerouslySetInnerHTML={{ __html: email.cuerpo_html }} />
          </Paper>
        ) : (
          <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>
            {email.cuerpo_texto || '(Sin contenido)'}
          </Typography>
        )}

        {/* Tracking info detallada */}
        {(email.abierto_at || email.clicked_at) && (
          <Box sx={{ mt: 2, p: 1.5, borderRadius: 2, backgroundColor: 'rgba(16,185,129,0.04)', border: '1px solid rgba(16,185,129,0.15)' }}>
            <Typography variant="caption" sx={{ fontWeight: 700, color: '#10b981', display: 'block', mb: 0.5 }}>
              Tracking
            </Typography>
            {email.abierto_at && (
              <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
                Primera apertura: {new Date(email.abierto_at).toLocaleString('es-CL')} ({email.veces_abierto} veces)
              </Typography>
            )}
            {email.clicked_at && (
              <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
                Primer click: {new Date(email.clicked_at).toLocaleString('es-CL')} ({email.veces_clicked} veces)
              </Typography>
            )}
          </Box>
        )}
      </DialogContent>
    </Dialog>
  );
}

function EmailTab() {
  const [emails, setEmails] = useState([]);
  const [stats, setStats] = useState(null);
  const [smtpConfig, setSmtpConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [carpeta, setCarpeta] = useState('');
  const [composeOpen, setComposeOpen] = useState(false);
  const [selectedEmail, setSelectedEmail] = useState(null);
  const [contactos, setContactos] = useState([]);
  const [deals, setDeals] = useState([]);

  const cargar = useCallback(async () => {
    setLoading(true);
    try {
      const params = carpeta ? `?carpeta=${carpeta}` : '';
      const [emailsR, statsR, configR, contR, dealsR] = await Promise.all([
        axios.get(`${API}/email${params}`),
        axios.get(`${API}/email/estadisticas`),
        axios.get(`${API}/email/config`),
        axios.get(`${API}/contactos?limit=200`),
        axios.get(`${API}/deals?limit=200`),
      ]);
      setEmails(emailsR.data || []);
      setStats(statsR.data || null);
      setSmtpConfig(configR.data || null);
      setContactos(contR.data || []);
      setDeals(dealsR.data || []);
    } catch (err) { console.error(err); }
    setLoading(false);
  }, [carpeta]);

  useEffect(() => { cargar(); }, [cargar]);

  const handleEnviarBorrador = async (emailId) => {
    try {
      await axios.post(`${API}/email/${emailId}/enviar`);
      cargar();
    } catch (err) { console.error(err); }
  };

  const handleEliminar = async (emailId) => {
    try {
      await axios.delete(`${API}/email/${emailId}`);
      cargar();
    } catch (err) { console.error(err); }
  };

  if (loading) return <Box sx={{ textAlign: 'center', py: 4 }}><CircularProgress size={30} /></Box>;

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, height: '100%' }}>
      {/* SMTP Warning */}
      {smtpConfig && !smtpConfig.configurado && (
        <Alert severity="warning" sx={{ borderRadius: 2 }}>
          SMTP no configurado. Agrega SMTP_HOST, SMTP_USER y SMTP_PASSWORD en tu .env para enviar correos reales.
          Los emails se guardaran como borradores.
        </Alert>
      )}

      {/* Stats */}
      {stats && (
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr 1fr', sm: 'repeat(4, 1fr)' }, gap: 1.5 }}>
          <Paper elevation={0} sx={{ p: 1.5, borderRadius: 2, textAlign: 'center', border: '1px solid rgba(28,35,43,0.06)' }}>
            <Typography variant="h6" sx={{ fontWeight: 800, color: '#3b82f6' }}>{stats.enviados}</Typography>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.65rem' }}>Enviados</Typography>
          </Paper>
          <Paper elevation={0} sx={{ p: 1.5, borderRadius: 2, textAlign: 'center', border: '1px solid rgba(28,35,43,0.06)' }}>
            <Typography variant="h6" sx={{ fontWeight: 800, color: '#10b981' }}>{stats.tasa_apertura}%</Typography>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.65rem' }}>Tasa apertura</Typography>
          </Paper>
          <Paper elevation={0} sx={{ p: 1.5, borderRadius: 2, textAlign: 'center', border: '1px solid rgba(28,35,43,0.06)' }}>
            <Typography variant="h6" sx={{ fontWeight: 800, color: '#f59e0b' }}>{stats.tasa_click}%</Typography>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.65rem' }}>Tasa click</Typography>
          </Paper>
          <Paper elevation={0} sx={{ p: 1.5, borderRadius: 2, textAlign: 'center', border: '1px solid rgba(28,35,43,0.06)' }}>
            <Typography variant="h6" sx={{ fontWeight: 800, color: '#94a3b8' }}>{stats.borradores}</Typography>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.65rem' }}>Borradores</Typography>
          </Paper>
        </Box>
      )}

      {/* Toolbar */}
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
        <Button variant="contained" size="small" onClick={() => setComposeOpen(true)}
          sx={{ borderRadius: 2, textTransform: 'none', fontWeight: 700 }}>
          + Nuevo Email
        </Button>
        <Box sx={{ flexGrow: 1 }} />
        {[
          { val: '', label: 'Todos' },
          { val: 'enviados', label: 'Enviados' },
          { val: 'borradores', label: 'Borradores' },
        ].map((f) => (
          <Chip key={f.val} label={f.label} size="small"
            onClick={() => setCarpeta(f.val)}
            sx={{
              cursor: 'pointer', fontWeight: 600, borderRadius: 2,
              backgroundColor: carpeta === f.val ? '#1f3a5f' : 'rgba(31,58,95,0.08)',
              color: carpeta === f.val ? '#fff' : '#1f3a5f',
            }} />
        ))}
      </Box>

      {/* Email list */}
      <Box sx={{ flexGrow: 1, overflow: 'auto' }}>
        {emails.length > 0 ? emails.map((email) => {
          const cfg = ESTADO_EMAIL_CONFIG[email.estado] || ESTADO_EMAIL_CONFIG.borrador;
          return (
            <Paper key={email.id} elevation={0}
              onClick={() => setSelectedEmail(email)}
              sx={{
                p: 1.5, mb: 0.8, borderRadius: 2, cursor: 'pointer',
                border: '1px solid rgba(28,35,43,0.06)',
                display: 'flex', alignItems: 'center', gap: 1.5,
                transition: 'all 0.12s',
                backgroundColor: email.estado === 'borrador' ? 'rgba(0,0,0,0.015)' : 'transparent',
                '&:hover': { borderColor: cfg.color, boxShadow: '0 2px 8px rgba(0,0,0,0.06)' },
              }}>
              {/* Estado icon */}
              <Tooltip title={cfg.label}>
                <Typography sx={{ fontSize: '1.1rem', width: 28, textAlign: 'center' }}>{cfg.icon}</Typography>
              </Tooltip>

              {/* Destinatario + Asunto */}
              <Box sx={{ flexGrow: 1, minWidth: 0 }}>
                <Box sx={{ display: 'flex', gap: 0.8, alignItems: 'center' }}>
                  <Typography variant="body2" sx={{ fontWeight: 700 }}>
                    {email.para_nombre || email.para_email}
                  </Typography>
                  {email.email_abierto && (
                    <Chip label="Abierto" size="small" sx={{ fontSize: '0.55rem', height: 16, backgroundColor: '#10b98115', color: '#10b981' }} />
                  )}
                  {email.email_clicked && (
                    <Chip label="Click" size="small" sx={{ fontSize: '0.55rem', height: 16, backgroundColor: '#f59e0b15', color: '#f59e0b' }} />
                  )}
                </Box>
                <Typography variant="body2" sx={{
                  color: 'text.secondary', whiteSpace: 'nowrap', overflow: 'hidden',
                  textOverflow: 'ellipsis', fontSize: '0.85rem',
                }}>
                  {email.asunto}
                </Typography>
              </Box>

              {/* Timestamp */}
              <Typography variant="caption" sx={{ color: 'text.disabled', fontSize: '0.65rem', whiteSpace: 'nowrap' }}>
                {email.enviado_at
                  ? tiempoRelativo(email.enviado_at)
                  : tiempoRelativo(email.created_at)
                }
              </Typography>

              {/* Acciones */}
              <Box sx={{ display: 'flex', gap: 0.3 }} onClick={(e) => e.stopPropagation()}>
                {email.estado === 'borrador' && (
                  <Tooltip title="Enviar">
                    <IconButton size="small" onClick={() => handleEnviarBorrador(email.id)}>
                      <Typography sx={{ fontSize: '0.85rem' }}>📤</Typography>
                    </IconButton>
                  </Tooltip>
                )}
                <Tooltip title="Eliminar">
                  <IconButton size="small" onClick={() => handleEliminar(email.id)}>
                    <Typography sx={{ fontSize: '0.85rem' }}>🗑️</Typography>
                  </IconButton>
                </Tooltip>
              </Box>
            </Paper>
          );
        }) : (
          <Box sx={{ textAlign: 'center', py: 6 }}>
            <Typography sx={{ fontSize: '2.5rem', mb: 1 }}>📭</Typography>
            <Typography variant="body1" sx={{ color: 'text.secondary', fontWeight: 600 }}>
              No hay correos
            </Typography>
            <Typography variant="body2" sx={{ color: 'text.disabled', mb: 2 }}>
              Envia tu primer email desde aqui
            </Typography>
            <Button variant="outlined" size="small" onClick={() => setComposeOpen(true)}
              sx={{ borderRadius: 2, textTransform: 'none' }}>
              Redactar email
            </Button>
          </Box>
        )}
      </Box>

      {/* Compose dialog */}
      <ComposeEmailDialog
        open={composeOpen}
        onClose={() => setComposeOpen(false)}
        onSent={cargar}
        contactos={contactos}
        deals={deals}
      />

      {/* Detail dialog */}
      <EmailDetailDialog
        email={selectedEmail}
        open={!!selectedEmail}
        onClose={() => setSelectedEmail(null)}
      />
    </Box>
  );
}


// ---------------------------------------------------------------------------
// TareasTab — Gestión de tareas CRM
// ---------------------------------------------------------------------------

const PRIORIDAD_CONFIG = {
  baja:    { label: 'Baja',    color: '#94a3b8', icon: '🔵' },
  media:   { label: 'Media',   color: '#f59e0b', icon: '🟡' },
  alta:    { label: 'Alta',    color: '#ef4444', icon: '🔴' },
  urgente: { label: 'Urgente', color: '#7c3aed', icon: '🟣' },
};

const ESTADO_TAREA_CONFIG = {
  pendiente:   { label: 'Pendiente',   color: '#94a3b8' },
  en_progreso: { label: 'En progreso', color: '#3b82f6' },
  completada:  { label: 'Completada',  color: '#10b981' },
  cancelada:   { label: 'Cancelada',   color: '#ef4444' },
};

function TareasTab() {
  const [tareas, setTareas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [filtroEstado, setFiltroEstado] = useState('');
  const [filtroPrioridad, setFiltroPrioridad] = useState('');
  const [form, setForm] = useState({
    titulo: '', descripcion: '', prioridad: 'media', fecha_vencimiento: '',
    asignado_a: '', deal_id: '', contacto_id: '', empresa_id: '',
  });
  const [deals, setDeals] = useState([]);
  const [contactos, setContactos] = useState([]);
  const [empresas, setEmpresas] = useState([]);

  const cargar = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filtroEstado) params.set('estado', filtroEstado);
      if (filtroPrioridad) params.set('prioridad', filtroPrioridad);
      const qs = params.toString() ? `?${params.toString()}` : '';

      const [tareasR, dealsR, contR, empR] = await Promise.all([
        axios.get(`${API}/tareas${qs}`),
        axios.get(`${API}/deals?limit=200`),
        axios.get(`${API}/contactos?limit=200`),
        axios.get(`${API}/empresas?limit=200`),
      ]);
      setTareas(tareasR.data || []);
      setDeals(dealsR.data || []);
      setContactos(contR.data || []);
      setEmpresas(empR.data || []);
    } catch (err) { console.error(err); }
    setLoading(false);
  }, [filtroEstado, filtroPrioridad]);

  useEffect(() => { cargar(); }, [cargar]);

  const crearTarea = async () => {
    if (!form.titulo.trim()) return;
    try {
      await axios.post(`${API}/tareas`, {
        ...form,
        deal_id: form.deal_id || null,
        contacto_id: form.contacto_id || null,
        empresa_id: form.empresa_id || null,
        fecha_vencimiento: form.fecha_vencimiento || null,
      });
      setDialogOpen(false);
      setForm({ titulo: '', descripcion: '', prioridad: 'media', fecha_vencimiento: '', asignado_a: '', deal_id: '', contacto_id: '', empresa_id: '' });
      cargar();
    } catch (err) { console.error(err); }
  };

  const cambiarEstado = async (id, nuevoEstado) => {
    try {
      await axios.patch(`${API}/tareas/${id}`, { estado: nuevoEstado });
      cargar();
    } catch (err) { console.error(err); }
  };

  const eliminar = async (id) => {
    try { await axios.delete(`${API}/tareas/${id}`); cargar(); } catch (err) { console.error(err); }
  };

  if (loading) return <Box sx={{ textAlign: 'center', py: 4 }}><CircularProgress size={30} /></Box>;

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      {/* Toolbar */}
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
        <Button variant="contained" size="small" onClick={() => setDialogOpen(true)}
          sx={{ borderRadius: 2, textTransform: 'none', fontWeight: 700 }}>
          + Nueva Tarea
        </Button>
        <Box sx={{ flexGrow: 1 }} />
        <FormControl size="small" sx={{ minWidth: 130 }}>
          <InputLabel>Estado</InputLabel>
          <Select value={filtroEstado} label="Estado" onChange={(e) => setFiltroEstado(e.target.value)}
            sx={{ borderRadius: 2 }}>
            <MenuItem value="">Todos</MenuItem>
            {Object.entries(ESTADO_TAREA_CONFIG).map(([k, v]) => (
              <MenuItem key={k} value={k}>{v.label}</MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 130 }}>
          <InputLabel>Prioridad</InputLabel>
          <Select value={filtroPrioridad} label="Prioridad" onChange={(e) => setFiltroPrioridad(e.target.value)}
            sx={{ borderRadius: 2 }}>
            <MenuItem value="">Todas</MenuItem>
            {Object.entries(PRIORIDAD_CONFIG).map(([k, v]) => (
              <MenuItem key={k} value={k}>{v.icon} {v.label}</MenuItem>
            ))}
          </Select>
        </FormControl>
      </Box>

      {/* Lista de tareas */}
      {tareas.length > 0 ? tareas.map((t) => {
        const pCfg = PRIORIDAD_CONFIG[t.prioridad] || PRIORIDAD_CONFIG.media;
        const eCfg = ESTADO_TAREA_CONFIG[t.estado] || ESTADO_TAREA_CONFIG.pendiente;
        return (
          <Paper key={t.id} elevation={0} sx={{
            p: 2, borderRadius: 2,
            border: `1px solid ${t.vencida ? '#ef444440' : 'rgba(28,35,43,0.08)'}`,
            backgroundColor: t.vencida ? 'rgba(239,68,68,0.03)' : 'transparent',
            display: 'flex', alignItems: 'center', gap: 1.5,
            opacity: t.estado === 'completada' || t.estado === 'cancelada' ? 0.6 : 1,
          }}>
            {/* Checkbox-like toggle */}
            <Tooltip title={t.estado === 'completada' ? 'Reabrir' : 'Completar'}>
              <IconButton size="small" onClick={() =>
                cambiarEstado(t.id, t.estado === 'completada' ? 'pendiente' : 'completada')
              }>
                <Typography sx={{ fontSize: '1.1rem' }}>
                  {t.estado === 'completada' ? '✅' : '⬜'}
                </Typography>
              </IconButton>
            </Tooltip>

            {/* Content */}
            <Box sx={{ flexGrow: 1, minWidth: 0 }}>
              <Box sx={{ display: 'flex', gap: 0.8, alignItems: 'center', flexWrap: 'wrap' }}>
                <Typography variant="body2" sx={{
                  fontWeight: 700,
                  textDecoration: t.estado === 'completada' ? 'line-through' : 'none',
                }}>
                  {t.titulo}
                </Typography>
                <Chip label={`${pCfg.icon} ${pCfg.label}`} size="small"
                  sx={{ fontSize: '0.6rem', height: 18, backgroundColor: `${pCfg.color}15`, color: pCfg.color }} />
                <Chip label={eCfg.label} size="small"
                  sx={{ fontSize: '0.6rem', height: 18, backgroundColor: `${eCfg.color}15`, color: eCfg.color }} />
              </Box>
              {t.descripcion && (
                <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
                  {t.descripcion}
                </Typography>
              )}
              <Box sx={{ display: 'flex', gap: 1, mt: 0.3, flexWrap: 'wrap' }}>
                {t.asignado_a && (
                  <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.65rem' }}>
                    👤 {t.asignado_a}
                  </Typography>
                )}
                {t.deal_titulo && (
                  <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.65rem' }}>
                    💼 {t.deal_titulo}
                  </Typography>
                )}
                {t.contacto_nombre && (
                  <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.65rem' }}>
                    🧑 {t.contacto_nombre}
                  </Typography>
                )}
                {t.empresa_nombre && (
                  <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.65rem' }}>
                    🏢 {t.empresa_nombre}
                  </Typography>
                )}
              </Box>
            </Box>

            {/* Due date */}
            {t.fecha_vencimiento && (
              <Typography variant="caption" sx={{
                color: t.vencida ? '#ef4444' : 'text.disabled',
                fontSize: '0.65rem', whiteSpace: 'nowrap', fontWeight: t.vencida ? 700 : 400,
              }}>
                {t.vencida ? '⚠️ ' : '📅 '}
                {new Date(t.fecha_vencimiento).toLocaleDateString('es-CL')}
              </Typography>
            )}

            {/* Actions */}
            <Box sx={{ display: 'flex', gap: 0.3 }}>
              {t.estado !== 'en_progreso' && t.estado !== 'completada' && (
                <Tooltip title="En progreso">
                  <IconButton size="small" onClick={() => cambiarEstado(t.id, 'en_progreso')}>
                    <Typography sx={{ fontSize: '0.8rem' }}>▶️</Typography>
                  </IconButton>
                </Tooltip>
              )}
              <Tooltip title="Eliminar">
                <IconButton size="small" onClick={() => eliminar(t.id)}>
                  <Typography sx={{ fontSize: '0.8rem' }}>🗑️</Typography>
                </IconButton>
              </Tooltip>
            </Box>
          </Paper>
        );
      }) : (
        <Box sx={{ textAlign: 'center', py: 6 }}>
          <Typography sx={{ fontSize: '2.5rem', mb: 1 }}>📋</Typography>
          <Typography variant="body1" sx={{ color: 'text.secondary', fontWeight: 600 }}>
            No hay tareas
          </Typography>
          <Button variant="outlined" size="small" onClick={() => setDialogOpen(true)}
            sx={{ borderRadius: 2, textTransform: 'none', mt: 1 }}>
            Crear primera tarea
          </Button>
        </Box>
      )}

      {/* Dialog crear tarea */}
      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} maxWidth="sm" fullWidth
        PaperProps={{ sx: { borderRadius: 4 } }}>
        <DialogTitle sx={{ fontWeight: 700 }}>Nueva Tarea</DialogTitle>
        <Divider />
        <DialogContent sx={{ pt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
          <TextField label="Título" required fullWidth value={form.titulo}
            onChange={(e) => setForm({ ...form, titulo: e.target.value })} />
          <TextField label="Descripción" fullWidth multiline rows={2} value={form.descripcion}
            onChange={(e) => setForm({ ...form, descripcion: e.target.value })} />
          <Box sx={{ display: 'flex', gap: 2 }}>
            <FormControl fullWidth size="small">
              <InputLabel>Prioridad</InputLabel>
              <Select value={form.prioridad} label="Prioridad"
                onChange={(e) => setForm({ ...form, prioridad: e.target.value })}>
                {Object.entries(PRIORIDAD_CONFIG).map(([k, v]) => (
                  <MenuItem key={k} value={k}>{v.icon} {v.label}</MenuItem>
                ))}
              </Select>
            </FormControl>
            <TextField label="Fecha vencimiento" type="date" fullWidth size="small"
              InputLabelProps={{ shrink: true }}
              value={form.fecha_vencimiento}
              onChange={(e) => setForm({ ...form, fecha_vencimiento: e.target.value })} />
          </Box>
          <TextField label="Asignado a" fullWidth size="small" value={form.asignado_a}
            onChange={(e) => setForm({ ...form, asignado_a: e.target.value })} />
          <Box sx={{ display: 'flex', gap: 2 }}>
            <FormControl fullWidth size="small">
              <InputLabel>Deal</InputLabel>
              <Select value={form.deal_id} label="Deal"
                onChange={(e) => setForm({ ...form, deal_id: e.target.value })}>
                <MenuItem value="">Sin vincular</MenuItem>
                {deals.map(d => <MenuItem key={d.id} value={d.id}>{d.titulo}</MenuItem>)}
              </Select>
            </FormControl>
            <FormControl fullWidth size="small">
              <InputLabel>Contacto</InputLabel>
              <Select value={form.contacto_id} label="Contacto"
                onChange={(e) => setForm({ ...form, contacto_id: e.target.value })}>
                <MenuItem value="">Sin vincular</MenuItem>
                {contactos.map(c => <MenuItem key={c.id} value={c.id}>{c.nombre} {c.apellido || ''}</MenuItem>)}
              </Select>
            </FormControl>
          </Box>
          <FormControl fullWidth size="small">
            <InputLabel>Empresa</InputLabel>
            <Select value={form.empresa_id} label="Empresa"
              onChange={(e) => setForm({ ...form, empresa_id: e.target.value })}>
              <MenuItem value="">Sin vincular</MenuItem>
              {empresas.map(e => <MenuItem key={e.id} value={e.id}>{e.nombre}</MenuItem>)}
            </Select>
          </FormControl>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 3 }}>
          <Button onClick={() => setDialogOpen(false)} color="inherit">Cancelar</Button>
          <Button onClick={crearTarea} variant="contained" disabled={!form.titulo.trim()}>Crear Tarea</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// LlamadasTab — Registro de llamadas
// ---------------------------------------------------------------------------

const TIPO_LLAMADA_CONFIG = {
  entrante: { label: 'Entrante', color: '#3b82f6', icon: '📲' },
  saliente: { label: 'Saliente', color: '#10b981', icon: '📱' },
  perdida:  { label: 'Perdida',  color: '#ef4444', icon: '📵' },
};

const RESULTADO_LLAMADA_CONFIG = {
  conectada:     { label: 'Conectada',     color: '#10b981' },
  no_contesta:   { label: 'No contesta',   color: '#f59e0b' },
  buzon_voz:     { label: 'Buzón de voz',  color: '#6366f1' },
  numero_errado: { label: 'Número errado', color: '#ef4444' },
  ocupado:       { label: 'Ocupado',       color: '#94a3b8' },
};

function LlamadasTab() {
  const [llamadas, setLlamadas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [contactos, setContactos] = useState([]);
  const [deals, setDeals] = useState([]);
  const [empresas, setEmpresas] = useState([]);
  const [form, setForm] = useState({
    tipo: 'saliente', resultado: 'conectada', numero: '', duracion_seg: 0,
    notas: '', deal_id: '', contacto_id: '', empresa_id: '',
  });

  const cargar = useCallback(async () => {
    setLoading(true);
    try {
      const [llR, contR, dealsR, empR] = await Promise.all([
        axios.get(`${API}/llamadas`),
        axios.get(`${API}/contactos?limit=200`),
        axios.get(`${API}/deals?limit=200`),
        axios.get(`${API}/empresas?limit=200`),
      ]);
      setLlamadas(llR.data || []);
      setContactos(contR.data || []);
      setDeals(dealsR.data || []);
      setEmpresas(empR.data || []);
    } catch (err) { console.error(err); }
    setLoading(false);
  }, []);

  useEffect(() => { cargar(); }, [cargar]);

  const crearLlamada = async () => {
    try {
      await axios.post(`${API}/llamadas`, {
        ...form,
        duracion_seg: parseInt(form.duracion_seg) || 0,
        deal_id: form.deal_id || null,
        contacto_id: form.contacto_id || null,
        empresa_id: form.empresa_id || null,
      });
      setDialogOpen(false);
      setForm({ tipo: 'saliente', resultado: 'conectada', numero: '', duracion_seg: 0, notas: '', deal_id: '', contacto_id: '', empresa_id: '' });
      cargar();
    } catch (err) { console.error(err); }
  };

  const eliminar = async (id) => {
    try { await axios.delete(`${API}/llamadas/${id}`); cargar(); } catch (err) { console.error(err); }
  };

  const formatDuracion = (seg) => {
    if (!seg) return '0s';
    const m = Math.floor(seg / 60);
    const s = seg % 60;
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
  };

  if (loading) return <Box sx={{ textAlign: 'center', py: 4 }}><CircularProgress size={30} /></Box>;

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
        <Button variant="contained" size="small" onClick={() => setDialogOpen(true)}
          sx={{ borderRadius: 2, textTransform: 'none', fontWeight: 700 }}>
          + Registrar Llamada
        </Button>
        <Typography variant="caption" sx={{ color: 'text.secondary', ml: 1 }}>
          {llamadas.length} llamadas registradas
        </Typography>
      </Box>

      {llamadas.length > 0 ? llamadas.map((ll) => {
        const tCfg = TIPO_LLAMADA_CONFIG[ll.tipo] || TIPO_LLAMADA_CONFIG.saliente;
        const rCfg = RESULTADO_LLAMADA_CONFIG[ll.resultado] || RESULTADO_LLAMADA_CONFIG.conectada;
        return (
          <Paper key={ll.id} elevation={0} sx={{
            p: 2, borderRadius: 2, border: '1px solid rgba(28,35,43,0.08)',
            display: 'flex', alignItems: 'center', gap: 1.5,
          }}>
            <Typography sx={{ fontSize: '1.2rem' }}>{tCfg.icon}</Typography>
            <Box sx={{ flexGrow: 1, minWidth: 0 }}>
              <Box sx={{ display: 'flex', gap: 0.8, alignItems: 'center', flexWrap: 'wrap' }}>
                <Chip label={tCfg.label} size="small"
                  sx={{ fontSize: '0.6rem', height: 18, backgroundColor: `${tCfg.color}15`, color: tCfg.color }} />
                <Chip label={rCfg.label} size="small"
                  sx={{ fontSize: '0.6rem', height: 18, backgroundColor: `${rCfg.color}15`, color: rCfg.color }} />
                {ll.numero && (
                  <Typography variant="body2" sx={{ fontWeight: 700 }}>{ll.numero}</Typography>
                )}
                <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                  ⏱️ {formatDuracion(ll.duracion_seg)}
                </Typography>
              </Box>
              {ll.notas && (
                <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', mt: 0.3 }}>
                  {ll.notas}
                </Typography>
              )}
              <Box sx={{ display: 'flex', gap: 1, mt: 0.3 }}>
                {ll.contacto_nombre && (
                  <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.65rem' }}>
                    👤 {ll.contacto_nombre}
                  </Typography>
                )}
                {ll.empresa_nombre && (
                  <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.65rem' }}>
                    🏢 {ll.empresa_nombre}
                  </Typography>
                )}
              </Box>
            </Box>
            <Typography variant="caption" sx={{ color: 'text.disabled', fontSize: '0.65rem', whiteSpace: 'nowrap' }}>
              {tiempoRelativo(ll.created_at)}
            </Typography>
            <Tooltip title="Eliminar">
              <IconButton size="small" onClick={() => eliminar(ll.id)}>
                <Typography sx={{ fontSize: '0.8rem' }}>🗑️</Typography>
              </IconButton>
            </Tooltip>
          </Paper>
        );
      }) : (
        <Box sx={{ textAlign: 'center', py: 6 }}>
          <Typography sx={{ fontSize: '2.5rem', mb: 1 }}>📞</Typography>
          <Typography variant="body1" sx={{ color: 'text.secondary', fontWeight: 600 }}>
            No hay llamadas registradas
          </Typography>
          <Button variant="outlined" size="small" onClick={() => setDialogOpen(true)}
            sx={{ borderRadius: 2, textTransform: 'none', mt: 1 }}>
            Registrar primera llamada
          </Button>
        </Box>
      )}

      {/* Dialog */}
      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} maxWidth="sm" fullWidth
        PaperProps={{ sx: { borderRadius: 4 } }}>
        <DialogTitle sx={{ fontWeight: 700 }}>Registrar Llamada</DialogTitle>
        <Divider />
        <DialogContent sx={{ pt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Box sx={{ display: 'flex', gap: 2 }}>
            <FormControl fullWidth size="small">
              <InputLabel>Tipo</InputLabel>
              <Select value={form.tipo} label="Tipo"
                onChange={(e) => setForm({ ...form, tipo: e.target.value })}>
                {Object.entries(TIPO_LLAMADA_CONFIG).map(([k, v]) => (
                  <MenuItem key={k} value={k}>{v.icon} {v.label}</MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl fullWidth size="small">
              <InputLabel>Resultado</InputLabel>
              <Select value={form.resultado} label="Resultado"
                onChange={(e) => setForm({ ...form, resultado: e.target.value })}>
                {Object.entries(RESULTADO_LLAMADA_CONFIG).map(([k, v]) => (
                  <MenuItem key={k} value={k}>{v.label}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </Box>
          <Box sx={{ display: 'flex', gap: 2 }}>
            <TextField label="Número" fullWidth size="small" value={form.numero}
              onChange={(e) => setForm({ ...form, numero: e.target.value })} />
            <TextField label="Duración (seg)" type="number" sx={{ minWidth: 140 }} size="small"
              value={form.duracion_seg}
              onChange={(e) => setForm({ ...form, duracion_seg: e.target.value })} />
          </Box>
          <TextField label="Notas" fullWidth multiline rows={3} value={form.notas}
            onChange={(e) => setForm({ ...form, notas: e.target.value })} />
          <Box sx={{ display: 'flex', gap: 2 }}>
            <FormControl fullWidth size="small">
              <InputLabel>Contacto</InputLabel>
              <Select value={form.contacto_id} label="Contacto"
                onChange={(e) => setForm({ ...form, contacto_id: e.target.value })}>
                <MenuItem value="">Sin vincular</MenuItem>
                {contactos.map(c => <MenuItem key={c.id} value={c.id}>{c.nombre} {c.apellido || ''}</MenuItem>)}
              </Select>
            </FormControl>
            <FormControl fullWidth size="small">
              <InputLabel>Deal</InputLabel>
              <Select value={form.deal_id} label="Deal"
                onChange={(e) => setForm({ ...form, deal_id: e.target.value })}>
                <MenuItem value="">Sin vincular</MenuItem>
                {deals.map(d => <MenuItem key={d.id} value={d.id}>{d.titulo}</MenuItem>)}
              </Select>
            </FormControl>
          </Box>
          <FormControl fullWidth size="small">
            <InputLabel>Empresa</InputLabel>
            <Select value={form.empresa_id} label="Empresa"
              onChange={(e) => setForm({ ...form, empresa_id: e.target.value })}>
              <MenuItem value="">Sin vincular</MenuItem>
              {empresas.map(e => <MenuItem key={e.id} value={e.id}>{e.nombre}</MenuItem>)}
            </Select>
          </FormControl>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 3 }}>
          <Button onClick={() => setDialogOpen(false)} color="inherit">Cancelar</Button>
          <Button onClick={crearLlamada} variant="contained">Registrar</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// PlantillasTab — Plantillas de email
// ---------------------------------------------------------------------------

function PlantillasTab() {
  const [plantillas, setPlantillas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState(null);
  const [form, setForm] = useState({
    nombre: '', categoria: '', asunto: '', cuerpo_html: '', cuerpo_texto: '',
  });

  const cargar = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/plantillas`);
      setPlantillas(res.data || []);
    } catch (err) { console.error(err); }
    setLoading(false);
  }, []);

  useEffect(() => { cargar(); }, [cargar]);

  const guardar = async () => {
    if (!form.nombre.trim() || !form.asunto.trim()) return;
    try {
      if (editando) {
        await axios.patch(`${API}/plantillas/${editando.id}`, form);
      } else {
        await axios.post(`${API}/plantillas`, form);
      }
      setDialogOpen(false);
      setEditando(null);
      setForm({ nombre: '', categoria: '', asunto: '', cuerpo_html: '', cuerpo_texto: '' });
      cargar();
    } catch (err) { console.error(err); }
  };

  const editar = (p) => {
    setEditando(p);
    setForm({
      nombre: p.nombre, categoria: p.categoria || '', asunto: p.asunto,
      cuerpo_html: p.cuerpo_html || '', cuerpo_texto: p.cuerpo_texto || '',
    });
    setDialogOpen(true);
  };

  const eliminar = async (id) => {
    try { await axios.delete(`${API}/plantillas/${id}`); cargar(); } catch (err) { console.error(err); }
  };

  if (loading) return <Box sx={{ textAlign: 'center', py: 4 }}><CircularProgress size={30} /></Box>;

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
        <Button variant="contained" size="small"
          onClick={() => { setEditando(null); setForm({ nombre: '', categoria: '', asunto: '', cuerpo_html: '', cuerpo_texto: '' }); setDialogOpen(true); }}
          sx={{ borderRadius: 2, textTransform: 'none', fontWeight: 700 }}>
          + Nueva Plantilla
        </Button>
        <Typography variant="caption" sx={{ color: 'text.secondary', ml: 1 }}>
          {plantillas.length} plantillas
        </Typography>
      </Box>

      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr', md: '1fr 1fr 1fr' }, gap: 1.5 }}>
        {plantillas.map((p) => (
          <Paper key={p.id} elevation={0} sx={{
            p: 2, borderRadius: 2, border: '1px solid rgba(28,35,43,0.08)',
            cursor: 'pointer', transition: 'all 0.15s',
            '&:hover': { borderColor: '#6366f1', boxShadow: '0 4px 12px rgba(0,0,0,0.06)' },
          }}
            onClick={() => editar(p)}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
              <Typography sx={{ fontSize: '1.2rem' }}>📄</Typography>
              <Typography variant="body2" sx={{ fontWeight: 700, flexGrow: 1 }}>{p.nombre}</Typography>
              <Tooltip title="Eliminar">
                <IconButton size="small" onClick={(e) => { e.stopPropagation(); eliminar(p.id); }}>
                  <Typography sx={{ fontSize: '0.7rem' }}>🗑️</Typography>
                </IconButton>
              </Tooltip>
            </Box>
            {p.categoria && (
              <Chip label={p.categoria} size="small" sx={{ fontSize: '0.6rem', height: 18, mb: 0.5 }} />
            )}
            <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
              Asunto: {p.asunto}
            </Typography>
            <Typography variant="caption" sx={{ color: 'text.disabled', fontSize: '0.6rem' }}>
              Usada {p.veces_usada || 0} veces
            </Typography>
          </Paper>
        ))}
      </Box>

      {plantillas.length === 0 && (
        <Box sx={{ textAlign: 'center', py: 6 }}>
          <Typography sx={{ fontSize: '2.5rem', mb: 1 }}>📄</Typography>
          <Typography variant="body1" sx={{ color: 'text.secondary', fontWeight: 600 }}>
            No hay plantillas
          </Typography>
          <Button variant="outlined" size="small"
            onClick={() => { setEditando(null); setForm({ nombre: '', categoria: '', asunto: '', cuerpo_html: '', cuerpo_texto: '' }); setDialogOpen(true); }}
            sx={{ borderRadius: 2, textTransform: 'none', mt: 1 }}>
            Crear primera plantilla
          </Button>
        </Box>
      )}

      {/* Dialog */}
      <Dialog open={dialogOpen} onClose={() => { setDialogOpen(false); setEditando(null); }} maxWidth="md" fullWidth
        PaperProps={{ sx: { borderRadius: 4 } }}>
        <DialogTitle sx={{ fontWeight: 700 }}>
          {editando ? 'Editar Plantilla' : 'Nueva Plantilla'}
        </DialogTitle>
        <Divider />
        <DialogContent sx={{ pt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Box sx={{ display: 'flex', gap: 2 }}>
            <TextField label="Nombre" required fullWidth value={form.nombre}
              onChange={(e) => setForm({ ...form, nombre: e.target.value })} />
            <TextField label="Categoría" sx={{ minWidth: 180 }} value={form.categoria}
              onChange={(e) => setForm({ ...form, categoria: e.target.value })} />
          </Box>
          <TextField label="Asunto" required fullWidth value={form.asunto}
            onChange={(e) => setForm({ ...form, asunto: e.target.value })} />
          <TextField label="Contenido (texto)" fullWidth multiline rows={8}
            value={form.cuerpo_texto}
            onChange={(e) => setForm({ ...form, cuerpo_texto: e.target.value })}
            placeholder="Escribe el contenido de la plantilla...&#10;&#10;Puedes usar variables como {{nombre}}, {{empresa}}, etc." />
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 3 }}>
          <Button onClick={() => { setDialogOpen(false); setEditando(null); }} color="inherit">Cancelar</Button>
          <Button onClick={guardar} variant="contained" disabled={!form.nombre.trim() || !form.asunto.trim()}>
            {editando ? 'Guardar cambios' : 'Crear Plantilla'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// CotizacionesTab — Cotizaciones / Quotes
// ---------------------------------------------------------------------------

const ESTADO_COTIZACION_CONFIG = {
  borrador:  { label: 'Borrador',  color: '#94a3b8', icon: '📝' },
  enviada:   { label: 'Enviada',   color: '#3b82f6', icon: '📤' },
  aceptada:  { label: 'Aceptada',  color: '#10b981', icon: '✅' },
  rechazada: { label: 'Rechazada', color: '#ef4444', icon: '❌' },
  expirada:  { label: 'Expirada',  color: '#f59e0b', icon: '⏰' },
};

function CotizacionesTab() {
  const [cotizaciones, setCotizaciones] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [deals, setDeals] = useState([]);
  const [contactos, setContactos] = useState([]);
  const [empresas, setEmpresas] = useState([]);
  const [form, setForm] = useState({
    titulo: '', descripcion: '', items: [{ descripcion: '', cantidad: 1, precio_unitario: 0 }],
    descuento_pct: 0, iva_pct: 19, moneda: 'CLP', notas: '',
    fecha_expiracion: '', deal_id: '', contacto_id: '', empresa_id: '',
  });

  const cargar = useCallback(async () => {
    setLoading(true);
    try {
      const [cotR, dealsR, contR, empR] = await Promise.all([
        axios.get(`${API}/cotizaciones`),
        axios.get(`${API}/deals?limit=200`),
        axios.get(`${API}/contactos?limit=200`),
        axios.get(`${API}/empresas?limit=200`),
      ]);
      setCotizaciones(cotR.data || []);
      setDeals(dealsR.data || []);
      setContactos(contR.data || []);
      setEmpresas(empR.data || []);
    } catch (err) { console.error(err); }
    setLoading(false);
  }, []);

  useEffect(() => { cargar(); }, [cargar]);

  const addItem = () => {
    setForm(prev => ({
      ...prev,
      items: [...prev.items, { descripcion: '', cantidad: 1, precio_unitario: 0 }],
    }));
  };

  const updateItem = (idx, field, value) => {
    setForm(prev => {
      const items = [...prev.items];
      items[idx] = { ...items[idx], [field]: value };
      return { ...prev, items };
    });
  };

  const removeItem = (idx) => {
    setForm(prev => ({
      ...prev,
      items: prev.items.filter((_, i) => i !== idx),
    }));
  };

  const subtotal = form.items.reduce((s, it) => s + (it.cantidad * it.precio_unitario), 0);
  const descuento = subtotal * (form.descuento_pct / 100);
  const baseIva = subtotal - descuento;
  const iva = baseIva * (form.iva_pct / 100);
  const total = baseIva + iva;

  const crearCotizacion = async () => {
    if (!form.titulo.trim()) return;
    try {
      await axios.post(`${API}/cotizaciones`, {
        ...form,
        items: form.items.filter(it => it.descripcion.trim()),
        deal_id: form.deal_id || null,
        contacto_id: form.contacto_id || null,
        empresa_id: form.empresa_id || null,
        fecha_expiracion: form.fecha_expiracion || null,
      });
      setDialogOpen(false);
      setForm({
        titulo: '', descripcion: '', items: [{ descripcion: '', cantidad: 1, precio_unitario: 0 }],
        descuento_pct: 0, iva_pct: 19, moneda: 'CLP', notas: '',
        fecha_expiracion: '', deal_id: '', contacto_id: '', empresa_id: '',
      });
      cargar();
    } catch (err) { console.error(err); }
  };

  const cambiarEstado = async (id, estado) => {
    try {
      await axios.patch(`${API}/cotizaciones/${id}`, { estado });
      cargar();
    } catch (err) { console.error(err); }
  };

  const eliminar = async (id) => {
    try { await axios.delete(`${API}/cotizaciones/${id}`); cargar(); } catch (err) { console.error(err); }
  };

  if (loading) return <Box sx={{ textAlign: 'center', py: 4 }}><CircularProgress size={30} /></Box>;

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
        <Button variant="contained" size="small" onClick={() => setDialogOpen(true)}
          sx={{ borderRadius: 2, textTransform: 'none', fontWeight: 700 }}>
          + Nueva Cotización
        </Button>
        <Typography variant="caption" sx={{ color: 'text.secondary', ml: 1 }}>
          {cotizaciones.length} cotizaciones
        </Typography>
      </Box>

      {cotizaciones.length > 0 ? cotizaciones.map((c) => {
        const eCfg = ESTADO_COTIZACION_CONFIG[c.estado] || ESTADO_COTIZACION_CONFIG.borrador;
        return (
          <Paper key={c.id} elevation={0} sx={{
            p: 2, borderRadius: 2, border: '1px solid rgba(28,35,43,0.08)',
            display: 'flex', alignItems: 'center', gap: 1.5,
          }}>
            <Typography sx={{ fontSize: '1.2rem' }}>💰</Typography>
            <Box sx={{ flexGrow: 1, minWidth: 0 }}>
              <Box sx={{ display: 'flex', gap: 0.8, alignItems: 'center', flexWrap: 'wrap' }}>
                <Typography variant="body2" sx={{ fontWeight: 700 }}>{c.titulo}</Typography>
                <Chip label={c.numero} size="small"
                  sx={{ fontSize: '0.6rem', height: 18, fontWeight: 700, fontFamily: 'monospace' }} />
                <Chip label={`${eCfg.icon} ${eCfg.label}`} size="small"
                  sx={{ fontSize: '0.6rem', height: 18, backgroundColor: `${eCfg.color}15`, color: eCfg.color }} />
              </Box>
              <Box sx={{ display: 'flex', gap: 1, mt: 0.3, flexWrap: 'wrap' }}>
                {c.empresa_nombre && (
                  <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.65rem' }}>
                    🏢 {c.empresa_nombre}
                  </Typography>
                )}
                {c.contacto_nombre && (
                  <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.65rem' }}>
                    👤 {c.contacto_nombre}
                  </Typography>
                )}
                {c.deal_titulo && (
                  <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.65rem' }}>
                    💼 {c.deal_titulo}
                  </Typography>
                )}
              </Box>
            </Box>
            <Typography variant="body2" sx={{ fontWeight: 800, whiteSpace: 'nowrap' }}>
              {formatCLP(c.total)}
            </Typography>
            <Typography variant="caption" sx={{ color: 'text.disabled', fontSize: '0.65rem', whiteSpace: 'nowrap' }}>
              {tiempoRelativo(c.created_at)}
            </Typography>
            {/* Acciones */}
            <Box sx={{ display: 'flex', gap: 0.3 }}>
              {c.estado === 'borrador' && (
                <Tooltip title="Marcar como enviada">
                  <IconButton size="small" onClick={() => cambiarEstado(c.id, 'enviada')}>
                    <Typography sx={{ fontSize: '0.8rem' }}>📤</Typography>
                  </IconButton>
                </Tooltip>
              )}
              {c.estado === 'enviada' && (
                <>
                  <Tooltip title="Aceptar">
                    <IconButton size="small" onClick={() => cambiarEstado(c.id, 'aceptada')}>
                      <Typography sx={{ fontSize: '0.8rem' }}>✅</Typography>
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Rechazar">
                    <IconButton size="small" onClick={() => cambiarEstado(c.id, 'rechazada')}>
                      <Typography sx={{ fontSize: '0.8rem' }}>❌</Typography>
                    </IconButton>
                  </Tooltip>
                </>
              )}
              <Tooltip title="Eliminar">
                <IconButton size="small" onClick={() => eliminar(c.id)}>
                  <Typography sx={{ fontSize: '0.8rem' }}>🗑️</Typography>
                </IconButton>
              </Tooltip>
            </Box>
          </Paper>
        );
      }) : (
        <Box sx={{ textAlign: 'center', py: 6 }}>
          <Typography sx={{ fontSize: '2.5rem', mb: 1 }}>💰</Typography>
          <Typography variant="body1" sx={{ color: 'text.secondary', fontWeight: 600 }}>
            No hay cotizaciones
          </Typography>
          <Button variant="outlined" size="small" onClick={() => setDialogOpen(true)}
            sx={{ borderRadius: 2, textTransform: 'none', mt: 1 }}>
            Crear primera cotización
          </Button>
        </Box>
      )}

      {/* Dialog crear cotización */}
      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} maxWidth="md" fullWidth
        PaperProps={{ sx: { borderRadius: 4, maxHeight: '90vh' } }}>
        <DialogTitle sx={{ fontWeight: 700 }}>Nueva Cotización</DialogTitle>
        <Divider />
        <DialogContent sx={{ pt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
          <TextField label="Título" required fullWidth value={form.titulo}
            onChange={(e) => setForm({ ...form, titulo: e.target.value })} />
          <TextField label="Descripción" fullWidth multiline rows={2} value={form.descripcion}
            onChange={(e) => setForm({ ...form, descripcion: e.target.value })} />

          {/* Items */}
          <Typography variant="subtitle2" sx={{ fontWeight: 700, mt: 1 }}>Ítems</Typography>
          {form.items.map((item, idx) => (
            <Box key={idx} sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
              <TextField label="Descripción" size="small" sx={{ flexGrow: 1 }} value={item.descripcion}
                onChange={(e) => updateItem(idx, 'descripcion', e.target.value)} />
              <TextField label="Cant." type="number" size="small" sx={{ width: 80 }} value={item.cantidad}
                onChange={(e) => updateItem(idx, 'cantidad', parseFloat(e.target.value) || 0)} />
              <TextField label="Precio unit." type="number" size="small" sx={{ width: 130 }} value={item.precio_unitario}
                onChange={(e) => updateItem(idx, 'precio_unitario', parseFloat(e.target.value) || 0)} />
              <Typography variant="body2" sx={{ fontWeight: 700, minWidth: 90, textAlign: 'right' }}>
                {formatCLP(item.cantidad * item.precio_unitario)}
              </Typography>
              <IconButton size="small" onClick={() => removeItem(idx)} disabled={form.items.length <= 1}>
                <Typography sx={{ fontSize: '0.8rem' }}>🗑️</Typography>
              </IconButton>
            </Box>
          ))}
          <Button size="small" onClick={addItem} sx={{ alignSelf: 'flex-start', textTransform: 'none' }}>
            + Agregar ítem
          </Button>

          {/* Totales */}
          <Paper elevation={0} sx={{ p: 2, borderRadius: 2, backgroundColor: 'rgba(0,0,0,0.02)', border: '1px solid rgba(0,0,0,0.06)' }}>
            <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', mb: 1 }}>
              <TextField label="Descuento %" type="number" size="small" sx={{ width: 120 }}
                value={form.descuento_pct} onChange={(e) => setForm({ ...form, descuento_pct: parseFloat(e.target.value) || 0 })} />
              <TextField label="IVA %" type="number" size="small" sx={{ width: 100 }}
                value={form.iva_pct} onChange={(e) => setForm({ ...form, iva_pct: parseFloat(e.target.value) || 0 })} />
              <Box sx={{ flexGrow: 1 }} />
              <Box sx={{ textAlign: 'right' }}>
                <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
                  Subtotal: {formatCLP(subtotal)}
                </Typography>
                {form.descuento_pct > 0 && (
                  <Typography variant="caption" sx={{ color: '#ef4444', display: 'block' }}>
                    Descuento: -{formatCLP(descuento)}
                  </Typography>
                )}
                <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
                  IVA ({form.iva_pct}%): {formatCLP(iva)}
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 800 }}>
                  Total: {formatCLP(total)}
                </Typography>
              </Box>
            </Box>
          </Paper>

          {/* Vincular */}
          <Box sx={{ display: 'flex', gap: 2 }}>
            <FormControl fullWidth size="small">
              <InputLabel>Deal</InputLabel>
              <Select value={form.deal_id} label="Deal"
                onChange={(e) => setForm({ ...form, deal_id: e.target.value })}>
                <MenuItem value="">Sin vincular</MenuItem>
                {deals.map(d => <MenuItem key={d.id} value={d.id}>{d.titulo}</MenuItem>)}
              </Select>
            </FormControl>
            <FormControl fullWidth size="small">
              <InputLabel>Contacto</InputLabel>
              <Select value={form.contacto_id} label="Contacto"
                onChange={(e) => setForm({ ...form, contacto_id: e.target.value })}>
                <MenuItem value="">Sin vincular</MenuItem>
                {contactos.map(c => <MenuItem key={c.id} value={c.id}>{c.nombre} {c.apellido || ''}</MenuItem>)}
              </Select>
            </FormControl>
            <FormControl fullWidth size="small">
              <InputLabel>Empresa</InputLabel>
              <Select value={form.empresa_id} label="Empresa"
                onChange={(e) => setForm({ ...form, empresa_id: e.target.value })}>
                <MenuItem value="">Sin vincular</MenuItem>
                {empresas.map(e => <MenuItem key={e.id} value={e.id}>{e.nombre}</MenuItem>)}
              </Select>
            </FormControl>
          </Box>
          <TextField label="Fecha expiración" type="date" size="small" sx={{ maxWidth: 200 }}
            InputLabelProps={{ shrink: true }}
            value={form.fecha_expiracion}
            onChange={(e) => setForm({ ...form, fecha_expiracion: e.target.value })} />
          <TextField label="Notas" fullWidth multiline rows={2} value={form.notas}
            onChange={(e) => setForm({ ...form, notas: e.target.value })} />
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 3 }}>
          <Button onClick={() => setDialogOpen(false)} color="inherit">Cancelar</Button>
          <Button onClick={crearCotizacion} variant="contained" disabled={!form.titulo.trim()}>
            Crear Cotización
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}


// ---------------------------------------------------------------------------
// CRM — componente principal
// ---------------------------------------------------------------------------

function CRM() {
  const [pipeline, setPipeline] = useState([]);
  const [empresas, setEmpresas] = useState([]);
  const [contactos, setContactos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState(0);
  const [selectedDeal, setSelectedDeal] = useState(null);
  const [newDealOpen, setNewDealOpen] = useState(false);

  const cargarPipeline = useCallback(async () => {
    try {
      const [pipeR, empR, contR] = await Promise.all([
        axios.get(`${API}/deals/pipeline`),
        axios.get(`${API}/empresas`),
        axios.get(`${API}/contactos`),
      ]);
      setPipeline(pipeR.data || []);
      setEmpresas(empR.data || []);
      setContactos(contR.data || []);
    } catch (err) {
      console.error('Error cargando pipeline:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { cargarPipeline(); }, [cargarPipeline]);

  // Métricas rápidas
  const totalDeals = pipeline.reduce((sum, col) => sum + col.deals.length, 0);
  const valorTotal = pipeline.reduce((sum, col) => sum + (col.valor_total || 0), 0);
  const dealsActivos = pipeline
    .filter((col) => !['ganado', 'perdido'].includes(col.estado))
    .reduce((sum, col) => sum + col.deals.length, 0);

  if (loading) {
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', gap: 2 }}>
        <CircularProgress size={36} />
        <Typography variant="body1" sx={{ color: 'text.secondary' }}>Cargando CRM...</Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, height: '100%', minHeight: 0 }}>
      {/* Header */}
      <Paper sx={{ p: 2.5, borderRadius: 3 }}>
        <Box sx={{ display: 'flex', flexDirection: { xs: 'column', md: 'row' }, gap: 2, alignItems: { md: 'center' } }}>
          <Box sx={{ flexGrow: 1 }}>
            <Typography variant="h5" sx={{ fontWeight: 700 }}>CRM & Ventas</Typography>
            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
              {totalDeals} deals · {dealsActivos} activos · Pipeline: {formatCLP(valorTotal)}
            </Typography>
          </Box>

          {/* Métricas rápidas */}
          <Box sx={{ display: 'flex', gap: 1.5 }}>
            {[
              { label: 'Prospectos', value: pipeline.find(c => c.estado === 'prospecto')?.deals.length || 0, color: '#6366f1' },
              { label: 'Negociando', value: pipeline.find(c => c.estado === 'negociacion')?.deals.length || 0, color: '#3b82f6' },
              { label: 'Ganados', value: pipeline.find(c => c.estado === 'ganado')?.deals.length || 0, color: '#10b981' },
            ].map((m) => (
              <Paper key={m.label} elevation={0} sx={{
                px: 2, py: 1, borderRadius: 2, textAlign: 'center',
                backgroundColor: `${m.color}08`, border: `1px solid ${m.color}20`,
              }}>
                <Typography variant="h6" sx={{ fontWeight: 800, color: m.color }}>{m.value}</Typography>
                <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.65rem' }}>{m.label}</Typography>
              </Paper>
            ))}
          </Box>

          <Button variant="contained" onClick={() => setNewDealOpen(true)}
            sx={{ borderRadius: 2, textTransform: 'none', fontWeight: 700, whiteSpace: 'nowrap' }}>
            + Nuevo Deal
          </Button>
        </Box>
      </Paper>

      {/* Tabs */}
      <Tabs value={tab} onChange={(_, v) => setTab(v)} variant="scrollable" scrollButtons="auto" sx={{
        '& .MuiTab-root': { textTransform: 'none', fontWeight: 600, minWidth: 90 },
      }}>
        <Tab label="Pipeline" />
        <Tab label="Contactos" />
        <Tab label="Email" />
        <Tab label="Tareas" />
        <Tab label="Llamadas" />
        <Tab label="Plantillas" />
        <Tab label="Cotizaciones" />
      </Tabs>

      {/* Tab content */}
      {tab === 0 && (
        <Box sx={{ flexGrow: 1, overflow: 'auto', display: 'flex', gap: 2, pb: 2, minHeight: 0 }}>
          {pipeline.map((col) => (
            <KanbanColumn
              key={col.estado}
              config={PIPELINE_CONFIG[col.estado] || PIPELINE_CONFIG.prospecto}
              deals={col.deals}
              valorTotal={col.valor_total}
              onDealClick={setSelectedDeal}
            />
          ))}
        </Box>
      )}

      {tab === 1 && (
        <Box sx={{ flexGrow: 1, overflow: 'auto', pb: 2 }}>
          <EmpresasContactosTab />
        </Box>
      )}

      {tab === 2 && (
        <Box sx={{ flexGrow: 1, overflow: 'hidden', pb: 2 }}>
          <EmailTab />
        </Box>
      )}

      {tab === 3 && (
        <Box sx={{ flexGrow: 1, overflow: 'auto', pb: 2 }}>
          <TareasTab />
        </Box>
      )}

      {tab === 4 && (
        <Box sx={{ flexGrow: 1, overflow: 'auto', pb: 2 }}>
          <LlamadasTab />
        </Box>
      )}

      {tab === 5 && (
        <Box sx={{ flexGrow: 1, overflow: 'auto', pb: 2 }}>
          <PlantillasTab />
        </Box>
      )}

      {tab === 6 && (
        <Box sx={{ flexGrow: 1, overflow: 'auto', pb: 2 }}>
          <CotizacionesTab />
        </Box>
      )}

      {/* Deal detail dialog */}
      <DealDetailDialog
        deal={selectedDeal}
        open={!!selectedDeal}
        onClose={() => setSelectedDeal(null)}
        onUpdate={() => { cargarPipeline(); setSelectedDeal(null); }}
        onAddActivity={cargarPipeline}
      />

      {/* New deal dialog */}
      <NewDealDialog
        open={newDealOpen}
        onClose={() => setNewDealOpen(false)}
        onCreated={cargarPipeline}
        empresas={empresas}
        contactos={contactos}
      />
    </Box>
  );
}

export default CRM;
