"use strict";

// Served by the same FastAPI application as /api/jobs (no CORS configuration needed).
const API = "/api/jobs";
const POLL_MS = 5000;
const PAGE_SIZE = 20;

const STORES = [
  { id: "dns", label: "DNS" },
  { id: "citilink", label: "Ситилинк" },
  { id: "onlinetrade", label: "Onlinetrade" },
];
const FINISHED = new Set(["found", "not_found", "failed", "canceled"]);
const STATUS_LABELS = {
  pending: "В очереди",
  in_progress: "Поиск…",
  found: "Найдено",
  not_found: "Не найдено",
  failed: "Ошибка",
  canceled: "Отменено",
};

const el = (id) => document.getElementById(id);
const state = {
  jobs: [],
  selectedJobId: null,
  job: null,
  progress: null,
  expanded: new Set(),
  page: 1,
  filterQuery: "",
  filterStatus: "all",
  busySubmit: false,
  loadingFor: null,
  jobsRequest: 0,
  detailsRequest: 0,
};

const rubles = new Intl.NumberFormat("ru-RU", {
  style: "currency",
  currency: "RUB",
  maximumFractionDigits: 2,
});

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

function safeUrl(raw) {
  if (typeof raw !== "string" || !/^https?:\/\//i.test(raw.trim())) return null;
  try {
    const url = new URL(raw);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch {
    return null;
  }
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("ru-RU", {
    day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

function percent(value) {
  const number = Number(value);
  return Number.isFinite(number) ? Math.max(0, Math.min(100, number)) : 0;
}

function formatMoney(value) {
  const number = Number(value);
  return Number.isFinite(number) ? rubles.format(number) : "—";
}

function setConnection(online) {
  el("connection").classList.toggle("online", online);
  el("connection").classList.toggle("offline", !online);
  el("connection-text").textContent = online ? "API подключён" : "Нет соединения";
}

let toastTimeout;
function toast(message, isError = false) {
  const node = el("toast");
  node.textContent = message;
  node.classList.toggle("error", isError);
  node.hidden = false;
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => { node.hidden = true; }, 5500);
}

async function request(url, options = {}) {
  let response;
  try {
    response = await fetch(url, { credentials: "same-origin", ...options });
  } catch {
    throw new Error("Не удалось подключиться к серверу. Проверьте, что price_parser запущен.");
  }

  if (!response.ok) {
    let detail = "";
    try {
      const payload = await response.json();
      detail = typeof payload.detail === "string" ? payload.detail : "";
    } catch { /* A non-JSON HTTP error. */ }
    throw new Error(detail || `Ошибка сервера: HTTP ${response.status}`);
  }

  return response.json();
}

function currentQueries() {
  return el("queries").value.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
}

function setSubmitBusy(busy) {
  state.busySubmit = busy;
  el("queries").disabled = busy;
  el("upload-button").disabled = busy;
  el("create-button").textContent = busy ? "Создание…" : "Создать задание";
  updateQueryCount();
}

function updateQueryCount() {
  const count = currentQueries().length;
  el("query-count").textContent = `${count} ${plural(count, "позиция", "позиции", "позиций")}`;
  el("create-button").disabled = state.busySubmit || count === 0;
}

function plural(n, one, few, many) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  return mod10 === 1 && mod100 !== 11 ? one :
    mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14) ? few : many;
}

function renderJobs() {
  const container = el("jobs-list");
  if (state.jobs.length === 0) {
    container.innerHTML = '<p class="empty-state">Заданий пока нет. Создайте первое выше.</p>';
    return;
  }

  container.innerHTML = state.jobs.map((job) => `
    <button type="button" class="job-row ${job.id === state.selectedJobId ? "is-selected" : ""}"
      data-job-id="${Number(job.id)}" aria-pressed="${job.id === state.selectedJobId}">
      <span class="job-main">
        <span class="job-number">Задание #${Number(job.id)}</span>
        <span class="job-date">${escapeHtml(formatDate(job.created_at))}</span>
      </span>
      <span class="job-amount">${Number(job.total_products) || 0} ${plural(Number(job.total_products) || 0, "товар", "товара", "товаров")}</span>
      <span class="job-arrow" aria-hidden="true">›</span>
    </button>
  `).join("");
}

function selectJob(id) {
  if (!Number.isInteger(id) || id <= 0) return;
  if (state.selectedJobId === id && state.job) return;
  state.selectedJobId = id;
  state.job = null;
  state.progress = null;
  state.expanded.clear();
  state.page = 1;
  el("job-content").hidden = false;
  el("selected-job-label").textContent = `ЗАДАНИЕ #${id}`;
  el("job-created").textContent = "Загрузка данных…";
  el("progress-content").innerHTML = '<p class="empty-state">Загрузка прогресса…</p>';
  el("results-body").innerHTML = '<tr><td colspan="5" class="empty-state">Загрузка результатов…</td></tr>';
  el("results-count").textContent = "";
  el("page-indicator").textContent = "";
  el("cancel-job").disabled = true;
  el("export-job").href = `${API}/${id}/export`;
  renderJobs();
  const url = new URL(window.location.href);
  url.searchParams.set("job", String(id));
  window.history.replaceState(null, "", url);
  void loadDetails();
  if (window.matchMedia("(max-width: 760px)").matches) {
    el("job-content").scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

async function loadJobs({ selectId = null, silent = false } = {}) {
  const token = ++state.jobsRequest;
  el("refresh-jobs").disabled = true;
  try {
    const jobs = await request(API);
    if (token !== state.jobsRequest) return;
    if (!Array.isArray(jobs)) throw new Error("Сервер вернул неверный формат списка заданий.");
    state.jobs = jobs.slice().sort((a, b) => Number(b.id) - Number(a.id));
    setConnection(true);
    const requestedId = selectId ?? state.selectedJobId;
    const exists = state.jobs.some((job) => job.id === requestedId);
    const chosenId = exists ? requestedId : state.jobs[0]?.id ?? null;
    if (chosenId === null) {
      state.selectedJobId = null;
      state.job = null;
      state.progress = null;
      el("job-content").hidden = true;
      const url = new URL(window.location.href);
      url.searchParams.delete("job");
      window.history.replaceState(null, "", url);
      renderJobs();
    } else if (chosenId !== state.selectedJobId || state.job === null) {
      selectJob(chosenId);
    } else {
      renderJobs();
    }
  } catch (error) {
    if (token !== state.jobsRequest) return;
    setConnection(false);
    if (!silent) toast(error.message, true);
    if (!state.jobs.length) {
      el("jobs-list").innerHTML = '<p class="empty-state">Не удалось загрузить задания. Нажмите «Обновить».</p>';
    }
  } finally {
    if (token === state.jobsRequest) el("refresh-jobs").disabled = false;
  }
}

function jobComplete(progress) {
  return progress?.overall?.total > 0 && progress.overall.completed >= progress.overall.total;
}

function renderProgress() {
  if (!state.job || !state.progress) return;
  const { overall, stores } = state.progress;
  const pct = percent(overall.percent);
  const statuses = Object.values(stores).map((store) => store.statuses || {});
  const count = (status) => statuses.reduce((total, group) => total + (Number(group[status]) || 0), 0);
  const canceled = count("canceled");
  const complete = jobComplete(state.progress);
  const label = complete ? (canceled ? "Завершено с отменой" : "Завершено") : "В работе";
  const statusClass = complete ? (canceled ? "canceled" : "done") : "active";

  el("job-created").textContent = `Создано: ${formatDate(state.job.created_at)} · ${state.job.total_products} ${plural(state.job.total_products, "товар", "товара", "товаров")}`;
  el("cancel-job").disabled = complete;
  el("export-job").href = `${API}/${state.selectedJobId}/export`;

  const cards = STORES.map(({ id, label: storeLabel }) => {
    const store = stores[id] || { total: 0, completed: 0, percent: 0, statuses: {} };
    const s = store.statuses || {};
    const found = Number(s.found) || 0;
    const failed = Number(s.failed) || 0;
    return `<div class="store-card">
      <div class="store-card-top"><span class="store-name">${storeLabel}</span><span class="store-percent">${percent(store.percent)}%</span></div>
      <div class="progress-track" role="progressbar" aria-label="${storeLabel}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${percent(store.percent)}">
        <div class="progress-bar" style="width:${percent(store.percent)}%"></div>
      </div>
      <div class="store-description">${Number(store.completed)} из ${Number(store.total)} обработано<br>
      Найдено: ${found}${failed ? ` · Ошибок: ${failed}` : ""}</div>
    </div>`;
  }).join("");

  el("progress-content").innerHTML = `
    <div class="overall">
      <div><div class="overall-number">${pct}%</div><div class="overall-detail">${Number(overall.completed)} из ${Number(overall.total)} поисков завершено</div></div>
      <span class="status-label ${statusClass}">${label}</span>
    </div>
    <div class="progress-track" role="progressbar" aria-label="Общий прогресс" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}">
      <div class="progress-bar" style="width:${pct}%"></div>
    </div>
    <div class="stores-progress">${cards}</div>
    <div class="progress-meta">
      <span>Найдено: <b>${count("found")}</b></span>
      <span>Не найдено: <b>${count("not_found")}</b></span>
      <span>Ошибки: <b>${count("failed")}</b></span>
      <span>Отменено: <b>${canceled}</b></span>
    </div>
  `;
}

function getSearch(product, storeId) {
  return product.searches?.find((search) => search.store === storeId);
}

function validOffers(search) {
  return (search?.offers || []).filter((offer) => Number.isFinite(Number(offer.price)) && Number(offer.price) > 0);
}

function minOffer(search) {
  const offers = validOffers(search);
  return offers.length ? offers.reduce((best, current) => Number(current.price) < Number(best.price) ? current : best) : null;
}

function productMatches(product) {
  if (!String(product.query ?? "").toLocaleLowerCase("ru-RU").includes(state.filterQuery)) return false;
  const searches = product.searches || [];
  switch (state.filterStatus) {
    case "found": return searches.some((search) => validOffers(search).length > 0);
    case "not_found": return searches.some((search) => search.status === "not_found");
    case "failed": return searches.some((search) => search.status === "failed");
    case "active": return searches.some((search) => !FINISHED.has(search.status));
    case "canceled": return searches.some((search) => search.status === "canceled");
    default: return true;
  }
}

function renderCell(search, bestPrice) {
  if (!search) return '<span class="cell-note">—</span>';
  const offer = minOffer(search);
  if (offer) {
    const link = safeUrl(offer.url);
    const content = escapeHtml(formatMoney(offer.price));
    const cls = Number(offer.price) === bestPrice ? "offer-price best" : "offer-price";
    return link ? `<a href="${escapeHtml(link)}" target="_blank" rel="noopener noreferrer" class="${cls}" title="Открыть предложение">${content}</a>` : `<span class="${cls}">${content}</span>`;
  }
  const text = search.status === "found" ? "Без цены" : (STATUS_LABELS[search.status] || "—");
  return `<span class="cell-note ${escapeHtml(search.status || "")}">${escapeHtml(text)}</span>`;
}

function renderOffers(product) {
  return `<div class="offer-detail-grid">${STORES.map(({ id, label }) => {
    const search = getSearch(product, id);
    const offers = validOffers(search).sort((a, b) => Number(a.price) - Number(b.price));
    const contents = offers.length ? offers.map((offer) => {
      const href = safeUrl(offer.url);
      return `<div class="offer-item">
        ${href ? `<a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">${escapeHtml(offer.name || offer.url)}</a>` : `<span>${escapeHtml(offer.name || "Предложение")}</span>`}
        <div class="offer-item-price">${escapeHtml(formatMoney(offer.price))}</div>
      </div>`;
    }).join("") : `<p class="cell-note">${escapeHtml(STATUS_LABELS[search?.status] || "Нет данных")}</p>`;
    return `<div class="offer-detail-group"><h3>${label}</h3>${contents}</div>`;
  }).join("")}</div>`;
}

function renderResults() {
  if (!state.job) return;
  const products = [...(state.job.products || [])].sort((a, b) => Number(a.position) - Number(b.position));
  const filtered = products.filter(productMatches);
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  state.page = Math.min(Math.max(1, state.page), pages);
  const visible = filtered.slice((state.page - 1) * PAGE_SIZE, state.page * PAGE_SIZE);
  const tbody = el("results-body");

  tbody.innerHTML = visible.length ? visible.map((product) => {
    const offers = STORES.map(({ id }) => minOffer(getSearch(product, id))).filter(Boolean);
    const bestPrice = offers.length ? Math.min(...offers.map((offer) => Number(offer.price))) : null;
    const isExpanded = state.expanded.has(product.id);
    const cells = STORES.map(({ id }) => `<td>${renderCell(getSearch(product, id), bestPrice)}</td>`).join("");
    return `<tr class="product-row">
      <td><span class="product-position">${Number(product.position) + 1}.</span><span class="product-title">${escapeHtml(product.query)}</span></td>
      ${cells}
      <td><button type="button" class="expand-button" data-expand="${Number(product.id)}" aria-label="${isExpanded ? "Скрыть" : "Показать"} предложения: ${escapeHtml(product.query)}" aria-expanded="${isExpanded}">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>
      </button></td>
    </tr>${isExpanded ? `<tr class="offer-detail-row"><td colspan="5">${renderOffers(product)}</td></tr>` : ""}`;
  }).join("") : '<tr><td colspan="5" class="empty-state">По выбранному фильтру ничего не найдено.</td></tr>';

  el("results-count").textContent = `Показано ${visible.length} из ${filtered.length} товаров`;
  el("page-indicator").textContent = `${state.page} / ${pages}`;
  el("prev-page").disabled = state.page <= 1;
  el("next-page").disabled = state.page >= pages;
  el("results-subtitle").textContent = `${products.length} ${plural(products.length, "товар", "товара", "товаров")} · нажмите стрелку, чтобы увидеть все предложения`;
}

async function loadDetails({ silent = false } = {}) {
  const id = state.selectedJobId;
  if (!id || state.loadingFor === id) return;
  const token = ++state.detailsRequest;
  state.loadingFor = id;
  el("refresh-details").disabled = true;

  try {
    const [job, progress] = await Promise.all([
      request(`${API}/${id}`),
      request(`${API}/${id}/progress`),
    ]);
    if (id !== state.selectedJobId || token !== state.detailsRequest) return;
    state.job = job;
    state.progress = progress;
    setConnection(true);
    renderProgress();
    renderResults();
  } catch (error) {
    if (id !== state.selectedJobId || token !== state.detailsRequest) return;
    if (!silent) toast(error.message, true);
    if (!state.job) {
      el("progress-content").innerHTML = `<p class="empty-state">Не удалось загрузить прогресс. Нажмите «Обновить».</p>`;
      el("results-body").innerHTML = '<tr><td colspan="5" class="empty-state">Не удалось загрузить результаты.</td></tr>';
    }
  } finally {
    if (token === state.detailsRequest) {
      state.loadingFor = null;
      el("refresh-details").disabled = false;
    }
  }
}

async function submitQueries(event) {
  event.preventDefault();
  if (state.busySubmit) return;
  const queries = currentQueries();
  if (!queries.length) return;
  setSubmitBusy(true);
  try {
    const job = await request(API, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ queries }),
    });
    el("queries").value = "";
    el("create-panel").open = false;
    toast(`Задание #${job.id} создано.`);
    await loadJobs({ selectId: job.id });
  } catch (error) {
    toast(error.message, true);
  } finally {
    setSubmitBusy(false);
  }
}

async function uploadExcel(event) {
  const file = event.target.files?.[0];
  if (!file || state.busySubmit) return;
  if (!file.name.toLowerCase().endsWith(".xlsx")) {
    toast("Поддерживаются только файлы .xlsx", true);
    el("excel-file").value = "";
    return;
  }
  setSubmitBusy(true);
  try {
    const form = new FormData();
    form.append("file", file);
    const job = await request(`${API}/upload`, { method: "POST", body: form });
    el("create-panel").open = false;
    toast(`Задание #${job.id} создано из файла ${file.name}.`);
    await loadJobs({ selectId: job.id });
  } catch (error) {
    toast(error.message, true);
  } finally {
    el("excel-file").value = "";
    setSubmitBusy(false);
  }
}

async function cancelCurrentJob() {
  if (!state.selectedJobId || !state.progress || jobComplete(state.progress)) return;
  const id = state.selectedJobId;
  if (!window.confirm(`Отменить незавершённые поиски задания #${id}?`)) return;
  el("cancel-job").disabled = true;
  try {
    await request(`${API}/${id}/cancel`, { method: "POST" });
    toast(`Задание #${id}: отмена отправлена.`);
    await loadDetails();
  } catch (error) {
    toast(error.message, true);
    if (id === state.selectedJobId && state.progress && !jobComplete(state.progress)) {
      el("cancel-job").disabled = false;
    }
  }
}

function init() {
  el("queries").addEventListener("input", updateQueryCount);
  el("create-form").addEventListener("submit", (event) => { void submitQueries(event); });
  el("upload-button").addEventListener("click", () => el("excel-file").click());
  el("excel-file").addEventListener("change", (event) => { void uploadExcel(event); });
  el("refresh-jobs").addEventListener("click", () => { void loadJobs(); });
  el("refresh-details").addEventListener("click", () => { void loadDetails(); });
  el("cancel-job").addEventListener("click", () => { void cancelCurrentJob(); });

  el("jobs-list").addEventListener("click", (event) => {
    const button = event.target.closest("[data-job-id]");
    if (button) selectJob(Number(button.dataset.jobId));
  });

  el("results-body").addEventListener("click", (event) => {
    const button = event.target.closest("[data-expand]");
    if (!button) return;
    const productId = Number(button.dataset.expand);
    if (state.expanded.has(productId)) state.expanded.delete(productId);
    else state.expanded.add(productId);
    renderResults();
  });

  el("filter-query").addEventListener("input", (event) => {
    state.filterQuery = event.target.value.trim().toLocaleLowerCase("ru-RU");
    state.page = 1;
    renderResults();
  });
  el("filter-status").addEventListener("change", (event) => {
    state.filterStatus = event.target.value;
    state.page = 1;
    renderResults();
  });
  el("prev-page").addEventListener("click", () => { state.page -= 1; renderResults(); });
  el("next-page").addEventListener("click", () => { state.page += 1; renderResults(); });

  updateQueryCount();
  const urlJob = Number(new URLSearchParams(window.location.search).get("job"));
  if (Number.isSafeInteger(urlJob) && urlJob > 0) state.selectedJobId = urlJob;
  void loadJobs();

  window.setInterval(() => {
    if (document.hidden || !state.selectedJobId || state.loadingFor !== null) return;
    if (!state.progress || !jobComplete(state.progress)) void loadDetails({ silent: true });
  }, POLL_MS);
}

init();
