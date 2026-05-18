import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { Card, CardContent } from "./ui/card";
import { Input } from "./ui/input";
import {
  Loader2,
  Search as SearchIcon,
  X as XIcon,
  ExternalLink,
} from "lucide-react";
import { toast } from "sonner";
import { API_ENDPOINTS, apiFetch } from "../config/api";
import { useTheme } from "./ThemeProvider";

/**
 * KnowledgeGraph -- M5 Broadsheet Terminal monochrome rebuild.
 *
 * Test contracts preserved (verified via
 * `grep -nE "data-testid=" frontend/e2e/knowledge-graph.spec.ts`):
 *   - text "No entities extracted yet" (empty state fallback)
 *   - canvas first locator (the force-directed graph itself)
 *   - the four stat cards keep `data-slot="card"` (via the Card
 *     primitive) so the horizontal-overflow rubric assertion
 *     `[data-state="active"][role="tabpanel"] [data-slot="card"]`
 *     still binds to them.
 *
 * Internal data-testids preserved verbatim:
 *   kg-stat-companies / kg-stat-people / kg-stat-technologies /
 *   kg-stat-products
 *   kg-type-filter-companies / kg-type-filter-people /
 *   kg-type-filter-technologies / kg-type-filter-products
 *   kg-search-input, kg-empty-state, kg-trending-widget,
 *   kg-trending-entity-<id>, kg-entity-detail-panel,
 *   kg-entity-detail-close-btn, kg-entity-co-mention-<id>,
 *   kg-entity-article-<id>
 *
 * Per docs/designs/frontend-overhaul.md M5 (and section 11.4 user
 * decision):
 *   - Drop the four hardcoded type colors (#3b82f6 / #10b981 /
 *     #f59e0b / #a855f7). Node fill is `--foreground` lerped
 *     toward `--accent-signal` by `mentions / 50` clamped to 1.
 *   - Type is encoded by shape only:
 *       company   -> square
 *       person    -> circle
 *       technology -> triangle
 *       product   -> diamond
 *   - Stat cards show the count next to its shape glyph
 *     (square / circle / triangle / diamond) in `--foreground`.
 *   - Type filter chips: active = signal-wash + signal border;
 *     inactive = mono outline.
 *   - Detail / trending panels: hairline mono lists, type shown
 *     via shape glyph not color.
 */

type EntityType = "company" | "person" | "technology" | "product" | "other";

interface GraphNode {
  id: string;
  name: string;
  type: EntityType;
  connections: number;
  mention_count: number;
}

interface GraphEdge {
  source: string;
  target: string;
  weight: number;
}

interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  total_entities: number;
}

interface ApiNode {
  id: string;
  name: string;
  type: string;
  mention_count: number;
}

interface ApiEdge {
  source: string;
  target: string;
  weight: number;
}

interface ApiResponse {
  nodes: ApiNode[];
  edges: ApiEdge[];
  total_entities?: number;
}

interface CoMention {
  id: number;
  name: string;
  type: string;
  count: number;
}

interface EntityArticle {
  id: number;
  title: string;
  source: string;
  url: string;
  published_at: string | null;
}

interface EntityDetail {
  id: number;
  name: string;
  type: string;
  mention_count: number;
  first_mention_at: string | null;
  co_mentions: CoMention[];
  articles: EntityArticle[];
}

interface TrendingEntity {
  id: number;
  name: string;
  type: string;
  mention_count: number;
  score: number;
}

const NODE_LIMIT = 50;

const EMPTY_GRAPH: GraphData = { nodes: [], edges: [], total_entities: 0 };

const FILTERABLE_TYPES: { key: EntityType; label: string }[] = [
  { key: "company", label: "Companies" },
  { key: "person", label: "People" },
  { key: "technology", label: "Technologies" },
  { key: "product", label: "Products" },
];

// Shape glyph map -- used in stat cards, type filter chips,
// trending list, and the detail header. The monochrome palette
// means shape is the ONLY type encoding the user sees.
const SHAPE_GLYPH: Record<EntityType, string> = {
  company: "■",      // black square
  person: "●",       // black circle
  technology: "▲",   // black up-pointing triangle
  product: "◆",      // black diamond
  other: "○",        // white circle (fallback)
};

function normalizeType(t: string): EntityType {
  const lower = (t || "").toLowerCase();
  if (lower === "company" || lower === "person" || lower === "technology" || lower === "product") {
    return lower;
  }
  return "other";
}

