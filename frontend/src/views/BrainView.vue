<template>
  <div class="brain-page">
    <div ref="host" class="canvas" />
    <div class="zoom-controls" aria-label="大脑缩放">
      <button type="button" title="缩小" @click="zoomBy(1.32)">−</button>
      <input
        type="range"
        min="30"
        max="1500"
        :value="zoomPercent"
        aria-label="知识大脑缩放尺度"
        @input="setZoom($event.target.value)"
      />
      <button
        type="button"
        class="zoom-label"
        title="回到全脑视角"
        @click="resetView"
      >
        {{ zoomPercent }}%
      </button>
      <button type="button" title="放大" @click="zoomBy(0.76)">+</button>
    </div>
    <header>
      <p>WESMARTFLOW · PERSONAL KNOWLEDGE CORTEX</p>
      <h1>我的知识大脑</h1>
      <span>{{
        mapSource
          ? "正在根据你的学习证据生成知识地图。"
          : "每一次理解，都会在这里留下微光。"
      }}</span>
    </header>
    <div class="stats">
      <span
        ><b>{{ nodes.length }}</b
        >知识粒子</span
      ><span
        ><b>{{ lit }}</b
        >已点亮</span
      ><span
        ><b>{{ edgeCount }}</b
        >形成连接</span
      ><button
        v-if="frontierNodes.length"
        class="frontier-stat"
        @click="selectConcept(frontierNodes[0])"
      >
        <b>{{ frontierNodes.length }}</b
        >适合开启
      </button>
    </div>
    <nav>
      <button
        v-for="r in regions"
        :key="r.id"
        :class="{ active: active === r.id }"
        @click="selectRegion(r.id)"
      >
        <i :style="{ background: r.color }" />{{ r.name
        }}<b>{{ counts[r.id] || 0 }}</b>
      </button>
    </nav>
    <p class="legend">
      <i /> 已形成理解 <span>●</span> 初次遇见 <em>●</em> 推荐探索
    </p>
    <p class="hint">拖动旋转 · 滚动或拉动尺度条 · 点击知识粒子</p>
    <p class="caption">✦ 一张会呼吸、会生长的个人知识地图。</p>
    <aside
      v-if="regionDrawerOpen && activeRegion"
      class="region-drawer"
      aria-label="当前学习区域节点列表"
    >
      <button
        class="region-close"
        type="button"
        aria-label="关闭节点列表"
        @click="clearRegion"
      >
        ×
      </button>
      <small :style="{ color: activeRegion.color }">LEARNING REGION</small>
      <h2>{{ activeRegion.name }}</h2>
      <p>
        这里有
        {{ activeNodes.length }} 个知识节点。选一个节点，大脑会锁定它的位置。
      </p>
      <div v-if="activeNodes.length" class="region-node-list">
        <article
          v-for="node in activeNodes"
          :key="node.id"
          :ref="(el) => setRegionNodeRef(node.id, el)"
          class="region-node-item"
          :class="{
            selected: selected?.id === node.id,
            frontier: node.is_frontier,
          }"
        >
          <button
            type="button"
            class="region-node-trigger"
            @click="selectConcept(node)"
          >
            <i
              :style="{
                background: node.is_frontier ? '#ffe39a' : activeRegion.color,
              }"
            />
            <span>
              <strong>{{ node.title }}</strong>
              <small>{{
                node.is_frontier
                  ? "现在适合开启"
                  : node.next_action || "继续积累理解"
              }}</small>
            </span>
            <b>{{ Math.round((node.mastery_level || 0) * 100) }}%</b>
          </button>
          <div v-if="selected?.id === node.id" class="locked-node-detail">
            <p class="selected-intro">
              {{ node.description || "已在大脑中锁定这个知识节点。" }}
            </p>
            <button
              class="detail-toggle"
              type="button"
              @click="detailExpanded = !detailExpanded"
            >
              {{ detailExpanded ? "收起完整介绍" : "展开完整介绍" }}
              <span>{{ detailExpanded ? "⌃" : "⌄" }}</span>
            </button>
            <div v-if="detailExpanded" class="full-node-detail">
              <p v-if="detailLoading" class="detail-loading">
                正在加载完整知识内容…
              </p>
              <template v-else-if="selectedDetail">
                <section
                  v-if="selectedDetail.content?.summary"
                  class="reading-section"
                >
                  <h3>概念介绍</h3>
                  <p class="summary-copy">
                    {{ selectedDetail.content.summary }}
                  </p>
                </section>
                <section
                  v-if="selectedDetail.content?.key_points?.length"
                  class="reading-section"
                >
                  <h3>核心要点</h3>
                  <ul>
                    <li
                      v-for="keyPoint in selectedDetail.content.key_points"
                      :key="keyPoint"
                    >
                      {{ keyPoint }}
                    </li>
                  </ul>
                </section>
                <section
                  v-if="selectedDetail.content?.examples?.length"
                  class="reading-section"
                >
                  <h3>示例与应用</h3>
                  <ul>
                    <li
                      v-for="example in selectedDetail.content.examples.slice(
                        0,
                        3,
                      )"
                      :key="example"
                    >
                      {{ example }}
                    </li>
                  </ul>
                </section>
                <section
                  v-if="selectedDetail.content?.common_mistakes?.length"
                  class="reading-section caution"
                >
                  <h3>容易混淆</h3>
                  <ul>
                    <li
                      v-for="mistake in selectedDetail.content.common_mistakes"
                      :key="mistake"
                    >
                      {{ mistake }}
                    </li>
                  </ul>
                </section>
              </template>
              <section
                v-if="selectedEvidence"
                class="reading-section evidence-section"
              >
                <h3>你的学习足迹</h3>
                <p v-if="evidenceSummary">{{ evidenceSummary }}</p>
                <p v-else>
                  还没有形成可展示的学习证据；完成一次练习、互动探索或课程任务后会出现在这里。
                </p>
                <div
                  v-if="selectedEvidence.source_details?.length"
                  class="source-list"
                >
                  <span
                    v-for="source in selectedEvidence.source_details.slice(
                      0,
                      3,
                    )"
                    :key="source.source_id"
                    >{{
                      source.source_title || source.title || "学习来源"
                    }}</span
                  >
                </div>
              </section>
              <section v-if="relatedNodes.length" class="reading-section">
                <h3>关联路径</h3>
                <div class="detail-related-list">
                  <button
                    v-for="related in relatedNodes"
                    :key="related.id"
                    type="button"
                    @click="selectConcept(related)"
                  >
                    <span>{{ relationLabel(node, related.id) }}</span
                    >{{ related.title }}
                  </button>
                </div>
              </section>
            </div>
            <div class="locked-actions">
              <button type="button" @click="learn">继续学习 ↗</button
              ><button type="button" @click="review">习题强化</button>
            </div>
          </div>
        </article>
      </div>
      <div v-else class="region-empty">
        这个区域还没有形成可展示的知识节点。
      </div>
    </aside>
    <section v-if="!loading && !nodes.length" class="empty">
      <strong>✦</strong>
      <h2>你的知识大脑正在等待第一束光</h2>
      <p>开始一次学习或探索，理解过的知识会在这里逐渐形成连接。</p>
      <button @click="$router.push('/explore')">去探索</button>
    </section>
    <div v-if="loading" class="loading">✦ 正在唤醒知识大脑</div>
  </div>
</template>
<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { api } from "../api/base.js";
import { nodeApi } from "../api/nodes.js";
const router = useRouter(),
  host = ref(null),
  nodes = ref([]),
  selected = ref(null),
  active = ref(null),
  regionDrawerOpen = ref(false),
  loading = ref(true),
  mapSource = ref(""),
  selectedDetail = ref(null),
  selectedEvidence = ref(null),
  detailLoading = ref(false),
  detailExpanded = ref(true),
  zoomPercent = ref(100);
