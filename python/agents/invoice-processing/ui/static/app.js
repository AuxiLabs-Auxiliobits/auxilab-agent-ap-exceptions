/* ============================================================
   AP Exception Intelligence — Dashboard JS
   ============================================================ */

'use strict';

// ── State ────────────────────────────────────────────────────
let DATA = null;
let charts = {};
let activeView = 'overview';

// ── Init ─────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initClock();
  initThemeToggle();
  initNav();
  initRefresh();
  initModal();
  initQueueFilters();
  loadData();
});

// ── Clock ────────────────────────────────────────────────────
function initClock() {
  const el = document.getElementById('topbar-time');
  const tick = () => {
    const now = new Date();
    const options = { timeZone: 'Asia/Kolkata', year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false };
    el.textContent = now.toLocaleString('en-IN', options) + ' IST';
  };
  tick();
  setInterval(tick, 1000);
}

// ── Theme Toggle ─────────────────────────────────────────────
function initThemeToggle() {
  const btn = document.getElementById('theme-toggle-btn');
  const iconDark = document.getElementById('theme-icon-dark');
  const iconLight = document.getElementById('theme-icon-light');

  const currentTheme = localStorage.getItem('theme') || 'dark';
  if (currentTheme === 'light') {
    document.documentElement.classList.add('light-mode');
    if (iconDark) iconDark.style.display = 'none';
    if (iconLight) iconLight.style.display = 'block';
  }

  btn?.addEventListener('click', () => {
    document.documentElement.classList.toggle('light-mode');
    const isLight = document.documentElement.classList.contains('light-mode');
    localStorage.setItem('theme', isLight ? 'light' : 'dark');

    if (iconDark) iconDark.style.display = isLight ? 'none' : 'block';
    if (iconLight) iconLight.style.display = isLight ? 'block' : 'none';

    // Re-render charts for color updates
    renderCharts();
    renderAnalytics();
  });
}

// ── Navigation ───────────────────────────────────────────────
function initNav() {
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', e => {
      e.preventDefault();
      const view = item.dataset.view;
      switchView(view);
    });
  });

  // Btn-ghost view links (e.g. "View All →")
  document.querySelectorAll('.btn-ghost[data-view]').forEach(btn => {
    btn.addEventListener('click', () => switchView(btn.dataset.view));
  });

  // Mobile sidebar toggle
  const toggle = document.getElementById('menu-toggle');
  const sidebar = document.getElementById('sidebar');
  toggle?.addEventListener('click', () => sidebar.classList.toggle('open'));
  document.addEventListener('click', e => {
    if (sidebar.classList.contains('open') && !sidebar.contains(e.target) && e.target !== toggle) {
      sidebar.classList.remove('open');
    }
  });
}

function switchView(view) {
  if (activeView === view) return;
  activeView = view;
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

  const viewEl = document.getElementById(`view-${view}`);
  const navEl = document.getElementById(`nav-${view}`);
  if (viewEl) viewEl.classList.add('active');
  if (navEl) navEl.classList.add('active');

  const titles = {
    overview: ['Command Center', 'Real-time exception intelligence'],
    queue: ['Priority Queue', 'Ranked exception work items'],
    analytics: ['Analytics', 'Exception patterns & distributions'],
    history: ['Run History', 'Past pipeline execution runs'],
  };
  const [t, s] = titles[view] || ['Dashboard', ''];
  document.getElementById('view-title').textContent = t;
  document.getElementById('view-subtitle').textContent = s;

  // Trigger chart resize
  setTimeout(() => Object.values(charts).forEach(c => c?.resize?.()), 50);
}

// ── Refresh ──────────────────────────────────────────────────
function initRefresh() {
  document.getElementById('refresh-btn').addEventListener('click', () => {
    loadData(true);
  });
}

// ── Data loading ─────────────────────────────────────────────
async function loadData(forceRefresh = false) {
  const btn = document.getElementById('refresh-btn');
  btn.classList.add('spinning');
  try {
    const res = await fetch('/api/dashboard?' + Date.now());
    if (!res.ok) throw new Error('No pipeline data found');
    DATA = await res.json();
    render();
    updateStatus(true);
    if (forceRefresh) showToast('✓ Dashboard refreshed');
  } catch (err) {
    updateStatus(false, err.message);
    showToast('⚠ ' + err.message);
  } finally {
    btn.classList.remove('spinning');
  }
}

