<template>
  <div class="admin-kg" :class="{ dark: isDark }">
    <!-- 顶栏 -->
    <header class="kg-header">
      <div class="kg-header-left">
        <h1 class="page-title">KG 全景图</h1>
        <span v-if="stats" class="page-subtitle">
          {{ stats.concept_count }} 个概念 · {{ stats.edge_count }} 条关系
        </span>
      </div>
      <div class="kg-header-right">
        <div class="search-bar" :class="{ focused: searchFocused }">
          <svg
            width="13"
            height="13"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            v-model="searchTerm"
            placeholder="搜索概念名 / cid..."
            @focus="searchFocused = true"
            @blur="searchFocused = false"
            @keydown.enter="searchAndSelect"
          />
        </div>
        <select v-model="subjectFilter" class="sort-select" @change="reload">
          <option value="">全部学科</option>
          <option v-for="s in allSubjects" :key="s" :value="s">{{ s }}</option>
        </select>
        <label class="checkbox-pill" :class="{ active: includePending }">
          <input v-model="includePending" type="checkbox" @change="reload" />
          含 pending
        </label>
        <div class="graph-controls">
          <button class="ctrl-btn" title="重置视图" @click="resetView">
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path d="M3 12a9 9 0 109-9 9.75 9.75 0 00-6.74 2.74L3 8" />
              <path d="M3 3v5h5" />
            </svg>
          </button>
          <button class="ctrl-btn" title="刷新数据" @click="reload">
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path d="M21 12a9 9 0 01-9 9c-2.52 0-4.93-1-6.74-2.74L3 16" />
              <path d="M21 21v-5h-5" />
            </svg>
          </button>
          <span class="zoom-val">{{ Math.round(zoom * 100) }}%</span>
        </div>
      </div>
    </header>

    <!-- 主体区 -->
    <div class="kg-body">
      <!-- 加载中 -->
      <div v-if="loading" class="kg-loading">
        <div class="kg-spinner" />
        <span>加载知识图谱...</span>
      </div>

      <!-- 空状态 -->
      <div v-else-if="nodes.length === 0" class="kg-empty">
        <div class="ke-icon">🕸️</div>
        <div class="ke-title">暂无概念节点</div>
        <div class="ke-desc">导入 markdown 后，节点会自动出现在这里</div>
      </div>

      <!-- 图谱画布 -->
      <div
        v-else
        ref="canvasWrap"
        class="graph-canvas-wrap"
        @mousedown="onSvgMousedown"
        @mousemove="onSvgMousemove"
        @mouseup="onSvgMouseup"
        @mouseleave="onSvgMouseup"
        @wheel.prevent="onWheel"
      >
        <svg class="graph-svg" :viewBox="`0 0 ${svgW} ${svgH}`">
          <defs>
            <radialGradient id="kg-node-glow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stop-color="#6366f1" stop-opacity="0.3" />
              <stop offset="100%" stop-color="#6366f1" stop-opacity="0" />
            </radialGradient>
            <marker
              id="kg-arrow"
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="5"
              markerHeight="5"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor" />
            </marker>
          </defs>

          <g :transform="`translate(${pan.x},${pan.y}) scale(${zoom})`">
            <!-- 边层 -->
            <g class="edges-layer">
              <line
                v-for="edge in displayedEdges"
                :key="edge.id"
                :x1="getNode(edge.src)?.x"
                :y1="getNode(edge.src)?.y"
                :x2="getNode(edge.dst)?.x"
                :y2="getNode(edge.dst)?.y"
                :stroke="relationColors[edge.relation] || '#888'"
                :stroke-width="
                  selectedNode && isOnEdge(edge, selectedNode.id) ? 2 : 1
                "
                :stroke-dasharray="edge.relation === 'related' ? '4,3' : 'none'"
                :opacity="
                  selectedNode
                    ? isOnEdge(edge, selectedNode.id)
                      ? 0.78
                      : 0.06
                    : 0.22
                "
              />
            </g>

            <!-- 节点层 -->
            <g
              v-for="node in nodes"
              :key="node.id"
              :transform="`translate(${node.x},${node.y})`"
              class="node-group"
              :class="{
                selected: selectedNode?.id === node.id,
                dimmed: selectedNode && !isNeighbor(node.id, selectedNode.id),
              }"
              @mousedown.stop="onNodeMousedown($event, node)"
              @click.stop="selectNode(node)"
            >
              <!-- 选中光环 -->
              <circle
                v-if="selectedNode?.id === node.id"
                :r="getNodeRadius(node) + 12"
                :fill="getNodeColor(node)"
                opacity="0.12"
              />
              <!-- 度数指示外环（背景灰）-->
              <circle
                :r="getNodeRadius(node) + 4"
                fill="none"
                stroke="var(--bg-hover, #f1f5f9)"
                stroke-width="3"
              />
              <!-- 度数指示外环（前景：facet/度数饱和度）-->
              <circle
                :r="getNodeRadius(node) + 4"
                fill="none"
                :stroke="getDegreeColor(node)"
                stroke-width="3"
                stroke-linecap="round"
                :stroke-dasharray="`${getDegreeArc(node)} 999`"
                transform="rotate(-90)"
                opacity="0.85"
              />
              <!-- 节点本体 -->
              <circle
                :r="getNodeRadius(node)"
                :fill="getNodeBg(node)"
                :stroke="getNodeColor(node)"
                stroke-width="1.5"
                opacity="0.95"
              />
              <!-- pending 状态：右上角小红点 -->
              <circle
                v-if="node.status === 'pending'"
                :cx="getNodeRadius(node) * 0.7"
                :cy="-getNodeRadius(node) * 0.7"
                r="3.5"
                fill="#ef4444"
                stroke="#fff"
                stroke-width="1"
              />
              <!-- 中心：学科首字符 -->
              <text
                text-anchor="middle"
                dominant-baseline="central"
                :font-size="getNodeRadius(node) * 0.85"
                :fill="getNodeColor(node)"
                font-weight="700"
                style="user-select: none; pointer-events: none"
              >
                {{ getNodeIcon(node) }}
              </text>
              <!-- 标签 -->
              <text
                text-anchor="middle"
                :y="getNodeRadius(node) + 16"
                font-size="11"
                fill="var(--text-secondary, #64748b)"
                style="user-select: none; pointer-events: none"
                :font-weight="selectedNode?.id === node.id ? '600' : '400'"
              >
                {{ truncate(node.title, 12) }}
              </text>
            </g>
          </g>
        </svg>

        <!-- 图例（左下） -->
        <div class="legend">
          <div class="legend-title">关系类型</div>
          <div
            v-for="(color, rel) in relationColors"
            :key="rel"
            class="legend-item"
          >
            <span class="legend-line" :style="{ background: color }"></span>
            <span>{{ rel }}</span>
          </div>
        </div>
      </div>

      <!-- 详情侧栏 -->
      <transition name="slide">
        <aside v-if="selectedDetail" class="detail-panel">
          <header class="detail-head">
            <div>
              <div class="detail-title">{{ selectedDetail.title }}</div>
              <div class="detail-meta">
                <span class="badge subject-badge">
                  {{ selectedDetail.subject || "—" }}
                </span>
                <span class="badge">{{ selectedDetail.status }}</span>
                <span v-if="selectedDetail.is_canonical" class="badge"
                  >canonical</span
                >
              </div>
              <div class="detail-cid">{{ selectedDetail.cid }}</div>
            </div>
            <button class="ctrl-btn" @click="closeDetail">
              <svg
                width="13"
                height="13"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </header>

          <div v-if="selectedDetail.summary" class="section">
            <div class="section-title">概述</div>
            <div
              class="section-body md-body"
              v-html="renderMd(selectedDetail.summary)"
            ></div>
          </div>

          <div v-if="selectedDetail.aliases?.length" class="section">
            <div class="section-title">别名</div>
            <div class="section-body">
              <span
                v-for="a in selectedDetail.aliases"
                :key="a"
                class="alias-pill"
              >
                {{ a }}
              </span>
            </div>
          </div>

          <div v-if="selectedDetail.facets?.length" class="section">
            <div class="section-title">
              Facets ({{ selectedDetail.facets.length }})
            </div>
            <div class="section-body">
              <div
                v-for="(f, idx) in selectedDetail.facets"
                :key="f.id || idx"
                class="facet-card"
              >
                <div class="facet-head">
                  <span class="facet-kind">{{ f.kind }}</span>
                  <span class="facet-origin">{{ f.origin }}</span>
                </div>
                <div
                  class="facet-content md-body"
                  v-html="renderMd(f.content)"
                ></div>
              </div>
            </div>
          </div>

          <div v-if="selectedDetail.neighbors?.length" class="section">
            <div class="section-title">
              邻居 ({{ selectedDetail.neighbors.length }})
            </div>
            <div class="section-body">
              <div
                v-for="(n, idx) in selectedDetail.neighbors"
                :key="(n.edge_id || '') + '-' + idx"
                class="neighbor-row"
                @click="selectByPeer(n.peer_id)"
              >
                <span class="dir" :class="`dir-${n.direction}`">
                  {{ n.direction === "out" ? "→" : "←" }}
                </span>
                <span
                  class="rel-pill"
                  :style="{ color: relationColors[n.relation] || '#888' }"
                >
                  {{ n.relation }}
                </span>
                <span class="peer-name">{{ n.peer_name || n.peer_id }}</span>
              </div>
            </div>
          </div>
        </aside>
      </transition>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed, nextTick } from "vue";