const regions = [
  {
    id: "reason",
    name: "逻辑推理",
    color: "#8f7cff",
    a: [1.22, 0.48, 0.45],
    r: [1.05, 0.78, 0.86],
  },
  {
    id: "language",
    name: "语言表达",
    color: "#ff987d",
    a: [1.46, -0.72, 0.42],
    r: [0.92, 0.68, 0.98],
  },
  {
    id: "science",
    name: "科学探索",
    color: "#59ded4",
    a: [-0.24, 1.08, 0.43],
    r: [1.22, 0.72, 0.92],
  },
  {
    id: "creation",
    name: "创作实践",
    color: "#ffcc70",
    a: [-1.38, -0.57, 0.42],
    r: [0.95, 0.68, 0.96],
  },
  {
    id: "society",
    name: "社会理解",
    color: "#f782bd",
    a: [-1.48, 0.42, -0.28],
    r: [0.86, 0.66, 0.76],
  },
  {
    id: "skill",
    name: "专业技能",
    color: "#74df92",
    a: [0.05, -1.08, -0.38],
    r: [1.18, 0.58, 0.72],
  },
];
const zoneById = Object.fromEntries(regions.map((x) => [x.id, x]));
function text(n) {
  return [n.title, n.description, ...(n.tags || [])].join(" ").toLowerCase();
}
function relationLabel(node, targetId) {
  const direct = node.relations?.find(
    (relation) => relation.target_node_id === targetId,
  )?.relation_type;
  const reverse = nodes.value
    .find((item) => item.id === targetId)
    ?.relations?.find(
      (relation) => relation.target_node_id === node.id,
    )?.relation_type;
  return (
    {
      prerequisite: "前置",
      extends: "延伸",
      contrasts: "对照",
      related: "关联",
    }[direct || reverse] || "关联"
  );
}
function zone(n) {
  const t = text(n);
  if (/语文|英语|语言|写作|阅读|表达|词汇|口语|文学/.test(t))
    return zoneById.language;
  if (/物理|化学|生物|科学|天文|地理|实验|医学|生态/.test(t))
    return zoneById.science;
  if (/绘画|音乐|设计|创作|艺术|故事|视频|摄影|影像/.test(t))
    return zoneById.creation;
  if (/历史|社会|政治|心理|经济|哲学|沟通|文化/.test(t))
    return zoneById.society;
  if (/编程|计算机|工程|职业|产品|商业|数据|算法|系统|人工智能|ai/.test(t))
    return zoneById.skill;
  return zoneById.reason;
}
const relatedNodes = computed(() => {
    const selectedId = selected.value?.id;
    if (!selectedId) return [];
    const related = new Set(
      selected.value.relations?.map((r) => r.target_node_id) || [],
    );
    nodes.value.forEach((node) => {
      if (node.relations?.some((r) => r.target_node_id === selectedId))
        related.add(node.id);
    });
    return nodes.value.filter((node) => related.has(node.id));
  }),
  evidenceSummary = computed(() => {
    if (!selectedEvidence.value) return "";
    const bits = [];
    if (selectedEvidence.value.quizzes?.length)
      bits.push(`完成 ${selectedEvidence.value.quizzes.length} 次练习`);
    if (selectedEvidence.value.origins?.length)
      bits.push(`来自 ${selectedEvidence.value.origins.length} 段学习来源`);
    if (selectedEvidence.value.study_logs?.length)
      bits.push(`留下 ${selectedEvidence.value.study_logs.length} 条学习记录`);
    return bits.join(" · ");
  });
const activeRegion = computed(() =>
  active.value ? zoneById[active.value] : null,
);
const activeNodes = computed(() =>
  !active.value
    ? []
    : nodes.value
        .filter((node) => zone(node).id === active.value)
        .sort(
          (a, b) =>
            Number(Boolean(b.is_frontier)) - Number(Boolean(a.is_frontier)) ||
            (b.mastery_level || 0) - (a.mastery_level || 0) ||
            a.title.localeCompare(b.title, "zh"),
        ),
);
const counts = computed(() => {
    const x = Object.fromEntries(regions.map((r) => [r.id, 0]));
    nodes.value.forEach((n) => x[zone(n).id]++);
    return x;
  }),
  lit = computed(
    () => nodes.value.filter((n) => (n.mastery_level || 0) >= 0.2).length,
  ),
  edgeCount = computed(() => {
    const s = new Set();
    nodes.value.forEach((n) =>
      (n.relations || []).forEach((r) =>
        s.add([n.id, r.target_node_id].sort().join("/")),
      ),
    );
    return s.size;
  }),
  frontierNodes = computed(() => nodes.value.filter((n) => n.is_frontier));
