/**
 * 沉浸式课程后台生成进度的文案格式化（历史页与沉浸式横幅共用）。
 * progress 由后端 summarize_generation_progress 汇总：
 *   { phase, total, pdf, exercises, audio, kg }，各项 {done, failed, total} 或 null。
 */

const PHASE_LABEL = {
  pdf: "正在生成讲义 PDF",
  enrichment: "正在生成习题与语音",
  nodes: "正在点亮知识大脑",
  done: "正在收尾",
};

function part(label, item) {
  if (!item || !item.total) return "";
  const failed = item.failed ? `，${item.failed} 失败` : "";
  return `${label} ${item.done}/${item.total}${failed}`;
}

/** 例如：PDF 6/6 · 习题 4/6 · 语音 3/6 · 知识大脑 2/6 */
export function formatProgressParts(progress) {
  if (!progress) return "";
  return [
    part("PDF", progress.pdf),
    part("习题", progress.exercises),
    part("语音", progress.audio),
    part("知识大脑", progress.kg),
  ]
    .filter(Boolean)
    .join(" · ");
}

/** 当前阶段的一句话说明；没有进度数据时返回空串。 */
export function formatProgressPhase(progress) {
  if (!progress) return "";
  return PHASE_LABEL[progress.phase] || "";
}