function updateStatus(ok, msg = '') {
  const pill = document.getElementById('status-pill');
  const text = document.getElementById('status-text');
  pill.className = 'status-pill' + (ok ? '' : ' error');
  pill.querySelector('.status-dot').className = 'status-dot' + (ok ? ' pulsing' : '');
  text.textContent = ok ? 'Live Data' : 'Error';
}

// ── Render all ───────────────────────────────────────────────
function render() {
  if (!DATA) return;
  renderKPIs();
  renderRunBadge();
  renderCharts();
  renderBusinessValue();
  renderSnapshotTable();
  renderFullQueue();
  renderAnalytics();
  renderHistory();
}

// ── KPIs ─────────────────────────────────────────────────────
function renderKPIs() {
  const db = DATA.dashboard || {};
  const bv = db.business_value_metrics || {};

  set('val-blocked', db.payments_blocked ?? '—');
  set('val-escalations', db.escalations_required ?? '—');
  set('val-total', db.total_invoices ?? '—');
  set('val-approved', db.valid_invoices_count ?? '—');
  set('val-score', formatScore(db.average_normalized_priority_score));
  set('val-blocked-value', formatCurrency(bv.blocked_payment_value));
}

function renderRunBadge() {
  const ts = DATA.timestamp || '';
  const short = ts.slice(0, 12);
  document.getElementById('run-ts-short').textContent = short ? ('Last Run: ' + short) : 'Latest run';
}

// ── Charts ───────────────────────────────────────────────────
function renderCharts() {
  const db = DATA.dashboard || {};
  const byType = db.exception_count_by_type || {};

  // Donut — exception types
  destroyChart('chart-donut');
  const donutCtx = document.getElementById('chart-donut').getContext('2d');
  const donutColors = ['#00c8ff', '#ff4060', '#ffb300', '#00ff88', '#b060ff', '#ff8040', '#40e0d0', '#ff60a0'];
  const labels = Object.keys(byType);
  const values = Object.values(byType);
  charts['chart-donut'] = new Chart(donutCtx, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{ data: values, backgroundColor: donutColors.slice(0, labels.length), borderWidth: 0, hoverOffset: 6 }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      cutout: '68%',
      plugins: {
        legend: { display: false },
        tooltip: Object.assign(tooltipDefaults(), {
          callbacks: {
            label: ctx => ` ${ctx.label}: ${ctx.parsed} (${Math.round(ctx.parsed / values.reduce((a, b) => a + b, 0) * 100)}%)`
          }
        })
      }
    }
  });

  // Legend
  const legendEl = document.getElementById('donut-legend');
  legendEl.innerHTML = labels.map((l, i) =>
    `<div class="legend-item"><div class="legend-dot" style="background:${donutColors[i]}"></div>${l}</div>`
  ).join('');

  // Bar chart — priority tiers
  destroyChart('chart-bar');
  const queue = DATA.priority_queue || [];
  const tierCounts = { HIGH: 0, MEDIUM: 0, LOW: 0 };
  queue.forEach(inv => { if (inv.priority_tier in tierCounts) tierCounts[inv.priority_tier]++; });

  const barCtx = document.getElementById('chart-bar').getContext('2d');
  charts['chart-bar'] = new Chart(barCtx, {
    type: 'bar',
    data: {
      labels: ['HIGH', 'MEDIUM', 'LOW'],
      datasets: [{
        data: [tierCounts.HIGH, tierCounts.MEDIUM, tierCounts.LOW],
        backgroundColor: ['rgba(255,64,96,0.7)', 'rgba(255,179,0,0.7)', 'rgba(0,200,255,0.7)'],
        borderRadius: 8,
        borderWidth: 0,
        hoverBackgroundColor: ['#ff4060', '#ffb300', '#00c8ff'],
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: tooltipDefaults(),
      },
      scales: {
        x: { grid: { color: document.documentElement.classList.contains('light-mode') ? 'rgba(0,0,0,0.05)' : 'rgba(255,255,255,0.04)' }, ticks: { color: document.documentElement.classList.contains('light-mode') ? '#4a5568' : '#7a9bbf', font: { size: 12 } } },
        y: { grid: { color: document.documentElement.classList.contains('light-mode') ? 'rgba(0,0,0,0.05)' : 'rgba(255,255,255,0.04)' }, ticks: { color: document.documentElement.classList.contains('light-mode') ? '#4a5568' : '#7a9bbf', font: { size: 12 }, precision: 0 } }
      }
    }
  });
}

