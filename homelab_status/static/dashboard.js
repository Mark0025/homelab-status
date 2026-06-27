let allData = null;
let allRoutes = null;
let activeFilter = 'all';
let activeTab = 'services';

// ── Tab switching ─────────────────────────────────────────────────────────
function showTab(name, el) {
  activeTab = name;
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
  document.getElementById('services-view').style.display = name === 'services' ? '' : 'none';
  document.getElementById('routes-view').style.display = name === 'routes' ? '' : 'none';
  document.getElementById('git-view').style.display = name === 'git' ? '' : 'none';
  document.getElementById('timeline-view').style.display = name === 'timeline' ? '' : 'none';
  document.getElementById('intel-view').style.display = name === 'intel' ? '' : 'none';
  document.getElementById('learnings-view').style.display = name === 'learnings' ? '' : 'none';
  document.getElementById('plans-view').style.display = name === 'plans' ? '' : 'none';
  document.getElementById('journey-view').style.display = name === 'journey' ? '' : 'none';
  if (name === 'routes' && !allRoutes) loadRoutes();
  if (name === 'git') loadGitHistory();
  if (name === 'timeline') initTimeline();
  if (name === 'intel') initIntel();
  if (name === 'learnings') initLearnings();
  if (name === 'plans') initPlans();
  if (name === 'journey') initJourney();
}

// ── Learnings tab (#13 Layer A) — re-fixes rendered as a Mermaid story ──────
let _mermaidInit = false;
async function initLearnings() {
  const status = document.getElementById('learnings-status');
  const el = document.getElementById('learnings-mermaid');
  status.textContent = 'Finding fixes that didn’t hold…';
  try {
    const [listResp, mmResp] = await Promise.all([
      fetch('/api/intel/refixes?limit=200'),
      fetch('/api/intel/refixes/mermaid?limit=12'),
    ]);
    const list = await listResp.json();
    const mm = await mmResp.json();
    const badge = document.getElementById('learnings-count-badge');
    if (badge) badge.textContent = list.total ? `(${list.total})` : '';
    status.textContent = list.total
      ? `${list.total} re-fixes found — showing the 12 most recent`
      : 'No re-fixes — fixes are holding ✅';
    if (!_mermaidInit) { mermaid.initialize({ startOnLoad: false, theme: 'dark' }); _mermaidInit = true; }
    el.removeAttribute('data-processed');
    el.textContent = mm.diagram || '';
    await mermaid.run({ nodes: [el] });
  } catch (e) {
    status.textContent = 'Error: ' + e.message;
  }
}

// ── Dev Intelligence tab ──────────────────────────────────────────────────
let intelView = 'fixes';
let intelAgentData = null;

const AGENT_COLORS = {
  'claude-code': '#a855f7', 'cursor': '#3b82f6', 'mixed': '#f59e0b',
  'human': '#22c55e', 'copilot': '#06b6d4', 'aider': '#ec4899', 'other': '#64748b',
};
const MODEL_ICONS = {
  'Claude Opus': '🟣', 'Claude Sonnet': '🔵', 'Claude Haiku': '🟢',
};

async function initIntel() {
  const [agentResp] = await Promise.all([fetch('/api/intel/agent-stats')]);
  intelAgentData = await agentResp.json();
  renderAgentStrip(intelAgentData);
  showIntelView('fixes');
}

function renderAgentStrip(d) {
  if (!d) return;
  const total = d.total_commits || 1;
  const byAgent = d.by_agent || {};
  const pills = Object.entries(byAgent)
    .sort((a,b) => b[1]-a[1])
    .map(([agent, cnt]) => {
      const pct = ((cnt/total)*100).toFixed(1);
      const col = AGENT_COLORS[agent] || '#64748b';
      return `<div class="stat" style="border-left:3px solid ${col};min-width:140px">
        <div style="font-size:20px;font-weight:800;color:${col}">${pct}%</div>
        <div style="font-size:11px;color:var(--muted)">${agent}</div>
        <div style="font-size:10px;color:#334155">${cnt.toLocaleString()} commits</div>
      </div>`;
    }).join('');

  const models = (d.by_model||[]).slice(0,4).map(m => {
    const icon = Object.entries(MODEL_ICONS).find(([k]) => (m.claude_model||'').includes(k));
    return `<span style="font-size:11px;color:#a855f7;background:rgba(168,85,247,0.1);padding:2px 8px;border-radius:4px;margin-right:4px">
      ${icon ? icon[1] : '🤖'} ${m.claude_model||'?'} (${m.cnt})
    </span>`;
  }).join('');

  document.getElementById('intel-agent-strip').innerHTML = `
    <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px">${pills}</div>
    <div style="font-size:12px;color:var(--muted);margin-bottom:4px">Claude models used:</div>
    <div>${models}</div>
  `;
}

function showIntelView(view) {
  intelView = view;
  ['fixes','repos'].forEach(v => {
    const btn = document.getElementById('btn-intel-' + v);
    if (btn) {
      btn.style.background = v === view ? 'var(--blue)' : 'var(--surface2)';
      btn.style.color = v === view ? '#fff' : 'var(--muted)';
      btn.style.border = v === view ? 'none' : '1px solid var(--border)';
    }
  });
  if (view === 'fixes') loadFixes();
  else if (view === 'repos') loadRepoProfiles();
}

async function loadFixes(repo) {
  const url = repo ? '/api/intel/fixes?repo=' + encodeURIComponent(repo) : '/api/intel/fixes?limit=200';
  const resp = await fetch(url);
  const data = await resp.json();
  renderFixes(data.fixes || []);
}

