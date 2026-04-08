/**
 * IAMonitor.jsx — Centro de Comando de IA (tiempo real).
 *
 * Muestra cada comparación del pipeline como un par de nodos que se
 * unen (verde) o repelen (rojo punteado) según la decisión de la capa.
 *
 * Dependencia:
 *   npm i react-force-graph-2d
 *
 * Backend WebSocket:
 *   /api/compras/ws/ia-monitor
 */
import React, { useEffect, useMemo, useRef, useState, useCallback } from "react";
import ForceGraph2D from "react-force-graph-2d";
import useIAMonitorSocket from "../hooks/useIAMonitorSocket";

const MAX_NODES = 400;        // Nodos visibles antes de "envejecer" los más antiguos
const MAX_LINKS = 600;
const LINK_TTL_MS = 1000 * 60 * 60 * 24; // 24h: el histórico no debe caducar visualmente

// Colores por capa — coherentes con la arquitectura neuro-simbólica
const LAYER_COLORS = {
  pre_ratio:        "#ff5252",
  capa_0_etim:      "#ff9800",
  capa_0_5_marca:   "#ff6b9d",
  capa_1_unit:      "#ffc107",
  capa_1_5_graph:   "#e91e63",
  capa_2_embedding: "#2196f3",
  capa_3_llm:       "#9c27b0",
  capa_4_jaccard:   "#607d8b",
  cache:            "#4caf50",
};

const LAYER_LABELS = {
  pre_ratio:        "Pre: Ratio",
  capa_0_etim:      "Capa 0: ETIM",
  capa_0_5_marca:   "Capa 0.5: Marca",
  capa_1_unit:      "Capa 1: Unidad",
  capa_1_5_graph:   "Capa 1.5: Grafo",
  capa_2_embedding: "Capa 2: Embedding",
  capa_3_llm:       "Capa 3: LLM",
  capa_4_jaccard:   "Capa 4: Jaccard",
  cache:            "Cache",
};