function tooltipDefaults() {
  const isLight = document.documentElement.classList.contains('light-mode');
  return {
    backgroundColor: isLight ? '#ffffff' : '#0f1c31',
    titleColor: isLight ? '#1a202c' : '#e8f4ff',
    bodyColor: isLight ? '#4a5568' : '#7a9bbf',
    borderColor: isLight ? 'rgba(0,122,204,0.3)' : 'rgba(0,200,255,0.2)',
    borderWidth: 1,
  };
}

function destroyChart(id) {
  if (charts[id]) { charts[id].destroy(); delete charts[id]; }
}

// ── Business Value ────────────────────────────────────────────
function renderBusinessValue() {
  const bv = (DATA.dashboard || {}).business_value_metrics || {};
  const vals = [
    { id: 'blocked', amount: bv.blocked_payment_value || 0 },
    { id: 'dup', amount: bv.potential_duplicate_payment_value || 0 },
    { id: 'valid', amount: bv.valid_invoice_value || 0 },
  ];
  const max = Math.max(...vals.map(v => v.amount), 1);
  vals.forEach(({ id, amount }) => {
    const pct = Math.round((amount / max) * 100);
    const bar = document.getElementById(`vbar-${id}`);
    const amt = document.getElementById(`vamt-${id}`);
    if (bar) setTimeout(() => bar.style.width = pct + '%', 100);
    if (amt) amt.textContent = formatCurrency(amount);
  });
}

// ── Snapshot table (top 5) ────────────────────────────────────
function renderSnapshotTable() {
  const tbody = document.getElementById('snapshot-tbody');
  const queue = (DATA.priority_queue || []).slice(0, 5);
  if (!queue.length) {
    tbody.innerHTML = `<tr><td colspan="8"><div class="empty-state">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg>
      <h3>No exceptions found</h3><p>Run the pipeline to populate this view.</p>
    </div></td></tr>`;
    return;
  }
  tbody.innerHTML = queue.map(inv => invoiceRow(inv, true)).join('');
  bindDetailBtns(tbody);
}

// ── Full Priority Queue ───────────────────────────────────────
function renderFullQueue() {
  renderFilteredQueue();
}

function initQueueFilters() {
  ['tier-filter', 'status-filter'].forEach(id => {
    document.getElementById(id)?.addEventListener('change', renderFilteredQueue);
  });
  document.getElementById('queue-search')?.addEventListener('input', renderFilteredQueue);
}

function renderFilteredQueue() {
  if (!DATA) return;
  const tierF = document.getElementById('tier-filter')?.value || 'all';
  const statusF = document.getElementById('status-filter')?.value || 'all';
  const search = (document.getElementById('queue-search')?.value || '').toLowerCase();

  let queue = DATA.priority_queue || [];
  if (tierF !== 'all') queue = queue.filter(i => i.priority_tier === tierF);
  if (statusF === 'blocked') queue = queue.filter(i => i.payment_blocked);
  if (statusF === 'escalation') queue = queue.filter(i => i.escalation_required);
  if (search) {
    queue = queue.filter(i =>
      (i.invoice_id || '').toLowerCase().includes(search) ||
      (i.vendor_name || '').toLowerCase().includes(search) ||
      (i.invoice_number || '').toLowerCase().includes(search)
    );
  }

  const tbody = document.getElementById('queue-tbody');
  const countEl = document.getElementById('queue-count');
  countEl.textContent = `${queue.length} item${queue.length !== 1 ? 's' : ''}`;

  if (!queue.length) {
    tbody.innerHTML = `<tr><td colspan="11"><div class="empty-state">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
      <h3>No results</h3><p>Try adjusting your filters.</p>
    </div></td></tr>`;
    return;
  }
  tbody.innerHTML = queue.map(inv => invoiceRow(inv, false)).join('');
  bindDetailBtns(tbody);
}

