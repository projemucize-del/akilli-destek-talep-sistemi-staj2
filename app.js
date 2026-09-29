const state = { page: 1, pages: 1, activeSession: null, sessions: [] };
const $ = selector => document.querySelector(selector);
const body = $("#session-body");
const sessionForm = $("#session-form");

function escapeHtml(value = "") {
  const div = document.createElement("div");
  div.textContent = String(value);
  return div.innerHTML;
}

function formatDate(value) {
  return value
    ? new Intl.DateTimeFormat("tr-TR", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value))
    : "–";
}

function formatNumber(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "–";
  return Number(value).toLocaleString("tr-TR", { maximumFractionDigits: digits });
}

function statusClass(status) {
  return status === "Kayıt" ? "status-open" : "status-done";
}

function alertClass(level) {
  return level === "Kritik" ? "alert-critical" : level === "Uyarı" ? "alert-warning" : "alert-normal";
}

async function api(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || Object.values(data.errors || {})[0] || "İşlem tamamlanamadı.");
  }
  return data;
}

let toastTimer;
function showToast(message, type = "success") {
  const toast = $("#toast");
  clearTimeout(toastTimer);
  toast.className = `toast ${type}`;
  toast.textContent = message;
  toast.hidden = false;
  toastTimer = setTimeout(() => { toast.hidden = true; }, 3400);
}

async function checkHealth() {
  const badge = $("#api-state");
  try {
    const health = await api("/api/health");
    badge.className = "api-state online";
    badge.innerHTML = `<i></i>${escapeHtml(health.database)} · yerel servis`;
  } catch {
    badge.className = "api-state offline";
    badge.innerHTML = "<i></i>Servis bağlantısı yok";
  }
}

function updateLatest(reading) {
  const values = reading || {};
  $("#live-emg").textContent = formatNumber(values.emg);
  $("#live-force").textContent = formatNumber(values.force);
  $("#live-current").textContent = formatNumber(values.current, 3);
  $("#live-position").textContent = formatNumber(values.position);
  $("#live-battery").textContent = formatNumber(values.battery);
  $("#live-alert").textContent = values.alert_level || "–";
  $("#live-alert").className = values.alert_level ? alertClass(values.alert_level) : "";
  $("#live-message").textContent = values.alert_message || "Henüz okuma yok";
  $("#live-origin").textContent = values.reading_origin || "Veri yok";
}

async function loadStats() {
  const data = await api("/api/stats");
  $("#stat-sessions").textContent = data.sessions;
  $("#stat-active").textContent = data.active;
  $("#stat-readings").textContent = data.readings;
  $("#stat-alerts").textContent = data.alerts;
  updateLatest(data.latest);
}

function queryString() {
  const params = new URLSearchParams({ page: state.page, page_size: 7 });
  const search = $("#search").value.trim();
  const status = $("#status-filter").value;
  if (search) params.set("search", search);
  if (status) params.set("status", status);
  return params.toString();
}

function renderSessionRows(items) {
  body.innerHTML = items.map(item => `<tr class="${item.id === state.activeSession ? "selected-row" : ""}">
    <td><strong class="session-number">#${item.id}</strong></td>
    <td class="title-cell"><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.notes || "Not eklenmedi")}</small></td>
    <td><span class="source-badge">${escapeHtml(item.source)}</span></td>
    <td>${item.reading_count}</td>
    <td><span class="badge ${item.alert_count ? "alert-warning" : "alert-normal"}">${item.alert_count}</span></td>
    <td><span class="badge ${statusClass(item.status)}">${escapeHtml(item.status)}</span></td>
    <td><button class="action" type="button" data-id="${item.id}" aria-label="${escapeHtml(item.name)} ayrıntısını aç">İncele <span>→</span></button></td>
  </tr>`).join("");
}

async function loadSessions() {
  $("#list-error").hidden = true;
  try {
    const data = await api(`/api/sessions?${queryString()}`);
    state.pages = data.pages;
    state.sessions = data.items;
    renderSessionRows(data.items);
    $("#empty-state").hidden = data.items.length !== 0;
    $("#page-summary").textContent = `${data.total} test · Sayfa ${data.page}/${data.pages}`;
    $("#prev-page").disabled = data.page <= 1;
    $("#next-page").disabled = data.page >= data.pages;
    return data.items;
  } catch (error) {
    $("#list-error").textContent = `Kayıtlar alınamadı: ${error.message}`;
    $("#list-error").hidden = false;
    return [];
  }
}