function truncate(s, n = 42) {
  if (!s) return "";
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

// Convierte el timestamp (epoch seconds del backend) a hora local legible.
function formatEventTime(ts) {
  if (ts == null) return "";
  const ms = ts > 1e12 ? ts : ts * 1000; // backend emite en segundos float
  const d = new Date(ms);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString(undefined, { hour12: false });
}

function formatEventDateTime(ts) {
  if (ts == null) return "";
  const ms = ts > 1e12 ? ts : ts * 1000;
  const d = new Date(ms);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString(undefined, { hour12: false });
}

function btnStyle(bg, disabled) {
  return {
    background: disabled ? "#2a3240" : bg,
    color: "#ffffff",
    border: "none",
    borderRadius: 4,
    padding: "7px 12px",
    fontSize: 12,
    fontWeight: 600,
    cursor: disabled ? "not-allowed" : "pointer",
    opacity: disabled ? 0.55 : 1,
    transition: "filter 120ms ease",
  };
}

export default function IAMonitor() {
  const { status, lastEvent, buffer, history, historyLoaded } = useIAMonitorSocket();
  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const [hoveredLink, setHoveredLink] = useState(null);
  const [actionMsg, setActionMsg] = useState(null); // feedback transitorio de los botones
  const [actionBusy, setActionBusy] = useState(false);
  const historySeededRef = useRef(false);
  const fgRef = useRef(null);

  // Helper para disparar acciones de control contra el backend y mostrar feedback.
  const runAction = useCallback(async (label, url, method = "POST") => {
    if (actionBusy) return;
    setActionBusy(true);
    setActionMsg({ kind: "info", text: `${label}…` });
    try {
      const resp = await fetch(url, { method });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      const msg = data.mensaje || data.status || JSON.stringify(data);
      setActionMsg({ kind: "ok", text: `${label}: ${msg}` });
    } catch (err) {
      setActionMsg({ kind: "err", text: `${label}: ${err.message || err}` });
    } finally {
      setActionBusy(false);
      setTimeout(() => setActionMsg(null), 6000);
    }
  }, [actionBusy]);

  const handleRunPipeline = useCallback(() => {
    runAction("Pipeline", "/api/compras/ia-monitor/run-pipeline?max_pares=60");
  }, [runAction]);

  const handleFireDebug = useCallback(() => {
    runAction("Debug fire", "/api/compras/ia-monitor/debug/fire?n=15");
  }, [runAction]);

  const handleClearHistory = useCallback(async () => {
    await runAction("Limpiar histórico", "/api/compras/ia-monitor/history/clear");
    // Reset visual inmediato del grafo (el buffer se va a re-sincronizar solo
    // con los próximos eventos, pero queremos feedback instantáneo).
    setGraphData({ nodes: [], links: [] });
    historySeededRef.current = false;
  }, [runAction]);

  // Contadores de telemetría agregada
  const telemetry = useMemo(() => {
    const acc = {
      total: 0, match: 0, reject: 0, tokens: 0, cost: 0, latencia: 0,
      firstTs: null, lastTs: null,
    };
    for (const ev of buffer) {
      acc.total += 1;
      if (ev.decision === "match") acc.match += 1;
      if (ev.decision === "reject") acc.reject += 1;
      acc.tokens += ev.tokens || 0;
      acc.cost += ev.costo_usd || 0;
      acc.latencia += ev.latencia_ms || 0;
      if (ev.timestamp != null) {
        if (acc.firstTs == null || ev.timestamp < acc.firstTs) acc.firstTs = ev.timestamp;
        if (acc.lastTs == null || ev.timestamp > acc.lastTs) acc.lastTs = ev.timestamp;
      }
    }
    acc.latenciaAvg = acc.total ? acc.latencia / acc.total : 0;
    return acc;
  }, [buffer]);

  // Dada una lista de eventos, produce un nuevo graphData mergeando con el previo.
  const mergeEventsIntoGraph = useCallback((prev, events) => {
    const nodesMap = new Map(prev.nodes.map((n) => [n.id, n]));
    const now = Date.now();

    const upsert = (p, seenAt) => {
      const key = `${p.proveedor || "NA"}:${p.sku || p.id}`;
      if (!nodesMap.has(key)) {
        nodesMap.set(key, {
          id: key,
          label: truncate(p.nombre, 32),
          marca: p.marca,
          proveedor: p.proveedor,
          fullName: p.nombre,
          lastSeen: seenAt,
        });
      } else {
        nodesMap.get(key).lastSeen = Math.max(nodesMap.get(key).lastSeen, seenAt);
      }
      return key;
    };

    const newLinks = [];
    for (const ev of events) {
      if (!ev || !ev.producto_a || !ev.producto_b) continue;
      // createdAt: preferir el timestamp del backend si existe
      const createdAt = ev.timestamp
        ? (ev.timestamp > 1e12 ? ev.timestamp : ev.timestamp * 1000)
        : now;
      const aId = upsert(ev.producto_a, createdAt);
      const bId = upsert(ev.producto_b, createdAt);
      newLinks.push({
        source: aId,
        target: bId,
        decision: ev.decision,
        layer: ev.layer,
        layerLabel: LAYER_LABELS[ev.layer] || ev.layer,
        color: LAYER_COLORS[ev.layer] || "#888",
        razon: ev.razon,
        confidence: ev.confidence,
        latencia_ms: ev.latencia_ms,
        tokens: ev.tokens,
        costo_usd: ev.costo_usd,
        timestamp: ev.timestamp,
        event_id: ev.event_id,
        createdAt,
      });
    }

    const nodes = Array.from(nodesMap.values())
      .filter((n) => now - n.lastSeen < LINK_TTL_MS * 3)
      .slice(-MAX_NODES);
    const nodeIds = new Set(nodes.map((n) => n.id));

    const links = [...prev.links, ...newLinks]
      .filter((l) => {
        const src = typeof l.source === "object" ? l.source.id : l.source;
        const tgt = typeof l.target === "object" ? l.target.id : l.target;
        return nodeIds.has(src) && nodeIds.has(tgt) &&
               (now - l.createdAt) < LINK_TTL_MS;
      })
      .slice(-MAX_LINKS);

    return { nodes, links };
  }, []);

  // Seed del grafo al cargar el histórico (solo una vez).
  useEffect(() => {
    if (!historyLoaded || historySeededRef.current) return;
    if (!history || history.length === 0) {
      historySeededRef.current = true;
      return;
    }
    setGraphData((prev) => mergeEventsIntoGraph(prev, history));
    historySeededRef.current = true;
  }, [history, historyLoaded, mergeEventsIntoGraph]);

  // Inserta cada nuevo evento live en el grafo.
  useEffect(() => {
    if (!lastEvent || !lastEvent.producto_a || !lastEvent.producto_b) return;
    setGraphData((prev) => mergeEventsIntoGraph(prev, [lastEvent]));
  }, [lastEvent, mergeEventsIntoGraph]);

  // Custom painter para nodos: círculo con etiqueta encima
  const paintNode = useCallback((node, ctx, globalScale) => {
    const label = node.label;
    const fontSize = 11 / globalScale;
    ctx.font = `${fontSize}px Inter, sans-serif`;

    // Círculo
    ctx.beginPath();
    ctx.arc(node.x, node.y, 6, 0, 2 * Math.PI);
    ctx.fillStyle = "#1e88e5";
    ctx.fill();
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 1.4 / globalScale;
    ctx.stroke();

    // Etiqueta
    ctx.fillStyle = "#eaeaea";
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    ctx.fillText(label, node.x, node.y + 8);
  }, []);

  // Custom painter para aristas: línea verde (match) o roja punteada (reject)
  const paintLink = useCallback((link, ctx, globalScale) => {
    const start = link.source;
    const end = link.target;
    if (!start || !end || typeof start !== "object") return;

    const isMatch = link.decision === "match";
    const isCacheHit = link.decision === "cache_hit";
    const isRejected = link.decision === "reject";

    ctx.save();
    ctx.lineWidth = (isMatch ? 2.6 : 1.8) / globalScale;

    if (isRejected) {
      ctx.strokeStyle = link.color || "#ff3b30";
      ctx.setLineDash([6 / globalScale, 4 / globalScale]);
    } else if (isMatch) {
      ctx.strokeStyle = "#00c853";
      ctx.setLineDash([]);
    } else if (isCacheHit) {
      ctx.strokeStyle = "#4caf50";
      ctx.setLineDash([2 / globalScale, 2 / globalScale]);
    } else {
      ctx.strokeStyle = "#888";
      ctx.setLineDash([]);
    }

    ctx.beginPath();
    ctx.moveTo(start.x, start.y);
    ctx.lineTo(end.x, end.y);
    ctx.stroke();
    ctx.restore();

    // Etiqueta de la capa en el punto medio
    const midX = (start.x + end.x) / 2;
    const midY = (start.y + end.y) / 2;
    const fontSize = 9 / globalScale;
    ctx.font = `${fontSize}px Inter, sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";

    const textWidth = ctx.measureText(link.layerLabel).width;
    ctx.fillStyle = "rgba(10, 14, 20, 0.8)";
    ctx.fillRect(
      midX - textWidth / 2 - 3,
      midY - fontSize / 2 - 2,
      textWidth + 6,
      fontSize + 4,
    );
    ctx.fillStyle = link.color || "#ffffff";
    ctx.fillText(link.layerLabel, midX, midY);
  }, []);

  const statusColor =
    status === "open" ? "#00c853" :
    status === "connecting" ? "#ffb300" :
    status === "error" ? "#ff3b30" : "#888";

  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "1fr 320px",
      gridTemplateRows: "60px 1fr",
      height: "100vh",
      background: "#0a0e14",
      color: "#eaeaea",
      fontFamily: "Inter, system-ui, sans-serif",
    }}>
      {/* Header */}
      <header style={{
        gridColumn: "1 / 3",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0 24px",
        borderBottom: "1px solid #1b2230",
        gap: 16,
      }}>
        <h1 style={{ fontSize: 18, margin: 0, whiteSpace: "nowrap" }}>
          🛰️ Centro IA
        </h1>

        {/* Controles de pruebas */}
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button
            onClick={handleRunPipeline}
            disabled={actionBusy}
            title="Ejecuta el pipeline neuro-simbólico sobre los productos ya scrapeados en la BD (no re-scrapea)"
            style={btnStyle("#1e88e5", actionBusy)}
          >
            ▶ Ejecutar Pipeline
          </button>
          <button
            onClick={handleFireDebug}
            disabled={actionBusy}
            title="Inyecta 15 eventos sintéticos para validar la visualización"
            style={btnStyle("#6a4fb5", actionBusy)}
          >
            ✨ Debug fire
          </button>
          <button
            onClick={handleClearHistory}
            disabled={actionBusy}
            title="Vacía el histórico in-memory y resetea el grafo"
            style={btnStyle("#455a64", actionBusy)}
          >
            🧹 Limpiar
          </button>
          {actionMsg && (
            <span style={{
              marginLeft: 8,
              fontSize: 12,
              padding: "4px 10px",
              borderRadius: 4,
              background:
                actionMsg.kind === "ok"  ? "rgba(0,200,83,0.15)"  :
                actionMsg.kind === "err" ? "rgba(255,59,48,0.18)" :
                                           "rgba(255,179,0,0.15)",
              color:
                actionMsg.kind === "ok"  ? "#69f0ae" :
                actionMsg.kind === "err" ? "#ff8a80" :
                                           "#ffd54f",
              maxWidth: 360,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}>
              {actionMsg.text}
            </span>
          )}
        </div>

        <div style={{ display: "flex", gap: 18, alignItems: "center", fontSize: 13 }}>
          <span>
            <span style={{
              display: "inline-block", width: 10, height: 10, borderRadius: 5,
              background: statusColor, marginRight: 8,
            }} />
            {status.toUpperCase()}
          </span>
          <span>Eventos: <b>{telemetry.total}</b></span>
          <span style={{ color: "#00c853" }}>Match: <b>{telemetry.match}</b></span>
          <span style={{ color: "#ff3b30" }}>Reject: <b>{telemetry.reject}</b></span>
          <span>⌀ Latencia: <b>{telemetry.latenciaAvg.toFixed(1)} ms</b></span>
          <span>Tokens: <b>{telemetry.tokens}</b></span>
          <span>Costo: <b>${telemetry.cost.toFixed(6)}</b></span>
          {telemetry.lastTs != null && (
            <span title={formatEventDateTime(telemetry.lastTs)}>
              Última: <b>{formatEventTime(telemetry.lastTs)}</b>
            </span>
          )}
        </div>
      </header>

      {/* Grafo principal */}
      <main style={{ position: "relative" }}>
        <ForceGraph2D
          ref={fgRef}
          graphData={graphData}
          backgroundColor="#0a0e14"
          nodeRelSize={6}
          nodeCanvasObject={paintNode}
          linkCanvasObject={paintLink}
          linkCanvasObjectMode={() => "replace"}
          linkDirectionalParticles={(l) => (l.decision === "match" ? 3 : 0)}
          linkDirectionalParticleSpeed={0.008}
          linkDirectionalParticleColor={() => "#00c853"}
          onLinkHover={setHoveredLink}
          cooldownTicks={80}
          d3VelocityDecay={0.35}
        />
        {hoveredLink && (
          <div style={{
            position: "absolute", top: 20, left: 20,
            background: "rgba(10, 14, 20, 0.94)",
            border: "1px solid #1b2230",
            padding: "12px 16px", borderRadius: 8, maxWidth: 420,
            fontSize: 12, lineHeight: 1.6,
          }}>
            <div style={{ color: hoveredLink.color, fontWeight: 600, marginBottom: 6 }}>
              {hoveredLink.layerLabel} — {hoveredLink.decision.toUpperCase()}
            </div>
            <div>{hoveredLink.razon}</div>
            <div style={{ marginTop: 6, color: "#888" }}>
              confidence={hoveredLink.confidence?.toFixed(3)} ·
              latencia={hoveredLink.latencia_ms?.toFixed(1)}ms ·
              tokens={hoveredLink.tokens} ·
              costo=${hoveredLink.costo_usd?.toFixed(6)}
            </div>
          </div>
        )}
      </main>

      {/* Sidebar: stream de eventos */}
      <aside style={{
        borderLeft: "1px solid #1b2230",
        overflowY: "auto",
        padding: "12px 14px",
      }}>
        <h3 style={{ fontSize: 13, margin: "6px 0 12px", color: "#888", textTransform: "uppercase" }}>
          Stream de decisiones
        </h3>
        {[...buffer].slice(-30).reverse().map((ev) => (
          <div key={ev.event_id} style={{
            borderLeft: `3px solid ${LAYER_COLORS[ev.layer] || "#888"}`,
            padding: "8px 10px",
            marginBottom: 8,
            background: "#0f1520",
            borderRadius: 4,
            fontSize: 11,
          }}>
            <div style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "baseline",
              color: LAYER_COLORS[ev.layer] || "#888",
              fontWeight: 600,
              marginBottom: 4,
            }}>
              <span>{LAYER_LABELS[ev.layer]} · {ev.decision}</span>
              <span
                style={{ color: "#666", fontWeight: 400, fontSize: 10 }}
                title={formatEventDateTime(ev.timestamp)}
              >
                {formatEventTime(ev.timestamp)}
              </span>
            </div>
            <div>{truncate(ev.producto_a?.nombre, 34)}</div>
            <div style={{ opacity: 0.6 }}>↔ {truncate(ev.producto_b?.nombre, 34)}</div>
            <div style={{ marginTop: 4, color: "#666" }}>
              {ev.latencia_ms?.toFixed(1)}ms · conf={ev.confidence?.toFixed(2)}
            </div>
          </div>
        ))}
      </aside>
    </div>
  );
}
