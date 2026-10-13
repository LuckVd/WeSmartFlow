export const number = (value) =>
  value == null ? "未初始化" : Number(value).toLocaleString("zh-CN");
export const time = (value) => {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf())
    ? value
    : parsed.toLocaleString("zh-CN", { hour12: false });
};
export const bindingLabel = (value) =>
  ({ email: "邮箱", github: "GitHub", wechat: "微信" })[value] || value;
export const transactionLabel = (value) =>
  ({
    signup: "注册 / 迁移赠送",
    monthly: "月度补充",
    github_star: "Star 奖励",
    credit_card_add: "积分卡充值",
    credit_card_reset: "积分卡重置",
    usage: "API 消费",
  })[value] || value;
export function pageNumber(value) {
  return Math.min(1000000, Math.max(1, Math.floor(Number(value) || 1)));
}
export async function copy(value) {
  await navigator.clipboard.writeText(value);
}
