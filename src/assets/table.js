/* Shared behaviour for the static workspace pages (tenders, awards, portals): search, filters,
   sorting, incremental loading, URL-persisted state, sidebar and Cmd/Ctrl+K. No dependencies. */
(function () {
  "use strict";
  var root = document.documentElement, $ = function (s, r) { return (r || document).querySelector(s); }, $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var mac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
  var kbd = $("#kbd-mod"); if (kbd && mac) kbd.textContent = "⌘";

  /* sidebar: collapsed state on desktop, drawer on small screens */
  var btn = $("#btn-side"), scrim = $("#side-scrim"), sb = $("#sidebar"), small = window.matchMedia("(max-width: 1023px)");
  function paint() {
    var open = small.matches ? root.classList.contains("side-open") : !root.classList.contains("side-collapsed");
    if (btn) btn.setAttribute("aria-expanded", String(open));
    if (sb) { if (small.matches && !open) sb.setAttribute("inert", ""); else sb.removeAttribute("inert"); }
    if (scrim) scrim.hidden = !(small.matches && open);
  }
  try { if (localStorage.getItem("yb-side") === "0") root.classList.add("side-collapsed"); } catch (e) {}
  if (btn) btn.addEventListener("click", function () {
    if (small.matches) root.classList.toggle("side-open");
    else { root.classList.toggle("side-collapsed"); try { localStorage.setItem("yb-side", root.classList.contains("side-collapsed") ? "0" : "1"); } catch (e) {} }
    paint();
  });
  if (scrim) scrim.addEventListener("click", function () { root.classList.remove("side-open"); paint(); });
  $$("[data-side-close]").forEach(function (b) { b.addEventListener("click", function () { root.classList.remove("side-open"); paint(); }); });
  small.addEventListener("change", paint); paint();

  /* sticky column titles sit directly under the sticky filter row */
  var fbar = $(".filterbar");
  function fbh() { if (fbar) root.style.setProperty("--fb-h", fbar.offsetHeight + "px"); }
  fbh(); window.addEventListener("resize", fbh);

  /* global search leaves for the supplier directory with the query in the URL */
  var gq = $("#q");
  if (gq) gq.addEventListener("keydown", function (e) { if (e.key === "Enter" && gq.value.trim()) location.href = "/?q=" + encodeURIComponent(gq.value.trim()); });
  document.addEventListener("keydown", function (e) {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); if (gq) gq.focus(); }
    else if (e.key === "Escape" && root.classList.contains("side-open")) { root.classList.remove("side-open"); paint(); }
  });

  /* table: search + filters + sort + show more */
  var table = $("table[data-table]"); if (!table) return;
  var PAGE = 100, shown = PAGE, body = table.tBodies[0], rows = $$("tr", body), q = $("#tq"), count = $("#tcount"), more = $("#tmore"), empty = $("#tempty");
  var filters = $$("[data-filter]"), sortKey = "", sortDir = 1, today = Date.now();
  var params = new URLSearchParams(location.search);
  if (q && params.get("q")) q.value = params.get("q");
  filters.forEach(function (f) { var v = params.get(f.dataset.filter); if (v !== null) f.value = v; });
  if (params.get("sort")) { var sp = params.get("sort").split(":"); sortKey = sp[0]; sortDir = sp[1] === "desc" ? -1 : 1; }
  else if (table.dataset.sort) { var dp = table.dataset.sort.split(":"); sortKey = dp[0]; sortDir = dp[1] === "desc" ? -1 : 1; }

  function val(tr, key) { var td = tr.querySelector('[data-k="' + key + '"]'); return td ? td.getAttribute("data-v") : ""; }
  function status(tr) {  /* tender status is derived from the deadline in the visitor's clock, never stored */
    var c = tr.querySelector("[data-status]"); if (!c) return;
    var d = tr.getAttribute("data-deadline"); var t = d ? Date.parse(d) : NaN, s, cls;
    if (isNaN(t)) { s = "Open, see notice"; cls = "badge"; }
    else if (t < today) { s = "Closed"; cls = "badge badge-bad"; }
    else if (t - today < 7 * 864e5) { s = "Closing soon"; cls = "badge badge-warn"; }
    else { s = "Open"; cls = "badge badge-ok"; }
    c.innerHTML = '<span class="' + cls + '">' + s + "</span>"; tr.setAttribute("data-open", s === "Closed" ? "closed" : "open");
  }
  rows.forEach(status);

  function apply(keep) {
    var term = q ? q.value.trim().toLowerCase() : "", terms = term ? term.split(/\s+/) : [];
    var vis = rows.filter(function (tr) {
      for (var i = 0; i < filters.length; i++) { var f = filters[i], v = f.value; if (v && tr.getAttribute("data-f-" + f.dataset.filter) !== v) return false; }
      var hay = tr.getAttribute("data-s") || "";
      return terms.every(function (w) { return hay.indexOf(w) > -1; });
    });
    if (sortKey) {
      var num = table.querySelector('th [data-sort="' + sortKey + '"]'); num = num && num.dataset.type === "num";
      vis.sort(function (a, b) {
        var x = val(a, sortKey), y = val(b, sortKey);
        if (x === "" && y !== "") return 1; if (y === "" && x !== "") return -1;   /* missing values always last */
        var r = num ? parseFloat(x) - parseFloat(y) : x.localeCompare(y, undefined, { sensitivity: "base" });
        return (r || 0) * sortDir;
      });
    }
    if (!keep) shown = PAGE;
    rows.forEach(function (tr) { tr.hidden = true; });
    vis.forEach(function (tr, i) { body.appendChild(tr); tr.hidden = i >= shown; });
    count.textContent = vis.length + (vis.length === 1 ? " result" : " results") + (vis.length > shown ? ", showing " + shown : "");
    if (empty) empty.hidden = vis.length > 0;
    if (more) { more.hidden = vis.length <= shown; }
    $$("th", table).forEach(function (th) { var b = $("[data-sort]", th); if (!b) return; th.setAttribute("aria-sort", b.dataset.sort === sortKey ? (sortDir === 1 ? "ascending" : "descending") : "none"); });
    renderActives(); persist();
  }
  function persist() {
    var p = new URLSearchParams();
    if (q && q.value.trim()) p.set("q", q.value.trim());
    filters.forEach(function (f) { if (f.value) p.set(f.dataset.filter, f.value); });
    if (sortKey && sortKey + ":" + (sortDir === 1 ? "asc" : "desc") !== table.dataset.sort) p.set("sort", sortKey + ":" + (sortDir === 1 ? "asc" : "desc"));
    var s = p.toString(); try { history.replaceState(null, "", location.pathname + (s ? "?" + s : "")); } catch (e) {}
  }
  var act = $("#tactives");
  function renderActives() {
    if (!act) return; var h = "", n = 0;
    filters.forEach(function (f) { if (f.value) { n++; h += '<button type="button" class="act" data-clear-f="' + f.dataset.filter + '" aria-label="Remove filter ' + f.options[f.selectedIndex].text.replace(/"/g, "") + '">' + f.options[f.selectedIndex].text.replace(/</g, "&lt;") + ' <span aria-hidden="true">×</span></button>'; } });
    if (q && q.value.trim()) { n++; h += '<button type="button" class="act" data-clear-q aria-label="Clear search">“' + q.value.trim().replace(/</g, "&lt;") + '” <span aria-hidden="true">×</span></button>'; }
    if (n > 1) h += '<button type="button" class="linklike" data-clear-all>Clear</button>';
    act.innerHTML = h; act.hidden = !n;
  }
  if (act) act.addEventListener("click", function (e) {
    var t = e.target.closest("button"); if (!t) return;
    if (t.hasAttribute("data-clear-all")) { filters.forEach(function (f) { f.value = ""; }); if (q) q.value = ""; }
    else if (t.hasAttribute("data-clear-q")) { if (q) q.value = ""; }
    else if (t.dataset.clearF) { filters.forEach(function (f) { if (f.dataset.filter === t.dataset.clearF) f.value = ""; }); }
    apply();
  });
  if (q) q.addEventListener("input", function () { apply(); });
  filters.forEach(function (f) { f.addEventListener("change", function () { apply(); }); });
  table.addEventListener("click", function (e) {
    var b = e.target.closest("[data-sort]"); if (!b) return;
    if (sortKey === b.dataset.sort) sortDir = -sortDir; else { sortKey = b.dataset.sort; sortDir = 1; }
    apply();
  });
  if (more) more.addEventListener("click", function () { shown += PAGE; apply(true); });
  apply();
})();