function invoiceRow(inv, short) {
  const excs = inv.final_exception_list || [];
  const excPills = excs.map(e => `<span class="exc-pill">${e.primary_type}</span>`).join('');
  const tier = inv.priority_tier || 'LOW';
  const scoreClass = tier === 'HIGH' ? 'score-high' : tier === 'MEDIUM' ? 'score-medium' : 'score-low';

  const blockedIcon = inv.payment_blocked
    ? `<svg class="status-icon blocked-yes" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>`
    : `<svg class="status-icon blocked-no" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/></svg>`;
  const escIcon = inv.escalation_required
    ? `<svg class="status-icon esc-yes" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`
    : `<svg class="status-icon blocked-no" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/></svg>`;

  if (short) {
    return `<tr>
      <td><code style="color:var(--blue);font-family:'JetBrains Mono',monospace;font-size:12px">${inv.invoice_number || inv.invoice_id}</code></td>
      <td>${inv.vendor_name || '—'}</td>
      <td><strong>${formatCurrency(inv.invoice_amount)}</strong></td>
      <td><span class="tier-badge tier-${tier}">${tier}</span></td>
      <td><span class="${scoreClass}" style="font-weight:700">${inv.normalized_priority_score ?? '—'}</span></td>
      <td>${inv.sla_hours}h</td>
      <td>${blockedIcon}${escIcon}</td>
      <td>${excPills}</td>
    </tr>`;
  }

  return `<tr>
    <td><code style="color:var(--blue);font-family:'JetBrains Mono',monospace;font-size:12px">${inv.invoice_number || inv.invoice_id}</code></td>
    <td>${inv.vendor_name || '—'}</td>
    <td style="color:var(--text-muted)"><span title="Internal Tracking ID">${inv.invoice_id}</span></td>
    <td><strong>${formatCurrency(inv.invoice_amount)}</strong></td>
    <td><span class="tier-badge tier-${tier}">${tier}</span></td>
    <td><span class="${scoreClass}" style="font-weight:700">${inv.normalized_priority_score ?? '—'}</span></td>
    <td>${inv.sla_hours}h</td>
    <td>${blockedIcon}</td>
    <td>${escIcon}</td>
    <td>${excPills}</td>
    <td><button class="detail-btn" data-invoice-id="${inv.invoice_id}">Details</button></td>
  </tr>`;
}

function bindDetailBtns(tbody) {
  tbody.querySelectorAll('.detail-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const inv = [...(DATA.priority_queue || [])].find(i => i.invoice_id === btn.dataset.invoiceId);
      if (inv) openDetailModal(inv);
    });
  });
}

