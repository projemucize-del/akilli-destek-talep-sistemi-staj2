const state = { page: 1, pages: 1, role: "user", activeTicket: null };
const $ = selector => document.querySelector(selector);
const body = $("#ticket-body");
const form = $("#ticket-form");

function escapeHtml(value = "") { const div = document.createElement("div"); div.textContent = String(value); return div.innerHTML; }
function formatDate(value) { return value ? new Intl.DateTimeFormat("tr-TR", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "-"; }
function percent(value) { return `${Math.round(Number(value) * 100)}%`; }
function statusClass(status) { return status === "Açık" ? "status-open" : status === "İşlemde" ? "status-progress" : "status-done"; }
async function api(url, options = {}) {
  const response = await fetch(url, { headers: { "Content-Type": "application/json", ...(options.headers || {}) }, ...options });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || Object.values(data.errors || {})[0] || "İşlem tamamlanamadı.");
  return data;
}
async function checkHealth() {
  const badge = $("#api-state");
  try { const h = await api("/api/health"); badge.className = "api-state online"; badge.innerHTML = `<i></i>${escapeHtml(h.database)} + AI aktif`; }
  catch { badge.className = "api-state offline"; badge.innerHTML = "<i></i>Servis bağlantısı yok"; }
}
async function loadMetrics() {
  const data = await api("/api/ai/metrics");
  $("#category-accuracy").textContent = percent(data.category_accuracy);
  $("#priority-accuracy").textContent = percent(data.priority_accuracy);
  $("#ai-data-note").textContent = `${data.training_samples} eğitim ve ${data.evaluation_samples} değerlendirme örneği. ${data.data_notice}.`;
}
async function loadStats() {
  const data = await api("/api/stats");
  $("#stat-total").textContent = data.total; $("#stat-open").textContent = data.by_status["Açık"]; $("#stat-progress").textContent = data.by_status["İşlemde"]; $("#stat-done").textContent = data.by_status["Çözüldü"];
  const max = Math.max(1, ...data.by_category.map(item => item.value));
  $("#category-chart").innerHTML = data.by_category.map(item => `<div class="bar-row"><span>${escapeHtml(item.label)}</span><div class="bar-track"><i style="width:${Math.max(8, item.value / max * 100)}%"></i></div><strong>${item.value}</strong></div>`).join("");
}
function queryString() {
  const params = new URLSearchParams({ page: state.page, page_size: 6 });
  const values = { search: $("#search").value.trim(), status: $("#status-filter").value, category: $("#category-filter").value };
  Object.entries(values).forEach(([key, value]) => { if (value) params.set(key, value); }); return params.toString();
}
async function loadTickets() {
  $("#loading").hidden = false; $("#list-error").hidden = true; body.innerHTML = "";
  try {
    const data = await api(`/api/tickets?${queryString()}`); state.pages = data.pages;
    body.innerHTML = data.items.map(ticket => `<tr><td><strong>#${ticket.id}</strong></td><td class="title-cell"><strong>${escapeHtml(ticket.title)}</strong><small>${escapeHtml(ticket.description.slice(0, 72))}</small></td><td>${escapeHtml(ticket.category)}</td><td><span class="badge priority-${escapeHtml(ticket.priority)}">${escapeHtml(ticket.priority)}</span></td><td><span class="badge ${statusClass(ticket.status)}">${escapeHtml(ticket.status)}</span></td><td><button class="action" data-id="${ticket.id}">İncele</button></td></tr>`).join("");
    $("#empty-state").hidden = data.items.length !== 0; $("#page-summary").textContent = `${data.total} kayıt · Sayfa ${data.page}/${data.pages}`; $("#prev-page").disabled = data.page <= 1; $("#next-page").disabled = data.page >= data.pages;
  } catch (error) { $("#list-error").textContent = `Kayıtlar alınamadı: ${error.message}`; $("#list-error").hidden = false; }
  finally { $("#loading").hidden = true; }
}
async function refreshAll() { await Promise.all([loadTickets(), loadStats(), loadMetrics(), checkHealth()]); }

async function predictAI() {
  const box = $("#ai-result");
  box.hidden = false; box.className = "ai-result loading-ai"; box.textContent = "Metin analiz ediliyor...";
  try {
    const result = await api("/api/ai/predict", { method: "POST", body: JSON.stringify({ title: $("#title").value.trim(), description: $("#description").value.trim() }) });
    $("#category").value = result.category; $("#priority").value = result.priority;
    box.className = "ai-result";
    box.innerHTML = `<div><span>Önerilen kategori</span><strong>${escapeHtml(result.category)}</strong><small>Güven ${percent(result.category_confidence)}</small></div><div><span>Önerilen öncelik</span><strong>${escapeHtml(result.priority)}</strong><small>Güven ${percent(result.priority_confidence)}</small></div><p>${escapeHtml(result.warning)}</p>`;
  } catch (error) { box.className = "ai-result ai-error"; box.textContent = error.message; }
}

