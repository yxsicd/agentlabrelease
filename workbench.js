"use strict";
(() => {
  const workspace = document.getElementById("workspace");
  const frame = document.getElementById("report-frame");
  const overview = document.getElementById("overview");
  const loading = document.getElementById("loading");
  const backdrop = document.getElementById("drawer-backdrop");
  const mobile = matchMedia("(max-width:760px)");
  const labels = {"model-campaign":"三模型同题评测","frozen-cohort":"冻结整题与跨机还原",process:"调用收益证据",judgment:"判定与完整性",difficulty:"难点与能力路径","assistance-ledger":"11项帮助台账","protocol-ready":"可比运行输入",protocol:"评测协议与配置",results:"阶段结果与口径",cost:"耗时与Token证据",attribution:"学生／Harness归因",gaps:"正式评测剩余差距",overview:"总体概览",report:"完整评测报告",capabilities:"能力与难点",help:"教师帮助归因",history:"执行轨迹摘要",portability:"跨机迁移复核"};
  const base = new URL("reports/calendar/2026-10-25-v7/", location.href);
  const storageKey = "agentlab.public-workbench.v1";
  const defaults = {view:"overview",left:true,right:true,bottom:true,leftSize:224,rightSize:278,bottomSize:166};
  let state = {...defaults};
  let drawer = null;
  let loaded = false;
  let pendingDrag = null;
  let dragSnapshot = null;
  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey));
    if (saved && typeof saved === "object") {
      if (Object.hasOwn(labels, saved.view)) state.view = saved.view;
      for (const side of ["left", "right", "bottom"]) {
        if (typeof saved[side] === "boolean") state[side] = saved[side];
        if (Number.isFinite(saved[side + "Size"])) state[side + "Size"] = clamp(saved[side + "Size"], 90, 380);
      }
    }
  } catch (_) { /* Storage can be unavailable in private browser sessions. */ }
  function save() {
    try { localStorage.setItem(storageKey, JSON.stringify(state)); } catch (_) {}
  }
  function limits(side) {
    if (side === "bottom") return [90, Math.max(90, Math.min(360, workspace.clientHeight - 200))];
    const other = side === "left" ? "right" : "left";
    const minimum = side === "left" ? 160 : 200;
    return [minimum, Math.max(minimum, Math.min(380, workspace.clientWidth - 320 - (state[other] ? state[other + "Size"] : 0)))];
  }
  function panels() {
    for (const side of ["left", "right", "bottom"]) {
      workspace.classList.toggle("no-" + side, !state[side]);
      if (!mobile.matches || side === "bottom") {
        const [min, max] = limits(side);
        state[side + "Size"] = clamp(state[side + "Size"], min, max);
      }
      workspace.style.setProperty("--" + side + "-size", state[side + "Size"] + "px");
      const pressed = mobile.matches && side !== "bottom" ? drawer === side : state[side];
      const button = document.getElementById("toggle-" + side);
      button.setAttribute("aria-pressed", String(pressed));
      button.setAttribute("aria-controls", side === "left" ? "report-explorer" : side === "right" ? "assessment-context" : "evidence-panel");
      const handle = document.querySelector('[data-split="' + side + '"]');
      const [min, max] = limits(side);
      handle.setAttribute("aria-valuemin", min);
      handle.setAttribute("aria-valuemax", max);
      handle.setAttribute("aria-valuenow", state[side + "Size"]);
      handle.setAttribute("aria-valuetext", Math.round(state[side + "Size"]) + " 像素");
    }
    workspace.classList.toggle("mobile-left", drawer === "left");
    workspace.classList.toggle("mobile-right", drawer === "right");
    backdrop.hidden = !drawer;
    save();
  }
  function closeDrawer(restoreFocus = false) {
    const previous = drawer;
    drawer = null;
    panels();
    if (restoreFocus && previous) document.getElementById("toggle-" + previous).focus();
  }
  function setBusy(busy) {
    loading.hidden = !busy;
    frame.setAttribute("aria-busy", String(busy));
  }
  function scrollSection() {
    if (!loaded) return;
    const doc = frame.contentDocument;
    if (state.view === "report") frame.contentWindow.scrollTo(0, 0);
    else doc.getElementById(state.view)?.scrollIntoView({block:"start"});
  }
  function select() {
    const requested = location.hash.slice(1);
    if (Object.hasOwn(labels, requested)) state.view = requested;
    const home = state.view === "overview";
    overview.hidden = !home;
    frame.hidden = home;
    if (!home && !frame.hasAttribute("src")) {
      setBusy(true);
      frame.src = base.href;
    } else {
      setBusy(false);
      if (!home) scrollSection();
    }
    document.querySelectorAll("[data-view]").forEach(el => {
      const active = el.dataset.view === state.view || (el.closest(".tabs") && el.dataset.view === "report" && !home);
      el.classList.toggle("active", Boolean(active));
      if (active) el.setAttribute("aria-current", "page");
      else el.removeAttribute("aria-current");
    });
    document.getElementById("breadcrumb").textContent = "报告 / Calendar / " + labels[state.view];
    document.getElementById("status-view").textContent = labels[state.view];
    const external = document.querySelector(".tabs .external");
    external.href = base.href + (!home && state.view !== "report" ? "#" + state.view : "");
    save();
  }
  function navigate(view) {
    if (location.hash === "#" + view) select();
    else location.hash = view;
  }
  frame.addEventListener("load", () => {
    try {
      const doc = frame.contentDocument;
      // Route report links through the parent shell, avoiding nested workbenches.
      doc.addEventListener("click", event => {
        const link = event.target.closest("a[href]");
        if (!link || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        const url = new URL(link.getAttribute("href"), base);
        const root = new URL(".", location.href);
        if (url.origin === root.origin && url.pathname === root.pathname) {
          event.preventDefault(); navigate("overview");
        } else if (url.origin === base.origin && url.pathname === base.pathname && Object.hasOwn(labels, url.hash.slice(1))) {
          event.preventDefault(); navigate(url.hash.slice(1));
        }
      });
      doc.querySelectorAll("a[href]").forEach(link => {
        const url = new URL(link.getAttribute("href"), base);
        if (url.origin !== base.origin || url.pathname.endsWith(".json") || (url.pathname !== base.pathname && url.pathname.includes("/reports/"))) {
          link.target = "_blank"; link.rel = "noopener";
        }
      });
      doc.addEventListener("click", event => {
        const link=event.target.closest('a[href^="#run-"]');
        if (!link) return;
        const reset=doc.getElementById("reset-runs");
        if (reset) reset.click();
      });
      loaded = true;
      setBusy(false);
      if (state.view !== "overview") scrollSection();
    } catch (_) {
      setBusy(false);
      // The standalone report remains available if embedding is restricted.
      document.getElementById("status-view").textContent = "报告内嵌受限，请使用「独立打开」";
    }
  });
  for (const side of ["left", "right", "bottom"]) {
    document.getElementById("toggle-" + side).addEventListener("click", () => {
      if (side !== "bottom" && mobile.matches) drawer = drawer === side ? null : side;
      else state[side] = !state[side];
      panels();
    });
  }
  document.getElementById("bottom-close").addEventListener("click", () => {state.bottom = false; panels();});
  document.getElementById("reset-layout").addEventListener("click", () => {
    state = {...defaults, view:state.view}; drawer = null; panels();
  });
  backdrop.addEventListener("click", () => closeDrawer(true));
  addEventListener("hashchange", () => {closeDrawer(); select();});
  addEventListener("resize", panels);
  mobile.addEventListener("change", () => closeDrawer());
  document.addEventListener("keydown", event => {if (event.key === "Escape") closeDrawer(true);});
  for (const handle of document.querySelectorAll("[data-split]")) {
    const side = handle.dataset.split;
    handle.addEventListener("pointerdown", event => {
      if (mobile.matches || event.button !== 0) return;
      event.preventDefault(); handle.focus(); handle.setPointerCapture(event.pointerId);
      dragSnapshot = {start:side === "bottom" ? event.clientY : event.clientX, size:state[side + "Size"]};
      pendingDrag = side;
      workspace.classList.add("resizing");
    });
    handle.addEventListener("pointermove", event => {
      if (pendingDrag !== side) return;
      const current = side === "bottom" ? event.clientY : event.clientX;
      const direction = side === "left" ? 1 : -1;
      const [min, max] = limits(side);
      state[side + "Size"] = Math.round(clamp(dragSnapshot.size + direction * (current - dragSnapshot.start), min, max));
      panels();
    });
    const end = () => {pendingDrag = null; workspace.classList.remove("resizing"); save();};
    handle.addEventListener("pointerup", end);
    handle.addEventListener("pointercancel", end);
    handle.addEventListener("lostpointercapture", end);
    handle.addEventListener("dblclick", () => {state[side + "Size"] = defaults[side + "Size"]; panels();});
    handle.addEventListener("keydown", event => {
      const backward = side === "bottom" ? "ArrowDown" : side === "left" ? "ArrowLeft" : "ArrowRight";
      const forward = side === "bottom" ? "ArrowUp" : side === "left" ? "ArrowRight" : "ArrowLeft";
      if (![backward, forward, "Home"].includes(event.key)) return;
      event.preventDefault();
      const [min, max] = limits(side);
      state[side + "Size"] = event.key === "Home" ? defaults[side + "Size"] : clamp(state[side + "Size"] + (event.key === forward ? 1 : -1) * (event.shiftKey ? 30 : 10), min, max);
      panels();
    });
  }
  document.getElementById("report-explorer").addEventListener("click", event => {
    if (event.target.closest("a[data-view]") && mobile.matches) closeDrawer();
  });
  panels(); select();
})();