function formatDate(value: string | null): string {
  if (!value) return "—";
  const dt = new Date(value.replace(" ", "T"));
  if (isNaN(dt.getTime())) return value;
  return dt.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

/**
 * Read the resolved CSS variable for a token like `--foreground`
 * and return it as a plain CSS color string. We re-read on every
 * theme switch so canvas paints reskin live.
 */
function readCssVar(name: string): string {
  if (typeof window === "undefined") return "";
  return getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
}

interface CanvasPalette {
  background: string;     // --background-tint (canvas fill)
  rule: string;           // --rule (edges + node borders)
  foreground: string;     // --foreground (ink end of the lerp)
  foregroundSoft: string; // --foreground-soft (labels, dimmed)
  signal: string;         // --accent-signal (saturation end)
}

function readPalette(): CanvasPalette {
  return {
    background: readCssVar("--background-tint") || "#f1efe7",
    rule: readCssVar("--rule") || "#cdcabf",
    foreground: readCssVar("--foreground") || "#1c1a16",
    foregroundSoft: readCssVar("--foreground-soft") || "#5a564f",
    signal: readCssVar("--accent-signal") || "#8a1f2a",
  };
}

/** Parse a CSS color into [r,g,b]. Handles #rgb, #rrggbb, and
 *  the oklch(...) and rgb(...) strings the design tokens emit.
 *  Returns black on failure so we never crash the canvas loop. */
function parseColor(c: string): [number, number, number] {
  if (!c) return [28, 26, 22];
  // Use a throwaway <canvas> via the browser's parser so we get
  // oklch / rgb / hex all in one shot.
  if (typeof document === "undefined") return [28, 26, 22];
  const probe = document.createElement("canvas");
  probe.width = 1;
  probe.height = 1;
  const ctx = probe.getContext("2d");
  if (!ctx) return [28, 26, 22];
  ctx.fillStyle = "#000";
  ctx.fillStyle = c;
  // After assignment, `ctx.fillStyle` is normalized to "#rrggbb"
  // or "rgba(r,g,b,a)" form depending on the source. We match
  // both. (Modern Chromium normalises oklch -> rgb.)
  const v = ctx.fillStyle as string;
  const hex = v.match(/^#([0-9a-f]{6})$/i);
  if (hex) {
    const n = parseInt(hex[1], 16);
    return [(n >> 16) & 0xff, (n >> 8) & 0xff, n & 0xff];
  }
  const rgb = v.match(/rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)/i);
  if (rgb) return [parseInt(rgb[1]), parseInt(rgb[2]), parseInt(rgb[3])];
  return [28, 26, 22];
}

/** Lerp `a` toward `b` by `t` (clamped to 0..1). */
function lerp(a: number, b: number, t: number): number {
  const k = Math.max(0, Math.min(1, t));
  return a + (b - a) * k;
}

/** Compose `rgba(...)` from rgb triple + alpha 0..1. */
function rgba(rgb: [number, number, number], a = 1): string {
  return `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${a})`;
}

interface KnowledgeGraphProps {
  // Endpoint-backed; no props.
}

export function KnowledgeGraph({}: KnowledgeGraphProps) {
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [zoom, setZoom] = useState(1);
  const { theme } = useTheme();
  const [palette, setPalette] = useState<CanvasPalette>(() => readPalette());
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const nodePositionsRef = useRef<Map<string, { x: number; y: number; vx: number; vy: number }>>(new Map());
  const animationFrameRef = useRef<number>();

  const [activeTypes, setActiveTypes] = useState<Set<EntityType>>(new Set());

  const [searchQuery, setSearchQuery] = useState("");
  const [focusedMatchIdx, setFocusedMatchIdx] = useState(-1);
  const [cameraOffset, setCameraOffset] = useState({ x: 0, y: 0 });
  const searchInputRef = useRef<HTMLInputElement>(null);

  const [detail, setDetail] = useState<EntityDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const reduceMotion = useReducedMotion();

  const [trending, setTrending] = useState<TrendingEntity[]>([]);

  useEffect(() => {
    fetchGraphData();
    fetchTrending();
  }, []);

  // Re-read palette on theme change AND on every observed
  // documentElement classList mutation. The theme provider
  // toggles `dark` on <html>; this MutationObserver guarantees
  // the canvas reskins live when M3 wires the keyboard shortcut
  // to flip the theme.
  useEffect(() => {
    setPalette(readPalette());
    if (typeof window === "undefined") return;
    const obs = new MutationObserver(() => setPalette(readPalette()));
    obs.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });
    return () => obs.disconnect();
  }, [theme]);

  const fetchGraphData = async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const url = `${API_ENDPOINTS.knowledgeGraph}?limit=${NODE_LIMIT}`;
      const data = await apiFetch<ApiResponse>(url);

      const nodes: GraphNode[] = (data.nodes || []).map((n) => ({
        id: n.id,
        name: n.name,
        type: normalizeType(n.type),
        connections: n.mention_count,
        mention_count: n.mention_count,
      }));
      const edges: GraphEdge[] = (data.edges || []).map((e) => ({
        source: e.source,
        target: e.target,
        weight: e.weight,
      }));
      const next: GraphData = {
        nodes,
        edges,
        total_entities: data.total_entities ?? nodes.length,
      };

      setGraphData(next);
      initializePositions(next);

      // Polish iter (design-review #6): suppress the empty-state toast on
      // mount. The inline `kg-empty-state` panel ("No entities indexed
      // yet") already conveys the same information without the floating
      // bottom-right overlay overlapping the trending sidebar. Toasts are
      // for state changes, not first-render conditions.
      if (nodes.length > 0) {
        toast.success(`Loaded ${nodes.length} entities`);
      }
    } catch (error) {
      console.error("Error fetching knowledge graph:", error);
      const message =
        error instanceof Error ? error.message : "Failed to load knowledge graph";
      setErrorMsg(message);
      setGraphData(EMPTY_GRAPH);
      initializePositions(EMPTY_GRAPH);
      toast.error("Failed to load knowledge graph");
    } finally {
      setLoading(false);
    }
  };

  const fetchTrending = async () => {
    try {
      const data = await apiFetch<{ entities: TrendingEntity[] }>(
        `${API_ENDPOINTS.knowledgeGraphTrending}?days=7&limit=5`
      );
      setTrending(data.entities || []);
    } catch (error) {
      console.error("Error fetching trending entities:", error);
      setTrending([]);
    }
  };

  const initializePositions = (data: GraphData) => {
    const positions = new Map();
    const centerX = 400;
    const centerY = 300;
    const radius = Math.min(220, 80 + data.nodes.length * 4);

    data.nodes.forEach((node, index) => {
      const angle = (index / Math.max(data.nodes.length, 1)) * 2 * Math.PI;
      positions.set(node.id, {
        x: centerX + radius * Math.cos(angle),
        y: centerY + radius * Math.sin(angle),
        vx: 0,
        vy: 0,
      });
    });

    nodePositionsRef.current = positions;
  };

  const matches = useMemo(() => {
    if (!graphData) return [] as GraphNode[];
    const q = searchQuery.trim().toLowerCase();
    if (!q) return [] as GraphNode[];
    return graphData.nodes.filter((n) =>
      n.name.toLowerCase().includes(q)
    );
  }, [graphData, searchQuery]);

  useEffect(() => {
    if (matches.length === 0) {
      setFocusedMatchIdx(-1);
    } else if (focusedMatchIdx >= matches.length) {
      setFocusedMatchIdx(0);
    } else if (focusedMatchIdx === -1) {
      setFocusedMatchIdx(0);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matches]);

  // -- Canvas draw loop ----------------------------------------------------
  useEffect(() => {
    if (!graphData || !canvasRef.current) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const matchSet = new Set(matches.map((m) => m.id));
    const focusedId =
      focusedMatchIdx >= 0 && matches[focusedMatchIdx]
        ? matches[focusedMatchIdx].id
        : null;
    const typeFilterActive = activeTypes.size > 0;

    // Resolve the two ends of the mention-saturation lerp once
    // per frame setup -- ink (low mention count) -> signal (high
    // mention count). Pre-parsing into rgb triples is cheaper
    // than re-parsing inside the per-node loop.
    const inkRGB = parseColor(palette.foreground);
    const signalRGB = parseColor(palette.signal);
    const ruleRGB = parseColor(palette.rule);
    const softRGB = parseColor(palette.foregroundSoft);

    /** Compute the monochrome fill for a node from its mention
     *  count alone. Saturation grows linearly to the signal end
     *  by mentions / 50, clamped. Type does NOT enter the
     *  formula -- that's the whole point of M5. */
    const inkForMentions = (n: number): [number, number, number] => {
      const t = Math.min(1, Math.max(0, n / 50));
      return [
        lerp(inkRGB[0], signalRGB[0], t),
        lerp(inkRGB[1], signalRGB[1], t),
        lerp(inkRGB[2], signalRGB[2], t),
      ];
    };

    /** Draw the type-encoded shape at (x, y) with radius r. */
    const drawShape = (
      type: EntityType,
      x: number,
      y: number,
      r: number,
    ) => {
      ctx.beginPath();
      switch (type) {
        case "company": {
          // Square -- side = 2*r so its bounding box matches the
          // circle's diameter for visual parity.
          const s = r;
          ctx.rect(x - s, y - s, s * 2, s * 2);
          break;
        }
        case "technology": {
          // Equilateral triangle, point up.
          ctx.moveTo(x, y - r);
          ctx.lineTo(x + r * 0.95, y + r * 0.7);
          ctx.lineTo(x - r * 0.95, y + r * 0.7);
          ctx.closePath();
          break;
        }
        case "product": {
          // Diamond (square rotated 45 degrees).
          ctx.moveTo(x, y - r * 1.1);
          ctx.lineTo(x + r * 1.1, y);
          ctx.lineTo(x, y + r * 1.1);
          ctx.lineTo(x - r * 1.1, y);
          ctx.closePath();
          break;
        }
        case "person":
        case "other":
        default: {
          // Circle.
          ctx.arc(x, y, r, 0, 2 * Math.PI);
          break;
        }
      }
    };

    const animate = () => {
      ctx.fillStyle = palette.background;
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.save();
      ctx.translate(canvas.width / 2, canvas.height / 2);
      ctx.scale(zoom, zoom);
      ctx.translate(-canvas.width / 2 + cameraOffset.x, -canvas.height / 2 + cameraOffset.y);

      const newPositions = new Map(nodePositionsRef.current);

      // Repulsion
      graphData.nodes.forEach((node1) => {
        const pos1 = newPositions.get(node1.id);
        if (!pos1) return;

        graphData.nodes.forEach((node2) => {
          if (node1.id === node2.id) return;
          const pos2 = newPositions.get(node2.id);
          if (!pos2) return;

          const dx = pos1.x - pos2.x;
          const dy = pos1.y - pos2.y;
          const distance = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = 1000 / (distance * distance);

          pos1.vx += (dx / distance) * force;
          pos1.vy += (dy / distance) * force;
        });
      });

      // Attraction along edges
      graphData.edges.forEach((edge) => {
        const pos1 = newPositions.get(edge.source);
        const pos2 = newPositions.get(edge.target);
        if (!pos1 || !pos2) return;

        const dx = pos2.x - pos1.x;
        const dy = pos2.y - pos1.y;
        const distance = Math.sqrt(dx * dx + dy * dy) || 1;
        const force = distance * 0.001 * Math.min(edge.weight || 1, 5);

        pos1.vx += (dx / distance) * force;
        pos1.vy += (dy / distance) * force;
        pos2.vx -= (dx / distance) * force;
        pos2.vy -= (dy / distance) * force;
      });

      newPositions.forEach((pos) => {
        pos.x += pos.vx;
        pos.y += pos.vy;
        pos.vx *= 0.8;
        pos.vy *= 0.8;

        pos.x = Math.max(50, Math.min(750, pos.x));
        pos.y = Math.max(50, Math.min(550, pos.y));
      });

      nodePositionsRef.current = newPositions;

      const isDimmed = (node: GraphNode): boolean => {
        if (typeFilterActive && !activeTypes.has(node.type)) return true;
        if (searchQuery.trim() && !matchSet.has(node.id)) return true;
        return false;
      };

      // Edges -- hairline rule color, slightly faded when one
      // endpoint is filtered out.
      graphData.edges.forEach((edge) => {
        const pos1 = newPositions.get(edge.source);
        const pos2 = newPositions.get(edge.target);
        if (!pos1 || !pos2) return;
        const n1 = graphData.nodes.find((n) => n.id === edge.source);
        const n2 = graphData.nodes.find((n) => n.id === edge.target);
        const edgeFilteredOut =
          (n1 && isDimmed(n1)) || (n2 && isDimmed(n2));

        const w = Math.max(1, Math.min(edge.weight || 1, 5));
        ctx.strokeStyle = rgba(ruleRGB, edgeFilteredOut ? 0.18 : 0.6);
        ctx.lineWidth = 0.8 + w * 0.4;
        ctx.beginPath();
        ctx.moveTo(pos1.x, pos1.y);
        ctx.lineTo(pos2.x, pos2.y);
        ctx.stroke();
      });

      // Nodes -- monochrome fill by mention count, shape by type.
      graphData.nodes.forEach((node) => {
        const pos = newPositions.get(node.id);
        if (!pos) return;

        const isActive = selectedNode?.id === node.id;
        const dimmed = isDimmed(node);
        const isFocused = focusedId === node.id;
        const isMatch = matchSet.has(node.id);

        const baseRadius = Math.max(12, Math.min(28, 12 + Math.sqrt(node.mention_count) * 3));
        const r = isFocused ? baseRadius + 4 : isMatch ? baseRadius + 2 : baseRadius;

        const fillRGB =
          isActive || isFocused
            ? signalRGB
            : inkForMentions(node.mention_count);
        ctx.globalAlpha = dimmed ? 0.25 : 1;
        ctx.fillStyle = rgba(fillRGB, 1);
        drawShape(node.type, pos.x, pos.y, r);
        ctx.fill();

        // Hairline border in the same color so the outline reads
        // as an ink contour rather than an SaaS-y outline. Active
        // / focused nodes get a 2px signal border.
        ctx.lineWidth = isActive || isFocused ? 2 : 1;
        ctx.strokeStyle =
          isActive || isFocused ? rgba(signalRGB, 1) : rgba(ruleRGB, 0.9);
        ctx.stroke();
        ctx.globalAlpha = 1;

        // Label -- mono-weight by default, bold when this node
        // is a match. Color uses the soft foreground so the
        // ink-saturation lerp stays the readable signal.
        ctx.fillStyle = dimmed ? rgba(softRGB, 0.6) : rgba(softRGB, 1);
        ctx.font = isMatch
          ? "bold 12px 'JetBrains Mono', ui-monospace, monospace"
          : "12px 'JetBrains Mono', ui-monospace, monospace";
        ctx.textAlign = "center";
        ctx.fillText(node.name, pos.x, pos.y + r + 14);
      });

      ctx.restore();
      animationFrameRef.current = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      if (animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current);
    };
  }, [graphData, zoom, selectedNode, palette, matches, focusedMatchIdx, activeTypes, searchQuery, cameraOffset]);

  const openDetail = useCallback(async (entityId: string | number) => {
    setDetailOpen(true);
    setDetailLoading(true);
    try {
      const data = await apiFetch<EntityDetail>(
        API_ENDPOINTS.knowledgeGraphEntity(entityId)
      );
      setDetail(data);
    } catch (err) {
      console.error("Failed to load entity detail", err);
      toast.error("Failed to load entity detail");
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const closeDetail = useCallback(() => {
    setDetailOpen(false);
  }, []);

  const handleSearchKey = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (matches.length === 0) {
        if (e.key === "Escape") {
          setSearchQuery("");
        }
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setFocusedMatchIdx((idx) =>
          idx + 1 >= matches.length ? 0 : idx + 1
        );
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setFocusedMatchIdx((idx) =>
          idx <= 0 ? matches.length - 1 : idx - 1
        );
      } else if (e.key === "Enter") {
        e.preventDefault();
        const m = matches[focusedMatchIdx >= 0 ? focusedMatchIdx : 0];
        if (m) {
          const pos = nodePositionsRef.current.get(m.id);
          if (pos) {
            setCameraOffset({ x: 400 - pos.x, y: 300 - pos.y });
          }
          setSelectedNode(m);
        }
      } else if (e.key === "Escape") {
        e.preventDefault();
        setSearchQuery("");
        setFocusedMatchIdx(-1);
        setCameraOffset({ x: 0, y: 0 });
      }
    },
    [matches, focusedMatchIdx]
  );

  const handleCanvasClick = (event: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas || !graphData) return;

    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const cx = (event.clientX - rect.left) * scaleX;
    const cy = (event.clientY - rect.top) * scaleY;
    const x =
      (cx - canvas.width / 2) / zoom + canvas.width / 2 - cameraOffset.x;
    const y =
      (cy - canvas.height / 2) / zoom + canvas.height / 2 - cameraOffset.y;

    for (const node of graphData.nodes) {
      const pos = nodePositionsRef.current.get(node.id);
      if (!pos) continue;

      const r = Math.max(12, Math.min(28, 12 + Math.sqrt(node.mention_count) * 3));
      const distance = Math.sqrt((x - pos.x) ** 2 + (y - pos.y) ** 2);
      if (distance < r + 4) {
        setSelectedNode(node);
        openDetail(node.id);
        return;
      }
    }

    setSelectedNode(null);
  };

  const handleCanvasWheel = (event: React.WheelEvent<HTMLCanvasElement>) => {
    if (!event.ctrlKey && !event.metaKey) return;
    event.preventDefault();
    const delta = event.deltaY > 0 ? -0.1 : 0.1;
    setZoom((z) => Math.max(0.4, Math.min(3, z + delta)));
  };

  const toggleType = (t: EntityType) => {
    setActiveTypes((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });
  };

  if (loading) {
    return (
      <div className="rule-h-thick pt-6 flex items-center justify-center py-12">
        <Loader2 className="w-6 h-6 animate-spin text-foreground-soft" />
      </div>
    );
  }

  const isEmpty = !graphData || graphData.nodes.length === 0;

  const companyCount = graphData
    ? graphData.nodes.filter((n) => n.type === "company").length
    : 0;
  const personCount = graphData
    ? graphData.nodes.filter((n) => n.type === "person").length
    : 0;
  const techCount = graphData
    ? graphData.nodes.filter((n) => n.type === "technology").length
    : 0;
  const productCount = graphData
    ? graphData.nodes.filter((n) => n.type === "product").length
    : 0;

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* === ENTITY CENSUS section ============================== */}
      {graphData && (
        <section className="space-y-3">
          <div className="flex items-center gap-3">
            <span className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
              ━ ENTITY CENSUS
            </span>
            <span className="flex-1 border-t border-[var(--rule)]" />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Card
              data-testid="kg-stat-companies"
              className="bg-card border border-[var(--rule)] rounded-none"
            >
              <CardContent className="p-4 space-y-1.5">
                <div className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
                  Companies
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="text-2xl font-display font-medium text-foreground tabular-nums">
                    {companyCount}
                  </span>
                  <span className="font-mono-tx text-[13px] text-foreground-soft">
                    {SHAPE_GLYPH.company}
                  </span>
                </div>
              </CardContent>
            </Card>
            <Card
              data-testid="kg-stat-people"
              className="bg-card border border-[var(--rule)] rounded-none"
            >
              <CardContent className="p-4 space-y-1.5">
                <div className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
                  People
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="text-2xl font-display font-medium text-foreground tabular-nums">
                    {personCount}
                  </span>
                  <span className="font-mono-tx text-[13px] text-foreground-soft">
                    {SHAPE_GLYPH.person}
                  </span>
                </div>
              </CardContent>
            </Card>
            <Card
              data-testid="kg-stat-technologies"
              className="bg-card border border-[var(--rule)] rounded-none"
            >
              <CardContent className="p-4 space-y-1.5">
                <div className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
                  Technologies
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="text-2xl font-display font-medium text-foreground tabular-nums">
                    {techCount}
                  </span>
                  <span className="font-mono-tx text-[13px] text-foreground-soft">
                    {SHAPE_GLYPH.technology}
                  </span>
                </div>
              </CardContent>
            </Card>
            <Card
              data-testid="kg-stat-products"
              className="bg-card border border-[var(--rule)] rounded-none"
            >
              <CardContent className="p-4 space-y-1.5">
                <div className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
                  Products
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="text-2xl font-display font-medium text-foreground tabular-nums">
                    {productCount}
                  </span>
                  <span className="font-mono-tx text-[13px] text-foreground-soft">
                    {SHAPE_GLYPH.product}
                  </span>
                </div>
              </CardContent>
            </Card>
          </div>
        </section>
      )}

      {/* === GRAPH + TRENDING grid ============================== */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        <section className="lg:col-span-3 space-y-3">
          <div className="flex items-center gap-3">
            <span className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
              ━ KNOWLEDGE GRAPH
            </span>
            <span className="flex-1 border-t border-[var(--rule)]" />
          </div>
          <p className="text-[13px] text-foreground-soft leading-relaxed">
            Entities and co-mentions extracted from this week's articles.
            Node saturation scales with mention count; shape encodes type
            (■ company · ● person · ▲ tech · ◆ product).
          </p>

          {/* Type filter chips -- mono outline default, signal
              wash + signal border when active. */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft pr-1">
              Filter
            </span>
            {FILTERABLE_TYPES.map(({ key, label }) => {
              const isOn = activeTypes.has(key);
              return (
                <button
                  key={key}
                  type="button"
                  data-testid={`kg-type-filter-${label.toLowerCase()}`}
                  onClick={() => toggleType(key)}
                  className={[
                    "inline-flex items-center gap-1.5 border px-3 py-1 font-mono-tx text-[11px] uppercase-eyebrow transition-colors",
                    isOn
                      ? "bg-signal-wash text-signal border-[var(--accent-signal)]"
                      : "bg-card text-foreground border-[var(--rule)] hover:border-[var(--accent-signal)]",
                  ].join(" ")}
                >
                  <span className="font-mono-tx">{SHAPE_GLYPH[key]}</span>
                  <span>{label}</span>
                </button>
              );
            })}
            {activeTypes.size > 0 && (
              <button
                type="button"
                onClick={() => setActiveTypes(new Set())}
                className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft hover:text-signal pl-1"
              >
                [ clear ]
              </button>
            )}
          </div>

          {/* Search input -- hairline bottom border, mono caret */}
          <div className="relative max-w-md">
            <SearchIcon className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-foreground-soft pointer-events-none" />
            <Input
              ref={searchInputRef}
              data-testid="kg-search-input"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={handleSearchKey}
              placeholder="search entities... (↑/↓ cycle, ⏎ centre, esc clear)"
              className="h-8 pl-7 pr-16 text-[12px] font-mono-tx rounded-none border-[var(--rule)]"
            />
            {searchQuery && (
              <button
                type="button"
                aria-label="Clear search"
                onClick={() => {
                  setSearchQuery("");
                  setFocusedMatchIdx(-1);
                  setCameraOffset({ x: 0, y: 0 });
                  searchInputRef.current?.focus();
                }}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-foreground-soft hover:text-signal"
              >
                <XIcon className="w-3.5 h-3.5" />
              </button>
            )}
            {searchQuery && (
              <div className="absolute right-7 top-1/2 -translate-y-1/2 font-mono-tx text-[10px] text-foreground-soft tabular-nums pointer-events-none">
                {matches.length === 0
                  ? "no match"
                  : `${focusedMatchIdx + 1}/${matches.length}`}
              </div>
            )}
          </div>

          {errorMsg && (
            <div className="border border-[var(--rule)] bg-[var(--background-tint)] p-3 font-mono-tx text-[11px] text-foreground">
              ━ ERROR — couldn't reach the knowledge graph endpoint: {errorMsg}
            </div>
          )}

          {isEmpty && !errorMsg && (
            <div
              data-testid="kg-empty-state"
              className="border border-[var(--rule)] bg-[var(--background-tint)] p-8 text-center space-y-2"
            >
              <p className="font-display text-[18px] font-medium text-foreground">
                No entities indexed yet
              </p>
              <p className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
                No entities extracted yet. Run an ingest + summarize cycle
                to populate the graph.
              </p>
            </div>
          )}

          {/* Canvas chrome -- hairline border, no rounded
              corners, mono zoom controls. */}
          <div className="relative border border-[var(--rule)] bg-[var(--background-tint)] overflow-hidden">
            <canvas
              ref={canvasRef}
              width={800}
              height={600}
              className="w-full cursor-pointer"
              onClick={handleCanvasClick}
              onWheel={handleCanvasWheel}
            />

            <div className="absolute top-3 right-3 flex flex-col gap-1">
              <button
                type="button"
                onClick={() => setZoom(Math.min(zoom + 0.2, 3))}
                aria-label="Zoom in"
                className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground bg-card border border-[var(--rule)] px-2 py-1 hover:border-[var(--accent-signal)] hover:text-signal"
              >
                [ + ]
              </button>
              <button
                type="button"
                onClick={() => setZoom(Math.max(zoom - 0.2, 0.4))}
                aria-label="Zoom out"
                className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground bg-card border border-[var(--rule)] px-2 py-1 hover:border-[var(--accent-signal)] hover:text-signal"
              >
                [ − ]
              </button>
              <button
                type="button"
                onClick={() => {
                  setZoom(1);
                  setCameraOffset({ x: 0, y: 0 });
                }}
                aria-label="Reset zoom"
                className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground bg-card border border-[var(--rule)] px-2 py-1 hover:border-[var(--accent-signal)] hover:text-signal"
              >
                [ ⛶ ]
              </button>
            </div>
          </div>
        </section>

        {/* === TRENDING THIS WEEK sidebar ===================== */}
        <section
          data-testid="kg-trending-widget"
          className="lg:col-span-1 space-y-3"
        >
          <div className="flex items-center gap-3">
            <span className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
              ━ TRENDING
            </span>
            <span className="flex-1 border-t border-[var(--rule)]" />
          </div>
          <p className="font-mono-tx text-[11px] text-foreground-soft">
            top mentions, recency-weighted
          </p>

          {trending.length === 0 ? (
            <p className="font-mono-tx text-[11px] text-foreground-soft py-2">
              no trends in window yet.
            </p>
          ) : (
            <ol className="border-t border-[var(--rule)]">
              {trending.map((t, idx) => {
                const tType = normalizeType(t.type);
                return (
                  <li
                    key={t.id}
                    className="border-b border-[var(--rule)]"
                  >
                    <button
                      type="button"
                      data-testid={`kg-trending-entity-${t.id}`}
                      onClick={() => openDetail(t.id)}
                      className="w-full flex items-center gap-2 py-2 hover:bg-[var(--background-tint)] transition-colors text-left"
                    >
                      <span className="font-mono-tx text-[11px] text-foreground-soft tabular-nums w-6 pl-1">
                        {String(idx + 1).padStart(2, "0")}
                      </span>
                      <span className="font-mono-tx text-[12px] text-foreground-soft w-4 shrink-0">
                        {SHAPE_GLYPH[tType]}
                      </span>
                      <span className="flex-1 text-[13px] text-foreground truncate">
                        {t.name}
                      </span>
                      <span className="font-mono-tx text-[11px] text-signal tabular-nums pr-2">
                        {t.mention_count}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ol>
          )}
        </section>
      </div>

      {/* === ENTITY DETAIL drawer ============================== */}
      <AnimatePresence>
        {detailOpen && (
          <>
            <motion.div
              key="kg-detail-scrim"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: reduceMotion ? 0 : 0.15 }}
              className="fixed inset-0 z-40"
              style={{ backgroundColor: "rgba(0,0,0,0.35)" }}
              onClick={closeDetail}
            />
            <motion.aside
              key="kg-detail-drawer"
              data-testid="kg-entity-detail-panel"
              initial={reduceMotion ? { x: 0 } : { x: "100%" }}
              animate={{ x: 0 }}
              exit={reduceMotion ? { x: 0 } : { x: "100%" }}
              transition={{ duration: reduceMotion ? 0 : 0.22, ease: "easeOut" }}
              className="fixed right-0 top-0 bottom-0 z-50 kg-drawer-width bg-card border-l border-[var(--rule)] shadow-xl flex flex-col"
              role="dialog"
              aria-label="Entity detail"
            >
              <div className="flex items-start justify-between gap-3 px-4 py-4 border-b border-[var(--rule)]">
                <div className="flex-1 min-w-0 space-y-1.5">
                  {detailLoading ? (
                    <Loader2 className="w-4 h-4 animate-spin text-foreground-soft" />
                  ) : detail ? (
                    <>
                      <h2 className="font-display text-[22px] font-medium text-foreground flex items-center gap-2 truncate">
                        <span className="font-mono-tx text-[16px] text-foreground-soft shrink-0">
                          {SHAPE_GLYPH[normalizeType(detail.type)]}
                        </span>
                        <span className="truncate">{detail.name}</span>
                      </h2>
                      <div className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
                        {detail.type} · {detail.mention_count} mention
                        {detail.mention_count === 1 ? "" : "s"}
                      </div>
                    </>
                  ) : (
                    <p className="font-mono-tx text-[11px] text-foreground-soft">
                      Failed to load entity.
                    </p>
                  )}
                </div>
                <button
                  type="button"
                  data-testid="kg-entity-detail-close-btn"
                  onClick={closeDetail}
                  aria-label="Close detail panel"
                  className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft hover:text-signal transition-colors"
                >
                  [ × ]
                </button>
              </div>

              <div className="flex-1 overflow-y-auto px-4 py-4 space-y-5">
                {detailLoading && (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="w-6 h-6 animate-spin text-foreground-soft" />
                  </div>
                )}
                {!detailLoading && detail && (
                  <>
                    <div className="space-y-1">
                      <div className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
                        First mention
                      </div>
                      <div className="font-mono-tx text-[12px] text-foreground">
                        {formatDate(detail.first_mention_at)}
                      </div>
                    </div>

                    <div className="space-y-2">
                      <div className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
                        Top co-mentions
                      </div>
                      {detail.co_mentions.length === 0 ? (
                        <p className="font-mono-tx text-[11px] text-foreground-soft">
                          No other entities co-mentioned in the same articles.
                        </p>
                      ) : (
                        <div className="flex flex-wrap gap-1.5">
                          {detail.co_mentions.map((c) => {
                            const cType = normalizeType(c.type);
                            return (
                              <button
                                key={c.id}
                                type="button"
                                data-testid={`kg-entity-co-mention-${c.id}`}
                                onClick={() => openDetail(c.id)}
                                className="inline-flex items-center gap-1.5 border border-[var(--rule)] bg-card px-2 py-1 font-mono-tx text-[11px] text-foreground hover:border-[var(--accent-signal)] hover:text-signal transition-colors"
                              >
                                <span className="text-foreground-soft">
                                  {SHAPE_GLYPH[cType]}
                                </span>
                                <span>{c.name}</span>
                                <span className="text-foreground-soft tabular-nums">
                                  ×{c.count}
                                </span>
                              </button>
                            );
                          })}
                        </div>
                      )}
                    </div>

                    <div className="space-y-3">
                      <div className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
                        Mentioned in
                      </div>
                      {detail.articles.length === 0 ? (
                        <p className="font-mono-tx text-[11px] text-foreground-soft">
                          No articles found.
                        </p>
                      ) : (
                        <ul className="space-y-3">
                          {detail.articles.map((a) => (
                            <li
                              key={a.id}
                              className="border-t border-[var(--rule)] pt-3"
                            >
                              <a
                                data-testid={`kg-entity-article-${a.id}`}
                                href={a.url || "#"}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="block group space-y-1"
                              >
                                <div className="font-display text-[16px] text-foreground group-hover:text-signal group-hover:underline leading-snug flex items-start gap-1">
                                  <span className="flex-1">{a.title}</span>
                                  <ExternalLink className="w-3 h-3 text-foreground-soft shrink-0 mt-0.5" />
                                </div>
                                <div className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
                                  {a.source} · {formatDate(a.published_at)}
                                </div>
                              </a>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  </>
                )}
              </div>
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