function asList(value) {
  if (Array.isArray(value)) return value;
  if (value && Array.isArray(value.items)) return value.items;
  if (value && Array.isArray(value.concepts)) return value.concepts;
  return [];
}
function conceptId(value) {
  if (value === null || value === undefined) return null;
  if (typeof value === "string" || typeof value === "number")
    return String(value);
  return (
    value.id ??
    value.concept_id ??
    value.canonical_concept_id ??
    value.node_id ??
    value.target_id ??
    null
  );
}
function normalizeMastery(concept) {
  let value =
    concept.mastery_level ??
    concept.mastery ??
    concept.progress?.mastery_level ??
    concept.progress?.mastery ??
    concept.state?.mastery_level ??
    concept.state?.mastery ??
    concept.user_state?.mastery_level ??
    concept.user_state?.mastery;
  if (value === undefined || value === null) {
    const status = String(
      concept.status ?? concept.state?.status ?? "",
    ).toLowerCase();
    value = /mastered|proficient/.test(status)
      ? 0.82
      : /learning|active/.test(status)
        ? 0.48
        : /encountered|discovered/.test(status)
          ? 0.18
          : 0;
  }
  value = Number(value);
  if (!Number.isFinite(value)) value = 0;
  return Math.max(0, Math.min(1, value > 1 ? value / 100 : value));
}
function normalizeTags(concept) {
  const tags =
    concept.tags ??
    concept.labels ??
    concept.domains ??
    concept.domain ??
    concept.subject ??
    [];
  return Array.isArray(tags)
    ? tags.filter(Boolean)
    : tags
      ? [String(tags)]
      : [];
}
function endpoint(edge, keys) {
  for (const key of keys) {
    const value = edge?.[key];
    const id = conceptId(value);
    if (id !== null && id !== undefined) return String(id);
  }
  return null;
}
function normalizeBrainMap(payload) {
  const rawConcepts = asList(payload?.concepts),
    frontier = asList(payload?.frontier),
    result = [],
    byId = new Map();
  const unwrap = (raw) =>
    raw?.concept ?? raw?.node ?? raw?.concept_detail ?? raw;
  const addConcept = (raw, frontierEntry = null) => {
    const inner = unwrap(raw),
      source =
        inner === raw
          ? raw
          : {
              ...raw,
              ...inner,
              state: inner?.state ?? raw?.state,
              learner_state: inner?.learner_state ?? raw?.learner_state,
              user_state: inner?.user_state ?? raw?.user_state,
              progress: inner?.progress ?? raw?.progress,
            },
      id = conceptId(source) || conceptId(raw) || conceptId(frontierEntry);
    if (!id) return null;
    let node = byId.get(String(id));
    if (!node) {
      node = {
        ...source,
        id: String(id),
        title:
          source?.title ??
          source?.name ??
          source?.label ??
          source?.display_name ??
          source?.canonical_name ??
          source?.concept_name ??
          "未命名知识点",
        description:
          source?.description ?? source?.summary ?? source?.definition ?? "",
        tags: normalizeTags(source),
        mastery_level: normalizeMastery(source),
        relations: [],
      };
      byId.set(node.id, node);
      result.push(node);
    }
    if (frontierEntry) {
      node.is_frontier = true;
      node.recommendation_reason =
        frontierEntry.reason ??
        frontierEntry.recommendation_reason ??
        frontierEntry.why ??
        frontierEntry.explanation ??
        node.recommendation_reason;
      node.recommendation_score =
        frontierEntry.score ??
        frontierEntry.recommendation_score ??
        node.recommendation_score;
    }
    return node;
  };
  rawConcepts.forEach((concept) => addConcept(concept));
  frontier.forEach((entry) => {
    const raw = typeof entry === "object" ? entry : { id: entry };
    addConcept(raw, raw);
  });
  const relationKeys = ["connections", "relations", "edges"];
  relationKeys
    .flatMap((key) => asList(payload?.[key]))
    .forEach((edge) => {
      const from = endpoint(edge, [
          "source_id",
          "from_id",
          "source_concept_id",
          "from_concept_id",
          "source",
          "from",
          "parent_id",
        ]),
        to = endpoint(edge, [
          "target_id",
          "to_id",
          "target_concept_id",
          "to_concept_id",
          "target",
          "to",
          "child_id",
        ]);
      if (!from || !to || from === to) return;
      const a = byId.get(from),
        b = byId.get(to);
      if (!a || !b) return;
      const add = (left, right) => {
        if (!left.relations.some((r) => r.target_node_id === right.id))
          left.relations.push({
            target_node_id: right.id,
            relation_type: edge.type ?? edge.relationship ?? edge.relation_type,
          });
      };
      add(a, b);
      add(b, a);
    });
  return { nodes: result, source: payload?.source ?? "" };
}
function hash(v) {
  let h = 2166136261;
  for (const c of String(v)) h = Math.imul(h ^ c.charCodeAt(0), 16777619);
  return (h >>> 0) / 4294967295;
}
function pointInZone(z, seed, spread = 0.75) {
  const u = hash(seed + "u"),
    v = hash(seed + "v"),
    w = Math.cbrt(hash(seed + "w")) * spread,
    theta = 2 * Math.PI * u,
    phi = Math.acos(2 * v - 1);
  return new THREE.Vector3(
    z.a[0] + Math.sin(phi) * Math.cos(theta) * z.r[0] * w,
    z.a[1] + Math.cos(phi) * z.r[1] * w,
    z.a[2] + Math.sin(phi) * Math.sin(theta) * z.r[2] * w,
  );
}
function point(n, spread = 0.75) {
  return pointInZone(zone(n), n.id, spread);
}
let scene,
  camera,
  renderer,
  controls,
  brain,
  ro,
  raf,
  glow,
  groups = [],
  pick = [],
  volumes = {},
  pulses = [],
  surfacePulses = [],
  focusState = null,
  defaultDistance = 16,
  cortexMaterials = [],
  gyrusMaterials = [],
  surfaceSignalMaterials = [];