// ── Analytics ────────────────────────────────────────────────
function renderAnalytics() {
  const db = DATA.dashboard || {};
  const byType = db.exception_count_by_type || {};

  // Horizontal bar chart — type frequency
  destroyChart('chart-hbar');
  const hbarCtx = document.getElementById('chart-hbar').getContext('2d');
  const sortedTypes = Object.entries(byType).sort((a, b) => b[1] - a[1]);
  charts['chart-hbar'] = new Chart(hbarCtx, {
    type: 'bar',
    data: {
      labels: sortedTypes.map(([t]) => t),
      datasets: [{
        data: sortedTypes.map(([, v]) => v),
        backgroundColor: 'rgba(0,200,255,0.6)',
        hoverBackgroundColor: '#00c8ff',
        borderRadius: 6,
        borderWidth: 0,
      }]
    },
    options: {
      indexAxis: 'y',
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: tooltipDefaults() },
      scales: {
        x: { grid: { color: document.documentElement.classList.contains('light-mode') ? 'rgba(0,0,0,0.05)' : 'rgba(255,255,255,0.04)' }, ticks: { color: document.documentElement.classList.contains('light-mode') ? '#4a5568' : '#7a9bbf', font: { size: 12 }, precision: 0 } },
        y: { grid: { display: false }, ticks: { color: document.documentElement.classList.contains('light-mode') ? '#1a202c' : '#e8f4ff', font: { size: 12 } } }
      }
    }
  });

  // Gauge — avg priority score
  destroyChart('chart-gauge');
  const gaugeCtx = document.getElementById('chart-gauge').getContext('2d');
  const score = db.average_normalized_priority_score || 0;
  const gaugeColor = score >= 75 ? '#ff4060' : score >= 40 ? '#ffb300' : '#00ff88';
  charts['chart-gauge'] = new Chart(gaugeCtx, {
    type: 'doughnut',
    data: {
      datasets: [{
        data: [score, 100 - score],
        backgroundColor: [gaugeColor, 'rgba(255,255,255,0.04)'],
        borderWidth: 0,
        circumference: 240, rotation: 240,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      cutout: '78%',
      plugins: { legend: { display: false }, tooltip: { enabled: false } }
    }
  });
  const readingEl = document.getElementById('gauge-reading');
  if (readingEl) {
    readingEl.style.color = gaugeColor;
    readingEl.textContent = score.toFixed(1);
  }

  // Stats list
  const statsEl = document.getElementById('analytics-stats');
  const stats = [
    { label: 'Total Invoices', value: db.total_invoices ?? '—' },
    { label: 'Valid Invoices', value: db.valid_invoices_count ?? '—' },
    { label: 'Multi-Exception', value: db.multi_exception_invoice_count ?? '—' },
    { label: 'Comm. Drafts', value: db.communication_drafts_produced ?? '—' },
    { label: '% Other Type', value: (db.percentage_other ?? '—') + '%' },
  ];
  statsEl.innerHTML = stats.map(s =>
    `<div class="stat-item">
      <div class="stat-item-label">${s.label}</div>
      <div class="stat-item-value">${s.value}</div>
    </div>`
  ).join('');
}

// ── History ──────────────────────────────────────────────────
function renderHistory() {
  const tbody = document.getElementById('history-tbody');
  const runs = DATA.run_history || [];
  if (!runs.length) {
    tbody.innerHTML = `<tr><td colspan="6" style="color:var(--text-muted);text-align:center;padding:30px">No history available</td></tr>`;
    return;
  }
  tbody.innerHTML = runs.map((r, i) => `
    <tr class="${i === 0 ? 'run-active-row' : ''}">
      <td><code style="font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--blue)">${r.run_id}</code></td>
      <td>${r.timestamp}</td>
      <td>${r.total_invoices}</td>
      <td>${r.payments_blocked}</td>
      <td>${r.escalations_required}</td>
      <td><strong>${(r.avg_score || 0).toFixed(1)}</strong></td>
    </tr>
  `).join('');
}

// ── Detail Modal ──────────────────────────────────────────────
function initModal() {
  document.getElementById('modal-close').addEventListener('click', closeModal);
  document.getElementById('modal-overlay').addEventListener('click', e => {
    if (e.target === document.getElementById('modal-overlay')) closeModal();
  });
}

function openDetailModal(inv) {
  const tier = inv.priority_tier || 'LOW';
  const excs = inv.final_exception_list || [];
  const tierColor = tier === 'HIGH' ? 'var(--red)' : tier === 'MEDIUM' ? 'var(--amber)' : 'var(--blue)';

  document.getElementById('modal-header').innerHTML = `
    <h3>${inv.invoice_id} — ${inv.vendor_name || 'Unknown Vendor'}</h3>
    <div class="modal-meta">
      Invoice ${inv.invoice_number || 'N/A'} &nbsp;·&nbsp;
      Age: ${inv.invoice_age_days} days &nbsp;·&nbsp;
      Run: ${DATA.run_id}
    </div>
  `;

  document.getElementById('modal-body').innerHTML = `
    <!-- Priority & Status Row -->
    <div class="modal-section">
      <h4>Priority & Status</h4>
      <div class="modal-kpi-row">
        <div class="modal-kpi"><div class="modal-kpi-label">Tier</div>
          <div class="modal-kpi-value" style="color:${tierColor}">${tier}</div></div>
        <div class="modal-kpi"><div class="modal-kpi-label">Score</div>
          <div class="modal-kpi-value" style="color:${tierColor}">${inv.normalized_priority_score}</div></div>
        <div class="modal-kpi"><div class="modal-kpi-label">Amount</div>
          <div class="modal-kpi-value">${formatCurrency(inv.invoice_amount)}</div></div>
        <div class="modal-kpi"><div class="modal-kpi-label">SLA</div>
          <div class="modal-kpi-value">${inv.sla_hours}h</div></div>
        <div class="modal-kpi"><div class="modal-kpi-label">Payment</div>
          <div class="modal-kpi-value" style="color:${inv.payment_blocked ? 'var(--red)' : 'var(--green)'}">
            ${inv.payment_blocked ? 'Blocked' : 'Clear'}</div></div>
        <div class="modal-kpi"><div class="modal-kpi-label">Escalation</div>
          <div class="modal-kpi-value" style="color:${inv.escalation_required ? 'var(--amber)' : 'var(--green)'}">
            ${inv.escalation_required ? 'Required' : 'None'}</div></div>
      </div>
    </div>

    <!-- Resolution -->
    <div class="modal-section">
      <h4>Resolution Owners</h4>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        ${(inv.resolution_owners || []).map(o => `<span class="exc-pill">${o}</span>`).join('') || '<span style="color:var(--text-muted)">None assigned</span>'}
      </div>
    </div>

    <!-- Root Cause Categories -->
    <div class="modal-section">
      <h4>Root Cause Categories</h4>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        ${(inv.root_cause_categories || []).map(c => `<span class="exc-pill" style="background:var(--purple-dim);color:var(--purple);border-color:rgba(176,96,255,0.2)">${c}</span>`).join('') || '<span style="color:var(--text-muted)">None</span>'}
      </div>
    </div>

    <!-- Exceptions -->
    <div class="modal-section">
      <h4>Exception Details (${excs.length})</h4>
      ${excs.map(e => `
        <div class="exc-card">
          <div class="exc-card-type">${e.primary_type}</div>
          <div class="exc-card-row">
            <span class="exc-card-label">Root Cause</span>
            <span class="exc-card-val">${e.root_cause_hypothesis || '—'}</span>
          </div>
          <div class="exc-card-row">
            <span class="exc-card-label">Recommended</span>
            <span class="exc-card-val">${e.recommended_action || '—'}</span>
          </div>
          <div class="exc-card-row">
            <span class="exc-card-label">Evidence Used</span>
            <span class="exc-card-val">${e.evidence_used || '—'}</span>
          </div>
          <div class="exc-card-row">
            <span class="exc-card-label">Evidence Checked</span>
            <span class="exc-card-val">${e.evidence_checked || '—'}</span>
          </div>
          <div class="exc-card-row">
            <span class="exc-card-label">Business Rule</span>
            <span class="exc-card-val">${e.business_rule_triggered || '—'}</span>
          </div>
          <div class="exc-card-row">
            <span class="exc-card-label">Confidence</span>
            <span class="exc-card-val" style="color:var(--green)">${((e.confidence || 0) * 100).toFixed(0)}%</span>
          </div>
        </div>
      `).join('') || '<p style="color:var(--text-muted)">No exceptions.</p>'}
    </div>

    <!-- Communication Draft -->
    ${inv.communication_draft ? `
    <div class="modal-section">
      <h4>Communication Draft</h4>
      <div style="background:var(--bg-surface);border:1px solid var(--border);border-radius:10px;padding:14px;font-size:13px;color:var(--text-secondary);white-space:pre-wrap;word-break:break-word">${inv.communication_draft}</div>
    </div>` : ''}

    <!-- Decision Trace -->
    <div class="modal-section">
      <h4>Decision Trace</h4>
      <div class="trace-list">
        ${(inv.decision_trace || []).map(t => `
          <div class="trace-item">
            <div class="trace-dot"></div>
            <span>${t}</span>
          </div>
        `).join('') || '<p style="color:var(--text-muted)">No trace available.</p>'}
      </div>
    </div>
  `;

  document.getElementById('modal-overlay').classList.add('open');
}

function closeModal() {
  document.getElementById('modal-overlay').classList.remove('open');
}

// ── Helpers ───────────────────────────────────────────────────
function set(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function formatCurrency(val) {
  if (val == null || val === '') return '—';
  const n = parseFloat(val);
  if (isNaN(n)) return '—';
  return '$' + n.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

function formatScore(val) {
  if (val == null) return '—';
  return parseFloat(val).toFixed(1);
}

function showToast(msg, duration = 3000) {
  const toast = document.getElementById('toast');
  toast.textContent = msg;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), duration);
}

// ── Upload / Ingestion ─────────────────────────────────────────
let selectedFile = null;
let currentJobId = null;
let jobPollInterval = null;

function initUpload() {
  const zone = document.getElementById('upload-zone');
  const input = document.getElementById('file-input');
  const cancelBtn = document.getElementById('btn-cancel-upload');
  const startBtn = document.getElementById('btn-start-upload');
  const uploadAnotherBtn = document.getElementById('btn-upload-another');
  const viewDashboardBtn = document.getElementById('btn-view-dashboard');

  if (!zone) return;

  // Drag and drop
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('dragover'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('dragover');
    if (e.dataTransfer.files.length) handleFileSelection(e.dataTransfer.files[0]);
  });

  input.addEventListener('change', e => {
    if (e.target.files.length) handleFileSelection(e.target.files[0]);
  });

  cancelBtn.addEventListener('click', resetUploadState);
  startBtn.addEventListener('click', uploadFile);
  if (uploadAnotherBtn) uploadAnotherBtn.addEventListener('click', resetUploadState);
  if (viewDashboardBtn) viewDashboardBtn.addEventListener('click', () => switchView('overview'));
}

