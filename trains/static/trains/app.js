// Utility condivise
const T = {
  time(iso) {
    if (!iso) return "—";
    return new Date(iso).toLocaleTimeString("it-IT", {hour: "2-digit", minute: "2-digit"});
  },
  delayClass(d) {
    if (d === null || d === undefined) return "secondary";
    if (d <= 1) return "success";
    if (d <= 5) return "warning";
    return "danger";
  },
  delayBadge(d) {
    if (d === null || d === undefined) return '<span class="badge text-bg-secondary">—</span>';
    const c = T.delayClass(d);
    const txt = d <= 1 && d >= -1 ? "in orario" : (d > 0 ? `+${d} min` : `${d} min`);
    return `<span class="badge text-bg-${c}">${txt}</span>`;
  },
  lineBadge(code, color) {
    if (!code) return '<span class="text-muted">—</span>';
    return `<a class="line-badge text-decoration-none" style="background:${color}" href="/linea/${code}/">${code}</a>`;
  },
  esc(s) { return String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c])); },
  async json(url) {
    const r = await fetch(url, {headers: {Accept: "application/json"}});
    if (!r.ok) throw new Error(`${url}: ${r.status}`);
    return r.json();
  },
  clock() { return new Date().toLocaleTimeString("it-IT"); },
};
Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
Chart.defaults.plugins.legend.labels.usePointStyle = true;