import { adminApi } from "@/api/admin";
import { useTheme } from "@/composables/useTheme";
import { renderMd } from "@/composables/useMarkdown";

const { isDark } = useTheme();

// ── 状态 ────────────────────────────────────────────
const canvasWrap = ref(null);
const svgW = ref(1200);
const svgH = ref(800);
const zoom = ref(1);
const pan = ref({ x: 0, y: 0 });

const loading = ref(false);
const nodes = ref([]); // 已含 x/y 坐标
const edges = ref([]);
const stats = ref(null);

const subjectFilter = ref("");
const includePending = ref(false);
const searchTerm = ref("");
const searchFocused = ref(false);

const selectedNode = ref(null);
const selectedDetail = ref(null);

// ── 颜色映射 ─────────────────────────────────────────

// 关系类型 → 颜色
const relationColors = {
  prerequisite: "#6366f1",
  part_of: "#10b981",
  related: "#94a3b8",
  contrasts: "#ef4444",
  application_of: "#a855f7",
  special_case_of: "#3b82f6",
  generalizes: "#14b8a6",
  equivalent_to: "#f97316",
};

// 学科 → 颜色（与知识大脑配色一致）
const SUBJECT_COLORS = {
  算法: "#6366f1",
  数据结构: "#10b981",
  AI: "#a855f7",
  数学: "#f59e0b",
  英语: "#3b82f6",
  math: "#f59e0b",
  cs: "#6366f1",
  ai: "#a855f7",
  english: "#3b82f6",
};
const DEFAULT_COLORS = [
  "#6366f1",
  "#10b981",
  "#a855f7",
  "#f59e0b",
  "#3b82f6",
  "#ef4444",
  "#14b8a6",
  "#f97316",
];
const colorCache = {};
function getSubjectColor(subj) {
  if (!subj) return "#94a3b8";
  if (!colorCache[subj]) {
    const idx = Object.keys(colorCache).length % DEFAULT_COLORS.length;
    colorCache[subj] = SUBJECT_COLORS[subj] || DEFAULT_COLORS[idx];
  }
  return colorCache[subj];
}
function getNodeColor(node) {
  return getSubjectColor(node.subject);
}
function getNodeBg(node) {
  return getNodeColor(node) + "20";
}
function getNodeRadius(node) {
  // 基础 16，按 facet 数 + 度数加成（最大 32）
  const w =
    (node.facet_count || 0) * 0.8 +
    Math.log2(1 + (node.in_degree + node.out_degree)) * 1.6;
  return Math.min(32, 16 + w);
}
// 度数环：度数越多颜色越饱和 + 弧长越长
function getDegreeColor(node) {
  const deg = node.in_degree + node.out_degree;
  if (deg >= 6) return "#10b981";
  if (deg >= 3) return "#f59e0b";
  if (deg >= 1) return "#94a3b8";
  return "#cbd5e1";
}
function getDegreeArc(node) {
  const deg = node.in_degree + node.out_degree;
  // 0~6+ 度数 → 0~100% 弧长
  const pct = Math.min(1, deg / 6);
  const r = getNodeRadius(node) + 4;
  return (pct * 2 * Math.PI * r).toFixed(1);
}
function getNodeIcon(node) {
  // 学科首字母（中文取首字，英文取大写首字母）
  const s = node.subject || "?";
  return s.charAt(0).toUpperCase();
}
function truncate(s, n) {
  s = String(s || "");
  if (s.length <= n) return s;
  return s.slice(0, n) + "…";
}