function handleFileSelection(file) {
  selectedFile = file;
  document.getElementById('upload-zone').style.display = 'none';
  document.getElementById('upload-status').style.display = 'block';
  document.getElementById('upload-filename').textContent = file.name;

  const ext = file.name.split('.').pop().toLowerCase();
  const autoRunCheckbox = document.getElementById('auto-run-pipeline').closest('label');
  const autoRunLabelText = document.getElementById('auto-run-label-text');
  if (ext === 'csv') {
    autoRunCheckbox.style.display = 'flex';
    autoRunLabelText.textContent = 'Run exception pipeline automatically';
  } else {
    autoRunCheckbox.style.display = 'flex';
    autoRunLabelText.textContent = 'Run AI extraction & validation pipeline automatically';
  }
}

function resetUploadState() {
  selectedFile = null;
  document.getElementById('file-input').value = '';
  document.getElementById('upload-zone').style.display = 'block';
  document.getElementById('upload-status').style.display = 'none';
  document.getElementById('upload-progress-bar').style.width = '0%';
  document.getElementById('upload-progress-bar').classList.remove('striped');
  document.getElementById('pipeline-status-area').style.display = 'none';
  document.getElementById('upload-actions').style.display = 'flex';
  document.getElementById('post-upload-actions').style.display = 'none';
  document.getElementById('pipeline-logs').textContent = '';
  setUploadState('Ready', 'state-ready');
  if (jobPollInterval) clearInterval(jobPollInterval);
}

