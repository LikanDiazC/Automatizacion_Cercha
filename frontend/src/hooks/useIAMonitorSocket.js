/**
 * useIAMonitorSocket — Hook para el Centro de Comando de IA.
 *
 * Responsabilidades:
 *   • Conectar al WebSocket /api/compras/ws/ia-monitor del backend.
 *   • Reconexión automática con back-off exponencial.
 *   • Enviar "ping" periódico para mantener vivo el socket.
 *   • Exponer el último evento + el estado de conexión al componente.
 *   • Buffer circular con los últimos N eventos para paneles de telemetría.
 */
import { useEffect, useRef, useState, useCallback } from "react";

const WS_PATH = "/api/compras/ws/ia-monitor";
const HISTORY_URL = "/api/compras/ia-monitor/history?limit=500";
const MAX_BUFFER = 500;
const PING_INTERVAL_MS = 20000;
const INITIAL_BACKOFF_MS = 500;
const MAX_BACKOFF_MS = 15000;

function buildWsUrl() {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  const host = import.meta.env.VITE_API_HOST || window.location.host;
  return `${proto}://${host}${WS_PATH}`;
}

export default function useIAMonitorSocket() {
  const [status, setStatus] = useState("idle"); // "idle" | "connecting" | "open" | "closed" | "error"
  const [lastEvent, setLastEvent] = useState(null);
  const [buffer, setBuffer] = useState([]); // últimos N eventos
  const [history, setHistory] = useState(null); // seed inicial desde REST (null = pendiente, [] = vacío)
  const [historyLoaded, setHistoryLoaded] = useState(false);

  const wsRef = useRef(null);
  const backoffRef = useRef(INITIAL_BACKOFF_MS);
  const pingTimerRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const mountedRef = useRef(true);
  const seenEventIdsRef = useRef(new Set()); // dedupe histórico vs live

  const clearTimers = useCallback(() => {
    if (pingTimerRef.current) {
      clearInterval(pingTimerRef.current);
      pingTimerRef.current = null;
    }
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;
    setStatus("connecting");

    let ws;
    try {
      ws = new WebSocket(buildWsUrl());
    } catch (err) {
      console.error("[IA Monitor] No pude crear WebSocket:", err);
      scheduleReconnect();
      return;
    }

    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) return;
      backoffRef.current = INITIAL_BACKOFF_MS;
      setStatus("open");
      pingTimerRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send("ping");
      }, PING_INTERVAL_MS);
    };

    ws.onmessage = (msg) => {
      if (!mountedRef.current) return;
      let payload;
      try {
        payload = JSON.parse(msg.data);
      } catch {
        return;
      }
      // Ignoramos mensajes internos del protocolo
      if (payload.event_type === "pong" || payload.event_type === "hello") {
        return;
      }
      if (payload.event_type === "heartbeat") {
        // Mantenemos el estado visible pero no entra al buffer
        return;
      }
      // Dedupe contra el histórico ya cargado (mismo event_id)
      if (payload.event_id && seenEventIdsRef.current.has(payload.event_id)) {
        return;
      }
      if (payload.event_id) seenEventIdsRef.current.add(payload.event_id);
      setLastEvent(payload);
      setBuffer((prev) => {
        const next = [...prev, payload];
        return next.length > MAX_BUFFER ? next.slice(next.length - MAX_BUFFER) : next;
      });
    };

    ws.onerror = () => {
      if (!mountedRef.current) return;
      setStatus("error");
    };

    ws.onclose = () => {
      if (!mountedRef.current) return;
      setStatus("closed");
      clearTimers();
      scheduleReconnect();
    };
  }, [clearTimers]);

  const scheduleReconnect = useCallback(() => {
    if (!mountedRef.current) return;
    const delay = Math.min(backoffRef.current, MAX_BACKOFF_MS);
    reconnectTimerRef.current = setTimeout(connect, delay);
    backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF_MS);
  }, [connect]);

  // Carga inicial del histórico vía REST ANTES de abrir el WebSocket,
  // para que el usuario vea los eventos de la última corrida aunque se
  // conecte después de que terminó el pipeline.
  useEffect(() => {
    mountedRef.current = true;
    let cancelled = false;

    (async () => {
      try {
        const resp = await fetch(HISTORY_URL, { cache: "no-store" });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        if (cancelled || !mountedRef.current) return;
        const events = Array.isArray(data.events) ? data.events : [];
        // Registrar IDs para deduplicar con eventos live que podrían repetirlos.
        for (const ev of events) {
          if (ev.event_id) seenEventIdsRef.current.add(ev.event_id);
        }
        setHistory(events);
        setBuffer(events.slice(-MAX_BUFFER));
      } catch (err) {
        console.warn("[IA Monitor] No pude cargar histórico:", err);
        if (!cancelled && mountedRef.current) setHistory([]);
      } finally {
        if (!cancelled && mountedRef.current) setHistoryLoaded(true);
      }
    })();

    connect();

    return () => {
      cancelled = true;
      mountedRef.current = false;
      clearTimers();
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.close();
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { status, lastEvent, buffer, history, historyLoaded };
}
