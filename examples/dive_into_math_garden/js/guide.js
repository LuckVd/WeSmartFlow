/**
 * guide.js — 渐进引导引擎（当前为规则化实现）
 *
 * 职责：根据学生答错的次数，给出逐步增强、但绝不直接剧透的引导。
 * 这是「AI 引导」能力的确定性实现；未来可替换为调用真实 Agent
 * （例如把 buildHint 的决策交给 wesmartflow 的 ReAct Agent，
 * 由 LLM 生成更个性化的引导话术），接口保持 { text, highlightKeys, reveal } 不变。
 */

const layerKeys = (cells, y) => cells.filter((k) => k.split(",")[1] === String(y));

/**
 * 生成引导
 * @param {number} attempts 已答错次数（1 = 第一次答错）
 * @param {{cells: string[], layers: number, answer: number}} ctx
 * @returns {{text: string, highlightKeys: string[]|null, reveal: boolean}}
 */
function buildHint(attempts, ctx) {
  const { cells, layers, answer } = ctx;
  const layerCounts = countByLayer(cells, layers);

  if (attempts === 1) {
    return {
      text: "再仔细观察一下，有些小方块可能被前面的挡住了～试着转一转，从不同角度看。",
      highlightKeys: null,
      reveal: false,
    };
  }

  if (attempts === 2) {
    return {
      text: `试试一层一层地数。最下面这一层（已经帮你标成橙色）有几个方块？数完这层再往上数。`,
      highlightKeys: layerKeys(cells, 0),
      reveal: false,
    };
  }

  if (attempts === 3) {
    return {
      text: "换一个思路：看右边的「俯视图」——从正上方往下看，每个格子上叠了几层都标出来了，把它们加起来试试。",
      highlightKeys: null,
      reveal: false,
    };
  }

  const parts = layerCounts
    .map((n, i) => `第 ${i + 1} 层 ${n} 个`)
    .filter((_, i) => layerCounts[i] > 0);
  return {
    text: `我们一层一层看：${parts.join("，")}。合起来一共 ${answer} 个。`,
    highlightKeys: null,
    reveal: true,
  };
}

/** 用于「AI 猜」时的拟人化表达 */
function guessSpeech(count) {
  return `我数了数，从各个角度观察后，我觉得一共有 ${count} 个小立方体。对不对呢？`;
}
