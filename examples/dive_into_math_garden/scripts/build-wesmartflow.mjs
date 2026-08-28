import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT_DIR = process.env.WESMARTFLOW_EXAMPLE_OUT_DIR || path.join(ROOT, "dist");
const PUBLIC_PATH = process.env.WESMARTFLOW_EXAMPLE_PUBLIC_PATH || "./";
const ENTRY_FILE = "index.html";
const INCLUDE = [ENTRY_FILE, "css", "js"];

function assertExists(target) {
  if (!fs.existsSync(target)) {
    throw new Error(`缺少构建所需文件：${path.relative(ROOT, target)}`);
  }
}

function copyRecursive(src, dest) {
  const stat = fs.statSync(src);
  if (stat.isDirectory()) {
    fs.mkdirSync(dest, { recursive: true });
    for (const name of fs.readdirSync(src)) {
      copyRecursive(path.join(src, name), path.join(dest, name));
    }
    return;
  }
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.copyFileSync(src, dest);
}

function rewriteHtmlBase(html) {
  if (!PUBLIC_PATH || PUBLIC_PATH === "./") return html;
  const base = PUBLIC_PATH.endsWith("/") ? PUBLIC_PATH : `${PUBLIC_PATH}/`;
  return html.replace("<head>", `<head>\n  <base href="${base}">`);
}

for (const name of INCLUDE) {
  assertExists(path.join(ROOT, name));
}

fs.rmSync(OUT_DIR, { recursive: true, force: true });
fs.mkdirSync(OUT_DIR, { recursive: true });

for (const name of INCLUDE) {
  const src = path.join(ROOT, name);
  const dest = path.join(OUT_DIR, name);
  if (name === ENTRY_FILE) {
    const html = fs.readFileSync(src, "utf8");
    fs.writeFileSync(dest, rewriteHtmlBase(html), "utf8");
  } else {
    copyRecursive(src, dest);
  }
}

assertExists(path.join(OUT_DIR, ENTRY_FILE));
console.log(`走进数学花园静态产物已输出到 ${OUT_DIR}`);