// ── 辅助 ─────────────────────────────────────────────
const allSubjects = computed(() => stats.value?.subjects || []);

function getNode(id) {
  return nodes.value.find((n) => n.id === id);
}
function isOnEdge(edge, nodeId) {
  return edge.src === nodeId || edge.dst === nodeId;
}
function isNeighbor(nodeId, selectedId) {
  if (nodeId === selectedId) return true;
  return edges.value.some(
    (e) =>
      (e.src === selectedId && e.dst === nodeId) ||
      (e.dst === selectedId && e.src === nodeId),
  );
}

// 渲染哪些边：未选中时只显示强关系；选中时显示与该节点直连的全部
const displayedEdges = computed(() => {
  if (selectedNode.value) {
    const sid = selectedNode.value.id;
    return edges.value.filter((e) => e.src === sid || e.dst === sid);
  }
  return edges.value.filter(
    (e) =>
      e.relation === "prerequisite" ||
      e.relation === "part_of" ||
      e.relation === "special_case_of" ||
      e.relation === "generalizes",
  );
});

// ── 数据加载 + 布局 ──────────────────────────────────

async function loadGraph() {
  loading.value = true;
  try {
    const data = await adminApi.kgGraph({
      subject: subjectFilter.value,
      includePending: includePending.value,
    });
    const rawNodes = data.nodes || [];
    edges.value = data.edges || [];
    stats.value = data.stats || null;
    layoutNodes(rawNodes);
    nodes.value = rawNodes;
    // 等 DOM 渲染后用真实画布尺寸再布局一次
    await nextTick();
    relayoutWithRealSize();
  } catch (err) {
    console.error("加载 KG 图谱失败", err);
    alert("加载失败：" + err.message);
  } finally {
    loading.value = false;
  }
}