function drawChart(readings = []) {
  const svg = $("#sensor-chart");
  const rows = readings.slice(0, 32).reverse();
  if (!rows.length) {
    svg.innerHTML = '<g class="chart-empty"><circle cx="470" cy="112" r="26"/><text x="470" y="118" text-anchor="middle">∿</text><text x="470" y="166" text-anchor="middle">Grafik için sensör girdisi yok</text></g>';
    return;
  }

  const left = 58;
  const top = 22;
  const width = 842;
  const height = 202;
  const xAt = index => left + index * (width / Math.max(1, rows.length - 1));
  const yAt = value => top + height - Math.max(0, Math.min(100, Number(value))) * height / 100;
  const points = key => rows.map((row, index) => `${xAt(index).toFixed(1)},${yAt(row[key]).toFixed(1)}`).join(" ");
  const grid = [0, 25, 50, 75, 100].map(value => {
    const y = yAt(value);
    return `<line x1="${left}" y1="${y}" x2="${left + width}" y2="${y}"/><text x="45" y="${y + 4}" text-anchor="end">${value}</text>`;
  }).join("");
  const latest = rows.length - 1;
  svg.innerHTML = `
    <rect class="safe-zone" x="${left}" y="${top}" width="${width}" height="${height}" rx="10"/>
    <g class="grid">${grid}</g>
    <polyline class="emg-line halo" points="${points("emg")}"/>
    <polyline class="emg-line" points="${points("emg")}"/>
    <polyline class="force-line halo" points="${points("force")}"/>
    <polyline class="force-line" points="${points("force")}"/>
    <circle class="emg-point" cx="${xAt(latest)}" cy="${yAt(rows[latest].emg)}" r="5"/>
    <circle class="force-point" cx="${xAt(latest)}" cy="${yAt(rows[latest].force)}" r="5"/>
    <text class="axis-label" x="58" y="254">Eski</text><text class="axis-label" x="900" y="254" text-anchor="end">Yeni</text>`;
}

function renderAnalytics(item) {
  const analytics = item.analytics || {};
  const averages = analytics.averages || {};
  const maximums = analytics.maximums || {};
  $("#chart-session-name").textContent = item.name || "Sensör sinyalleri";
  $("#chart-session-meta").textContent = `#${item.id} · ${item.source} · ${item.reading_count} okuma · ${item.status}`;
  $("#metric-avg-emg").textContent = formatNumber(averages.emg);
  $("#metric-avg-force").textContent = formatNumber(averages.force);
  $("#metric-max-force").textContent = formatNumber(maximums.force);
  $("#metric-max-current").textContent = formatNumber(maximums.current, 3);
  $("#metric-safe-ratio").textContent = analytics.count ? `%${formatNumber(analytics.safe_ratio)}` : "–";
  $("#metric-safe-count").textContent = analytics.count ? `${analytics.safe_count}/${analytics.count} okuma` : "prototip sınırı";
  $("#metric-correlation").textContent = analytics.emg_force_correlation === null ? "–" : `r ${formatNumber(analytics.emg_force_correlation, 3)}`;
  $("#metric-correlation-label").textContent = analytics.correlation_label || "korelasyon";
  drawChart(item.readings);
}

async function selectSession(id) {
  const item = await api(`/api/sessions/${id}`);
  state.activeSession = item.id;
  renderAnalytics(item);
  renderSessionRows(state.sessions);
  return item;
}

async function refreshAll() {
  const [, items] = await Promise.all([loadStats(), loadSessions(), checkHealth()]);
  const selectedExists = state.activeSession && (state.sessions.some(item => item.id === state.activeSession) || !items.length);
  const target = selectedExists ? state.activeSession : items[0]?.id;
  if (target) await selectSession(target);
}

