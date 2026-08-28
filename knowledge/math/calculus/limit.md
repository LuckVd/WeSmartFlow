---
slug: limit
name: 极限
summary: 当自变量趋近某个值时，函数值无限接近的那个稳定常数。
difficulty: 3
aliases: [limit]
tags: [微积分, 极限论, 基础]

prerequisites: [function]
part_of: [calculus]
related: [continuity]
---

# 直观理解

极限刻画的是"无限接近但可能永远不到达"的现象。例如 $\frac{1}{n}$ 当 $n$ 不断增大时会越来越靠近 $0$，但永远不等于 $0$，我们说"$n \to \infty$ 时 $\frac{1}{n}$ 的极限为 $0$"。

# 严格定义

设函数 $f(x)$ 在 $x_0$ 的某去心邻域内有定义。若存在常数 $A$，使得对任意 $\varepsilon > 0$，都存在 $\delta > 0$，当 $0 < |x - x_0| < \delta$ 时恒有 $|f(x) - A| < \varepsilon$，则称 $A$ 是 $f(x)$ 当 $x \to x_0$ 时的极限。

# 例子

- $\lim_{x \to 2} (3x + 1) = 7$
- $\lim_{x \to 0} \frac{\sin x}{x} = 1$（重要极限）
- $\lim_{n \to \infty} \left(1 + \frac{1}{n}\right)^n = e$

# 易错点

- **极限存在与函数值无关**：$\lim_{x \to x_0} f(x)$ 是否存在、等于多少，与 $f(x_0)$ 是否有定义、值是多少**完全无关**。
- **左右极限必须都存在且相等**，整体极限才存在。学生常忘了检查这一点，尤其是分段函数。
