/* Shared auth for same-origin example APIs. Never forward the app token to a vendor. */
(() => {
  if (window.__exampleUsageAuth) return;
  window.__exampleUsageAuth = true;
  const originalFetch = window.fetch.bind(window);
  function notice(message, login = false) {
    let banner = document.getElementById("example-usage-notice");
    if (!banner) {
      banner = document.createElement("div");
      banner.id = "example-usage-notice";
      banner.setAttribute("role", "alert");
      Object.assign(banner.style, {
        position: "fixed",
        top: "12px",
        left: "50%",
        transform: "translateX(-50%)",
        zIndex: "99999",
        padding: "12px 20px",
        background: "#fff",
        color: "#222",
        borderRadius: "12px",
        boxShadow: "0 2px 16px #0004",
      });
      document.body.appendChild(banner);
    }
    banner.textContent = message;
    if (login) {
      const link = document.createElement("a");
      link.href = "/#/login";
      link.textContent = " 前往登录";
      banner.appendChild(link);
    }
  }
  window.fetch = async (input, options = {}) => {
    const url = new URL(
      input instanceof Request ? input.url : input,
      location.href,
    );
    if (url.origin !== location.origin || !url.pathname.startsWith("/api/")) {
      return originalFetch(input, options);
    }
    const headers = new Headers(
      options.headers || (input instanceof Request ? input.headers : undefined),
    );
    const token = localStorage.getItem("wesmartflow-token");
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const response = await originalFetch(input, { ...options, headers });
    if (response.status === 401 || response.status === 403)
      notice("请登录后使用 AI 功能。", true);
    if (response.status === 429) {
      const error = await response
        .clone()
        .json()
        .catch(() => ({}));
      notice(
        error.detail || error.message || "本次请求超出用量限制，请稍后重试。",
      );
    }
    return response;
  };
})();