function setUploadState(text, cls) {
  const badge = document.getElementById('upload-state');
  badge.textContent = text;
  badge.className = 'state-badge ' + cls;
}

async function uploadFile() {
  if (!selectedFile) return;

  const formData = new FormData();
  formData.append('file', selectedFile);

  const autoRun = document.getElementById('auto-run-pipeline').checked;
  formData.append('run_pipeline', autoRun);

  document.getElementById('upload-actions').style.display = 'none';
  const progressWrap = document.querySelector('.progress-wrap');
  const progressBar = document.getElementById('upload-progress-bar');
  progressWrap.style.display = 'block';
  progressBar.style.width = '50%';

  try {
    const res = await fetch('/api/upload', {
      method: 'POST',
      body: formData
    });
    const data = await res.json();

    progressBar.style.width = '100%';

    if (data.success) {
      if (data.job_id) {
        setUploadState('Pipeline Running', 'state-running');
        progressBar.classList.add('striped');
        currentJobId = data.job_id;
        startJobPolling();
      } else {
        setUploadState('Uploaded', 'state-done');
        showToast(data.message);
        document.getElementById('post-upload-actions').style.display = 'flex';
      }
    } else {
      throw new Error(data.error);
    }
  } catch (err) {
    setUploadState('Error', 'state-error');
    progressBar.style.background = 'var(--red)';
    showToast(err.message || 'Upload failed');
    document.getElementById('post-upload-actions').style.display = 'flex';
  }
}

