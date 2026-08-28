import "./style.css";
import "./ui-scale.css";
import { createLab } from "./app.js";

const params = new URLSearchParams(window.location.search);
const root = document.querySelector("#app");
const platformKey = "chemistry-lab:wesmartflow-entry";

try {
  if (params.get("source") === "wesmartflow") sessionStorage.setItem(platformKey, "1");
} catch {
  /* Storage can be unavailable in privacy mode. */
}

let platformHref = "";
try {
  platformHref = sessionStorage.getItem(platformKey) ? "/#/explore" : "";
} catch {
  /* Stay standalone when storage is unreadable. */
}

createLab({ root, platformHref }).render();
