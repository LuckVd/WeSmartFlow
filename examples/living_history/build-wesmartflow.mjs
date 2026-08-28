import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)));
const OUT_DIR = process.env.WESMARTFLOW_EXAMPLE_OUT_DIR || path.join(ROOT, "dist");
const INCLUDE = ["index.html"];

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

for (const name of INCLUDE) {
  if (!fs.existsSync(path.join(ROOT, name))) {
    throw new Error(`缺少构建所需文件：${name}`);
  }
}

fs.rmSync(OUT_DIR, { recursive: true, force: true });
fs.mkdirSync(OUT_DIR, { recursive: true });

for (const name of INCLUDE) {
  copyRecursive(path.join(ROOT, name), path.join(OUT_DIR, name));
}

if (!fs.existsSync(path.join(OUT_DIR, "index.html"))) {
  throw new Error("构建产物缺少入口 index.html");
}
console.log(`living-history 构建完成 → ${OUT_DIR}`);