function startJobPolling() {
  document.getElementById('pipeline-status-area').style.display = 'block';

  jobPollInterval = setInterval(async () => {
    try {
      const res = await fetch('/api/jobs/' + currentJobId);
      const job = await res.json();

      const statusText = document.getElementById('pipeline-status-text');
      const logsPre = document.getElementById('pipeline-logs');
      const loader = document.querySelector('.pipeline-loader');

      if (job.status === 'running') {
        statusText.textContent = job.message || 'Pipeline running...';
        statusText.style.color = 'var(--amber)';
      } else if (job.status === 'done') {
        clearInterval(jobPollInterval);
        loader.classList.remove('pulsing-loader');
        loader.style.background = 'var(--green)';
        statusText.textContent = 'Pipeline completed successfully!';
        statusText.style.color = 'var(--green)';
        setUploadState('Done', 'state-done');
        document.getElementById('upload-progress-bar').classList.remove('striped');

        if (job.stdout) {
          logsPre.textContent = job.stdout;
          logsPre.scrollTop = logsPre.scrollHeight;
        }

        showToast('Pipeline finished processing new data');
        document.getElementById('post-upload-actions').style.display = 'flex';

        if (job.type === 'inference') {
          if (job.postprocessing) {
            const pp = job.postprocessing;
            const invProc = pp["Invoice Processing"] || {};
            const invDet = pp["Invoice Details"] || {};
            const vendInfo = pp["Vendor Information"] || {};

            const status = invProc["Invoice Status"] || "Unknown";
            const reason = invProc["Rejection Reason"] || "";
            const phase = invProc["Rejection Phase"] || "";

            const isRejected = status.toLowerCase() === "rejected" || status === "ERROR" || status === "REJECT";

            const mockInv = {
              invoice_id: job.filename,
              vendor_name: vendInfo["Vendor Name"] || "Unknown",
              invoice_number: invDet["Vendor Invoice"] || "Unknown",
              invoice_age_days: 0,
              priority_tier: isRejected ? "HIGH" : "LOW",
              normalized_priority_score: isRejected ? 100 : 0,
              invoice_amount: invDet["Invoice Total"] || "0.00",
              sla_hours: isRejected ? 24 : 0,
              payment_blocked: isRejected,
              escalation_required: isRejected,
              resolution_owners: ["AP Specialist"],
              root_cause_categories: [reason ? "Validation Failed" : "Success"],
              final_exception_list: isRejected ? [{
                primary_type: reason || "Validation Failure",
                root_cause_hypothesis: phase ? `Failed during ${phase}` : "Unknown",
                recommended_action: "Review extracted data and correct",
                evidence_used: "Acting Agent Pipeline",
                evidence_checked: "Reconstructed Rules Book",
                business_rule_triggered: "N/A",
                confidence: 1.0
              }] : [],
              decision_trace: [
                `Acting Agent: ${status}`,
                reason ? `Reason: ${reason}` : "Invoice Passed Validation",
                `Phase: ${phase || "All"}`
              ]
            };

            // Put it in the logs
            logsPre.textContent = "=== INFERENCE RESULT ===\n" + JSON.stringify(job.postprocessing, null, 2);
            logsPre.scrollTop = 0;

            if (isRejected) {
              showToast('Invoice rejected. Added to Priority Queue.');
              // Give the background queue pipeline a moment to process, then refresh
              setTimeout(() => {
                loadData(true);
                switchView('queue');
              }, 5000);
            }

          } else if (job.result) {
            logsPre.textContent = "=== INFERENCE RESULT ===\n" + JSON.stringify(job.result, null, 2);
            logsPre.scrollTop = 0;
          } else {
            logsPre.textContent = job.stderr || job.stdout;
          }
        } else {
          // Auto refresh dashboard data in background
          loadData();
        }
      } else if (job.status === 'error') {
        clearInterval(jobPollInterval);
        loader.classList.remove('pulsing-loader');
        loader.style.background = 'var(--red)';
        statusText.textContent = 'Pipeline failed';
        statusText.style.color = 'var(--red)';
        setUploadState('Error', 'state-error');
        document.getElementById('upload-progress-bar').classList.remove('striped');
        document.getElementById('upload-progress-bar').style.background = 'var(--red)';

        logsPre.textContent = job.message || 'Unknown error occurred';
        document.getElementById('post-upload-actions').style.display = 'flex';
      }

    } catch (err) {
      console.error("Polling error:", err);
    }
  }, 2000);
}

// Hook it up in DOMContentLoaded
document.addEventListener('DOMContentLoaded', () => {
  initUpload();
});