function analyticsCards(analytics) {
  const averages = analytics.averages || {};
  const maximums = analytics.maximums || {};
  const correlation = analytics.emg_force_correlation === null ? "–" : `r ${formatNumber(analytics.emg_force_correlation, 3)}`;
  return `<div class="detail-analytics">
    <article><span>Ort. EMG / FSR</span><strong>${formatNumber(averages.emg)} <small>/</small> ${formatNumber(averages.force)}</strong></article>
    <article><span>Maks. kuvvet</span><strong>${formatNumber(maximums.force)}<small>%</small></strong></article>
    <article><span>Maks. akım</span><strong>${formatNumber(maximums.current, 3)}<small>A</small></strong></article>
    <article><span>Güvenli oran</span><strong>%${formatNumber(analytics.safe_ratio)}</strong></article>
    <article><span>EMG–FSR ilişkisi</span><strong>${correlation}</strong><small>${escapeHtml(analytics.correlation_label)}</small></article>
  </div>`;
}

function readingRows(readings) {
  if (!readings.length) return '<tr><td colspan="8" class="empty-cell">Bu oturumda henüz okuma yok.</td></tr>';
  return readings.slice(0, 50).map(row => `<tr>
    <td>${formatDate(row.recorded_at)}</td>
    <td><span class="reading-origin">${escapeHtml(row.reading_origin || "Örnek Üretici")}</span></td>
    <td>${formatNumber(row.emg)}</td><td>${formatNumber(row.force)}</td><td>${formatNumber(row.current, 3)}</td>
    <td>${formatNumber(row.position)}</td><td>${formatNumber(row.battery)}</td>
    <td><span class="badge ${alertClass(row.alert_level)}">${escapeHtml(row.alert_level)}</span></td>
  </tr>`).join("");
}

function manualReadingForm() {
  return `<details class="manual-entry">
    <summary><span><b>＋</b> Manuel test girdisi ekle</span><small>Donanım bağlantısı değildir</small></summary>
    <form id="reading-form" novalidate>
      <div class="reading-fields">
        <label>EMG (%)<input name="emg" type="number" min="0" max="100" step="0.1" required placeholder="0–100"></label>
        <label>FSR (%)<input name="force" type="number" min="0" max="100" step="0.1" required placeholder="0–100"></label>
        <label>Motor akımı (A)<input name="current" type="number" min="0" max="5" step="0.001" required placeholder="0–5"></label>
        <label>Konum (°)<input name="position" type="number" min="0" max="180" step="0.1" required placeholder="0–180"></label>
        <label>Batarya (%)<input name="battery" type="number" min="0" max="100" step="0.1" required placeholder="0–100"></label>
      </div>
      <div class="entry-footer"><p id="reading-message" class="form-message" role="status">Girilen değer “Manuel Test Girdisi” olarak işaretlenir.</p><button class="primary compact" type="submit">Okumayı kaydet</button></div>
    </form>
  </details>`;
}

async function showDetail(id) {
  try {
    const item = await selectSession(id);
    $("#detail-title").textContent = item.name;
    const controls = item.status === "Kayıt" ? `<div class="detail-actions">
      <button id="add-sample" class="primary" type="button">Örnek okuma üret <span>＋</span></button>
      <button id="complete-session" class="secondary" type="button">Testi tamamla</button>
    </div>${manualReadingForm()}` : '<div class="completed-note">Bu oturum tamamlandı; kayıtlar salt okunur durumdadır.</div>';
    $("#detail-content").innerHTML = `
      <div class="detail-summary">
        <div><span>Kaynak</span><strong class="source-badge">${escapeHtml(item.source)}</strong></div>
        <div><span>Durum</span><strong><span class="badge ${statusClass(item.status)}">${escapeHtml(item.status)}</span></strong></div>
        <div><span>Başlangıç</span><strong>${formatDate(item.started_at)}</strong></div>
        <div><span>Test notu</span><strong>${escapeHtml(item.notes || "Not eklenmedi")}</strong></div>
      </div>
      <section class="dialog-section"><div class="dialog-section-title"><h3>Oturum analizi</h3><span>${item.analytics.count} okuma</span></div>${analyticsCards(item.analytics)}</section>
      ${controls}
      <section class="dialog-section"><div class="dialog-section-title"><h3>Okuma geçmişi</h3><span>Son 50 kayıt</span></div>
        <div class="table-wrap detail-table"><table><thead><tr><th>Zaman</th><th>Giriş türü</th><th>EMG</th><th>FSR</th><th>Akım</th><th>Konum</th><th>Batarya</th><th>Durum</th></tr></thead><tbody>${readingRows(item.readings)}</tbody></table></div>
      </section>`;

    const dialog = $("#detail-dialog");
    if (!dialog.open) dialog.showModal();
    $("#add-sample")?.addEventListener("click", () => addSample(item.id));
    $("#complete-session")?.addEventListener("click", () => completeSession(item.id));
    $("#reading-form")?.addEventListener("submit", event => addManualReading(event, item.id));
  } catch (error) {
    showToast(`Test ayrıntısı alınamadı: ${error.message}`, "error");
  }
}