function reload() {
  selectedNode.value = null;
  selectedDetail.value = null;
  loadGraph();
}

// 力导向布局：簇内 + 簇间双层（简化版）
function layoutNodes(rawNodes) {
  const N = rawNodes.length;
  if (N === 0) return;

  const W = svgW.value || 1200;
  const H = svgH.value || 800;
  const cx = W / 2;
  const cy = H / 2;

  // 邻接表
  const adj = Object.create(null);
  for (const n of rawNodes) adj[n.id] = new Set();
  for (const e of edges.value) {
    if (adj[e.src] && adj[e.dst]) {
      adj[e.src].add(e.dst);
      adj[e.dst].add(e.src);
    }
  }

  // 连通分量
  const visited = new Set();
  const components = [];
  for (const n of rawNodes) {
    if (visited.has(n.id)) continue;
    const stack = [n.id];
    const comp = [];
    while (stack.length) {
      const id = stack.pop();
      if (visited.has(id)) continue;
      visited.add(id);
      const node = rawNodes.find((x) => x.id === id);
      if (node) comp.push(node);
      for (const nb of adj[id] || []) if (!visited.has(nb)) stack.push(nb);
    }
    components.push(comp);
  }
  // 大簇优先
  components.sort((a, b) => b.length - a.length);

  // 每簇内：圆形排布 + 力导向松弛
  const clusters = components.map((comp) => {
    const m = comp.length;
    // 簇半径 = 节点数平方根缩放（初始就拉开些）
    const baseR = 80 + Math.sqrt(m) * 60;
    const particles = comp.map((n, i) => {
      const a = (i / m) * 2 * Math.PI;
      return {
        id: n.id,
        x: Math.cos(a) * baseR,
        y: Math.sin(a) * baseR,
        r: getNodeRadius(n) + 12,
      };
    });
    runForceLayout(particles, comp, adj, {
      iterations: 260,
      repulsion: 14000, // 斜力从 4200 调到 14000，节点互相推得更开
      linkDist: 140, // 弹簧理想长度从 75 调到 140，连连边的两个节点也不会贴一起
      damping: 0.78,
      gravity: 0.025, // 引力调弱，不会被拽回中心堆一块
    });
    // 簇外接圆
    let maxR = 0;
    for (const p of particles) {
      maxR = Math.max(maxR, Math.hypot(p.x, p.y) + p.r);
    }
    return { comp, particles, boundR: maxR };
  });

  // 簇间布局：簇当超级节点，圆形初始化 + 互斥
  const numC = clusters.length;
  const totalCirc = clusters.reduce((s, c) => s + c.boundR * 2 + 60, 0);
  const initR = numC > 1 ? totalCirc / (2 * Math.PI) : 0;
  const supers = clusters.map((cl, i) => ({
    x: cx + initR * Math.cos((i / numC) * 2 * Math.PI - Math.PI / 2),
    y: cy + initR * Math.sin((i / numC) * 2 * Math.PI - Math.PI / 2),
    r: cl.boundR + 30,
  }));
  if (numC > 1) {
    runSimpleRepulsion(supers, {
      iterations: 180,
      repulsion: 12000,
      gravity: 0.05,
      gcx: cx,
      gcy: cy,
    });
  } else {
    supers[0].x = cx;
    supers[0].y = cy;
  }

  // 合并最终坐标
  clusters.forEach((cl, ci) => {
    const sx = supers[ci].x;
    const sy = supers[ci].y;
    cl.comp.forEach((n, ni) => {
      const p = cl.particles[ni];
      n.x = sx + p.x;
      n.y = sy + p.y;
    });
  });

  // 平移让左上角对齐 + 更新画布尺寸
  if (rawNodes.length > 0) {
    const PAD = 60;
    const xs = rawNodes.map((n) => n.x);
    const ys = rawNodes.map((n) => n.y);
    const minX = Math.min(...xs) - PAD;
    const minY = Math.min(...ys) - PAD;
    const maxX = Math.max(...xs) + PAD;
    const maxY = Math.max(...ys) + PAD;
    const offX = -minX;
    const offY = -minY;
    rawNodes.forEach((n) => {
      n.x += offX;
      n.y += offY;
    });
    svgW.value = Math.max(svgW.value, maxX - minX);
    svgH.value = Math.max(svgH.value, maxY - minY);
  }
}

