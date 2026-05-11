// ── module-mode import: Mermaid ESM bundle ─────────────────────────
import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs";
window.__mermaid = mermaid;
mermaid.initialize({
  startOnLoad: false,
  securityLevel: "strict",
  theme: "base",
  themeVariables: {
    primaryColor: "#e0f2f7",
    primaryTextColor: "#06596e",
    primaryBorderColor: "#0e7a91",
    lineColor: "#0e7a91",
    secondaryColor: "#f5f5f5",
    tertiaryColor: "#fafbfc",
    fontFamily: "ui-sans-serif, system-ui, sans-serif"
  }
});

// ── main browser script (DOM wiring + tree controls + Mermaid kick) ─
(function () {
  "use strict";

  /* ── Tree IDs registered for this page ── */
  const TREE_IDS = ["im-core-tree", "pc-core-tree", "pc-exhibitor-tree",
                    "pc-visitor-tree", "ind-core-tree", "ind-view-tree"];

  /* ── Outer tab switching ── */
  const outerBtns   = document.querySelectorAll(".tab-bar > .tab-btn");
  const outerPanels = document.querySelectorAll(".tab-panel");

  function activateOuter(name) {
    outerBtns.forEach(function (b) {
      b.classList.toggle("active", b.dataset.tab === name);
    });
    outerPanels.forEach(function (p) {
      p.classList.toggle("active", p.id === "panel-" + name);
    });
  }

  outerBtns.forEach(function (btn) {
    btn.addEventListener("click", function () {
      const name = btn.dataset.tab;
      activateOuter(name);
      // For tabs with sub-tabs, write the compound key matching the
      // currently-active sub-panel so deep-links survive a refresh.
      let urlKey = name;
      if (name === "pc" || name === "ind" || name === "im") {
        const activeSub = document.querySelector(
          "#panel-" + name + " .sub-tab-btn.active"
        );
        if (activeSub) {
          urlKey = name + "-" + activeSub.dataset.sub;
        }
      }
      const url = new URL(window.location);
      url.searchParams.set("tab", urlKey);
      history.replaceState(null, "", url);
    });
  });

  /* ── Sub-tab switching ── */
  document.querySelectorAll(".sub-tab-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const outer = btn.dataset.outer;
      btn.parentElement.querySelectorAll(".sub-tab-btn").forEach(function (b) {
        b.classList.remove("active");
      });
      btn.classList.add("active");
      const panel = btn.closest(".tab-panel");
      panel.querySelectorAll(":scope > .sub-panel").forEach(function (p) {
        p.classList.toggle("active", p.id === btn.dataset.target);
      });
      const url = new URL(window.location);
      url.searchParams.set("tab", outer + "-" + btn.dataset.sub);
      history.replaceState(null, "", url);

      /* Mermaid renders only when its panel is visible — offscreen */
      /* panels compute zero dimensions and the SVG comes out broken. */
      if (btn.dataset.target === "sub-im-detail") initMermaidOnce();
    });
  });

  /* ── Tree expand/collapse ── */
  function attachToggle(container) {
    if (!container) return;
    container.addEventListener("click", function (e) {
      const caret = e.target.closest(".caret-icon-parent");
      if (!caret) return;
      const li = caret.closest("li.tree-node");
      if (!li) return;
      const nested = li.querySelector(":scope > ul.nested");
      if (nested) {
        nested.classList.toggle("active");
        caret.classList.toggle("open");
      }
    });
    container.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") {
        const caret = e.target.closest(".caret-icon-parent");
        if (caret) {
          e.preventDefault();
          caret.click();
        }
      }
    });
  }
  TREE_IDS.forEach(function (id) {
    attachToggle(document.getElementById(id));
  });

  /* ── Expand / Collapse all ── */
  document.querySelectorAll(".expand-all-btn").forEach(function (btn) {
    if (!btn.dataset.tree) return;
    btn.addEventListener("click", function () {
      const tree = document.getElementById(btn.dataset.tree);
      if (!tree) return;
      tree.querySelectorAll(".nested").forEach(function (n) { n.classList.add("active"); });
      tree.querySelectorAll(".caret-icon-parent").forEach(function (c) { c.classList.add("open"); });
    });
  });
  document.querySelectorAll(".collapse-all-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const tree = document.getElementById(btn.dataset.tree);
      if (!tree) return;
      tree.querySelectorAll(".nested").forEach(function (n) { n.classList.remove("active"); });
      tree.querySelectorAll(".caret-icon-parent").forEach(function (c) { c.classList.remove("open"); });
    });
  });

  /* ── Search / filter ── */
  function filterTree(treeId, query) {
    const tree = document.getElementById(treeId);
    if (!tree) return;
    const q = query.trim().toLowerCase();

    if (!q) {
      tree.querySelectorAll(".tree-node").forEach(function (n) {
        n.classList.remove("hidden");
      });
      return;
    }

    const allNodes = Array.from(tree.querySelectorAll("li.tree-node"));

    function nodeMatches(li) {
      const label = (li.dataset.label || "");
      if (label.includes(q)) return true;
      const childLis = li.querySelectorAll("li.tree-node");
      for (let i = 0; i < childLis.length; i++) {
        if ((childLis[i].dataset.label || "").includes(q)) return true;
      }
      return false;
    }

    allNodes.forEach(function (li) {
      if (nodeMatches(li)) {
        li.classList.remove("hidden");
        let parent = li.parentElement;
        while (parent && parent !== tree) {
          if (parent.classList.contains("nested")) {
            parent.classList.add("active");
            const sibling = parent.previousElementSibling;
            if (sibling) {
              const c = sibling.querySelector(".caret-icon-parent");
              if (c) c.classList.add("open");
            }
          }
          parent = parent.parentElement;
        }
      } else {
        li.classList.add("hidden");
      }
    });
  }

  [
    ["search-im",            "im-tree"],
    ["search-pc-core",       "pc-core-tree"],
    ["search-pc-exhibitor",  "pc-exhibitor-tree"],
    ["search-pc-visitor",    "pc-visitor-tree"],
    ["search-ind-core",      "ind-core-tree"],
    ["search-ind-view",      "ind-view-tree"],
  ].forEach(function (pair) {
    const input = document.getElementById(pair[0]);
    const treeId = pair[1];
    if (!input) return;
    input.addEventListener("input", function () {
      filterTree(treeId, input.value);
    });
  });

  /* ── Count badges ── */
  function countNodes(treeId) {
    const tree = document.getElementById(treeId);
    if (!tree) return 0;
    return tree.querySelectorAll("li.tree-node").length;
  }
  function setBadge(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  [
    ["im-core-total-count",       "im-core-tree"],
    ["pc-core-total-count",       "pc-core-tree"],
    ["pc-exhibitor-total-count",  "pc-exhibitor-tree"],
    ["pc-visitor-total-count",    "pc-visitor-tree"],
    ["ind-core-total-count",      "ind-core-tree"],
    ["ind-view-total-count",      "ind-view-tree"],
  ].forEach(function (pair) {
    setBadge(pair[0], countNodes(pair[1]) + " total nodes");
  });

  /* ── IM Detail (Mermaid) ── */
  let mermaidRendered = false;

  function initMermaidOnce() {
    if (mermaidRendered) return;
    if (!window.__mermaid) {
      // Library still loading — try again shortly.
      setTimeout(initMermaidOnce, 80);
      return;
    }
    const node = document.getElementById("im-mermaid");
    if (!node) return;
    mermaidRendered = true;
    // Defer to next tick so the panel's display:block is honoured.
    setTimeout(function () {
      window.__mermaid.run({ nodes: [node] }).catch(function (err) {
        console.error("Mermaid render error", err);
        node.textContent = "Mermaid render failed: " + err.message;
        mermaidRendered = false;
      });
    }, 0);
  }

  // Mermaid "Copy source" button: works regardless of render state.
  const copyBtn = document.getElementById("im-mermaid-copy");
  if (copyBtn) {
    copyBtn.addEventListener("click", function () {
      const dataEl = document.getElementById("im-mermaid-src");
      const src = dataEl ? JSON.parse(dataEl.textContent) : "";
      const done = function () {
        const original = copyBtn.textContent;
        copyBtn.textContent = "Copied ✓";
        setTimeout(function () { copyBtn.textContent = original; }, 1400);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(src).then(done, function () {
          // Fallback below
          fallbackCopy();
        });
      } else {
        fallbackCopy();
      }
      function fallbackCopy() {
        const ta = document.createElement("textarea");
        ta.value = src;
        ta.style.position = "fixed"; ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand("copy"); done(); }
        catch (e) { /* swallow */ }
        document.body.removeChild(ta);
      }
    });
  }

  // If we landed directly on the diagram sub-tab via ?tab=im-detail,
  // render the Mermaid diagram immediately.
  document.addEventListener("DOMContentLoaded", function () {
    const detail = document.getElementById("sub-im-detail");
    if (detail && detail.classList.contains("active")) initMermaidOnce();
  });

})();
