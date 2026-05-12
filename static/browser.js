// -- module-mode import: Mermaid ESM bundle ---------------------------
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
    fontFamily: "ui-sans-serif, system-ui, sans-serif",
    fontSize: "18px"
  },
  flowchart: { useMaxWidth: false },
  classDiagram: { useMaxWidth: false }
});

// -- main browser script (DOM wiring + tree controls + Mermaid kick) --
(function () {
  "use strict";

  const TREE_IDS = ["im-core-tree", "pc-core-tree", "pc-exhibitor-tree",
                    "pc-visitor-tree", "ind-core-tree", "ind-view-tree"];

  /* -- Outer tab switching -- */
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
      let urlKey = name;
      if (name === "pc" || name === "ind" || name === "im") {
        const activeSub = document.querySelector("#panel-" + name + " .sub-tab-btn.active");
        if (activeSub) urlKey = name + "-" + activeSub.dataset.sub;
      }
      const url = new URL(window.location);
      url.searchParams.set("tab", urlKey);
      history.replaceState(null, "", url);
    });
  });

  /* -- Sub-tab switching -- */
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

      if (btn.dataset.target === "sub-im-detail")      initMermaidOnce();
      if (btn.dataset.target === "sub-im-interactive") initCytoscapeOnce();
    });
  });

  /* -- Tree expand/collapse -- */
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
        if (caret) { e.preventDefault(); caret.click(); }
      }
    });
  }
  TREE_IDS.forEach(function (id) { attachToggle(document.getElementById(id)); });

  /* -- Expand / Collapse all -- */
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

  /* -- Search / filter -- */
  function filterTree(treeId, query) {
    const tree = document.getElementById(treeId);
    if (!tree) return;
    const q = query.trim().toLowerCase();
    if (!q) {
      tree.querySelectorAll(".tree-node").forEach(function (n) { n.classList.remove("hidden"); });
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
    input.addEventListener("input", function () { filterTree(treeId, input.value); });
  });

  /* -- Count badges -- */
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

  /* -- IM Detail (Mermaid) -- */
  let mermaidRendered = false;
  function initMermaidOnce() {
    if (mermaidRendered) return;
    if (!window.__mermaid) { setTimeout(initMermaidOnce, 80); return; }
    const node = document.getElementById("im-mermaid");
    if (!node) return;
    mermaidRendered = true;
    setTimeout(function () {
      window.__mermaid.run({ nodes: [node] }).catch(function (err) {
        console.error("Mermaid render error", err);
        node.textContent = "Mermaid render failed: " + err.message;
        mermaidRendered = false;
      });
    }, 0);
  }

  /* -- Copy Mermaid source button -- */
  const copyBtn = document.getElementById("im-mermaid-copy");
  if (copyBtn) {
    copyBtn.addEventListener("click", function () {
      const dataEl = document.getElementById("im-mermaid-src");
      const src = dataEl ? JSON.parse(dataEl.textContent) : "";
      const done = function () {
        const original = copyBtn.textContent;
        copyBtn.textContent = "Copied";
        setTimeout(function () { copyBtn.textContent = original; }, 1400);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(src).then(done, fallbackCopy);
      } else {
        fallbackCopy();
      }
      function fallbackCopy() {
        const ta = document.createElement("textarea");
        ta.value = src;
        ta.style.position = "fixed"; ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand("copy"); done(); } catch (e) { /* swallow */ }
        document.body.removeChild(ta);
      }
    });
  }

  // If we landed directly on a panel via deep-link, render it now.
  document.addEventListener("DOMContentLoaded", function () {
    const detail = document.getElementById("sub-im-detail");
    if (detail && detail.classList.contains("active")) initMermaidOnce();
    const interactive = document.getElementById("sub-im-interactive");
    if (interactive && interactive.classList.contains("active")) initCytoscapeOnce();
  });

  /* -- IM Interactive (Cytoscape.js) -- */
  // Renders the same Information Model as the Mermaid tab, but as a
  // movable graph: drag nodes, scroll to zoom, drag-background to pan.
  // Node positions persist to localStorage across reloads.

  const LS_POSITIONS_KEY = "im-cy-positions-v1";
  const LS_LAYOUT_KEY    = "im-cy-layout-v1";

  const STEREO_COLORS = {
    Kind:            "#0e7a91",
    SubKind:         "#1aa3bf",
    Role:            "#0a7e45",
    RoleMixin:       "#b36000",
    Phase:           "#7048a6",
    PhaseMixin:      "#9b78d4",
    Mixin:           "#6d7c8a",
    Category:        "#005596",
    EventType:       "#c81e7a",
    SituationType:   "#c81e7a",
    Quality:         "#888",
    Mode:            "#888",
    Relator:         "#444",
    NamedIndividual: "#d97706",
    external:        "#9ca3af"
  };

  let cytoscapeRendered = false;
  let cyInstance = null;

  function initCytoscapeOnce() {
    if (cytoscapeRendered) {
      if (cyInstance) { cyInstance.resize(); cyInstance.fit(undefined, 30); }
      return;
    }
    if (typeof cytoscape === "undefined") {
      setTimeout(initCytoscapeOnce, 80);
      return;
    }
    const dataEl = document.getElementById("im-cytoscape-data");
    const host   = document.getElementById("im-cy");
    if (!dataEl || !host) return;

    let elements;
    try {
      const payload = JSON.parse(dataEl.textContent);
      elements = [...(payload.nodes || []), ...(payload.edges || [])];
    } catch (e) {
      host.textContent = "Failed to parse Cytoscape data: " + e.message;
      return;
    }

    if (typeof cytoscapeDagre !== "undefined" && !cytoscape.__dagreRegistered) {
      try { cytoscape.use(cytoscapeDagre); cytoscape.__dagreRegistered = true; }
      catch (e) { /* already registered */ }
    }

    cytoscapeRendered = true;

    cyInstance = cytoscape({
      container: host,
      elements: elements,
      style: [
        {
          selector: "node",
          style: {
            "background-color": function (ele) { return STEREO_COLORS[ele.data("stereotype")] || "#0e7a91"; },
            "label": function (ele) {
              const lbl  = ele.data("label") || "";
              const ster = ele.data("stereotype");
              const attrs = ele.data("attrs") || [];
              const lines = [];
              if (ster) lines.push("<<" + ster + ">>");
              lines.push(lbl);
              attrs.forEach(function (a) {
                const card = a.card ? " [" + a.card + "]" : "";
                lines.push("+" + a.name + ": " + a.range + card);
              });
              return lines.join("\n");
            },
            "color": "#fff",
            "text-valign": "center",
            "text-halign": "center",
            "text-wrap": "wrap",
            "text-justification": "left",
            "font-size": "12px",
            "font-family": "ui-sans-serif, system-ui, sans-serif",
            "shape": "round-rectangle",
            "padding": "12px",
            "width":  "label",
            "height": "label",
            "border-width": 1.5,
            "border-color": "#06596e"
          }
        },
        {
          selector: "node[kind = 'individual']",
          style: { "shape": "round-tag", "border-color": "#7c2d12" }
        },
        {
          selector: "node[kind = 'external']",
          style: {
            "background-color": "#e5e7eb",
            "color": "#374151",
            "border-style": "dashed",
            "border-color": "#9ca3af"
          }
        },
        {
          selector: "edge",
          style: {
            "width": 1.5,
            "line-color": "#0e7a91",
            "target-arrow-color": "#0e7a91",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            "font-size": "10px",
            "color": "#06596e",
            "text-background-color": "#fff",
            "text-background-opacity": 0.85,
            "text-background-padding": "2px",
            "label": function (ele) {
              const lbl = ele.data("label") || "";
              const c   = ele.data("cardinality");
              return c ? lbl + "  [" + c + "]" : lbl;
            }
          }
        },
        {
          selector: "edge[kind = 'subClassOf']",
          style: {
            "target-arrow-shape": "triangle",
            "target-arrow-fill": "hollow",
            "line-color": "#374151",
            "target-arrow-color": "#374151",
            "label": "",
            "width": 1.8
          }
        },
        {
          selector: "edge[kind = 'instanceOf']",
          style: {
            "target-arrow-shape": "triangle",
            "target-arrow-fill": "hollow",
            "line-style": "dashed",
            "line-color": "#d97706",
            "target-arrow-color": "#d97706"
          }
        }
      ],
      wheelSensitivity: 0.2,
      minZoom: 0.2,
      maxZoom: 3,
      layout: { name: "preset" }
    });

    const layoutSelect = document.getElementById("im-cy-layout");
    const savedLayout  = localStorage.getItem(LS_LAYOUT_KEY) || "dagre";
    if (layoutSelect) layoutSelect.value = savedLayout;

    function runLayout(name) {
      const opts = layoutOptions(name);
      cyInstance.layout(opts).run();
    }

    const savedPositions = loadPositions();
    if (savedPositions) {
      cyInstance.nodes().forEach(function (n) {
        const p = savedPositions[n.id()];
        if (p) n.position(p);
      });
      cyInstance.fit(undefined, 30);
    } else {
      runLayout(savedLayout);
    }

    cyInstance.on("dragfree", "node", savePositions);

    if (layoutSelect) {
      layoutSelect.addEventListener("change", function () {
        localStorage.setItem(LS_LAYOUT_KEY, layoutSelect.value);
        localStorage.removeItem(LS_POSITIONS_KEY);
        runLayout(layoutSelect.value);
      });
    }

    const resetBtn = document.getElementById("im-cy-relayout");
    if (resetBtn) {
      resetBtn.addEventListener("click", function () {
        localStorage.removeItem(LS_POSITIONS_KEY);
        runLayout(layoutSelect ? layoutSelect.value : "dagre");
      });
    }

    function savePositions() {
      const positions = {};
      cyInstance.nodes().forEach(function (n) { positions[n.id()] = n.position(); });
      try { localStorage.setItem(LS_POSITIONS_KEY, JSON.stringify(positions)); }
      catch (e) { /* quota: ignore */ }
    }

    function loadPositions() {
      try {
        const raw = localStorage.getItem(LS_POSITIONS_KEY);
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        const ids = new Set(cyInstance.nodes().map(function (n) { return n.id(); }));
        const hit = Object.keys(parsed).some(function (id) { return ids.has(id); });
        return hit ? parsed : null;
      } catch (e) { return null; }
    }
  }

  function layoutOptions(name) {
    switch (name) {
      case "dagre":
        return { name: "dagre", rankDir: "LR", nodeSep: 50, rankSep: 90,
                 edgeSep: 20, animate: true, fit: true, padding: 30 };
      case "breadthfirst":
        return { name: "breadthfirst", directed: true, padding: 30,
                 spacingFactor: 1.4, animate: true, fit: true };
      case "cose":
        return { name: "cose", padding: 30, animate: true, fit: true,
                 idealEdgeLength: 120, nodeRepulsion: 8000 };
      case "circle":
        return { name: "circle", padding: 30, animate: true, fit: true };
      case "concentric":
        return { name: "concentric", padding: 30, animate: true, fit: true,
                 minNodeSpacing: 40 };
      default:
        return { name: "grid", padding: 30, animate: true, fit: true };
    }
  }

})();