// 簇内力导向：斥力 + 弹簧 + 向心引力
function runForceLayout(particles, comp, adj, opts) {
  const {
    iterations = 260,
    repulsion = 14000,
    linkDist = 140,
    damping = 0.78,
    gravity = 0.025,
  } = opts;
  const n = particles.length;
  if (n <= 1) return;
  const idIdx = Object.create(null);
  particles.forEach((p, i) => (idIdx[p.id] = i));
  const vx = new Array(n).fill(0);
  const vy = new Array(n).fill(0);
  const fx = new Array(n);
  const fy = new Array(n);

  for (let it = 0; it < iterations; it++) {
    for (let i = 0; i < n; i++) {
      fx[i] = 0;
      fy[i] = 0;
    }
    // 斜力 + 硬性不重叠：两节点距离小于 r1+r2 时强制推开
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const d2 = dx * dx + dy * dy + 0.01;
        const f = repulsion / d2;
        const dist = Math.sqrt(d2);
        const ux = dx / dist;
        const uy = dy / dist;
        fx[i] += ux * f;
        fy[i] += uy * f;
        fx[j] -= ux * f;
        fy[j] -= uy * f;
        // 硬性不重叠：节点太近时加大推力
        const minDist = (particles[i].r || 20) + (particles[j].r || 20);
        if (dist < minDist) {
          const overlap = minDist - dist;
          fx[i] += ux * overlap * 0.6;
          fy[i] += uy * overlap * 0.6;
          fx[j] -= ux * overlap * 0.6;
          fy[j] -= uy * overlap * 0.6;
        }
      }
    } // 弹簧（边）
    for (let i = 0; i < n; i++) {
      const id = particles[i].id;
      for (const nb of adj[id] || []) {
        const j = idIdx[nb];
        if (j === undefined || j <= i) continue;
        const dx = particles[j].x - particles[i].x;
        const dy = particles[j].y - particles[i].y;
        const dist = Math.hypot(dx, dy) + 0.01;
        const f = (dist - linkDist) * 0.08;
        const ux = dx / dist;
        const uy = dy / dist;
        fx[i] += ux * f;
        fy[i] += uy * f;
        fx[j] -= ux * f;
        fy[j] -= uy * f;
      }
    }
    // 向 (0,0) 引力
    for (let i = 0; i < n; i++) {
      fx[i] += -particles[i].x * gravity;
      fy[i] += -particles[i].y * gravity;
    }
    // 积分
    for (let i = 0; i < n; i++) {
      vx[i] = (vx[i] + fx[i]) * damping;
      vy[i] = (vy[i] + fy[i]) * damping;
      particles[i].x += vx[i];
      particles[i].y += vy[i];
    }
  }
}

// 簇间：超级节点纯斥力 + 向心引力（不需要弹簧）
function runSimpleRepulsion(particles, opts) {
  const {
    iterations = 150,
    repulsion = 8000,
    damping = 0.7,
    gravity = 0.05,
    gcx = 0,
    gcy = 0,
  } = opts;
  const n = particles.length;
  if (n <= 1) return;
  const vx = new Array(n).fill(0);
  const vy = new Array(n).fill(0);
  const fx = new Array(n);
  const fy = new Array(n);

  for (let it = 0; it < iterations; it++) {
    for (let i = 0; i < n; i++) {
      fx[i] = 0;
      fy[i] = 0;
    }
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const dist = Math.hypot(dx, dy) + 0.01;
        // 让两簇的边界保持距离：距离按外接圆半径加权
        const minDist = particles[i].r + particles[j].r + 10;
        if (dist < minDist) {
          const overlap = minDist - dist;
          const ux = dx / dist;
          const uy = dy / dist;
          fx[i] += ux * overlap * 0.5;
          fy[i] += uy * overlap * 0.5;
          fx[j] -= ux * overlap * 0.5;
          fy[j] -= uy * overlap * 0.5;
        }
        const f = repulsion / (dist * dist);
        const ux = dx / dist;
        const uy = dy / dist;
        fx[i] += ux * f;
        fy[i] += uy * f;
        fx[j] -= ux * f;
        fy[j] -= uy * f;
      }
    }
    for (let i = 0; i < n; i++) {
      fx[i] += (gcx - particles[i].x) * gravity;
      fy[i] += (gcy - particles[i].y) * gravity;
    }
    for (let i = 0; i < n; i++) {
      vx[i] = (vx[i] + fx[i]) * damping;
      vy[i] = (vy[i] + fy[i]) * damping;
      particles[i].x += vx[i];
      particles[i].y += vy[i];
    }
  }
}

// 用真实画布尺寸再次布局（保证撑满）
function relayoutWithRealSize() {
  if (!canvasWrap.value || canvasWrap.value.clientWidth === 0) return;
  svgW.value = Math.max(canvasWrap.value.clientWidth, svgW.value);
  svgH.value = Math.max(canvasWrap.value.clientHeight, svgH.value);
}