function renderFixes(fixes) {
  if (!fixes.length) {
    document.getElementById('intel-content').innerHTML =
      '<div class="loading" style="color:var(--muted)">No fix patterns found yet. Run a profile refresh.</div>';
    return;
  }

  // Group by repo
  const byRepo = {};
  fixes.forEach(f => (byRepo[f.repo] = byRepo[f.repo]||[]).push(f));

  let html = '';
  for (const [repo, items] of Object.entries(byRepo).sort((a,b) => b[1].length - a[1].length)) {
    html += `<div style="margin-bottom:24px">
      <div style="font-size:13px;font-weight:700;color:#e2e8f0;padding:6px 0;border-bottom:1px solid var(--border);margin-bottom:8px;display:flex;align-items:center;gap:8px">
        ${repo}
        <span style="font-size:11px;color:#ef4444;background:rgba(239,68,68,0.1);padding:1px 7px;border-radius:4px">${items.length} fixes</span>
      </div>`;
    for (const f of items) {
      const agentCol = AGENT_COLORS[f.agent] || '#64748b';
      const icon = f.agent === 'claude-code' ? '🤖' : f.agent === 'cursor' ? '🖱️' : '👤';
      html += `<div style="display:flex;gap:10px;padding:8px;border-radius:6px;margin-bottom:4px;background:var(--surface2);border-left:3px solid #ef4444">
        <div style="flex:1;min-width:0">
          <div style="font-size:12px;font-weight:600;color:#f87171">${f.what_broke || f.commit_subject || '—'}</div>
          ${f.how_fixed ? `<div style="font-size:11px;color:#94a3b8;margin-top:2px">${f.how_fixed}</div>` : ''}
          <div style="display:flex;gap:8px;margin-top:4px;flex-wrap:wrap">
            <span style="font-size:10px;color:${agentCol}">${icon} ${f.agent || 'human'}${f.model ? ' · ' + f.model : ''}</span>
            ${f.pr_number ? `<span style="font-size:10px;color:#64748b">PR #${f.pr_number}</span>` : ''}
            ${f.days_to_fix != null ? `<span style="font-size:10px;color:#64748b">${f.days_to_fix}d to fix</span>` : ''}
            <span style="font-size:10px;color:#334155">${(f.date||f.author_date||'').slice(0,10)}</span>
          </div>
        </div>
      </div>`;
    }
    html += '</div>';
  }
  document.getElementById('intel-content').innerHTML = html;
}

async function loadRepoProfiles() {
  const resp = await fetch('/api/intel/profiles?active_only=false');
  const data = await resp.json();
  renderRepoProfiles(data.profiles || []);
}

function renderRepoProfiles(profiles) {
  if (!profiles.length) {
    document.getElementById('intel-content').innerHTML = `
      <div style="text-align:center;padding:40px;color:var(--muted)">
        <div style="font-size:32px;margin-bottom:12px">🔍</div>
        <div style="font-weight:600;margin-bottom:8px">No profiles built yet</div>
        <div style="font-size:12px">Click "↻ Profile Repos" to deep-analyse all repos from GitHub API.<br>Takes ~2 min for 100+ repos.</div>
      </div>`;
    return;
  }

  const sorted = [...profiles].sort((a,b) => (b.total_commits||0) - (a.total_commits||0));
  let html = `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(380px,1fr));gap:12px">`;

  for (const p of sorted) {
    const agentCol = AGENT_COLORS[p.primary_agent] || '#64748b';
    const agentIcon = p.primary_agent === 'claude-code' ? '🤖' : p.primary_agent === 'cursor' ? '🖱️' : p.primary_agent === 'mixed' ? '🔀' : '👤';
    const networks = JSON.parse(p.docker_networks||'[]');
    const connects = JSON.parse(p.connects_to||'[]');
    const badges = [
      p.has_ci ? '<span style="font-size:10px;background:rgba(34,197,94,0.1);color:#22c55e;padding:1px 6px;border-radius:3px">CI</span>' : '',
      p.has_tests ? '<span style="font-size:10px;background:rgba(59,130,246,0.1);color:#3b82f6;padding:1px 6px;border-radius:3px">Tests</span>' : '',
      p.has_docker ? '<span style="font-size:10px;background:rgba(168,85,247,0.1);color:#a855f7;padding:1px 6px;border-radius:3px">Docker</span>' : '',
      p.claude_md_exists ? '<span style="font-size:10px;background:rgba(245,158,11,0.1);color:#f59e0b;padding:1px 6px;border-radius:3px">CLAUDE.md</span>' : '',
      p.coderabbit_used ? '<span style="font-size:10px;background:rgba(6,182,212,0.1);color:#06b6d4;padding:1px 6px;border-radius:3px">CodeRabbit</span>' : '',
    ].filter(Boolean).join(' ');

    html += `<div style="background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:14px;border-left:3px solid ${agentCol}">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;margin-bottom:8px">
        <div>
          <div style="font-weight:700;font-size:14px">${p.display_name||p.repo}</div>
          <div style="font-size:11px;color:var(--muted)">${p.language||''} · ${p.total_commits||0} commits · ${p.open_issues||0} open issues</div>
        </div>
        <div style="display:flex;align-items:center;gap:6px">
          <button onclick="openEmployeeRecord('${p.owner||'Mark0025'}','${p.repo}')" title="Full employee record"
            style="font-size:10px;background:var(--surface2);border:1px solid var(--border);color:#94a3b8;border-radius:4px;padding:2px 6px;cursor:pointer">📋 record</button>
          <span style="color:${agentCol};font-size:18px" title="${p.primary_agent}">${agentIcon}</span>
        </div>
      </div>
      ${p.purpose ? `<div style="font-size:12px;color:#94a3b8;margin-bottom:6px">${p.purpose.slice(0,200)}</div>` : ''}
      ${p.what_it_does_not_do ? `<div style="font-size:11px;color:#64748b;border-left:2px solid #ef4444;padding-left:8px;margin-bottom:6px">
        <span style="color:#ef4444;font-weight:600">Doesn't: </span>${p.what_it_does_not_do.slice(0,150)}</div>` : ''}
      <div style="display:flex;gap:4px;flex-wrap:wrap;margin-bottom:8px">${badges}</div>
      ${networks.length ? `<div style="font-size:10px;color:#a855f7;margin-bottom:4px">🔗 ${networks.join(', ')}</div>` : ''}
      ${connects.length ? `<div style="font-size:10px;color:#64748b">Talks to: ${connects.join(', ')}</div>` : ''}
      ${p.public_url ? `<div style="margin-top:6px"><a href="${p.public_url}" target="_blank" style="font-size:11px;color:#3b82f6;text-decoration:none">${p.public_url}</a></div>` : ''}
      ${p.claude_model ? `<div style="font-size:10px;color:#a855f7;margin-top:4px">🤖 ${p.claude_model}</div>` : ''}
      <div id="ai-for-${p.repo}" style="margin-top:8px"></div>
      <div id="plans-for-${p.repo}" style="margin-top:10px;border-top:1px solid var(--border);padding-top:8px">
        <span style="font-size:10px;color:var(--muted)">Loading plans…</span>
      </div>
    </div>`;
  }
  html += '</div>';
  document.getElementById('intel-content').innerHTML = html;

  // Lazy-load plan docs + AI analysis for each repo card
  sorted.forEach(p => { loadPlansForRepo(p.repo); loadAnalysisForRepo(p.repo); });
}

// #52: read the LATEST AI analysis snapshot from the API and show it on the card,
// clearly flagged AI-built + dated. Auto-updates when the daily run appends a
// newer snapshot — the UI never touches REPO-ANALYSIS.md, only the API.
async function loadAnalysisForRepo(repo) {
  const el = document.getElementById('ai-for-' + repo);
  if (!el) return;
  const a = await fetch('/api/registry/analysis/' + encodeURIComponent(repo))
    .then(r => r.json()).catch(() => null);
  if (!a || a.analyzed === false || !a.llm_purpose) { el.innerHTML = ''; return; }
  const gradeColor = {A:'#22c55e','B':'#84cc16',C:'#f59e0b',D:'#f97316',F:'#ef4444'}[(a.grade||'')[0]] || '#64748b';
  const when = a.analyzed_at ? new Date(a.analyzed_at).toLocaleDateString() : '';
  el.innerHTML = `
    <div style="background:rgba(168,85,247,0.06);border:1px solid rgba(168,85,247,0.25);border-radius:6px;padding:8px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
        <span style="font-size:10px;color:#a855f7">🤖 AI analysis${a.lens && a.lens!=='baseline' ? ' · '+a.lens : ''}</span>
        ${a.grade ? `<span style="font-size:11px;font-weight:700;color:${gradeColor}">${a.grade}${a.maturity?' · '+a.maturity:''}</span>` : ''}
      </div>
      <div style="font-size:11px;color:#cbd5e1">${(a.llm_purpose||'').slice(0,180)}</div>
      ${a.llm_why ? `<div style="font-size:10px;color:#64748b;margin-top:3px"><b>Why:</b> ${a.llm_why.slice(0,140)}</div>` : ''}
      <div style="font-size:9px;color:#475569;margin-top:4px">AI-built (may be off) · ${a.model||''} · ${when}</div>
    </div>`;
}

// The "employee record" — everything the app knows about one repo, joined:
// what it does (code) -> deployed/running -> friendly URLs+auth -> network alignment.
async function openEmployeeRecord(owner, repo) {
  const modal = document.getElementById('record-modal');
  const body = document.getElementById('record-body');
  document.getElementById('record-title').textContent = `📋 ${repo}`;
  body.innerHTML = '<div class="loading"><div class="spinner"></div> reading code + runtime + friendly URLs…</div>';
  modal.style.display = 'flex';
  try {
    const d = await fetch(`/api/intel/built/${owner}/${encodeURIComponent(repo)}`).then(r => r.json());
    const rt = d.runtime;
    const dep = d.deployed
      ? `<span style="color:#22c55e">✅ deployed</span> · ${d.running ? '<span style="color:#22c55e">running</span>' : '<span style="color:#f59e0b">unhealthy</span>'} · ${d.container_count} container(s)`
      : '<span style="color:#64748b">not deployed (no matching container)</span>';
    const friendly = (d.friendly_urls || []).map(u =>
      `<div style="font-size:12px;margin:2px 0">
        ${u.ssl ? '🔒' : '🔓'} <a href="${u.url}" target="_blank" style="color:#3b82f6;text-decoration:none">${u.url}</a>
        <span style="color:#64748b"> → ${u.forward}</span>
        <span style="font-size:10px;background:var(--surface2);padding:1px 5px;border-radius:3px;color:${u.auth==='public'?'#f59e0b':'#22c55e'}">${u.auth}</span>
      </div>`).join('') || '<span style="color:#64748b;font-size:12px">no friendly URLs found</span>';
    const deps = (d.code.deps || []).map(x => `<span style="font-size:10px;background:var(--surface2);padding:1px 6px;border-radius:3px;margin:1px">${x}</span>`).join(' ') || '—';
    const routes = (d.code.routes || []).slice(0,12).map(r => `<div style="font-size:11px;color:#94a3b8;font-family:monospace">${r}</div>`).join('') || '<span style="color:#64748b;font-size:11px">none detected</span>';

    body.innerHTML = `
      <div style="margin-bottom:14px">
        <div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px">Deployment (runtime)</div>
        <div style="font-size:13px">${dep}</div>
        ${rt ? `<div style="font-size:11px;color:#64748b;margin-top:2px">containers: ${(rt.containers||[]).join(', ')}</div>` : ''}
      </div>
      <div style="margin-bottom:14px">
        <div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px">Friendly URLs + auth (NPM)</div>
        ${friendly}
      </div>
      <div style="margin-bottom:14px">
        <div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px">Real dependencies (from ${d.code.dep_source||'code'})</div>
        <div>${deps}</div>
      </div>
      <div>
        <div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px">Real API routes (from ${(d.code.route_sources||[]).join(', ')||'source'})</div>
        ${routes}
      </div>`;
  } catch (e) {
    body.innerHTML = `<div style="color:#ef4444">Error: ${e.message}</div>`;
  }
}

function closeEmployeeRecord() {
  document.getElementById('record-modal').style.display = 'none';
}

async function loadPlansForRepo(repo) {
  const el = document.getElementById('plans-for-' + repo);
  if (!el) return;
  const docs = await fetch('/api/mdops/repo/' + encodeURIComponent(repo))
    .then(r => r.json()).catch(() => []);

  if (!docs.length) {
    el.innerHTML = '<span style="font-size:10px;color:#334155">No .md plans indexed for this repo</span>';
    return;
  }

  const plans = docs.filter(d => d.is_plan);
  const allDocs = docs;

  el.innerHTML = `
    <div style="font-size:10px;font-weight:600;color:#94a3b8;margin-bottom:5px;letter-spacing:0.05em">
      📄 PLANS & DOCS (${allDocs.length} indexed${plans.length ? ', ' + plans.length + ' plans' : ''})
    </div>
    <div style="display:flex;flex-direction:column;gap:3px">
      ${allDocs.slice(0,6).map(d => {
        const exists = d.file_exists ? '' : 'opacity:0.5;text-decoration:line-through;';
        const planBadge = d.is_plan
          ? '<span style="font-size:9px;background:rgba(245,158,11,0.15);color:#f59e0b;padding:0 4px;border-radius:3px;margin-left:4px">plan</span>'
          : '';
        return `<div onclick="openPlansDetail(${d.id})" style="cursor:pointer;display:flex;justify-content:space-between;align-items:center;
          padding:4px 6px;border-radius:4px;background:var(--surface2);${exists}"
          onmouseover="this.style.borderLeft='2px solid var(--blue)';this.style.paddingLeft='4px'"
          onmouseout="this.style.borderLeft='';this.style.paddingLeft='6px'">
          <div style="flex:1;min-width:0">
            <span style="font-size:11px;color:var(--text)">${d.filename}</span>
            ${planBadge}
            <div style="font-size:10px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:240px">${d.title||''}</div>
          </div>
          <span id="mini-grade-${d.id}" style="font-size:12px;font-weight:800;color:#334155;margin-left:8px;flex-shrink:0">…</span>
        </div>`;
      }).join('')}
      ${allDocs.length > 6 ? `<div style="font-size:10px;color:#334155;padding:2px 6px">+${allDocs.length - 6} more — search Plans tab</div>` : ''}
    </div>`;

  // Grade each plan doc (only plans, not all docs — keep it fast)
  plans.slice(0, 4).forEach(async d => {
    const grade = await fetch('/api/mdops/grade/' + d.id).then(r => r.json()).catch(() => null);
    if (!grade) return;
    const el2 = document.getElementById('mini-grade-' + d.id);
    if (el2) {
      const color = GRADE_COLORS[grade.grade] || '#64748b';
      el2.textContent = grade.grade;
      el2.style.color = color;
    }
  });
  // Non-plan docs get a dash
  allDocs.slice(0,6).filter(d => !d.is_plan).forEach(d => {
    const el2 = document.getElementById('mini-grade-' + d.id);
    if (el2) { el2.textContent = '—'; el2.style.color = '#334155'; }
  });
}

async function searchIntel() {
  const q = document.getElementById('intel-search').value;
  if (!q) { showIntelView(intelView); return; }
  const resp = await fetch('/api/intel/profiles?q=' + encodeURIComponent(q));
  const data = await resp.json();
  renderRepoProfiles(data.profiles || []);
}

async function triggerIntelRefresh() {
  const status = document.getElementById('intel-status');
  status.textContent = 'Profiling repos from GitHub...';
  await fetch('/api/intel/refresh', {method:'POST'});
  status.textContent = 'Running in background (~2 min). Reload tab after.';
  setTimeout(async () => { await loadRepoProfiles(); status.textContent = ''; }, 130000);
}

// ── Timeline tab ──────────────────────────────────────────────────────────
let timelineView = 'commits';  // 'commits' | 'prs'
let timelineLoaded = false;

function switchTimelineView(view) {
  timelineView = view;
  document.getElementById('btn-commits').style.background = view === 'commits' ? 'var(--blue)' : 'var(--surface2)';
  document.getElementById('btn-commits').style.color      = view === 'commits' ? '#fff' : 'var(--muted)';
  document.getElementById('btn-prs').style.background     = view === 'prs' ? 'var(--blue)' : 'var(--surface2)';
  document.getElementById('btn-prs').style.color          = view === 'prs' ? '#fff' : 'var(--muted)';
  loadTimeline();
}

async function initTimeline() {
  if (!allRepos) {
    // Populate repo dropdown from git repos
    const resp = await fetch('/api/git/repos');
    const data = await resp.json();
    allRepos = data.repos;
  }
  // Populate timeline repo dropdown
  const sel = document.getElementById('tl-repo');
  const sorted = [...(allRepos||[])].sort((a,b) => (b.commit_count||0) - (a.commit_count||0));
  sel.innerHTML = '<option value="">All repos</option>' +
    sorted.map(r => `<option value="${r.name}">${r.name} (${r.commit_count||0})</option>`).join('');

  loadTimeline();
}

async function loadTimeline() {
  const repo    = document.getElementById('tl-repo').value;
  const group   = document.getElementById('tl-group').value;
  const since   = document.getElementById('tl-since').value;
  const bots    = document.getElementById('tl-bots').checked;
  const container = document.getElementById('plotly-container');

  container.innerHTML = '<div class="loading"><div class="spinner"></div><br>Building charts...</div>';
  document.getElementById('tl-status').textContent = '';

  const params = new URLSearchParams();
  if (repo)  params.set('repo', repo);
  if (group) params.set('group_by', group);
  if (since) params.set('since', since);
  if (bots)  params.set('include_bots', 'true');

  const endpoint = timelineView === 'prs'
    ? `/api/timeline/prs?${new URLSearchParams({...(repo?{repo}:{})})}`
    : `/api/timeline/commits?${params}`;

  try {
    const resp = await fetch(endpoint);
    const html = await resp.text();
    // innerHTML silently drops <script> tags — use iframe srcdoc so scripts execute
    const iframe = document.createElement('iframe');
    iframe.style.cssText = 'width:100%;border:none;background:transparent;';
    iframe.style.height = '2000px';  // initial; resized after load
    container.innerHTML = '';
    container.appendChild(iframe);
    const doc = iframe.contentDocument || iframe.contentWindow.document;
    doc.open();
    doc.write(`<!DOCTYPE html><html><head>
      <script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></sc` + `ript>
      <style>
        body { margin:0; background:transparent; font-family:system-ui,sans-serif; }
        :root { --surface2:#252836; --border:#2e3148; --muted:#64748b; }
      </style>
      </head><body>${html}</body></html>`);
    doc.close();
    // Resize iframe to content after charts render
    iframe.onload = () => {
      try {
        const h = iframe.contentDocument.body.scrollHeight;
        iframe.style.height = (h + 40) + 'px';
      } catch(e) {}
    };
    setTimeout(() => {
      try {
        const h = iframe.contentDocument.body.scrollHeight;
        if (h > 100) iframe.style.height = (h + 40) + 'px';
      } catch(e) {}
    }, 1500);
  } catch(e) {
    container.innerHTML = `<div class="loading" style="color:#ef4444">Error: ${e.message}</div>`;
  }
}

async function triggerPRRefresh() {
  const status = document.getElementById('tl-status');
  status.textContent = 'Fetching PRs from GitHub...';
  await fetch('/api/timeline/refresh-prs', {method: 'POST'});
  status.textContent = 'PR fetch running in background (~2 min). Reload timeline after.';
}

// ── Git history tab ───────────────────────────────────────────────────────
let allCommits = null;       // currently loaded commits (for selected repo or search)
let allRepos = null;         // full repo list from /api/git/repos
let gitStatsData = null;
let currentRepoFilter = '';  // which repo is selected — drives per-repo fetch

async function loadGitHistory() {
  try {
    // Load stats + full repo list in parallel (both are fast from SQLite)
    const [statsResp, reposResp] = await Promise.all([
      fetch('/api/git/stats'),
      fetch('/api/git/repos'),
    ]);
    gitStatsData = await statsResp.json();
    const reposData = await reposResp.json();
    allRepos = reposData.repos;

    renderGitStats(gitStatsData);
    updateStaleBanner(gitStatsData);
    populateRepoFilter();

    const badge = document.getElementById('git-count-badge');
    if (badge) badge.textContent = `(${gitStatsData.total_commits.toLocaleString()})`;

    // Load all commits initially (no repo filter)
    await loadCommits('');

    if (gitStatsData.total_commits === 0) {
      document.getElementById('git-refresh-status').textContent = 'Fetching from GitHub...';
      triggerGitRefresh();
    }
  } catch(e) {
    document.getElementById('git-commits-container').innerHTML =
      `<div class="loading" style="color:#ef4444">Error: ${e.message}</div>`;
  }
}

async function loadCommits(repo) {
  currentRepoFilter = repo;
  const url = repo
    ? `/api/git/commits?limit=10000&repo=${encodeURIComponent(repo)}`
    : '/api/git/commits?limit=10000';
  const resp = await fetch(url);
  const data = await resp.json();
  allCommits = data.commits;
  renderCommits();
}

// #23 — surface data-freshness so the dashboard isn't confidently wrong.
// A failed token (#20) makes ingestion fetch 0, so the UI shows stale numbers
// with no tell. This banner makes the suspicion visible at the top of the page.
function updateStaleBanner(s) {
  const el = document.getElementById('stale-banner');
  if (!el || !s) return;
  let msg = null, broken = false;
  if (!s.last_fetched) {
    msg = '⚠️ Never synced from GitHub — counts may be empty or wrong.';
    broken = true;
  } else if (s.total_commits === 0) {
    msg = '⚠️ 0 commits ingested — GitHub sync is likely broken (check the token, issue #20).';
    broken = true;
  } else if (s.commits_last_7d === 0) {
    msg = '⚠️ 0 commits in the last 7 days — this can mean an idle week OR a broken sync. '
        + 'Last synced ' + new Date(s.last_fetched).toLocaleString() + '.';
  } else if (s.cache_fresh === false) {
    msg = '↻ Data is stale (cache past TTL). Last synced ' + new Date(s.last_fetched).toLocaleString() + '.';
  }
  if (msg) {
    el.textContent = msg;
    el.classList.toggle('broken', broken);
    el.hidden = false;
  } else {
    el.hidden = true;
  }
}

function renderGitStats(s) {
  if (!s) return;
  document.getElementById('git-stats').innerHTML = `
    <div class="stat"><div class="num" style="color:#22c55e">${s.total_commits.toLocaleString()}</div><div class="lbl">Total Commits</div></div>
    <div class="stat"><div class="num" style="color:#3b82f6">${s.total_repos}</div><div class="lbl">Repos Tracked</div></div>
    <div class="stat"><div class="num" style="color:#a855f7">${s.commits_last_7d}</div><div class="lbl">Last 7 Days</div></div>
    <div class="stat"><div class="num" style="color:#f59e0b">${s.commits_last_30d}</div><div class="lbl">Last 30 Days</div></div>
    <div class="stat" style="min-width:180px">
      <div style="font-size:11px;color:var(--muted)">Top Repos</div>
      ${(s.top_repos||[]).slice(0,3).map(r =>
        `<div style="font-size:11px;margin-top:2px"><span style="color:#e2e8f0">${r.repo}</span> <span style="color:#64748b">${r.cnt}</span></div>`
      ).join('')}
    </div>
    <div class="stat" style="min-width:160px">
      <div style="font-size:11px;color:var(--muted)">Authors</div>
      ${(s.by_author||[]).slice(0,3).map(a =>
        `<div style="font-size:11px;margin-top:2px"><span style="color:#e2e8f0">${a.author_name}</span> <span style="color:#64748b">${a.cnt}</span></div>`
      ).join('')}
    </div>
    <div class="stat"><div style="font-size:10px;color:var(--muted)">Last synced</div>
      <div style="font-size:11px;color:#64748b;margin-top:4px">${s.last_fetched ? new Date(s.last_fetched).toLocaleString() : 'Never'}</div>
      <div style="font-size:10px;margin-top:2px;color:${s.cache_fresh ? '#22c55e':'#f59e0b'}">${s.cache_fresh ? '✓ Fresh':'↻ Stale'}</div>
    </div>
  `;
}

function populateRepoFilter() {
  if (!allRepos) return;
  const sel = document.getElementById('git-repo-filter');
  // Sort: repos with most commits first
  const sorted = [...allRepos].sort((a, b) => (b.commit_count || 0) - (a.commit_count || 0));
  sel.innerHTML = `<option value="">All repos (${allRepos.length})</option>` +
    sorted.map(r => {
      const cnt = r.commit_count ? ` (${r.commit_count})` : '';
      const lang = r.language ? ` · ${r.language}` : '';
      return `<option value="${r.name}">${r.name}${cnt}${lang}</option>`;
    }).join('');
}

function renderCommits() {
  if (!allCommits) return;
  const search = document.getElementById('git-search').value.toLowerCase();
  // Repo filter is handled server-side by loadCommits — only apply text search here
  let commits = allCommits;

  if (search) commits = commits.filter(c =>
    [c.message, c.repo, c.author_name, c.sha].some(f => (f||'').toLowerCase().includes(search))
  );

  if (!commits.length) {
    document.getElementById('git-commits-container').innerHTML =
      '<div class="loading">No commits match.</div>';
    return;
  }

  // Group by repo
  const byRepo = {};
  commits.forEach(c => (byRepo[c.repo] = byRepo[c.repo] || []).push(c));

  let html = '';
  for (const [repo, repoComs] of Object.entries(byRepo).sort((a,b) => {
    const aDate = a[1][0].author_date || '';
    const bDate = b[1][0].author_date || '';
    return bDate.localeCompare(aDate);
  })) {
    const owner = repoComs[0].owner;
    html += `<div style="margin-bottom:20px">
      <div style="display:flex;align-items:center;gap:8px;padding:8px 0;border-bottom:1px solid var(--border);margin-bottom:8px">
        <span style="font-weight:700;font-size:13px">${repo}</span>
        <span style="font-size:11px;color:var(--muted)">${owner}</span>
        <span style="font-size:11px;color:var(--blue);margin-left:auto">${repoComs.length} commits</span>
        <a href="https://github.com/${owner}/${repo}" target="_blank"
           style="font-size:11px;color:var(--purple);text-decoration:none">⎇ GitHub</a>
      </div>`;

    for (const c of repoComs.slice(0, 50)) {
      const msg = c.message || '';
      const subject = msg.split('\n')[0];
      const body = msg.split('\n').slice(1).join(' ').trim();
      const date = c.author_date ? new Date(c.author_date).toLocaleDateString() : '';
      const typeMatch = subject.match(/^(feat|fix|chore|docs|refactor|test|style|perf|ci|build)(\([^)]*\))?:/);
      const typeColors = {feat:'#22c55e',fix:'#ef4444',chore:'#64748b',docs:'#3b82f6',refactor:'#a855f7',test:'#f59e0b',ci:'#06b6d4',build:'#94a3b8',perf:'#f59e0b',style:'#94a3b8'};
      const typeColor = typeMatch ? (typeColors[typeMatch[1]] || '#94a3b8') : '#94a3b8';
      const typeLabel = typeMatch ? typeMatch[0] : '';
      const subjectClean = typeMatch ? subject.slice(typeMatch[0].length).trim() : subject;

      const adds = c.additions || 0;
      const dels = c.deletions || 0;
      html += `<div style="display:flex;align-items:flex-start;gap:10px;padding:6px 8px;border-radius:6px;margin-bottom:2px;background:var(--surface2)">
        <span style="font-family:monospace;font-size:10px;color:var(--muted);padding-top:2px;white-space:nowrap">
          <a href="${c.url||'#'}" target="_blank" style="color:inherit;text-decoration:none">${(c.sha||'').slice(0,7)}</a>
        </span>
        <div style="flex:1;min-width:0">
          <div style="font-size:12px;color:#e2e8f0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="${subject}">
            ${typeLabel ? `<span style="color:${typeColor};font-weight:700">${typeLabel}</span> ` : ''}${subjectClean}
          </div>
          ${body ? `<div style="font-size:11px;color:#64748b;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${body.slice(0,120)}</div>` : ''}
        </div>
        <div style="display:flex;gap:6px;align-items:center;white-space:nowrap;flex-shrink:0">
          ${adds ? `<span style="font-size:10px;color:#22c55e">+${adds}</span>` : ''}
          ${dels ? `<span style="font-size:10px;color:#ef4444">-${dels}</span>` : ''}
          <span style="font-size:10px;color:#64748b">${c.author_name||''}</span>
          <span style="font-size:10px;color:#334155">${date}</span>
        </div>
      </div>`;
    }
    if (repoComs.length > 50) {
      html += `<div style="font-size:11px;color:var(--muted);padding:4px 8px">...and ${repoComs.length - 50} more</div>`;
    }
    html += '</div>';
  }

  document.getElementById('git-commits-container').innerHTML = html;
}

async function triggerGitRefresh() {
  const status = document.getElementById('git-refresh-status');
  status.textContent = 'Refreshing from GitHub...';
  try {
    await fetch('/api/git/refresh', {method: 'POST'});
    status.textContent = 'Running in background — reload in ~30s';
    setTimeout(async () => {
      await loadGitHistory();
      status.textContent = '';
    }, 35000);
  } catch(e) {
    status.textContent = 'Error: ' + e.message;
  }
}

// ── Status helpers ────────────────────────────────────────────────────────
function statusClass(s) {
  if (s.error === 'timeout') return 'timeout';
  if (s.error) return 'down';
  if (!s.reachable) return 'down';
  if (s.redirect_is_auth) return 'auth';
  return 'up';
}
function badgeText(s) {
  if (s.error === 'timeout') return 'TIMEOUT';
  if (s.error) return 'ERROR';
  if (!s.reachable) return `DOWN ${s.status_code ? '('+s.status_code+')' : ''}`;
  if (s.redirect_is_auth) return `AUTH WALL (${s.status_code})`;
  return `UP (${s.status_code})`;
}
function msClass(ms) {
  if (!ms) return '';
  if (ms < 500) return 'fast';
  if (ms < 2000) return 'slow';
  return 'very-slow';
}

// ── Services tab ──────────────────────────────────────────────────────────
function setFilter(cat, btn) {
  activeFilter = cat;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  renderServices();
}

function renderServices() {
  if (!allData) return;
  const grid = document.getElementById('grid');
  const search = document.getElementById('search').value.toLowerCase();

  let services = allData.services;
  if (activeFilter === 'problems') {
    services = services.filter(s => !s.reachable || s.error);
  } else if (activeFilter !== 'all') {
    services = services.filter(s => s.category === activeFilter);
  }
  if (search) {
    services = services.filter(s =>
      [s.name, s.description, s.what_it_does, s.url, s.container_name || ''].some(f => f.toLowerCase().includes(search))
    );
  }

  if (!services.length) {
    grid.innerHTML = '<div id="no-results">No services match.</div>';
    return;
  }

  const bycat = {};
  services.forEach(s => (bycat[s.category] = bycat[s.category] || []).push(s));
  const catOrder = ['terry','pete','ai','monitoring','infrastructure','voice','sites','tools'];
  const ordered = catOrder.filter(c => bycat[c]).concat(Object.keys(bycat).filter(c => !catOrder.includes(c)));

  let html = '';
  for (const cat of ordered) {
    const items = bycat[cat];
    const up = items.filter(s => s.reachable && !s.error).length;
    const col = up === items.length ? '#22c55e' : up === 0 ? '#ef4444' : '#f59e0b';
    html += `<div class="section-header">
      <h2>${items[0].category_label}</h2>
      <span class="count" style="color:${col}">${up}/${items.length} up</span>
    </div>`;

    for (const s of items) {
      const cls = statusClass(s);
      html += `<div class="card ${cls}">
        <div class="card-header">
          <div>
            <div class="card-name">${s.name}</div>
            <div class="card-cat">${s.category_label}</div>
          </div>
          <span class="badge ${cls}">${badgeText(s)}</span>
        </div>
        <div class="card-desc">${s.description}</div>
        <div class="card-detail">${s.what_it_does}</div>
        <div class="card-meta">
          ${s.has_docs ? `<span class="pill docs"><a href="${s.docs_url}" target="_blank">📖 docs</a></span>` : ''}
          ${s.has_health ? `<span class="pill health">✓ ${s.health_status}</span>` : ''}
          ${s.repo ? `<span class="pill repo"><a href="https://github.com/${s.repo}" target="_blank">⎇ ${s.repo.split('/')[1]}</a></span>` : ''}
          ${s.route_count ? `<span class="pill routes" onclick="viewRoutesFor('${s.name}')">🔌 ${s.route_count} routes</span>` : ''}
          ${s.response_time_ms ? `<span class="pill ${msClass(s.response_time_ms)}">${s.response_time_ms}ms</span>` : ''}
          ${s.server_header ? `<span class="pill">${s.server_header}</span>` : ''}
          ${(s.docker_networks||[]).map(n => `<span class="pill" style="color:#a855f7;border-color:rgba(168,85,247,0.3);background:rgba(168,85,247,0.08)">🔗 ${n.replace('-network','')}</span>`).join('')}
          ${s.container_name ? `<span class="pill" style="font-size:10px">📦 ${s.container_name}</span>` : ''}
        </div>
        ${s.redirect_is_auth ? `<div class="card-desc" style="color:#06b6d4">→ Auth wall (Clerk/login)</div>` : ''}
        ${s.error && s.error !== 'timeout' ? `<div class="card-error">Error: ${s.error}</div>` : ''}
        ${(s.connects_to||[]).length ? `<div class="card-desc" style="color:#64748b;font-size:11px">Talks to: ${s.connects_to.join(', ')}</div>` : ''}
        <div class="card-url"><a href="${s.url}" target="_blank">${s.url}</a></div>
      </div>`;
    }
  }
  grid.innerHTML = html;
}

function updateSummary(data) {
  document.getElementById('summary').innerHTML = `
    <div class="stat"><div class="num" style="color:#22c55e">${data.up}</div><div class="lbl">Up</div></div>
    <div class="stat"><div class="num" style="color:#ef4444">${data.down}</div><div class="lbl">Down / Error</div></div>
    <div class="stat"><div class="num" style="color:#06b6d4">${data.auth_wall}</div><div class="lbl">Auth Wall</div></div>
    <div class="stat"><div class="num" style="color:#3b82f6">${data.with_docs}</div><div class="lbl">Have Docs</div></div>
    <div class="stat"><div class="num" style="color:#f59e0b">${data.total_api_routes || 0}</div><div class="lbl">API Routes</div></div>
    <div class="stat"><div class="num" style="color:#94a3b8">${data.total}</div><div class="lbl">Total</div></div>
  `;
}

// ── Routes tab ────────────────────────────────────────────────────────────
function viewRoutesFor(serviceName) {
  showTab('routes', document.querySelectorAll('.tab')[1]);
  if (allRoutes) {
    document.getElementById('route-search').value = serviceName;
    renderRoutes();
  } else {
    loadRoutes().then(() => {
      document.getElementById('route-search').value = serviceName;
      renderRoutes();
    });
  }
}

async function loadRoutes() {
  try {
    const resp = await fetch('/api/routes');
    const data = await resp.json();
    allRoutes = data.routes;
    document.getElementById('route-count-badge').textContent = `(${data.total})`;
    renderRoutes();
  } catch(e) {
    document.getElementById('routes-container').innerHTML = `<div class="loading" style="color:#ef4444">Error: ${e.message}</div>`;
  }
}

function renderRoutes() {
  if (!allRoutes) return;
  const search = document.getElementById('route-search').value.toLowerCase();
  let routes = allRoutes;
  if (search) {
    routes = routes.filter(r =>
      [r.path, r.method, r.service_name, r.summary || '', r.description || '',
       r.business_summary || '', r.container_name || ''].some(f =>
        f.toLowerCase().includes(search)
      )
    );
  }

  if (!routes.length) {
    document.getElementById('routes-container').innerHTML = '<div class="loading">No routes match.</div>';
    return;
  }

  let html = `<table class="route-table">
    <thead><tr>
      <th>Service / Container</th><th>Method</th><th>Path</th>
      <th>What It Does (Plain English)</th><th>Technical Summary</th><th>Tags</th>
    </tr></thead><tbody>`;

  for (const r of routes) {
    const tags = Array.isArray(r.tags) ? r.tags : [];
    const tagHtml = tags.map(t => `<span class="tag-chip">${t}</span>`).join('');
    const biz = r.business_summary || r.summary || r.description || '';
    const tech = (r.summary && r.business_summary && r.summary !== r.business_summary) ? r.summary : '';
    const container = r.container_name ? `<div style="color:#64748b;font-size:10px;margin-top:2px">📦 ${r.container_name}</div>` : '';
    html += `<tr>
      <td class="route-svc">${r.service_name}${container}</td>
      <td><span class="method ${r.method}">${r.method}</span></td>
      <td class="route-path">${r.path}</td>
      <td class="route-summary" style="color:#e2e8f0;max-width:320px">${biz}</td>
      <td class="route-summary" style="color:#64748b;font-size:11px;max-width:200px">${tech}</td>
      <td><div class="route-tags">${tagHtml}</div></td>
    </tr>`;
  }
  html += '</tbody></table>';
  document.getElementById('routes-container').innerHTML = html;
}

// ── Data loading ──────────────────────────────────────────────────────────
async function load(force = false) {
  const btn = document.getElementById('refresh-btn');
  btn.disabled = true; btn.textContent = 'Checking...';
  try {
    const resp = await fetch(force ? '/api/status?force=true' : '/api/status');
    const data = await resp.json();
    if (data.running && !data.services.length) {
      setTimeout(() => load(), 2000);
      return;
    }
    allData = data;
    updateSummary(data);
    const ts = data.checked_at ? new Date(data.checked_at).toLocaleTimeString() : '—';
    document.getElementById('checked-at').textContent = `Checked: ${ts}`;
    renderServices();
    if (data.total_api_routes) {
      document.getElementById('route-count-badge').textContent = `(${data.total_api_routes})`;
    }
    // #23 — refresh the global freshness banner on every load, regardless of active tab.
    fetch('/api/git/stats').then(r => r.json()).then(updateStaleBanner).catch(() => {});
  } catch(e) {
    document.getElementById('grid').innerHTML = `<div class="loading" style="color:#ef4444">Error: ${e.message}</div>`;
  } finally {
    btn.disabled = false; btn.textContent = 'Refresh';
  }
}

function refresh() { load(true); }

load();
setInterval(() => load(false), 90000);

// ── Plans & Docs tab ──────────────────────────────────────────────────────
let plansInited = false;

const GRADE_COLORS = { A:'#22c55e', B:'#84cc16', C:'#f59e0b', D:'#f97316', F:'#ef4444' };

async function initPlans() {
  if (plansInited) return;
  plansInited = true;
  const stats = await fetch('/api/mdops/stats').then(r => r.json()).catch(() => ({}));
  const strip = document.getElementById('plans-stats-strip');
  strip.innerHTML = [
    ['Total docs', stats.total_docs ?? '…'],
    ['Plan/spec docs', stats.plan_docs ?? '…'],
    ['Git-tracked', stats.with_git ?? '…'],
    ['Projects', stats.projects ?? '…'],
  ].map(([label, val]) => `
    <div class="stat">
      <div style="font-size:22px;font-weight:800;color:#e2e8f0">${val}</div>
      <div style="font-size:11px;color:var(--muted)">${label}</div>
    </div>`).join('');
  document.getElementById('plans-count-badge').textContent = stats.total_docs ? `(${stats.total_docs})` : '';
}

let plansSearchTimer = null;
function plansSearch() {
  clearTimeout(plansSearchTimer);
  plansSearchTimer = setTimeout(_doPlansSearch, 300);
}

async function _doPlansSearch() {
  const q = document.getElementById('plans-search').value.trim();
  if (!q) { document.getElementById('plans-content').innerHTML = '<div style="color:var(--muted);font-size:13px;padding:20px 0">Type to search…</div>'; return; }
  const gitOnly = document.getElementById('plans-git-only').checked;
  document.getElementById('plans-status').textContent = 'Searching…';
  const results = await fetch(`/api/mdops/search?q=${encodeURIComponent(q)}&limit=60&git_only=${gitOnly}`).then(r => r.json()).catch(() => []);
  document.getElementById('plans-status').textContent = `${results.length} results`;
  renderPlanResults(results);
}

async function plansLoadProjects() {
  document.getElementById('plans-status').textContent = 'Loading…';
  const projects = await fetch('/api/mdops/projects?limit=120').then(r => r.json()).catch(() => []);
  document.getElementById('plans-status').textContent = `${projects.length} projects`;
  const content = document.getElementById('plans-content');
  content.innerHTML = `
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px">
      ${projects.map(p => `
        <div onclick="plansSearchProject('${(p.name||'').replace(/'/g,"\'")}',event)"
          style="background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:12px;cursor:pointer;transition:border-color 0.15s"
          onmouseover="this.style.borderColor='var(--blue)'" onmouseout="this.style.borderColor='var(--border)'">
          <div style="font-weight:600;font-size:13px;color:var(--text);margin-bottom:4px">${p.name||'(unnamed)'}</div>
          <div style="font-size:11px;color:var(--muted);margin-bottom:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${p.path||''}</div>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <span style="font-size:11px;color:#64748b">${p.doc_count||p.markdown_count||0} docs</span>
            ${p.is_git_repo ? '<span style="font-size:10px;background:#1e3a5f;color:#60a5fa;padding:1px 6px;border-radius:4px">git</span>' : ''}
            ${p.has_api ? '<span style="font-size:10px;background:#14532d;color:#4ade80;padding:1px 6px;border-radius:4px">api</span>' : ''}
            ${p.has_docker_compose ? '<span style="font-size:10px;background:#3b1f5e;color:#c084fc;padding:1px 6px;border-radius:4px">docker</span>' : ''}
          </div>
        </div>`).join('')}
    </div>`;
}

function plansSearchProject(name, e) {
  document.getElementById('plans-search').value = name;
  _doPlansSearch();
}

function renderPlanResults(results) {
  const content = document.getElementById('plans-content');
  if (!results.length) { content.innerHTML = '<div style="color:var(--muted);padding:20px 0">No results.</div>'; return; }
  content.innerHTML = `
    <table style="width:100%;border-collapse:collapse;font-size:12px">
      <thead>
        <tr style="color:var(--muted);text-align:left;border-bottom:1px solid var(--border)">
          <th style="padding:6px 10px">Doc</th>
          <th style="padding:6px 10px">Project</th>
          <th style="padding:6px 10px">Words</th>
          <th style="padding:6px 10px">Git</th>
          <th style="padding:6px 10px">Updated</th>
          <th style="padding:6px 10px">Grade</th>
        </tr>
      </thead>
      <tbody>
        ${results.map(r => `
          <tr onclick="openPlansDetail(${r.id})"
            style="border-bottom:1px solid var(--border);cursor:pointer"
            onmouseover="this.style.background='var(--surface2)'" onmouseout="this.style.background=''">
            <td style="padding:7px 10px">
              <div style="font-weight:600;color:var(--text)">${r.filename||''}</div>
              <div style="color:var(--muted);font-size:11px;max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${r.title||''}</div>
            </td>
            <td style="padding:7px 10px;color:var(--muted)">${r.project||''}</td>
            <td style="padding:7px 10px;color:var(--muted)">${r.word_count||''}</td>
            <td style="padding:7px 10px">${r.git_root ? '<span style="color:#60a5fa;font-size:11px">✓ git</span>' : '<span style="color:var(--muted);font-size:11px">—</span>'}</td>
            <td style="padding:7px 10px;color:var(--muted);white-space:nowrap">${(r.file_updated_at||'').split('T')[0]||'—'}</td>
            <td style="padding:7px 10px" id="grade-${r.id}"><span style="color:var(--muted);font-size:11px">…</span></td>
          </tr>`).join('')}
      </tbody>
    </table>`;
  // Lazy-load grades for git-tracked docs
  results.filter(r => r.git_root).forEach(r => loadGrade(r.id));
}

async function loadGrade(id) {
  const grade = await fetch(`/api/mdops/grade/${id}`).then(r => r.json()).catch(() => null);
  if (!grade) return;
  const cell = document.getElementById(`grade-${id}`);
  if (cell) {
    const color = GRADE_COLORS[grade.grade] || '#64748b';
    cell.innerHTML = `<span style="font-weight:800;color:${color};font-size:14px">${grade.grade}</span>
      <span style="color:var(--muted);font-size:10px;margin-left:4px">${grade.score}pt</span>`;
  }
}

async function openPlansDetail(id) {
  document.getElementById('plans-detail').style.display = '';
  document.getElementById('plans-detail-title').textContent = 'Loading…';
  document.getElementById('plans-detail-body').innerHTML = '<div class="loading"><div class="spinner"></div></div>';

  const [doc, grade] = await Promise.all([
    fetch(`/api/mdops/doc/${id}`).then(r => r.json()).catch(() => ({})),
    fetch(`/api/mdops/grade/${id}`).then(r => r.json()).catch(() => ({})),
  ]);

  document.getElementById('plans-detail-title').textContent = doc.filename || '(unknown)';

  const gradeColor = GRADE_COLORS[grade.grade] || '#64748b';
  const commits = (grade.recent_commits || []).slice(0,8);
  const breakdown = grade.grade_breakdown || {};

  document.getElementById('plans-detail-body').innerHTML = `
    <!-- Grade panel -->
    <div style="background:var(--surface2);border-radius:8px;padding:14px;margin-bottom:16px;border:1px solid var(--border)">
      <div style="display:flex;align-items:center;gap:16px;margin-bottom:12px">
        <div style="font-size:48px;font-weight:900;color:${gradeColor};line-height:1">${grade.grade||'?'}</div>
        <div>
          <div style="font-size:12px;color:var(--muted)">Score: ${grade.score||0} / 13</div>
          <div style="font-size:11px;color:var(--muted);margin-top:4px">
            ${grade.github_repo ? `<a href="https://github.com/${grade.github_repo}" target="_blank" style="color:#60a5fa">${grade.github_repo}</a>` : 'No GitHub remote detected'}
          </div>
        </div>
      </div>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;font-size:11px">
        ${Object.entries(breakdown).map(([k,v]) => `
          <div style="background:var(--surface);border-radius:6px;padding:7px 10px;border:1px solid var(--border)">
            <div style="color:${v > 0 ? '#22c55e' : '#64748b'};font-weight:700">${v > 0 ? '+'+v : '0'}</div>
            <div style="color:var(--muted)">${k.replace(/_/g,' ')}</div>
          </div>`).join('')}
      </div>
    </div>

    <!-- Metadata -->
    <div style="font-size:11px;color:var(--muted);margin-bottom:12px;display:flex;flex-direction:column;gap:3px">
      <div><strong>Path:</strong> ${doc.full_path||'—'}</div>
      <div><strong>Words:</strong> ${doc.word_count||'—'} &nbsp; <strong>Git root:</strong> ${grade.git_root||'none'}</div>
      <div><strong>PRs in repo:</strong> ${grade.pr_count||0} &nbsp;
           <strong>PR numbers found:</strong> ${(grade.pr_numbers||[]).map(n=>`<a href="https://github.com/${grade.github_repo}/pull/${n}" target="_blank" style="color:#60a5fa">#${n}</a>`).join(', ')||'none'}</div>
    </div>

    <!-- Commits -->
    ${commits.length ? `
    <div style="margin-bottom:16px">
      <div style="font-size:12px;font-weight:600;color:var(--text);margin-bottom:8px">Git commits touching this file</div>
      <div style="display:flex;flex-direction:column;gap:4px">
        ${commits.map(c => `
          <div style="background:var(--surface2);border-radius:6px;padding:8px 10px;border:1px solid var(--border);font-size:11px">
            <div style="display:flex;gap:8px;align-items:center">
              <code style="color:var(--muted)">${c.sha}</code>
              <span style="color:var(--muted)">${c.date}</span>
              ${c.pr_number ? `<a href="https://github.com/${grade.github_repo}/pull/${c.pr_number}" target="_blank" style="color:#60a5fa;font-size:10px">#${c.pr_number}</a>` : ''}
              <span style="color:${c.is_bot ? '#64748b' : '#22c55e'};font-size:10px">${c.is_bot ? 'bot' : c.author}</span>
            </div>
            <div style="color:var(--text);margin-top:3px">${c.subject}</div>
          </div>`).join('')}
      </div>
    </div>` : '<div style="color:var(--muted);font-size:12px;margin-bottom:16px">No git history for this file.</div>'}

    <!-- Doc content preview -->
    ${doc.content ? `
    <div>
      <div style="font-size:12px;font-weight:600;color:var(--text);margin-bottom:8px">Document content</div>
      <pre style="background:var(--surface2);border:1px solid var(--border);border-radius:6px;padding:12px;
        font-size:11px;color:var(--muted);overflow-x:auto;white-space:pre-wrap;max-height:400px;overflow-y:auto">${doc.content.replace(/</g,'&lt;').replace(/>/g,'&gt;')}</pre>
    </div>` : ''}
  `;
}

function closePlansDetail() {
  document.getElementById('plans-detail').style.display = 'none';
}

// ── Journey tab ───────────────────────────────────────────────────────────────
let journeyInited = false;
let activeEra = '';

async function initJourney() {
  if (journeyInited) return;
  journeyInited = true;
  const stats = await fetch('/api/journey/stats').then(r => r.json());
  renderJourneyStats(stats);
  document.getElementById('journey-ep-badge').textContent = stats.total_episodes ? `(${stats.total_episodes})` : '';
  await loadJourneyEpisodes();
}

function renderJourneyStats(s) {
  const el = document.getElementById('journey-stats');
  if (!el) return;
  el.innerHTML = [
    ['Repos', s.total_repos || 0, 'var(--blue)'],
    ['Episodes', s.total_episodes || 0, 'var(--purple)'],
    ['Questions', s.total_questions || 0, 'var(--cyan)'],
    ['Answered', s.answered_questions || 0, 'var(--green)'],
    ['Recorded', s.recorded_episodes || 0, 'var(--yellow)'],
    ['Published', s.published_episodes || 0, 'var(--green)'],
  ].map(([lbl, val, color]) => `
    <div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:10px 18px;min-width:90px;text-align:center">
      <div style="font-size:22px;font-weight:700;color:${color}">${val}</div>
      <div style="font-size:11px;color:var(--muted)">${lbl}</div>
    </div>`).join('');
}

function selectEra(era, btn) {
  activeEra = era;
  document.querySelectorAll('.j-era-btn').forEach(b => {
    b.style.color = 'var(--muted)'; b.classList.remove('active');
  });
  btn.style.color = 'var(--text)'; btn.classList.add('active');
  journeyInited = false; // allow reload
  loadJourneyEpisodes();
}

async function loadJourneyEpisodes() {
  const status = document.getElementById('j-status-filter')?.value || '';
  let url = '/api/journey/episodes?';
  if (activeEra) url += `chapter=${activeEra}&`;
  if (status) url += `status=${status}`;
  const data = await fetch(url).then(r => r.json());
  renderJourneyList(data.episodes || []);
}

const STATUS_COLOR = {draft:'#64748b', scheduled:'#f59e0b', recorded:'#3b82f6', published:'#22c55e'};

function renderJourneyList(eps) {
  const el = document.getElementById('j-episode-list');
  if (!eps.length) { el.innerHTML = '<div style="color:var(--muted);font-size:12px;padding:20px 0">No episodes found.</div>'; return; }
  el.innerHTML = eps.map(e => `
    <div onclick="loadJourneyEpisode(${e.id})"
      style="background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:10px 14px;cursor:pointer;transition:border-color 0.15s"
      onmouseover="this.style.borderColor='var(--blue)'" onmouseout="this.style.borderColor='var(--border)'"
      id="j-ep-card-${e.id}">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:6px">
        <span style="font-size:13px;font-weight:600;color:var(--text);flex:1">${e.title || '(untitled)'}</span>
        <span style="font-size:10px;padding:2px 7px;border-radius:10px;white-space:nowrap;
          background:${STATUS_COLOR[e.status]||'#64748b'}22;color:${STATUS_COLOR[e.status]||'#64748b'};border:1px solid ${STATUS_COLOR[e.status]||'#64748b'}55">${e.status}</span>
      </div>
      ${e.hook ? `<div style="font-size:11px;color:var(--muted);margin-top:4px;font-style:italic">"${e.hook.slice(0,100)}${e.hook.length>100?'…':''}"</div>` : ''}
      <div style="display:flex;gap:8px;margin-top:6px;flex-wrap:wrap">
        ${e.chapter ? `<span style="font-size:10px;color:var(--purple)">${e.chapter.replace(/_/g,' ')}</span>` : ''}
        ${e.language ? `<span style="font-size:10px;color:var(--cyan)">${e.language}</span>` : ''}
        ${e.total_commits ? `<span style="font-size:10px;color:var(--muted)">${e.total_commits} commits</span>` : ''}
        ${e.question_count !== undefined ? `<span style="font-size:10px;color:var(--muted)">${e.question_count} Qs</span>` : ''}
      </div>
    </div>`).join('');
}

// Track which episode + persona is currently open
let _currentEpisodeId = null;
let _currentPersona = 'default';

async function loadJourneyEpisode(id, persona) {
  _currentEpisodeId = id;
  _currentPersona = persona || 'default';

  const detail = document.getElementById('j-episode-detail');
  detail.innerHTML = '<div style="color:var(--muted);font-size:12px">Loading…</div>';

  const [qData, depsData] = await Promise.all([
    fetch(`/api/journey/episode/${id}/questions?persona=${_currentPersona}`).then(r => r.json()),
    fetch(`/api/journey/episode/${id}/deps`).then(r => r.json()),
  ]);

  const qs = qData.questions || [];
  const personas = qData.personas || ['default'];
  const deps = depsData.deps || {};
  const TYPE_COLOR = {origin:'#a855f7',technical:'#3b82f6',failure:'#ef4444',vision:'#22c55e',personal:'#f59e0b',pivot:'#06b6d4'};

  // ── Persona tabs ───────────────────────────────────────────────────
  const personaTabs = personas.map(p => `
    <button onclick="loadJourneyEpisode(${id},'${p}')"
      style="background:${p===_currentPersona?'var(--purple)':'var(--surface2)'};
             border:1px solid ${p===_currentPersona?'var(--purple)':'var(--border)'};
             color:${p===_currentPersona?'#fff':'var(--muted)'};
             border-radius:4px;padding:3px 10px;cursor:pointer;font-size:11px;font-weight:600">
      ${p}
    </button>`).join('');

  // ── Deps panel ────────────────────────────────────────────────────
  const depsSections = [];
  if (deps.npm && deps.npm.length) {
    depsSections.push(`<div style="margin-bottom:8px">
      <div style="font-size:10px;font-weight:700;color:var(--cyan);margin-bottom:4px">NPM PACKAGES (${deps.npm.length})</div>
      <div style="display:flex;flex-wrap:wrap;gap:4px">${deps.npm.map(p=>`<code style="font-size:10px;background:var(--surface);padding:2px 6px;border-radius:3px;color:var(--text)">${p}</code>`).join('')}</div>
    </div>`);
  }
  if (deps.pyproject && deps.pyproject.length) {
    depsSections.push(`<div style="margin-bottom:8px">
      <div style="font-size:10px;font-weight:700;color:var(--yellow);margin-bottom:4px">PYTHON (pyproject) (${deps.pyproject.length})</div>
      <div style="display:flex;flex-wrap:wrap;gap:4px">${deps.pyproject.map(p=>`<code style="font-size:10px;background:var(--surface);padding:2px 6px;border-radius:3px;color:var(--text)">${p}</code>`).join('')}</div>
    </div>`);
  }
  if (deps.requirements && deps.requirements.length) {
    depsSections.push(`<div style="margin-bottom:8px">
      <div style="font-size:10px;font-weight:700;color:var(--yellow);margin-bottom:4px">PYTHON (requirements) (${deps.requirements.length})</div>
      <div style="display:flex;flex-wrap:wrap;gap:4px">${deps.requirements.map(p=>`<code style="font-size:10px;background:var(--surface);padding:2px 6px;border-radius:3px;color:var(--text)">${p}</code>`).join('')}</div>
    </div>`);
  }
  const depsPanel = depsSections.length
    ? `<details style="margin-bottom:16px">
        <summary style="font-size:11px;color:var(--muted);cursor:pointer;user-select:none">📦 Packages used in this repo</summary>
        <div style="margin-top:8px;padding:10px;background:var(--surface2);border-radius:6px;border:1px solid var(--border)">${depsSections.join('')}</div>
       </details>`
    : '';

  // ── Questions list ─────────────────────────────────────────────────
  const questionCards = qs.map((q,i) => `
    <div id="qcard-${q.id}" style="margin-bottom:14px;padding:12px;background:var(--surface2);border-radius:6px;border-left:3px solid ${TYPE_COLOR[q.question_type]||'#64748b'}">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
        <span style="font-size:10px;color:${TYPE_COLOR[q.question_type]||'#64748b'};font-weight:600;text-transform:uppercase">${q.question_type||'general'}</span>
        <div style="display:flex;gap:6px;align-items:center">
          ${q.is_edited ? '<span title="Human-edited" style="font-size:9px;padding:1px 5px;border-radius:8px;background:#a855f722;color:#a855f7;border:1px solid #a855f755">✏️ edited</span>' : ''}
          <span style="font-size:10px;color:var(--muted)">Q${i+1}</span>
        </div>
      </div>

      <div id="qtext-${q.id}"
        style="font-size:13px;color:var(--text);font-weight:500;margin-bottom:6px;cursor:text"
        title="Click to edit"
        onclick="startEditQuestion(${q.id})">
        ${escHtml(q.question_text)}
      </div>
      <div id="qedit-${q.id}" style="display:none">
        <textarea id="qtextarea-${q.id}"
          style="width:100%;box-sizing:border-box;background:var(--surface);border:1px solid var(--blue);border-radius:4px;padding:6px;font-size:13px;color:var(--text);resize:vertical;min-height:60px"
          >${escHtml(q.question_text)}</textarea>
        <div style="display:flex;gap:6px;margin-top:4px">
          <button onclick="saveEditQuestion(${q.id})"
            style="background:var(--blue);border:none;color:#fff;border-radius:4px;padding:3px 12px;cursor:pointer;font-size:11px;font-weight:600">Save</button>
          <button onclick="cancelEditQuestion(${q.id})"
            style="background:var(--surface2);border:1px solid var(--border);color:var(--muted);border-radius:4px;padding:3px 10px;cursor:pointer;font-size:11px">Cancel</button>
        </div>
      </div>

      ${q.data_source ? `<div style="font-size:10px;color:var(--muted)">Source: <code style="color:var(--cyan)">${q.data_source}</code>${q.data_ref?` · <span title="${escHtml(q.data_ref)}">${q.data_ref.slice(0,60)}${q.data_ref.length>60?'…':''}</span>`:''}</div>` : ''}

      ${q.answer_text
        ? `<div style="margin-top:8px;padding:8px;background:var(--surface);border-radius:4px;border:1px solid var(--border);font-size:12px;color:var(--text)">${escHtml(q.answer_text)}</div>`
        : `<button onclick="markAnswered(${q.id})"
            style="margin-top:8px;background:none;border:1px dashed var(--border);color:var(--muted);border-radius:4px;padding:4px 10px;cursor:pointer;font-size:11px">
            + Add answer</button>`}
    </div>`).join('');

  detail.innerHTML = `
    <!-- Persona bar -->
    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:12px;padding-bottom:12px;border-bottom:1px solid var(--border)">
      <span style="font-size:10px;color:var(--muted);font-weight:600">PERSONA:</span>
      ${personaTabs}
      <button onclick="showCreatePersona(${id})"
        style="background:none;border:1px dashed var(--border);color:var(--muted);border-radius:4px;padding:3px 8px;cursor:pointer;font-size:11px">+ Custom</button>
      <button id="gen-persona-btn-${id}" onclick="showGeneratePersona(${id})"
        style="background:rgba(168,85,247,0.15);border:1px solid #a855f755;color:#a855f7;border-radius:4px;padding:3px 8px;cursor:pointer;font-size:11px">🤖 AI Style</button>
      <div id="new-persona-form-${id}" style="display:none">
        <input id="new-persona-name-${id}" placeholder="e.g. technical_deep_dive"
          style="background:var(--surface);border:1px solid var(--blue);border-radius:4px;padding:3px 8px;font-size:11px;color:var(--text);width:160px">
        <button onclick="createPersona(${id})"
          style="background:var(--blue);border:none;color:#fff;border-radius:4px;padding:3px 10px;cursor:pointer;font-size:11px;margin-left:4px">Create</button>
      </div>
      <div id="gen-persona-form-${id}" style="display:none;display:flex;gap:6px;align-items:center">
        <select id="gen-persona-style-${id}"
          style="background:var(--surface);border:1px solid var(--purple);border-radius:4px;padding:3px 8px;font-size:11px;color:var(--text)">
          <option value="gary_vee">Gary Vee</option>
          <option value="lex_fridman">Lex Fridman</option>
          <option value="tim_ferriss">Tim Ferriss</option>
        </select>
        <button id="gen-persona-go-${id}" onclick="generatePersona(${id})"
          style="background:var(--purple);border:none;color:#fff;border-radius:4px;padding:3px 10px;cursor:pointer;font-size:11px">Generate</button>
      </div>
    </div>

    <!-- Deps panel -->
    ${depsPanel}

    <!-- Questions -->
    <div style="font-size:11px;color:var(--muted);margin-bottom:10px">${qs.length} questions — click any question text to edit inline</div>
    ${questionCards}
    ${!qs.length ? '<div style="color:var(--muted);font-size:12px">No questions scaffolded yet.</div>' : ''}

    <!-- Action bar -->
    <div style="margin-top:12px;padding-top:12px;border-top:1px solid var(--border);display:flex;gap:8px;flex-wrap:wrap;align-items:center">
      <button id="deep-dive-btn-${id}" onclick="deepDiveEpisode(${id})"
        style="background:var(--purple);border:none;color:#fff;border-radius:6px;padding:5px 14px;cursor:pointer;font-size:12px;font-weight:600">🔍 Deep Dive</button>
      <button onclick="previewScript(${id})"
        style="background:var(--cyan);border:none;color:#000;border-radius:6px;padding:5px 14px;cursor:pointer;font-size:12px;font-weight:600">📄 Script</button>
      <span style="font-size:10px;color:var(--muted)">Status:</span>
      <button onclick="cycleEpisodeStatus(${id},'draft')"
        style="background:var(--surface2);border:1px solid ${STATUS_COLOR['draft']||'#64748b'}55;color:${STATUS_COLOR['draft']||'#64748b'};border-radius:6px;padding:4px 10px;cursor:pointer;font-size:11px">📝 Draft</button>
      <button onclick="cycleEpisodeStatus(${id},'scheduled')"
        style="background:var(--surface2);border:1px solid #f59e0b55;color:#f59e0b;border-radius:6px;padding:4px 10px;cursor:pointer;font-size:11px">📅 Scheduled</button>
      <button onclick="cycleEpisodeStatus(${id},'recorded')"
        style="background:var(--surface2);border:1px solid #3b82f655;color:#3b82f6;border-radius:6px;padding:4px 10px;cursor:pointer;font-size:11px">🎙️ Recorded</button>
      <button onclick="cycleEpisodeStatus(${id},'published')"
        style="background:var(--surface2);border:1px solid #22c55e55;color:#22c55e;border-radius:6px;padding:4px 10px;cursor:pointer;font-size:11px">✅ Published</button>
    </div>`;
}

function escHtml(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function startEditQuestion(qid) {
  document.getElementById(`qtext-${qid}`).style.display = 'none';
  document.getElementById(`qedit-${qid}`).style.display = '';
  document.getElementById(`qtextarea-${qid}`).focus();
}

function cancelEditQuestion(qid) {
  document.getElementById(`qedit-${qid}`).style.display = 'none';
  document.getElementById(`qtext-${qid}`).style.display = '';
}

async function saveEditQuestion(qid) {
  const text = document.getElementById(`qtextarea-${qid}`).value.trim();
  if (!text) return;
  const res = await fetch(`/api/journey/question/${qid}`, {
    method: 'PATCH', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({question_text: text}),
  });
  const data = await res.json();
  if (data.ok) {
    // update display without full reload
    const textEl = document.getElementById(`qtext-${qid}`);
    textEl.textContent = text;
    textEl.style.display = '';
    document.getElementById(`qedit-${qid}`).style.display = 'none';
    // mark as edited visually: add badge if not already there
    const card = document.getElementById(`qcard-${qid}`);
    if (card && !card.querySelector('.edited-badge')) {
      const badge = document.createElement('span');
      badge.className = 'edited-badge';
      badge.style = 'font-size:9px;padding:1px 5px;border-radius:8px;background:#a855f722;color:#a855f7;border:1px solid #a855f755';
      badge.textContent = '✏️ edited';
      card.querySelector('div').appendChild(badge);
    }
  }
}

function showCreatePersona(epId) {
  const form = document.getElementById(`new-persona-form-${epId}`);
  form.style.display = form.style.display === 'none' ? 'flex' : 'none';
  document.getElementById(`gen-persona-form-${epId}`).style.display = 'none';
}

function showGeneratePersona(epId) {
  const form = document.getElementById(`gen-persona-form-${epId}`);
  form.style.display = form.style.display === 'none' ? 'flex' : 'none';
  document.getElementById(`new-persona-form-${epId}`).style.display = 'none';
}

async function generatePersona(epId) {
  const sel = document.getElementById(`gen-persona-style-${epId}`);
  const name = sel.value;
  const btn = document.getElementById(`gen-persona-go-${epId}`);
  btn.textContent = '⏳ Generating…';
  btn.disabled = true;
  try {
    const res = await fetch(`/api/journey/episode/${epId}/persona/generate`, {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({name}),
    });
    const data = await res.json();
    if (data.error) { alert('Error: ' + data.error); return; }
    document.getElementById(`gen-persona-form-${epId}`).style.display = 'none';
    await loadJourneyEpisode(epId, name);
  } catch(e) {
    alert('Generate failed: ' + e.message);
  } finally {
    btn.textContent = 'Generate';
    btn.disabled = false;
  }
}

async function createPersona(epId) {
  const input = document.getElementById(`new-persona-name-${epId}`);
  const name = input.value.trim();
  if (!name) return;
  const res = await fetch(`/api/journey/episode/${epId}/persona`, {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({name}),
  });
  const data = await res.json();
  if (data.ok) {
    input.value = '';
    await loadJourneyEpisode(epId, name);
  } else {
    alert(data.error || 'Failed to create persona');
  }
}

async function cycleEpisodeStatus(id, status) {
  await fetch(`/api/journey/episode/${id}`, {
    method:'PATCH', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({status})
  });
  journeyInited = false;
  await loadJourneyEpisodes();
  await loadJourneyEpisode(id, _currentPersona);
}

async function deepDiveEpisode(id) {
  const btn = document.getElementById(`deep-dive-btn-${id}`);
  const origText = btn ? btn.textContent : '';
  if (btn) { btn.textContent = '⏳ Diving…'; btn.disabled = true; }

  try {
    const res = await fetch(`/api/journey/episode/${id}/enrich`, {method:'POST'});
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (data.error) {
      alert('Deep dive error: ' + data.error);
      return;
    }
    await loadJourneyEpisode(id, _currentPersona);
  } catch(e) {
    alert('Deep dive failed: ' + e.message);
  } finally {
    if (btn) { btn.textContent = origText; btn.disabled = false; }
  }
}

async function markAnswered(qid) {
  const ans = prompt('Your answer:');
  if (!ans) return;
  await fetch(`/api/journey/question/${qid}/answer`, {
    method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({answer_text: ans})
  });
  if (_currentEpisodeId) await loadJourneyEpisode(_currentEpisodeId, _currentPersona);
}

let _ttsStatus = null;

async function checkTtsStatus() {
  const data = await fetch('/api/journey/tts/status').then(r=>r.json());
  _ttsStatus = data;
  return data;
}

async function previewScript(epId) {
  const persona = _currentPersona || 'default';
  const modal = document.getElementById('script-modal');
  const body = document.getElementById('script-modal-body');
  const title = document.getElementById('script-modal-title');
  const sub = document.getElementById('script-modal-sub');
  body.innerHTML = '<div style="color:var(--muted)">Loading script…</div>';
  modal.style.display = '';

  const [data, ttsData] = await Promise.all([
    fetch(`/api/journey/episode/${epId}/script?persona=${persona}`).then(r=>r.json()),
    checkTtsStatus(),
  ]);

  if (data.error) { body.innerHTML = `<div style="color:var(--red)">${escHtml(data.error)}</div>`; return; }

  title.textContent = data.title || 'Interview Script';
  sub.textContent = `Persona: ${data.persona} · ${data.answered_count}/${data.total_questions} questions answered`;

  const SPEAKER_COLOR = {interviewer: 'var(--purple)', mark: 'var(--cyan)'};
  const SPEAKER_LABEL = {interviewer: '🎙️ Interviewer', mark: '💬 Mark'};

  const ttsBar = ttsData.available
    ? `<div style="margin-bottom:16px;padding:10px 14px;background:rgba(34,197,94,0.1);border:1px solid rgba(34,197,94,0.3);border-radius:6px;display:flex;align-items:center;gap:10px">
        <span style="color:var(--green)">🔊 ElevenLabs ready — interviewer voiced, you speak live</span>
        <button id="gen-audio-btn-${epId}" onclick="generateAudio(${epId})"
          style="background:var(--green);border:none;color:#000;border-radius:4px;padding:4px 12px;cursor:pointer;font-size:12px;font-weight:600;margin-left:auto">
          🎙️ Generate Audio
        </button>
       </div>`
    : `<div style="margin-bottom:16px;padding:10px 14px;background:rgba(100,116,139,0.1);border:1px solid var(--border);border-radius:6px">
        <span style="color:var(--muted)">🔇 ElevenLabs not configured — add <code>ELEVENLABS_API_KEY</code> to .env</span>
       </div>`;

  const lines = (data.lines || []).map((l,i) => {
    const color = SPEAKER_COLOR[l.speaker] || 'var(--text)';
    const label = SPEAKER_LABEL[l.speaker] || l.speaker;
    const typeTag = l.type ? `<span style="font-size:10px;color:var(--muted);margin-left:6px">[${l.type}]</span>` : '';
    return `<div id="script-line-${epId}-${i}" style="margin-bottom:16px">
      <div style="font-size:10px;font-weight:700;color:${color};text-transform:uppercase;letter-spacing:0.06em;margin-bottom:4px">${label}${typeTag}</div>
      <div style="background:var(--surface2);border-radius:6px;padding:10px 14px;border-left:3px solid ${color}">${escHtml(l.text)}</div>
      <div id="audio-${epId}-${i}" style="margin-top:4px"></div>
    </div>`;
  }).join('');

  body.innerHTML = ttsBar + (lines || '<div style="color:var(--muted)">No answered questions yet.</div>');
  body.dataset.epId = epId;
  body.dataset.persona = persona;
}

function generateAudio(epId) {
  const btn = document.getElementById(`gen-audio-btn-${epId}`);
  if (btn) { btn.textContent = '⏳ Generating…'; btn.disabled = true; }

  const persona = _currentPersona || 'default';
  const es = new EventSource(`/api/journey/episode/${epId}/tts-stream?persona=${persona}`);

  es.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.done) {
      es.close();
      if (btn) { btn.textContent = '🎙️ Generate Audio'; btn.disabled = false; }
      return;
    }
    if (data.error && data.idx === undefined) {
      // Stream-level error (no key, bad episode) — abort.
      es.close();
      if (btn) { btn.textContent = '🎙️ Generate Audio'; btn.disabled = false; }
      alert('TTS error: ' + data.error);
      return;
    }
    // Target the exact line the server voiced (only interviewer lines stream back).
    const el = document.getElementById(`audio-${epId}-${data.idx}`);
    if (!el) return;
    if (data.audio_b64) {
      const src = `data:${data.content_type};base64,${data.audio_b64}`;
      el.innerHTML = `<audio controls autoplay src="${src}" style="width:100%;height:32px;margin-top:4px"></audio>`;
    } else if (data.error) {
      el.innerHTML = `<span style="font-size:10px;color:var(--red)">${escHtml(data.error)}</span>`;
    }
  };

  es.onerror = () => {
    es.close();
    if (btn) { btn.textContent = '🎙️ Generate Audio'; btn.disabled = false; }
  };
}

function closeScriptModal() {
  document.getElementById('script-modal').style.display = 'none';
}
