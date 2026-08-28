#!/usr/bin/env node
/**
 * BingeMate 集成构建脚本（WeSmartFlow examples 构建契约）
 *
 * 契约来自 examples/README.md 第 4 节，由 examples/build.mjs 注入三个环境变量：
 *   WESMARTFLOW_EXAMPLE_ID          当前主题 id
 *   WESMARTFLOW_EXAMPLE_OUT_DIR     必须写入的绝对临时目录
 *   WESMARTFLOW_EXAMPLE_PUBLIC_PATH 部署后的公开根路径，例如 /bingemate/
 *
 * 本 Demo 是纯静态页面，没有打包步骤：
 * 页面内所有资源引用都是**同目录相对路径**（styles.css / app.js / *.mp4），
 * 因此原样复制即可在任意 publicPath 下正确解析，不需要重写 HTML。
 *
 * 未设置 OUT_DIR 时（即 `npm run build`）输出到本目录 dist/，用于独立构建验证。
 */

import { cpSync, existsSync, mkdirSync, rmSync, statSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const projectDir = dirname(fileURLToPath(import.meta.url));

/**
 * 需要进入产物的文件白名单。
 * 刻意用白名单而不是「排除法」，避免 README、EXTENSIONS.md、node_modules、
 * 日志或临时文件被一起发布到公开目录。新增素材时记得同步这里。
 */
const ASSETS = [
  "index.html",
  "app.js",
  "data.js",
  "styles.css",
  "friends_pivot.mp4",
  "raw_avengers.mp4",
  "cover_friends.jpg",
  "cover_avengers.jpg",
];

const ENTRY_FILE = "index.html";

function fail(message) {
  console.error(`[bingemate] ${message}`);
  process.exit(1);
}

const exampleId = process.env.WESMARTFLOW_EXAMPLE_ID || "bingemate";
const publicPath = process.env.WESMARTFLOW_EXAMPLE_PUBLIC_PATH || "/bingemate/";
const integratedOut = process.env.WESMARTFLOW_EXAMPLE_OUT_DIR;
const outDir = integratedOut ? resolve(integratedOut) : resolve(projectDir, "dist");
const mode = integratedOut ? "集成构建" : "独立构建";

const missing = ASSETS.filter((name) => !existsSync(resolve(projectDir, name)));
if (missing.length) fail(`缺少源文件：${missing.join(", ")}`);

rmSync(outDir, { recursive: true, force: true });
mkdirSync(outDir, { recursive: true });

let bytes = 0;
for (const name of ASSETS) {
  const from = resolve(projectDir, name);
  cpSync(from, resolve(outDir, name), { recursive: true });
  bytes += statSync(from).size;
}

// 入口文件缺失属于构建失败：非零退出，避免编排器把不完整产物替换掉上一份可用产物。
if (!existsSync(resolve(outDir, ENTRY_FILE))) {
  fail(`构建完成但缺少入口文件：${ENTRY_FILE}`);
}

console.log(`[bingemate] ${mode} id=${exampleId} publicPath=${publicPath}`);
console.log(`[bingemate] 产物目录 ${outDir}`);
console.log(
  `[bingemate] 复制 ${ASSETS.length} 个文件，共 ${(bytes / 1024 / 1024).toFixed(1)} MB`,
);