// ── 交互 ─────────────────────────────────────────────
let isPanning = false;
let panStart = { x: 0, y: 0 };
let draggingNode = null;
let dragStart = { x: 0, y: 0 };

function onSvgMousedown(e) {
  if (e.button !== 0) return;
  isPanning = true;
  panStart = { x: e.clientX - pan.value.x, y: e.clientY - pan.value.y };
}
function onNodeMousedown(e, node) {
  draggingNode = node;
  dragStart = {
    x: (e.clientX - pan.value.x) / zoom.value - node.x,
    y: (e.clientY - pan.value.y) / zoom.value - node.y,
  };
  e.stopPropagation();
}
function onSvgMousemove(e) {
  if (draggingNode) {
    draggingNode.x = (e.clientX - pan.value.x) / zoom.value - dragStart.x;
    draggingNode.y = (e.clientY - pan.value.y) / zoom.value - dragStart.y;
    return;
  }
  if (isPanning) {
    pan.value = { x: e.clientX - panStart.x, y: e.clientY - panStart.y };
  }
}
function onSvgMouseup() {
  isPanning = false;
  draggingNode = null;
}
function onWheel(e) {
  const delta = e.deltaY > 0 ? -0.1 : 0.1;
  const newZoom = Math.max(0.2, Math.min(3, zoom.value + delta));
  const rect = canvasWrap.value?.getBoundingClientRect();
  if (rect) {
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    pan.value = {
      x: mx - (mx - pan.value.x) * (newZoom / zoom.value),
      y: my - (my - pan.value.y) * (newZoom / zoom.value),
    };
  }
  zoom.value = newZoom;
}
function resetView() {
  zoom.value = 1;
  pan.value = { x: 0, y: 0 };
}

// ── 节点选择 / 详情 ──────────────────────────────────
async function selectNode(node) {
  selectedNode.value = node;
  try {
    selectedDetail.value = await adminApi.kgConceptDetail(node.id);
  } catch (err) {
    console.error("加载节点详情失败", err);
    selectedDetail.value = null;
  }
}
function selectByPeer(peerId) {
  const n = getNode(peerId);
  if (n) selectNode(n);
}
function closeDetail() {
  selectedNode.value = null;
  selectedDetail.value = null;
}
function searchAndSelect() {
  const term = searchTerm.value.trim().toLowerCase();
  if (!term) return;
  const hit = nodes.value.find(
    (n) =>
      (n.title || "").toLowerCase().includes(term) ||
      (n.slug || "").toLowerCase().includes(term) ||
      (n.id || "").toLowerCase().includes(term),
  );
  if (hit) {
    selectNode(hit);
    // 把节点居中到画布中央
    const rect = canvasWrap.value?.getBoundingClientRect();
    if (rect) {
      pan.value = {
        x: rect.width / 2 - hit.x * zoom.value,
        y: rect.height / 2 - hit.y * zoom.value,
      };
    }
  } else {
    alert(`没找到 "${term}"`);
  }
}

// ── 生命周期 ─────────────────────────────────────────
let _resizeObserver = null;
onMounted(async () => {
  await loadGraph();
  await nextTick();
  if (canvasWrap.value) {
    _resizeObserver = new ResizeObserver(() => {
      relayoutWithRealSize();
    });
    _resizeObserver.observe(canvasWrap.value);
  }
});
onUnmounted(() => {
  _resizeObserver?.disconnect();
  _resizeObserver = null;
});
</script>