function glowTexture() {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const x = c.getContext("2d"),
    g = x.createRadialGradient(64, 64, 0, 64, 64, 64);
  g.addColorStop(0, "#fff");
  g.addColorStop(0.14, "rgba(190,225,255,.92)");
  g.addColorStop(0.44, "rgba(100,175,255,.3)");
  g.addColorStop(1, "rgba(40,110,255,0)");
  x.fillStyle = g;
  x.fillRect(0, 0, 128, 128);
  return new THREE.CanvasTexture(c);
}
function hemi(side, count, seed = 0) {
  const p = [],
    c = [],
    base = new THREE.Color(),
    night = new THREE.Color("#0b1b3c"),
    gold = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < count; i++) {
    const t = (i + 0.5) / count,
      y0 = 1 - 2 * t,
      rr = Math.sqrt(1 - y0 * y0),
      a = i * gold + seed,
      x0 = Math.abs(rr * Math.cos(a)),
      z0 = rr * Math.sin(a);
    const fold =
        0.072 * Math.sin(9 * Math.atan2(z0, x0) + 5 * y0) +
        0.045 * Math.sin(21 * z0 - 7 * y0) +
        0.026 * Math.sin(37 * y0 + 11 * z0),
      b = 1 + fold;
    const frontal = Math.max(0, z0) * (0.34 + 0.18 * (1 - Math.abs(y0))),
      temporal =
        y0 < -0.08
          ? 0.34 * (1 - Math.abs(y0)) * Math.max(0.1, 1 - Math.abs(z0))
          : 0,
      occipital = z0 < 0 ? 0.16 * Math.max(0, 1 - Math.abs(y0)) : 0;
    const x = side * (0.26 + (4.54 + temporal) * x0 * b),
      y =
        3.25 * y0 * (1 + 0.025 * Math.sin(7 * a)) -
        0.11 * Math.max(0, z0) * (1 - y0 * y0),
      z =
        (3.76 + frontal + occipital) * z0 * b +
        0.16 * Math.max(0, z0) * Math.sqrt(1 - y0 * y0);
    p.push(x, y, z);
    const id =
      x > 1.1
        ? "reason"
        : y > 1
          ? "science"
          : x < -1.22
            ? "creation"
            : y < -1.05
              ? "skill"
              : "society";
    base
      .set(zoneById[id].color)
      .lerp(night, 0.64 + hash(seed + ":" + i) * 0.24);
    c.push(base.r, base.g, base.b);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(p, 3));
  g.setAttribute("color", new THREE.Float32BufferAttribute(c, 3));
  return g;
}
function cortex() {
  [hemi(-1, 7600), hemi(1, 7600, 0.31)].forEach((g) => {
    const surface = new THREE.PointsMaterial({
      size: 0.031,
      vertexColors: true,
      transparent: true,
      opacity: 0.77,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    brain.add(new THREE.Points(g, surface));
    const innerMaterial = new THREE.PointsMaterial({
      size: 0.012,
      color: "#c0dbff",
      transparent: true,
      opacity: 0.1,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    const inner = new THREE.Points(g.clone(), innerMaterial);
    inner.scale.setScalar(0.955);
    brain.add(inner);
    cortexMaterials.push([surface, 0.77], [innerMaterial, 0.1]);
  });
  /* 左右半球自然留白，不绘制黑色点状中线。 */ addCerebellumAndStem();
}
function addCerebellumAndStem() {
  const cerebellum = new THREE.Group();
  for (const side of [-1, 1])
    for (let i = 0; i < 1200; i++) {
      const u = hash(`cb:${side}:${i}`) * Math.PI * 2,
        v = hash(`cv:${side}:${i}`) * Math.PI,
        dot = new THREE.Sprite(
          new THREE.SpriteMaterial({
            map: glow,
            color: "#6f9cff",
            transparent: true,
            opacity: 0.1 + hash(`co:${side}:${i}`) * 0.18,
            depthWrite: false,
            blending: THREE.AdditiveBlending,
          }),
        );
      dot.position.set(
        side * (0.4 + Math.cos(u) * Math.sin(v) * 1.25),
        Math.cos(v) * 0.65 - 2.45,
        Math.sin(u) * Math.sin(v) * 0.82 - 2.55,
      );
      dot.scale.setScalar(0.025 + hash(`cs:${side}:${i}`) * 0.032);
      cerebellum.add(dot);
    }
  brain.add(cerebellum);
  const stemCurve = new THREE.CatmullRomCurve3([
    new THREE.Vector3(0, -2.42, -2.42),
    new THREE.Vector3(0.06, -3.08, -2.25),
    new THREE.Vector3(-0.07, -3.78, -1.82),
  ]);
  brain.add(
    new THREE.Mesh(
      new THREE.TubeGeometry(stemCurve, 32, 0.2, 9, false),
      new THREE.MeshBasicMaterial({
        color: "#426bd7",
        transparent: true,
        opacity: 0.26,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    ),
  );
}
function gyri() {
  const m = new THREE.LineBasicMaterial({
    color: "#bed9ff",
    transparent: true,
    opacity: 0.055,
    blending: THREE.AdditiveBlending,
  });
  gyrusMaterials.push([m, 0.055]);
  const sulci = [
    { theta: 0.84, phi: -1.15, span: 1.55 },
    { theta: 1.42, phi: -0.9, span: 1.65 },
    { theta: 1.96, phi: -0.74, span: 1.42 },
    { theta: 1.06, phi: 0.24, span: 1.35 },
    { theta: 1.68, phi: 0.36, span: 1.18 },
    { theta: 2.25, phi: 0.02, span: 1.02 },
  ];
  for (const side of [-1, 1])
    for (const [index, sulcus] of sulci.entries()) {
      const pts = [];
      for (let j = 0; j < 48; j++) {
        const u = j / 47 - 0.5,
          theta = sulcus.theta + 0.11 * Math.sin(u * Math.PI * 2 + index),
          phi = sulcus.phi + u * sulcus.span,
          y0 = Math.cos(theta),
          r = Math.sin(theta),
          x0 = Math.abs(r * Math.cos(phi)),
          z0 = r * Math.sin(phi),
          b =
            1 +
            0.072 * Math.sin(9 * Math.atan2(z0, x0) + 5 * y0) +
            0.045 * Math.sin(21 * z0 - 7 * y0);
        pts.push(
          new THREE.Vector3(
            side * (0.26 + 4.68 * x0 * b),
            3.28 * y0,
            3.8 * z0 * b,
          ),
        );
      }
      brain.add(
        new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), m),
      );
    }
}
function surfacePoint(side, theta, phi, lift = 0.08) {
  const y0 = Math.cos(theta),
    r = Math.sin(theta),
    x0 = Math.abs(r * Math.cos(phi)),
    z0 = r * Math.sin(phi),
    fold =
      0.072 * Math.sin(9 * Math.atan2(z0, x0) + 5 * y0) +
      0.045 * Math.sin(21 * z0 - 7 * y0) +
      0.026 * Math.sin(37 * y0 + 11 * z0),
    b = 1 + fold;
  const frontal = Math.max(0, z0) * (0.34 + 0.18 * (1 - Math.abs(y0))),
    temporal =
      y0 < -0.08
        ? 0.34 * (1 - Math.abs(y0)) * Math.max(0.1, 1 - Math.abs(z0))
        : 0,
    occipital = z0 < 0 ? 0.16 * Math.max(0, 1 - Math.abs(y0)) : 0;
  return new THREE.Vector3(
    side * (0.26 + (4.54 + temporal) * x0 * b + lift),
    3.25 * y0 * (1 + 0.025 * Math.sin(7 * phi)) -
      0.11 * Math.max(0, z0) * (1 - y0 * y0),
    (3.76 + frontal + occipital) * z0 * b +
      0.16 * Math.max(0, z0) * Math.sqrt(1 - y0 * y0),
  );
}
function addSurfacePulse(curve, color, seed) {
  const core = new THREE.Sprite(
    new THREE.SpriteMaterial({
      map: glow,
      color: "#effcff",
      transparent: true,
      opacity: 0.92,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    }),
  );
  core.scale.setScalar(0.075);
  brain.add(core);
  const tail = [];
  for (let i = 0; i < 4; i++) {
    const sprite = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: glow,
        color,
        transparent: true,
        opacity: 0.32 - i * 0.06,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    );
    sprite.scale.setScalar(0.06 - i * 0.01);
    brain.add(sprite);
    tail.push(sprite);
  }
  surfacePulses.push({
    curve,
    core,
    tail,
    offset: hash(`surface:${seed}`),
    speed: 0.024 + hash(`surface-speed:${seed}`) * 0.018,
    phase: hash(`surface-phase:${seed}`) * 6.28,
  });
}
function addSurfaceSignals() {
  const paths = [
    { side: -1, theta: 0.83, phi: -1.04, span: 1.12, color: "#68e2e6" },
    { side: 1, theta: 0.86, phi: -0.82, span: 1.18, color: "#9d8bff" },
    { side: -1, theta: 1.38, phi: -0.58, span: 1.34, color: "#66baff" },
    { side: 1, theta: 1.52, phi: -0.42, span: 1.25, color: "#7ef0d0" },
    { side: -1, theta: 1.1, phi: 0.34, span: 0.98, color: "#f5a2d0" },
    { side: 1, theta: 1.18, phi: 0.26, span: 1.02, color: "#89b6ff" },
  ];
  paths.forEach((path, index) => {
    const points = [];
    for (let step = 0; step < 44; step++) {
      const u = step / 43 - 0.5;
      points.push(
        surfacePoint(
          path.side,
          path.theta + 0.09 * Math.sin(u * Math.PI * 2 + index),
          path.phi + u * path.span,
          0.09,
        ),
      );
    }
    const curve = new THREE.CatmullRomCurve3(points);
    curve.arcLengthDivisions = 96;
    const material = new THREE.LineBasicMaterial({
      color: path.color,
      transparent: true,
      opacity: 0.19,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    brain.add(
      new THREE.Line(
        new THREE.BufferGeometry().setFromPoints(curve.getPoints(80)),
        material,
      ),
    );
    surfaceSignalMaterials.push([material, 0.19]);
    addSurfacePulse(curve, path.color, index);
  });
}
function regions3d() {
  regions.forEach((z) => {
    const fog = [],
      dust = [];
    for (let i = 0; i < 360; i++) {
      const p = pointInZone(z, z.id + "f" + i, 1);
      fog.push(p.x, p.y, p.z);
    }
    for (let i = 0; i < 150; i++) {
      const p = pointInZone(z, z.id + "d" + i, 0.9);
      dust.push(p.x, p.y, p.z);
    }
    const f = new THREE.BufferGeometry(),
      d = new THREE.BufferGeometry();
    f.setAttribute("position", new THREE.Float32BufferAttribute(fog, 3));
    d.setAttribute("position", new THREE.Float32BufferAttribute(dust, 3));
    const group = new THREE.Group(),
      mist = new THREE.Points(
        f,
        new THREE.PointsMaterial({
          size: 0.038,
          color: z.color,
          transparent: true,
          opacity: 0.12,
          depthWrite: false,
          blending: THREE.AdditiveBlending,
        }),
      ),
      motes = new THREE.Points(
        d,
        new THREE.PointsMaterial({
          size: 0.018,
          color: z.color,
          transparent: true,
          opacity: 0.3,
          depthWrite: false,
          blending: THREE.AdditiveBlending,
        }),
      );
    group.add(mist, motes);
    group.userData = { mist, motes, phase: hash(z.id + "p") * 6.28 };
    brain.add(group);
    volumes[z.id] = group;
  });
}
function addNode(n) {
  const p = point(n),
    z = zone(n),
    isFrontier = !!n.is_frontier,
    color = isFrontier ? "#ffe39a" : z.color,
    g = new THREE.Group();
  g.position.copy(p);
  g.userData = { n, home: p.clone(), phase: hash(n.id + "p") * 6.28 };
  const halo = new THREE.Sprite(
    new THREE.SpriteMaterial({
      map: glow,
      color,
      transparent: true,
      opacity: isFrontier ? 0.82 : 0.26 + (n.mastery_level || 0) * 0.62,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    }),
  );
  halo.scale.setScalar(
    (isFrontier ? 0.82 : 0.46) +
      (n.mastery_level || 0) * (isFrontier ? 0.36 : 0.78),
  );
  g.add(halo);
  const core = new THREE.Mesh(
    new THREE.SphereGeometry(
      (isFrontier ? 0.105 : 0.052) +
        (n.mastery_level || 0) * (isFrontier ? 0.08 : 0.12),
      18,
      18,
    ),
    new THREE.MeshBasicMaterial({
      color,
      transparent: true,
      opacity: isFrontier ? 0.96 : 0.48 + (n.mastery_level || 0) * 0.5,
    }),
  );
  core.userData.g = g;
  g.add(core);
  if (isFrontier) {
    const beacon = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: glow,
        color: "#fff7cf",
        transparent: true,
        opacity: 0.6,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    );
    beacon.scale.setScalar(0.25);
    beacon.position.y = 0.2;
    g.add(beacon);
  }
  brain.add(g);
  groups.push(g);
  pick.push(core);
}
function pulse(curve, color, seed) {
  const core = new THREE.Sprite(
    new THREE.SpriteMaterial({
      map: glow,
      color: "#f5fbff",
      transparent: true,
      opacity: 0.98,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    }),
  );
  core.scale.setScalar(0.155);
  brain.add(core);
  const tail = [];
  for (let i = 0; i < 5; i++) {
    const s = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: glow,
        color,
        transparent: true,
        opacity: 0.5 - i * 0.075,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    );
    s.scale.setScalar(0.13 - i * 0.018);
    brain.add(s);
    tail.push(s);
  }
  pulses.push({
    curve,
    core,
    tail,
    offset: hash("po" + seed),
    speed: 0.052 + hash("ps" + seed) * 0.042,
    phase: hash("pp" + seed) * 6.28,
  });
}
function links() {
  const by = Object.fromEntries(groups.map((g) => [g.userData.n.id, g])),
    seen = new Set();
  nodes.value.forEach((n) =>
    (n.relations || []).forEach((r) => {
      const a = by[n.id],
        b = by[r.target_node_id],
        key = [n.id, r.target_node_id].sort().join("/");
      if (!a || !b || seen.has(key)) return;
      seen.add(key);
      const st = a.userData.home,
        en = b.userData.home,
        mid = st
          .clone()
          .lerp(en, 0.5)
          .multiplyScalar(0.72)
          .add(
            new THREE.Vector3(
              (hash("cx" + key) - 0.5) * 0.22,
              0.1,
              (hash("cz" + key) - 0.5) * 0.22,
            ),
          ),
        curve = new THREE.CatmullRomCurve3([
          st,
          st.clone().multiplyScalar(0.9),
          mid,
          en.clone().multiplyScalar(0.9),
          en,
        ]);
      curve.arcLengthDivisions = 96;
      brain.add(
        new THREE.Mesh(
          new THREE.TubeGeometry(curve, 40, 0.009, 5, false),
          new THREE.MeshBasicMaterial({
            color: "#97c2ff",
            transparent: true,
            opacity: 0.17,
            depthWrite: false,
            blending: THREE.AdditiveBlending,
          }),
        ),
      );
      if (seen.size % 3 !== 2) pulse(curve, zone(b.userData.n).color, key);
    }),
  );
}
function setup() {
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(38, 1, 0.02, 100);
  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.setClearColor(0, 0);
  host.value.append(renderer.domElement);
  controls = new OrbitControls(camera, renderer.domElement);
  controls.enablePan = false;
  controls.enableDamping = true;
  controls.dampingFactor = 0.06;
  controls.minDistance = 0.65;
  controls.maxDistance = 52;
  controls.zoomSpeed = 1.25;
  controls.autoRotate = true;
  controls.autoRotateSpeed = 0.34;
  brain = new THREE.Group();
  brain.scale.setScalar(1.22);
  brain.rotation.y = -0.36;
  scene.add(brain);
  glow = glowTexture();
  cortex();
  gyri();
  addSurfaceSignals();
  regions3d();
}
function resize(initial = false) {
  const b = host.value.getBoundingClientRect(),
    w = Math.max(1, b.width),
    h = Math.max(1, b.height);
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  const f = THREE.MathUtils.degToRad(camera.fov),
    hf = 2 * Math.atan(Math.tan(f / 2) * camera.aspect),
    d = 1.12 * Math.max(4.55 / Math.tan(f / 2), 6.55 / Math.tan(hf / 2));
  if (initial) {
    defaultDistance = d;
    camera.position.set(0, 0.2, d);
    controls.target.set(0, 0, 0);
    controls.update();
    updateZoom();
  }
  camera.updateProjectionMatrix();
}
function interactions() {
  const ray = new THREE.Raycaster(),
    ptr = new THREE.Vector2();
  host.value.addEventListener("pointerdown", () => {
    controls.autoRotate = false;
    clearTimeout(host.value.timer);
  });
  host.value.addEventListener("pointerup", (e) => {
    host.value.timer = setTimeout(() => (controls.autoRotate = true), 4200);
    const b = host.value.getBoundingClientRect();
    ptr.set(
      ((e.clientX - b.left) / b.width) * 2 - 1,
      (-(e.clientY - b.top) / b.height) * 2 + 1,
    );
    ray.setFromCamera(ptr, camera);
    const h = ray.intersectObjects(pick, false)[0];
    if (h) selectConcept(h.object.userData.g.userData.n);
  });
  host.value.addEventListener(
    "wheel",
    () => {
      controls.autoRotate = false;
      clearTimeout(host.value.timer);
      host.value.timer = setTimeout(() => (controls.autoRotate = true), 4200);
    },
    { passive: true },
  );
}
const regionNodeRefs = new Map();
function setRegionNodeRef(id, element) {
  if (element) regionNodeRefs.set(id, element);
  else regionNodeRefs.delete(id);
}
function selectRegion(id) {
  active.value = id;
  regionDrawerOpen.value = true;
  selected.value = null;
  selectedDetail.value = null;
  selectedEvidence.value = null;
  focusRegion(id);
}
function clearRegion() {
  regionDrawerOpen.value = false;
  active.value = null;
  selected.value = null;
  detailExpanded.value = false;
  selectedDetail.value = null;
  selectedEvidence.value = null;
  focusState = null;
  resetView();
}
function focusRegion(id) {
  if (!controls || !brain) return;
  const region = zoneById[id];
  const target = new THREE.Vector3(...region.a).applyMatrix4(brain.matrixWorld);
  const direction = camera.position.clone().sub(controls.target).normalize();
  focusState = {
    target,
    camera: target
      .clone()
      .addScaledVector(direction, Math.max(5.2, defaultDistance * 0.7)),
  };
  controls.autoRotate = false;
}
function updateZoom() {
  if (!camera || !controls) return;
  const distance = camera.position.distanceTo(controls.target);
  zoomPercent.value = Math.round((defaultDistance / distance) * 100);
  const fade = Math.max(0.045, Math.min(1, (distance - 1.8) / 5.8));
  cortexMaterials.forEach(([material, opacity]) => {
    material.opacity = opacity * fade;
  });
  gyrusMaterials.forEach(([material, opacity]) => {
    material.opacity = opacity * fade;
  });
  surfaceSignalMaterials.forEach(([material, opacity]) => {
    material.opacity = opacity * Math.max(0.14, fade);
  });
}
function setZoom(value) {
  if (!camera || !controls) return;
  const percent = Math.max(30, Math.min(1500, Number(value) || 100)),
    distance = Math.max(
      controls.minDistance,
      Math.min(controls.maxDistance, (defaultDistance * 100) / percent),
    ),
    direction = camera.position.clone().sub(controls.target).normalize();
  camera.position.copy(controls.target).addScaledVector(direction, distance);
  controls.update();
  updateZoom();
}
function zoomBy(multiplier) {
  if (!camera || !controls) return;
  const current = camera.position.distanceTo(controls.target);
  setZoom(
    (defaultDistance /
      Math.max(
        controls.minDistance,
        Math.min(controls.maxDistance, current * multiplier),
      )) *
      100,
  );
}
function resetView() {
  if (!camera || !controls) return;
  focusState = null;
  camera.position.set(0, 0.2, defaultDistance);
  controls.target.set(0, 0, 0);
  controls.autoRotate = true;
  controls.update();
  updateZoom();
}
function lockInBrain(node) {
  const group = groups.find((item) => item.userData.n.id === node.id);
  if (!group || !camera || !controls) return;
  const target = new THREE.Vector3();
  group.getWorldPosition(target);
  const direction = camera.position.clone().sub(controls.target).normalize();
  focusState = {
    target,
    camera: target
      .clone()
      .addScaledVector(
        direction,
        Math.max(2.25, Math.min(defaultDistance * 0.46, 5.4)),
      ),
  };
  controls.autoRotate = false;
}
async function selectConcept(node) {
  active.value = zone(node).id;
  regionDrawerOpen.value = true;
  lockInBrain(node);
  selected.value = node;
  detailExpanded.value = true;
  nextTick(() =>
    regionNodeRefs
      .get(node.id)
      ?.scrollIntoView({ behavior: "smooth", block: "nearest" }),
  );
  selectedDetail.value = null;
  selectedEvidence.value = null;
  detailLoading.value = false;
  try {
    const [detail, evidence] = await Promise.all([
      nodeApi.getById(node.id),
      nodeApi.getEvidence(node.id).catch(() => null),
    ]);
    selectedDetail.value = detail;
    selectedEvidence.value = evidence;
  } catch (error) {
    console.warn("知识节点详情加载失败:", error);
  } finally {
    detailLoading.value = false;
  }
}
function findResumeSession() {
  const sessionSource = selectedEvidence.value?.source_details?.find(
    (source) =>
      source.source_type === "session" && (source.id || source.source_id),
  );
  if (sessionSource) return sessionSource;

  const studyLog = selectedEvidence.value?.study_logs?.find(
    (log) => log.session_id,
  );
  if (studyLog) {
    return { id: studyLog.session_id };
  }

  const quiz = selectedEvidence.value?.quizzes?.find((item) => item.session_id);
  if (quiz) {
    return { id: quiz.session_id, title: quiz.session_title };
  }

  return null;
}
function review() {
  router.push({ path: "/quiz", query: { nodeId: selected.value?.id } });
}
function learn() {
  const resumeSession = findResumeSession();
  if (resumeSession) {
    const title = resumeSession.title || resumeSession.source_title || "";
    router.push({
      path: title.startsWith("[AI课程]") ? "/immersive" : "/chat",
      query: { session_id: resumeSession.id || resumeSession.source_id },
    });
    return;
  }

  router.push({ path: "/chat", query: { topic: selected.value.title } });
}
function loop(t = 0) {
  raf = requestAnimationFrame(loop);
  if (focusState) {
    controls.target.lerp(focusState.target, 0.11);
    camera.position.lerp(focusState.camera, 0.11);
    if (
      controls.target.distanceTo(focusState.target) < 0.015 &&
      camera.position.distanceTo(focusState.camera) < 0.02
    )
      focusState = null;
  }
  controls.update();
  updateZoom();
  Object.entries(volumes).forEach(([id, g]) => {
    const show = !active.value || active.value === id;
    g.scale.setScalar(show ? 1 : 0.52);
    g.userData.mist.material.opacity = show ? 0.12 : 0.008;
    g.userData.motes.material.opacity = show ? 0.3 : 0.018;
    g.rotation.y = Math.sin(t * 0.0003 + g.userData.phase) * 0.07;
  });
  pulses.forEach((p) => {
    const u = (p.offset + t * 0.000055 * p.speed * 60) % 1;
    p.core.position.copy(p.curve.getPointAt(u));
    p.core.material.opacity = 0.74 + 0.25 * Math.sin(t * 0.006 + p.phase);
    p.tail.forEach((s, i) => {
      s.position.copy(p.curve.getPointAt((u - (i + 1) * 0.026 + 1) % 1));
      s.material.opacity = 0.32 - i * 0.052;
    });
  });
  surfacePulses.forEach((p) => {
    const u = (p.offset + t * 0.000037 * p.speed * 60) % 1;
    p.core.position.copy(p.curve.getPointAt(u));
    p.core.material.opacity = 0.62 + 0.3 * Math.sin(t * 0.005 + p.phase);
    p.tail.forEach((s, i) => {
      s.position.copy(p.curve.getPointAt((u - (i + 1) * 0.021 + 1) % 1));
      s.material.opacity = 0.25 - i * 0.05;
    });
  });
  groups.forEach((g) => {
    const n = g.userData.n,
      sel = selected.value?.id === n.id,
      show = !active.value || zone(n).id === active.value,
      frontier = !!n.is_frontier;
    g.position.y =
      g.userData.home.y + Math.sin(t * 0.0011 + g.userData.phase) * 0.028;
    g.scale.setScalar(sel ? 1.85 : show ? (frontier ? 1.18 : 1) : 0.58);
    g.children[0].material.opacity = sel
      ? 1
      : show
        ? frontier
          ? 0.82
          : 0.25 + (n.mastery_level || 0) * 0.58
        : 0.025;
    g.children[1].material.opacity = sel
      ? 1
      : show
        ? frontier
          ? 0.95
          : 0.42 + (n.mastery_level || 0) * 0.52
        : 0.06;
    if (frontier && g.children[2]) {
      g.children[2].position.y =
        0.2 + Math.sin(t * 0.002 + g.userData.phase) * 0.07;
      g.children[2].material.opacity =
        0.38 + 0.32 * Math.sin(t * 0.002 + g.userData.phase);
    }
  });
  renderer.render(scene, camera);
}
onMounted(async () => {
  setup();
  try {
    const payload = await api.get("/api/learning-map/brain");
    const map = normalizeBrainMap(payload);
    nodes.value = map.nodes;
    mapSource.value = map.source;
    await nextTick();
    nodes.value.forEach(addNode);
    links();
    interactions();
    ro = new ResizeObserver(() => resize());
    ro.observe(host.value);
    requestAnimationFrame(() => resize(true));
    loop();
  } catch (e) {
    console.warn("知识大脑加载失败", e);
  } finally {
    loading.value = false;
  }
});
onBeforeUnmount(() => {
  cancelAnimationFrame(raf);
  ro?.disconnect();
  controls?.dispose();
  renderer?.dispose();
  glow?.dispose();
});
</script>
<style scoped>
.brain-page {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 650px;
  overflow: hidden;
  color: #eff5ff;
  background: radial-gradient(
    ellipse at 50% 46%,
    #12346e 0%,
    #081934 40%,
    #02050d 80%
  );
}
.brain-page:before {
  position: absolute;
  z-index: 0;
  inset: -15%;
  content: "";
  pointer-events: none;
  opacity: 0.9;
  filter: blur(30px);
  background:
    radial-gradient(circle at 45% 48%, rgb(54 169 255 / 19%), transparent 22%),
    radial-gradient(circle at 61% 40%, rgb(148 94 255 / 12%), transparent 22%),
    radial-gradient(circle at 48% 72%, rgb(64 231 213 / 8%), transparent 20%);
  animation: drift 15s ease-in-out infinite alternate;
}
.brain-page:after {
  position: absolute;
  z-index: 0;
  inset: 0;
  content: "";
  pointer-events: none;
  opacity: 0.32;
  background-image: radial-gradient(
    rgb(165 198 255 / 22%) 0.65px,
    transparent 0.8px
  );
  background-size: 48px 48px;
  mask-image: radial-gradient(ellipse at center, #000 0%, transparent 77%);
}
@keyframes drift {
  to {
    transform: translate3d(2%, -2%, 0) scale(1.08);
  }
}
.canvas {
  position: absolute;
  z-index: 1;
  inset: 0;
  overflow: hidden;
  cursor: grab;
}
.canvas:active {
  cursor: grabbing;
}
.canvas :deep(canvas) {
  position: absolute;
  inset: 0;
  display: block;
  width: 100% !important;
  height: 100% !important;
}
header {
  position: absolute;
  z-index: 3;
  top: 36px;
  left: 43px;
  pointer-events: none;
}
header p {
  margin: 0 0 10px;
  color: #a6c7ff;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.21em;
}
h1 {
  margin: 0;
  font-size: 34px;
  letter-spacing: -0.06em;
}
header span {
  display: block;
  margin-top: 9px;
  color: #adbedb;
  font-size: 14px;
}
.stats {
  position: absolute;
  z-index: 3;
  top: 36px;
  right: 42px;
  display: flex;
  gap: 26px;
  padding: 13px 18px;
  border: 1px solid rgb(163 202 255 / 20%);
  border-radius: 16px;
  background: rgb(4 13 31 / 56%);
  backdrop-filter: blur(16px);
  color: #9eafcd;
  font-size: 11px;
}
.stats b {
  display: block;
  margin-bottom: 3px;
  color: #fff;
  font-size: 19px;
}
.frontier-stat {
  padding: 0;
  border: 0;
  color: #ffe6a5;
  background: transparent;
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.frontier-stat b {
  color: #fff0bd;
  text-shadow: 0 0 14px rgb(255 216 122 / 58%);
}
.recommendation {
  min-height: 0 !important;
  margin: -8px 0 16px !important;
  padding: 10px 11px;
  border: 1px solid rgb(255 225 151 / 22%);
  border-radius: 10px;
  color: #ffe6ae !important;
  background: rgb(255 213 104 / 8%);
  font-size: 12px !important;
  line-height: 1.55 !important;
}
nav {
  position: absolute;
  z-index: 4;
  top: 182px;
  left: 42px;
  display: grid;
  gap: 5px;
  width: 158px;
}
nav button {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  padding: 8px 9px;
  border: 1px solid transparent;
  border-radius: 9px;
  color: #acbdd9;
  background: transparent;
  text-align: left;
  cursor: pointer;
  transition: 0.2s;
}
nav button:hover,
nav button.active {
  color: #f8fbff;
  border-color: rgb(176 210 255 / 20%);
  background: rgb(123 160 227 / 13%);
}
nav i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  box-shadow: 0 0 13px currentColor;
}
nav b {
  margin-left: auto;
  color: #8294b7;
  font-size: 11px;
}
.legend {
  position: absolute;
  z-index: 3;
  bottom: 31px;
  left: 43px;
  color: #8fa2c2;
  font-size: 11px;
  pointer-events: none;
}
.legend i {
  display: inline-block;
  width: 6px;
  height: 6px;
  margin: 0 7px 1px 0;
  border-radius: 50%;
  background: #8ab4ff;
  box-shadow: 0 0 12px #8ab4ff;
}
.legend span {
  opacity: 0.38;
}
.legend em {
  color: #ffe8a2;
  font-style: normal;
  text-shadow: 0 0 12px #ffe8a2;
}
.hint {
  position: absolute;
  z-index: 3;
  right: 43px;
  bottom: 31px;
  color: #8597b8;
  font-size: 11px;
  pointer-events: none;
}
.caption {
  position: absolute;
  z-index: 3;
  bottom: 30px;
  left: 50%;
  transform: translateX(-50%);
  padding: 8px 13px;
  border: 1px solid rgb(180 210 255 / 16%);
  border-radius: 99px;
  color: #bdcde8;
  background: rgb(5 15 36 / 56%);
  backdrop-filter: blur(10px);
  font-size: 12px;
  white-space: nowrap;
  pointer-events: none;
}
.region-drawer {
  position: fixed;
  z-index: 1000;
  top: 181px;
  right: 42px;
  width: 348px;
  max-height: calc(100% - 220px);
  padding: 23px 17px 17px;
  border: 1px solid rgb(193 219 255 / 30%);
  border-radius: 18px;
  background: linear-gradient(145deg, rgb(22 46 88 / 96%), rgb(4 13 31 / 97%));
  box-shadow: 0 28px 75px rgb(0 0 0 / 52%);
  backdrop-filter: blur(22px);
  overflow: auto;
}
.region-drawer {
  display: block !important;
  visibility: visible !important;
}
.region-drawer > small {
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.17em;
}
.region-drawer h2 {
  margin: 7px 0 0;
  font-size: 23px;
  letter-spacing: -0.05em;
}
.region-drawer > p {
  margin: 8px 0 14px;
  color: #aebfdb;
  font-size: 12px;
  line-height: 1.55;
}
.region-close {
  position: absolute;
  z-index: 2;
  top: 11px;
  right: 12px;
  width: 30px;
  height: 30px;
  border: 1px solid rgb(186 213 255 / 22%);
  border-radius: 7px;
  color: #d8e8ff;
  background: rgb(125 164 232 / 12%);
  font-size: 20px;
  line-height: 22px;
  cursor: pointer;
}
.region-close:hover {
  background: rgb(125 164 232 / 25%);
}
.region-node-list {
  display: grid;
  gap: 7px;
}
.region-node-item {
  overflow: hidden;
  border: 1px solid transparent;
  border-radius: 10px;
  background: rgb(110 144 205 / 8%);
}
.region-node-item:hover {
  border-color: rgb(166 203 255 / 26%);
  background: rgb(126 165 231 / 16%);
}
.region-node-item.frontier {
  border-color: rgb(255 223 143 / 24%);
  background: rgb(255 213 104 / 9%);
}
.region-node-item.selected {
  border-color: rgb(151 194 255 / 48%);
  background: rgb(104 155 235 / 19%);
  box-shadow: 0 0 19px rgb(105 173 255 / 13%);
}
.region-node-trigger {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  padding: 10px;
  border: 0;
  color: #d9e6fb;
  background: transparent;
  text-align: left;
  cursor: pointer;
}
.region-node-trigger i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  box-shadow: 0 0 11px currentColor;
}
.region-node-trigger span {
  display: grid;
  min-width: 0;
  gap: 2px;
  flex: 1;
}
.region-node-trigger strong {
  overflow: hidden;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.region-node-trigger small {
  overflow: hidden;
  color: #9cafcf;
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.region-node-trigger b {
  color: #dbe8ff;
  font-size: 11px;
}
.locked-node-detail {
  padding: 0 10px 10px;
  border-top: 1px solid rgb(177 207 255 / 13%);
  color: #b8c9e4;
  font-size: 11px;
  line-height: 1.55;
}
.selected-intro {
  margin: 8px 0;
}
.detail-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 7px 0;
  border: 0;
  border-top: 1px solid rgb(177 207 255 / 12%);
  border-bottom: 1px solid rgb(177 207 255 / 12%);
  color: #dceaff;
  background: transparent;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
}
.detail-toggle span {
  font-size: 15px;
}
.full-node-detail {
  padding-top: 4px;
}
.reading-section {
  padding: 11px 0;
  border-bottom: 1px solid rgb(177 207 255 / 11%);
}
.reading-section h3 {
  margin: 0 0 6px;
  color: #e4efff;
  font-size: 11px;
}
.reading-section p {
  margin: 0;
  color: #b8c9e4;
}
.reading-section ul {
  margin: 0;
  padding-left: 17px;
}
.reading-section li + li {
  margin-top: 4px;
}
.summary-copy {
  white-space: pre-wrap;
}
.caution h3 {
  color: #ffd991;
}
.evidence-section p {
  line-height: 1.6;
}
.source-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 7px;
}
.source-list span {
  padding: 3px 5px;
  border-radius: 5px;
  color: #acc4e8;
  background: rgb(142 180 244 / 12%);
  font-size: 10px;
}
.detail-related-list {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}
.detail-related-list button {
  padding: 4px 6px;
  border: 1px solid rgb(154 190 245 / 20%);
  border-radius: 6px;
  color: #d7e6ff;
  background: rgb(99 141 214 / 12%);
  font-size: 10px;
  cursor: pointer;
}
.detail-related-list button span {
  margin-right: 4px;
  color: #8cb5ff;
}
.locked-actions {
  display: flex;
  gap: 6px;
  padding-top: 10px;
}
.locked-actions button {
  flex: 1;
  padding: 6px;
  border: 1px solid rgb(154 190 245 / 25%);
  border-radius: 6px;
  color: #d8e8ff;
  background: rgb(99 141 214 / 15%);
  font-size: 11px;
  cursor: pointer;
}
.locked-actions button:hover {
  background: rgb(99 141 214 / 30%);
}
.region-empty {
  padding: 18px 8px;
  color: #96a9c9;
  font-size: 12px;
  text-align: center;
}
.panel {
  position: absolute;
  z-index: 6;
  top: 151px;
  right: 42px;
  width: 300px;
  padding: 25px;
  border: 1px solid rgb(193 219 255 / 25%);
  border-radius: 18px;
  background: linear-gradient(145deg, rgb(22 46 88 / 89%), rgb(4 13 31 / 90%));
  box-shadow: 0 28px 75px rgb(0 0 0 / 44%);
  backdrop-filter: blur(21px);
}
.close {
  position: absolute;
  top: 10px;
  right: 13px;
  border: 0;
  color: #aabbd9;
  background: transparent;
  font-size: 25px;
  cursor: pointer;
}
.panel small {
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.17em;
}
.panel h2 {
  margin: 8px 0 0;
  font-size: 25px;
  letter-spacing: -0.05em;
}
.panel > p {
  min-height: 44px;
  margin: 10px 0 20px;
  color: #b8c6dd;
  font-size: 13px;
  line-height: 1.65;
}
.metric {
  display: flex;
  justify-content: space-between;
  color: #a9b9d5;
  font-size: 12px;
}
.metric b {
  color: #fff;
}
.track {
  height: 4px;
  margin: 9px 0 15px;
  overflow: hidden;
  border-radius: 99px;
  background: rgb(194 217 255 / 14%);
}
.track i {
  display: block;
  height: 100%;
  border-radius: inherit;
}
.note {
  padding: 0 0 13px;
  color: #a9bbd9;
  font-size: 12px;
}
.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  padding: 15px 0 17px;
  border-top: 1px solid rgb(193 216 255 / 15%);
}
.tags span {
  padding: 4px 7px;
  border-radius: 6px;
  color: #cfdbf3;
  background: rgb(142 180 244 / 14%);
  font-size: 11px;
}
.zoom-controls {
  position: absolute;
  z-index: 5;
  top: 128px;
  right: 42px;
  display: flex;
  align-items: center;
  gap: 3px;
  padding: 3px;
  overflow: hidden;
  border: 1px solid rgb(193 219 255 / 24%);
  border-radius: 10px;
  background: rgb(4 13 31 / 64%);
  backdrop-filter: blur(13px);
}
.zoom-controls button {
  width: 34px;
  height: 34px;
  border: 0;
  border-radius: 7px;
  color: #d9e7ff;
  background: transparent;
  font-size: 19px;
  cursor: pointer;
}
.zoom-controls .zoom-label {
  width: 52px;
  border-inline: 1px solid rgb(193 219 255 / 18%);
  border-radius: 0;
  font-size: 11px;
}
.zoom-controls input {
  width: 96px;
  accent-color: #86b7ff;
  cursor: pointer;
}
.zoom-controls button:hover {
  background: rgb(125 163 235 / 16%);
}
.state-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  padding: 0 0 13px;
  color: #a9bbd9;
  font-size: 11px;
}
.state-grid span {
  padding: 3px 6px;
  border-radius: 5px;
  background: rgb(142 180 244 / 10%);
}
.detail-section {
  padding: 12px 0;
  border-top: 1px solid rgb(193 216 255 / 15%);
  color: #b7c7e1;
  font-size: 12px;
  line-height: 1.55;
}
.detail-section h3 {
  margin: 0 0 6px;
  color: #dbe8ff;
  font-size: 12px;
}
.detail-section p {
  min-height: 0;
  margin: 0;
}
.detail-section ul {
  margin: 0;
  padding-left: 17px;
}
.detail-section li + li {
  margin-top: 3px;
}
.detail-loading {
  padding: 12px 0;
  color: #93a9cc;
  font-size: 12px;
}
.related-list {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  padding: 0 0 12px;
}
.related-list button {
  padding: 4px 7px;
  border: 1px solid rgb(160 191 241 / 18%);
  border-radius: 6px;
  color: #cddcf6;
  background: rgb(142 180 244 / 10%);
  font-size: 11px;
  cursor: pointer;
}
.actions {
  display: flex;
  gap: 7px;
}
.actions .go {
  flex: 1;
}
.review {
  padding: 0 10px;
  border: 1px solid rgb(150 184 242 / 25%);
  border-radius: 10px;
  color: #d7e5ff;
  background: rgb(89 124 191 / 16%);
  font-size: 12px;
  cursor: pointer;
}
.go,
.empty button {
  width: 100%;
  padding: 11px;
  border: 0;
  border-radius: 10px;
  color: #fff;
  background: linear-gradient(100deg, #8274ff, #52c4e6);
  font-weight: 800;
  cursor: pointer;
}
.go b {
  float: right;
  font-size: 16px;
}
.empty {
  position: absolute;
  z-index: 4;
  top: 50%;
  left: 50%;
  width: min(360px, calc(100% - 48px));
  transform: translate(-50%, -50%);
  text-align: center;
}
.empty strong {
  color: #90b6ff;
  font-size: 32px;
  text-shadow: 0 0 30px #6995ff;
}
.empty h2 {
  margin: 15px 0 8px;
  font-size: 21px;
}
.empty p {
  color: #aab9d8;
  font-size: 13px;
  line-height: 1.6;
}
.empty button {
  width: auto;
  margin-top: 8px;
  padding: 10px 17px;
}
.loading {
  position: absolute;
  z-index: 5;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  color: #b9c9ea;
  font-size: 13px;
}
@media (max-width: 800px) {
  .brain-page {
    min-height: 580px;
  }
  header {
    top: 24px;
    left: 20px;
  }
  h1 {
    font-size: 28px;
  }
  .stats,
  .hint,
  .caption,
  .legend {
    display: none;
  }
  .zoom-controls {
    top: auto;
    right: 14px;
    bottom: 94px;
  }
  nav {
    top: auto;
    bottom: 13px;
    left: 14px;
    grid-template-columns: repeat(3, 1fr);
    width: calc(100% - 28px);
  }
  nav button {
    padding: 7px 4px;
    font-size: 11px;
  }
  .region-drawer {
    position: fixed;
    top: auto;
    right: 14px;
    bottom: 96px;
    left: 14px;
    width: auto;
    max-height: calc(100% - 190px);
  }
}
</style>
