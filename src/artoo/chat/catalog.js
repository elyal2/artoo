// Catalog tab: upload documentation -> review the proposed before/after -> apply to OpenMetadata.
// Relies on escHtml() from index.html. Nothing is written until "Apply selected" is pressed.
(function () {
  const FIELD_LABEL = {
    table_description: 'Table description',
    table_business_rules: 'Business rules',
    table_display_name: 'Table name',
    column_description: 'Column description',
    column_display_name: 'Column name',
  };
  const ACCEPT = '.pdf,.png,.jpg,.jpeg,.gif,.webp,.docx,.csv,.tsv,.txt,.md,.json,.yaml,.yml,.xml,.sql,.html,.htm';

  const area = document.getElementById('catalog-area');
  const state = { files: [], proposal: null, busy: false, note: '' };

  function showView(view) {
    document.body.classList.toggle('view-catalog', view === 'catalog');
    document.querySelectorAll('.view-switch button').forEach(b => b.classList.toggle('active', b.dataset.view === view));
  }
  window.showView = showView;
  document.querySelectorAll('.view-switch button').forEach(b => b.addEventListener('click', () => showView(b.dataset.view)));

  function shortName(fqn) { return String(fqn).split('.').pop(); }

  function renderForm() {
    area.innerHTML = `<div class="cat-wrap">
      <div>
        <h1>Enrich the catalog from documentation</h1>
        <p class="cat-lead">Upload requirements, data dictionaries, specifications or diagrams. The model reads them next to what OpenMetadata already knows and proposes descriptions and business rules, each with its source. Nothing is written until you review and apply it.</p>
      </div>
      <div class="cat-drop" id="cat-drop" tabindex="0" role="button" aria-label="Choose documents">
        Drop documents here or click to choose
        <small>PDF · images · docx · csv · md · txt · json · yaml · sql — up to 10 files</small>
        <input type="file" id="cat-input" multiple accept="${ACCEPT}" hidden />
      </div>
      <div class="cat-files" id="cat-files"></div>
      <textarea class="cat-note" id="cat-note" placeholder="Optional note for the model: what these documents are about, which parts to ignore…"></textarea>
      <div class="cat-row">
        <button class="cat-btn" id="cat-run" type="button" disabled>Analyze documents</button>
        <span id="cat-status" class="cat-lead"></span>
      </div>
      <div id="cat-result"></div>
    </div>`;

    const drop = area.querySelector('#cat-drop');
    const input = area.querySelector('#cat-input');
    drop.addEventListener('click', () => input.click());
    drop.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); } });
    ['dragenter', 'dragover'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add('over'); }));
    ['dragleave', 'drop'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove('over'); }));
    drop.addEventListener('drop', e => addFiles(e.dataTransfer.files));
    input.addEventListener('change', () => { addFiles(input.files); input.value = ''; });
    area.querySelector('#cat-run').addEventListener('click', analyze);
    drawFiles();
  }

  function addFiles(list) {
    for (const f of list) if (!state.files.some(x => x.name === f.name && x.size === f.size)) state.files.push(f);
    drawFiles();
  }

  function drawFiles() {
    const box = area.querySelector('#cat-files');
    box.innerHTML = state.files.map((f, i) =>
      `<span class="cat-file">${escHtml(f.name)} <small>${(f.size / 1024).toFixed(0)} KB</small><button type="button" data-i="${i}" aria-label="Remove ${escHtml(f.name)}">✕</button></span>`).join('');
    box.querySelectorAll('button').forEach(b => b.addEventListener('click', () => { state.files.splice(+b.dataset.i, 1); drawFiles(); }));
    area.querySelector('#cat-run').disabled = state.busy || state.files.length === 0;
  }

  async function analyze() {
    const status = area.querySelector('#cat-status');
    const result = area.querySelector('#cat-result');
    const body = new FormData();
    state.files.forEach(f => body.append('files', f, f.name));
    body.append('instructions', area.querySelector('#cat-note').value);
    state.busy = true; state.note = ''; drawFiles(); result.innerHTML = '';
    status.innerHTML = `<span class="thinking"><span class="dot"></span><span class="dot"></span><span class="dot"></span><span>Reading ${state.files.length} document${state.files.length > 1 ? 's' : ''} and the current catalog — this can take a minute</span></span>`;
    try {
      const res = await fetch('/api/catalog/propose', { method: 'POST', body });
      if (!res.ok) {
        let detail = res.statusText;
        try { detail = (await res.json()).detail || detail; } catch {}
        throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
      }
      state.proposal = await res.json();
      status.textContent = '';
      renderProposal(result);
    } catch (err) {
      status.innerHTML = `<div class="error-msg">${escHtml(String(err.message || err))}</div>`;
    } finally {
      state.busy = false; drawFiles();
    }
  }

  function renderProposal(root) {
    const p = state.proposal;
    let html = '';
    if (p.summary) html += `<div class="cat-summary">${escHtml(p.summary)}</div>`;
    (p.warnings || []).forEach(w => { html += `<div class="cat-warn">${escHtml(w)}</div>`; });

    if (!p.items.length) {
      html += `<div class="cat-summary">The documentation did not suggest any change the catalog does not already have.</div>`;
    } else {
      html += `<div class="cat-section">Proposed changes · ${p.items.length}</div>`;
      const byTable = {};
      p.items.forEach((it, i) => { (byTable[it.table] = byTable[it.table] || []).push([it, i]); });
      Object.keys(byTable).forEach(t => {
        html += `<div class="cat-table-name">${escHtml(shortName(t))}</div>`;
        byTable[t].forEach(([it, i]) => { html += itemHtml(it, i); });
      });
    }
    if ((p.open_questions || []).length) {
      html += `<div class="cat-section">Open questions · ${p.open_questions.length}</div>`;
      p.open_questions.forEach(q => {
        html += `<div class="cat-q">${escHtml(q.question)}<small>${escHtml([q.source, (q.tables || []).join(', ')].filter(Boolean).join(' · '))}</small></div>`;
      });
    }
    if (p.items.length) {
      html += `<div class="cat-bar cat-row">
        <button class="cat-btn" id="cat-apply" type="button">Apply selected</button>
        <button class="cat-btn ghost" id="cat-all" type="button">Select all</button>
        <button class="cat-btn ghost" id="cat-none" type="button">Select none</button>
        <span id="cat-count" class="cat-lead"></span>
      </div>`;
    }
    root.innerHTML = html;

    root.querySelectorAll('.cat-item').forEach(el => {
      el.querySelector('input[type=checkbox]').addEventListener('change', () => { syncItem(el); updateCount(); });
    });
    const setAll = on => { root.querySelectorAll('.cat-item input[type=checkbox]:not(:disabled)').forEach(c => { c.checked = on; syncItem(c.closest('.cat-item')); }); updateCount(); };
    root.querySelector('#cat-all')?.addEventListener('click', () => setAll(true));
    root.querySelector('#cat-none')?.addEventListener('click', () => setAll(false));
    root.querySelector('#cat-apply')?.addEventListener('click', applySelected);
    updateCount();
  }

  function itemHtml(it, i) {
    const checked = it.confidence !== 'low';
    const col = it.column ? `<b>${escHtml(it.column)}</b> · ` : '';
    const badge = { high: 'badge-high', medium: 'badge-medium', low: 'badge-low' }[it.confidence] || 'badge-medium';
    const before = it.before ? escHtml(it.before) : '(empty)';
    return `<div class="cat-item ${checked ? '' : 'off'}" data-i="${i}">
      <div class="cat-item-head">
        <span class="what">${col}${escHtml(FIELD_LABEL[it.field] || it.field)}</span>
        <span class="badge ${badge}">${escHtml(it.confidence)}</span>
        <label><input type="checkbox" ${checked ? 'checked' : ''} aria-label="Apply this change" /> apply</label>
      </div>
      <div class="cat-diff">
        <div><h4>Now in the catalog</h4><div class="cat-before ${it.before ? '' : 'empty'}">${before}</div></div>
        <div><h4>Proposed (editable)</h4><textarea class="cat-after" aria-label="Proposed value">${escHtml(it.after)}</textarea></div>
      </div>
      <div class="cat-foot"><q>${escHtml(it.source)}</q>${it.rationale ? ` — ${escHtml(it.rationale)}` : ''}<span class="res"></span></div>
    </div>`;
  }

  function syncItem(el) { el.classList.toggle('off', !el.querySelector('input[type=checkbox]').checked); }
  function updateCount() {
    const n = area.querySelectorAll('.cat-item input[type=checkbox]:checked:not(:disabled)').length;
    const c = area.querySelector('#cat-count'); if (c) c.textContent = state.note ? `${n} selected · ${state.note}` : `${n} selected`;
    const b = area.querySelector('#cat-apply'); if (b) b.disabled = n === 0;
  }

  async function applySelected() {
    const btn = area.querySelector('#cat-apply');
    const picked = [...area.querySelectorAll('.cat-item')].filter(el => el.querySelector('input[type=checkbox]').checked && !el.querySelector('input[type=checkbox]').disabled);
    const items = picked.map(el => ({ ...state.proposal.items[+el.dataset.i], after: el.querySelector('.cat-after').value }));
    if (!items.length) return;
    btn.disabled = true; btn.textContent = 'Applying…';
    try {
      const res = await fetch('/api/catalog/apply', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ items }) });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
      const { outcomes } = await res.json();
      let ok = 0;
      outcomes.forEach(o => {
        const el = picked.find(p => state.proposal.items[+p.dataset.i].id === o.id);
        if (!el) return;
        const res = el.querySelector('.res');
        if (o.status === 'ok') {
          ok++; el.classList.add('done-ok'); res.className = 'res ok'; res.textContent = '✓ Written to OpenMetadata';
          el.querySelector('input[type=checkbox]').checked = false; el.querySelector('input[type=checkbox]').disabled = true;
          el.querySelector('.cat-after').readOnly = true;
        } else {
          el.classList.add('done-err'); res.className = 'res err'; res.textContent = '✕ ' + (o.detail || 'failed');
        }
      });
      state.note = `${ok} of ${outcomes.length} applied — ask a question in the chat to see the effect.`;
    } catch (err) {
      state.note = 'Apply failed: ' + (err.message || err);
    } finally {
      btn.textContent = 'Apply selected'; updateCount();
    }
  }

  state.note = '';
  renderForm();
})();