<style scoped>
.admin-kg {
  display: flex;
  flex-direction: column;
  height: calc(100dvh - 64px);
  width: 100%;
  overflow: hidden;
  background: var(--bg-page, #f8fafc);
  color: var(--text-primary, #1e293b);
  font-family:
    -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif;
}

/* 顶栏 */
.kg-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 20px;
  background: var(--bg-card, #ffffff);
  border-bottom: 1px solid var(--border-color, #e2e8f0);
  flex-shrink: 0;
  z-index: 10;
  gap: 12px;
}
.kg-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.kg-header-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: nowrap;
}
.page-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary, #1e293b);
  margin: 0;
}
.page-subtitle {
  font-size: 12px;
  color: var(--text-secondary, #64748b);
  white-space: nowrap;
}

/* 搜索框 */
.search-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  background: var(--bg-input, #f1f5f9);
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 6px;
  padding: 5px 10px;
  width: 220px;
  transition:
    border-color 0.15s,
    background 0.15s;
}
.search-bar.focused {
  border-color: #6366f1;
  background: var(--bg-card, #fff);
}
.search-bar svg {
  color: var(--text-secondary, #64748b);
  flex-shrink: 0;
}
.search-bar input {
  background: transparent;
  border: none;
  outline: none;
  flex: 1;
  font-size: 13px;
  color: var(--text-primary, #1e293b);
  min-width: 0;
}
.search-bar input::placeholder {
  color: var(--text-tertiary, #94a3b8);
}

/* 学科筛选 */
.sort-select {
  background: var(--bg-card, #fff);
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 6px;
  padding: 5px 28px 5px 10px;
  font-size: 13px;
  color: var(--text-primary, #1e293b);
  cursor: pointer;
  outline: none;
  appearance: none;
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'><path d='M1 1l4 4 4-4' stroke='%2364748b' stroke-width='1.5' fill='none' stroke-linecap='round'/></svg>");
  background-repeat: no-repeat;
  background-position: right 8px center;
}

/* checkbox 胶囊 */
.checkbox-pill {
  display: flex;
  align-items: center;
  gap: 5px;
  background: var(--bg-card, #fff);
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 6px;
  padding: 5px 10px;
  font-size: 13px;
  color: var(--text-secondary, #64748b);
  cursor: pointer;
  user-select: none;
  transition: all 0.15s;
}
.checkbox-pill.active {
  background: #eef2ff;
  border-color: #6366f1;
  color: #4f46e5;
}
.checkbox-pill input {
  margin: 0;
  accent-color: #6366f1;
}

/* 控制按钮 */
.graph-controls {
  display: flex;
  align-items: center;
  gap: 4px;
  padding-left: 6px;
  border-left: 1px solid var(--border-color, #e2e8f0);
}
.ctrl-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  background: var(--bg-card, #fff);
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 6px;
  color: var(--text-secondary, #64748b);
  cursor: pointer;
  transition: all 0.15s;
}
.ctrl-btn:hover {
  background: var(--bg-hover, #f1f5f9);
  color: var(--text-primary, #1e293b);
  border-color: #6366f1;
}
.zoom-val {
  font-size: 12px;
  color: var(--text-secondary, #64748b);
  min-width: 32px;
  text-align: center;
}

/* 主体 */
.kg-body {
  flex: 1;
  position: relative;
  overflow: hidden;
}

.graph-canvas-wrap {
  width: 100%;
  height: 100%;
  cursor: grab;
  user-select: none;
}
.graph-canvas-wrap:active {
  cursor: grabbing;
}
.graph-svg {
  width: 100%;
  height: 100%;
  display: block;
}

/* 节点动效 */
.node-group {
  cursor: pointer;
  transition: opacity 0.2s;
}
.node-group:hover circle:nth-of-type(3),
.node-group.selected circle:nth-of-type(3) {
  filter: drop-shadow(0 0 8px currentColor);
}
.node-group.dimmed {
  opacity: 0.25;
}

/* 加载 / 空 */
.kg-loading,
.kg-empty {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  color: var(--text-secondary, #64748b);
  font-size: 14px;
}
.kg-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border-color, #e2e8f0);
  border-top-color: #6366f1;
  border-radius: 50%;
  animation: kg-spin 0.8s linear infinite;
}
@keyframes kg-spin {
  to {
    transform: rotate(360deg);
  }
}
.ke-icon {
  font-size: 48px;
}
.ke-title {
  font-size: 16px;
  color: var(--text-primary, #1e293b);
  font-weight: 600;
}
.ke-desc {
  font-size: 13px;
  color: var(--text-secondary, #64748b);
}

/* 图例 */
.legend {
  position: absolute;
  left: 16px;
  bottom: 16px;
  background: var(--bg-card, rgba(255, 255, 255, 0.95));
  backdrop-filter: blur(8px);
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 12px;
  color: var(--text-secondary, #64748b);
  box-shadow: 0 4px 16px rgba(15, 23, 42, 0.06);
  z-index: 5;
}
.legend-title {
  font-size: 10px;
  color: var(--text-tertiary, #94a3b8);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 6px;
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 2px 0;
}
.legend-line {
  display: inline-block;
  width: 18px;
  height: 2px;
  border-radius: 1px;
}

/* 详情面板 */
.detail-panel {
  position: absolute;
  top: 16px;
  right: 16px;
  bottom: 16px;
  width: 360px;
  background: var(--bg-card, #ffffff);
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 10px;
  padding: 14px 16px;
  overflow-y: auto;
  z-index: 8;
  box-shadow: 0 8px 32px rgba(15, 23, 42, 0.1);
}
.detail-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 10px;
}
.detail-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary, #1e293b);
  line-height: 1.3;
  margin-bottom: 6px;
}
.detail-meta {
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
  margin-bottom: 4px;
}
.badge {
  background: var(--bg-hover, #f1f5f9);
  border: 1px solid var(--border-color, #e2e8f0);
  color: var(--text-secondary, #64748b);
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
}
.subject-badge {
  background: #eef2ff;
  color: #4f46e5;
  border-color: #c7d2fe;
}
.detail-cid {
  font-size: 11px;
  color: var(--text-tertiary, #94a3b8);
  font-family: "SF Mono", Menlo, monospace;
  word-break: break-all;
}
.section {
  margin-top: 14px;
}
.section-title {
  font-size: 11px;
  color: var(--text-tertiary, #94a3b8);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 6px;
}
.section-body {
  font-size: 13px;
  color: var(--text-primary, #1e293b);
  line-height: 1.55;
}
.alias-pill {
  display: inline-block;
  background: var(--bg-hover, #f1f5f9);
  border: 1px solid var(--border-color, #e2e8f0);
  color: var(--text-secondary, #64748b);
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  margin: 2px 4px 2px 0;
}
.facet-card {
  background: var(--bg-page, #f8fafc);
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 6px;
  padding: 8px 10px;
  margin-bottom: 6px;
}
.facet-head {
  display: flex;
  justify-content: space-between;
  margin-bottom: 4px;
}
.facet-kind {
  font-size: 11px;
  color: #6366f1;
  font-weight: 600;
}
.facet-origin {
  font-size: 10px;
  color: var(--text-tertiary, #94a3b8);
}
.facet-content {
  font-size: 12px;
  color: var(--text-primary, #1e293b);
  line-height: 1.5;
}

/* ---------- Markdown / KaTeX 渲染过的内容在详情面板里的样式收敛 ---------- */
/* v-html 生成的子元素拿不到 scoped attr，所以用 :deep() 穿透 */
.md-body :deep(p) {
  margin: 4px 0;
}
.md-body :deep(p:first-child) {
  margin-top: 0;
}
.md-body :deep(p:last-child) {
  margin-bottom: 0;
}
.md-body :deep(ul),
.md-body :deep(ol) {
  margin: 4px 0;
  padding-left: 20px;
}
.md-body :deep(li) {
  margin: 2px 0;
}
.md-body :deep(h1),
.md-body :deep(h2),
.md-body :deep(h3),
.md-body :deep(h4) {
  margin: 8px 0 4px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #1e293b);
}
.md-body :deep(code) {
  background: var(--bg-hover, #f1f5f9);
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 11px;
  font-family: "SF Mono", Menlo, Consolas, monospace;
}
.md-body :deep(pre) {
  background: var(--bg-hover, #f1f5f9);
  padding: 8px 10px;
  border-radius: 4px;
  overflow-x: auto;
  font-size: 11px;
  margin: 6px 0;
}
.md-body :deep(pre code) {
  background: transparent;
  padding: 0;
}
.md-body :deep(blockquote) {
  border-left: 3px solid #cbd5e1;
  padding-left: 8px;
  margin: 4px 0;
  color: var(--text-secondary, #64748b);
}
.md-body :deep(a) {
  color: #6366f1;
  text-decoration: none;
}
.md-body :deep(a:hover) {
  text-decoration: underline;
}
.md-body :deep(table) {
  border-collapse: collapse;
  font-size: 11px;
  margin: 6px 0;
}
.md-body :deep(th),
.md-body :deep(td) {
  border: 1px solid var(--border, #e2e8f0);
  padding: 3px 6px;
}
/* KaTeX 块级公式在窄面板里防溢出 */
.md-body :deep(.katex-display) {
  margin: 6px 0;
  overflow-x: auto;
  overflow-y: hidden;
}
.md-body :deep(.katex) {
  font-size: 1em;
}
.neighbor-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 5px;
  cursor: pointer;
  transition: background 0.15s;
  font-size: 12px;
}
.neighbor-row:hover {
  background: var(--bg-hover, #f1f5f9);
}
.dir {
  font-size: 14px;
  font-weight: 700;
  width: 16px;
  text-align: center;
}
.dir-out {
  color: #6366f1;
}
.dir-in {
  color: #f59e0b;
}
.rel-pill {
  font-size: 11px;
  font-weight: 600;
}
.peer-name {
  color: var(--text-primary, #1e293b);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 过渡 */
.slide-enter-active,
.slide-leave-active {
  transition:
    transform 0.25s ease,
    opacity 0.25s ease;
}
.slide-enter-from,
.slide-leave-to {
  transform: translateX(20px);
  opacity: 0;
}

/* 暗色主题适配（来自 useTheme，body 上会有 .dark 类） */
.admin-kg.dark {
  background: var(--bg-page, #0f172a);
  color: var(--text-primary, #e2e8f0);
}
@media (max-width: 800px) {
  .kg-header {
    flex-wrap: wrap;
    padding: 12px 16px;
  }
  .kg-header-right {
    flex-wrap: wrap;
    width: 100%;
  }
  .search-bar {
    flex: 1;
    min-width: 160px;
  }
}
</style>