async function addSample(id) {
  try {
    await api(`/api/sessions/${id}/sample`, { method: "POST", body: "{}" });
    showToast("Örnek üreticiden yeni test girdisi eklendi.");
    await Promise.all([loadStats(), loadSessions()]);
    await showDetail(id);
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function addManualReading(event, id) {
  event.preventDefault();
  const form = event.currentTarget;
  const message = form.querySelector("#reading-message");
  const payload = Object.fromEntries(new FormData(form).entries());
  try {
    await api(`/api/sessions/${id}/readings`, { method: "POST", body: JSON.stringify(payload) });
    message.className = "form-message success";
    message.textContent = "Manuel test girdisi kaydedildi.";
    showToast("Manuel test girdisi kaydedildi.");
    await Promise.all([loadStats(), loadSessions()]);
    await showDetail(id);
  } catch (error) {
    message.className = "form-message error";
    message.textContent = error.message;
  }
}

async function completeSession(id) {
  try {
    await api(`/api/sessions/${id}/complete`, { method: "PATCH", body: "{}" });
    showToast("Test oturumu tamamlandı ve veri girişine kapatıldı.");
    await Promise.all([loadStats(), loadSessions()]);
    await showDetail(id);
  } catch (error) {
    showToast(error.message, "error");
  }
}

sessionForm.addEventListener("submit", async event => {
  event.preventDefault();
  const message = $("#form-message");
  message.className = "form-message";
  message.textContent = "";
  try {
    const created = await api("/api/sessions", {
      method: "POST",
      body: JSON.stringify({ name: $("#name").value.trim(), notes: $("#notes").value.trim() }),
    });
    sessionForm.reset();
    state.page = 1;
    state.activeSession = created.id;
    message.className = "form-message success";
    message.textContent = `#${created.id} numaralı test oturumu başlatıldı.`;
    showToast("Yeni örnek veri oturumu oluşturuldu.");
    await refreshAll();
    await showDetail(created.id);
  } catch (error) {
    message.className = "form-message error";
    message.textContent = error.message;
  }
});

let debounce;
$("#search").addEventListener("input", () => {
  clearTimeout(debounce);
  debounce = setTimeout(() => { state.page = 1; loadSessions(); }, 250);
});
$("#status-filter").addEventListener("change", () => { state.page = 1; loadSessions(); });
$("#prev-page").addEventListener("click", () => { if (state.page > 1) { state.page -= 1; loadSessions(); } });
$("#next-page").addEventListener("click", () => { if (state.page < state.pages) { state.page += 1; loadSessions(); } });
$("#refresh").addEventListener("click", async () => {
  const button = $("#refresh");
  button.classList.add("is-refreshing");
  try { await refreshAll(); showToast("Panel verileri yenilendi."); }
  catch (error) { showToast(error.message, "error"); }
  finally { button.classList.remove("is-refreshing"); }
});
body.addEventListener("click", event => {
  const button = event.target.closest("button[data-id]");
  if (button) showDetail(Number(button.dataset.id));
});
$("#close-dialog").addEventListener("click", () => $("#detail-dialog").close());
$("#detail-dialog").addEventListener("click", event => {
  if (event.target === $("#detail-dialog")) $("#detail-dialog").close();
});

refreshAll().catch(error => showToast(`Panel yüklenemedi: ${error.message}`, "error"));