async function showDetail(id) {
  try {
    const ticket = await api(`/api/tickets/${id}`); state.activeTicket = ticket.id;
    const staffPanel = state.role === "staff" ? `<form id="status-form" class="status-form"><h3>Durum güncelleme</h3><div class="form-row"><label>Yeni durum<select id="new-status"><option ${ticket.status === "Açık" ? "selected" : ""}>Açık</option><option ${ticket.status === "İşlemde" ? "selected" : ""}>İşlemde</option><option ${ticket.status === "Çözüldü" ? "selected" : ""}>Çözüldü</option></select></label><label>İşlem notu<input id="status-note" maxlength="240" placeholder="Örn. Bağlantı kontrol edildi"></label></div><p id="status-message" class="form-message"></p><button class="primary" type="submit">Durumu kaydet</button></form>` : `<div class="notice">Durum değişikliği yalnızca <strong>Destek Personeli</strong> demo görünümünde gösterilir.</div>`;
    const history = ticket.history.map(item => `<li><i class="timeline-dot"></i><div><strong>${escapeHtml(item.old_status || "Kayıt")} → ${escapeHtml(item.new_status)}</strong><p>${escapeHtml(item.note)}</p><time>${formatDate(item.changed_at)}</time></div></li>`).join("");
    $("#detail-content").innerHTML = `<dl class="detail-grid"><dt>Numara</dt><dd>#${ticket.id}</dd><dt>Başlık</dt><dd>${escapeHtml(ticket.title)}</dd><dt>Kategori</dt><dd>${escapeHtml(ticket.category)}</dd><dt>Öncelik</dt><dd>${escapeHtml(ticket.priority)}</dd><dt>Durum</dt><dd><span class="badge ${statusClass(ticket.status)}">${escapeHtml(ticket.status)}</span></dd><dt>AI önerisi</dt><dd>${escapeHtml(ticket.ai_category)} · ${escapeHtml(ticket.ai_priority)} · güven ${percent(ticket.ai_confidence)}</dd><dt>Oluşturma</dt><dd>${formatDate(ticket.created_at)}</dd><dt>Açıklama</dt><dd>${escapeHtml(ticket.description)}</dd></dl>${staffPanel}<section class="history"><h3>İşlem geçmişi</h3><ol>${history}</ol></section>`;
    $("#detail-dialog").showModal(); const statusForm = $("#status-form"); if (statusForm) statusForm.addEventListener("submit", updateStatus);
  } catch (error) { alert(`Ayrıntı alınamadı: ${error.message}`); }
}
async function updateStatus(event) {
  event.preventDefault(); const message = $("#status-message");
  try { await api(`/api/tickets/${state.activeTicket}/status`, { method: "PATCH", body: JSON.stringify({ status: $("#new-status").value, note: $("#status-note").value }) }); message.className = "form-message success"; message.textContent = "Durum ve işlem geçmişi güncellendi."; await refreshAll(); setTimeout(() => showDetail(state.activeTicket), 250); }
  catch (error) { message.className = "form-message error"; message.textContent = error.message; }
}
form.addEventListener("submit", async event => {
  event.preventDefault(); const message = $("#form-message"); message.className = "form-message"; message.textContent = "";
  const payload = { title: $("#title").value.trim(), category: $("#category").value, priority: $("#priority").value, description: $("#description").value.trim() };
  try { const created = await api("/api/tickets", { method: "POST", body: JSON.stringify(payload) }); form.reset(); $("#ai-result").hidden = true; state.page = 1; message.className = "form-message success"; message.textContent = `#${created.id} numaralı test kaydı oluşturuldu.`; await refreshAll(); }
  catch (error) { message.className = "form-message error"; message.textContent = error.message; }
});
let debounce;
$("#ai-predict").addEventListener("click", predictAI);
$("#search").addEventListener("input", () => { clearTimeout(debounce); debounce = setTimeout(() => { state.page = 1; loadTickets(); }, 250); });
$("#status-filter").addEventListener("change", () => { state.page = 1; loadTickets(); }); $("#category-filter").addEventListener("change", () => { state.page = 1; loadTickets(); });
$("#prev-page").addEventListener("click", () => { if (state.page > 1) { state.page--; loadTickets(); } }); $("#next-page").addEventListener("click", () => { if (state.page < state.pages) { state.page++; loadTickets(); } });
$("#refresh").addEventListener("click", refreshAll); body.addEventListener("click", event => { const button = event.target.closest("button[data-id]"); if (button) showDetail(Number(button.dataset.id)); }); $("#close-dialog").addEventListener("click", () => $("#detail-dialog").close());
document.querySelectorAll(".role").forEach(button => button.addEventListener("click", () => { document.querySelectorAll(".role").forEach(item => item.classList.remove("active")); button.classList.add("active"); state.role = button.dataset.role; if ($("#detail-dialog").open && state.activeTicket) showDetail(state.activeTicket); }));
refreshAll();
