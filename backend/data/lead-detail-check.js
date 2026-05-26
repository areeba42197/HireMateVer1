
/* DATA */
const MD = {
  Professional:`Hi Asad,\n\nI came across your post about the Frontend Developer role at TechVentures PK and I'm very interested in this opportunity.\n\nI bring 2+ years of hands-on experience with React.js, JavaScript (ES6+), and REST APIs — with a track record of building clean, performant UIs in production environments.\n\nI'd love to connect and discuss how I can contribute to your team. My portfolio and CV are ready to share at your convenience.\n\nBest regards,\nAyesha S.`,
  Enthusiastic:`Hey Asad! 👋\n\nYour post about the Frontend Developer role immediately caught my eye — TechVentures PK is doing some really exciting work and I'd love to be a part of it!\n\nI'm a React developer with 2+ years building fast, beautiful UIs. I love collaborating closely with design and backend teams and I'm passionate about clean, maintainable code.\n\nWould love to chat — happy to share my portfolio anytime!\n\nCheers,\nAyesha S. 🚀`,
  Concise:`Hi Asad,\n\nInterested in the Frontend Developer role.\n\n• 2+ yrs React.js\n• Strong JS (ES6+), REST APIs, CSS\n• Remote-ready, available immediately\n\nPortfolio on request.\n\nBest, Ayesha S.`,
  Formal:`Dear Mr. Hussain,\n\nI am writing to express my sincere interest in the Frontend Developer position recently advertised by TechVentures PK.\n\nWith over two years of professional experience in React.js and modern JavaScript development, I am confident in my ability to contribute meaningfully to your product team.\n\nI would welcome the opportunity to discuss my qualifications at your earliest convenience.\n\nYours sincerely,\nAyesha Shahid`
};
const CD = {
  Engaging:`This looks like a fantastic opportunity! TechVentures PK has a great reputation for its engineering culture. I'd love to learn more — what does onboarding typically look like for remote team members? 🙌`,
  Curious:`Exciting role! Quick question — is the team fully distributed or are there hybrid options for Lahore-based candidates? Also curious about the tech stack beyond React on the frontend side.`,
  Professional:`Thank you for sharing this opportunity. The role aligns closely with my experience in React.js and frontend development. I would appreciate the chance to discuss this further — I'll send a message with my portfolio shortly.`,
  Concise:`Great opportunity — exactly the kind of role I've been looking for. DM incoming with my portfolio! 🚀`
};

let curMsgTone = 'Professional';
let curCmtTone = 'Engaging';
let cmtCount = 12;

window.onload = () => {
  document.getElementById('msg-ta').value = MD[curMsgTone];
  document.getElementById('cmt-ta').value = CD[curCmtTone];
  const t = localStorage.getItem('hm-theme') || 'light';
  applyTheme(t);
};

/* THEME */
function applyTheme(t) {
  document.documentElement.setAttribute('data-theme', t);
  document.getElementById('theme-btn').textContent = t === 'dark' ? '🌙' : '☀️';
  localStorage.setItem('hm-theme', t);
}
function toggleTheme() {
  const c = document.documentElement.getAttribute('data-theme');
  applyTheme(c === 'dark' ? 'light' : 'dark');
}

/* POST EXPAND */
function togglePost() {
  const el = document.getElementById('xtra');
  const btn = document.getElementById('sm-btn');
  const open = el.style.display !== 'none';
  el.style.display = open ? 'none' : 'block';
  btn.textContent = open ? '…see more' : 'see less';
}

/* COMMENT INPUT */
function ar(el) { el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, 120) + 'px'; }
function ts(el) { document.getElementById('cmt-send').classList.toggle('on', el.value.trim().length > 0); }

function replyTo(name) {
  const inp = document.getElementById('cmt-inp');
  inp.value = `@${name} `;
  inp.focus(); ar(inp); ts(inp);
  inp.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function postCmt() {
  const inp = document.getElementById('cmt-inp');
  const txt = inp.value.trim();
  if (!txt) return;
  addCmt(txt, 'Ayesha S.', 'AS', 'linear-gradient(135deg,var(--accent),#1e88e5)', 'Frontend Developer · Job Seeker', true);
  inp.value = ''; inp.style.height = 'auto';
  document.getElementById('cmt-send').classList.remove('on');
  toast('💬', 'Comment posted');
}

function addCmt(txt, name, init, bg, sub, isYou) {
  const list = document.getElementById('cmt-list');
  const badge = isYou ? `<span class="ab">· You</span>` : '';
  const div = document.createElement('div');
  div.className = 'ci fin';
  div.innerHTML = `
    <div class="c-av" style="background:${bg}">${init}</div>
    <div class="c-body">
      <div class="c-bub">
        <div class="c-name">${esc(name)} ${badge}</div>
        <div class="c-sub">${sub}</div>
        <div class="c-txt">${esc(txt)}</div>
      </div>
      <div class="c-foot"><span class="ct">Just now</span><button class="ca" onclick="replyTo('${esc(name)}')">Reply</button></div>
    </div>`;
  list.insertBefore(div, list.firstChild);
  cmtCount++;
  document.getElementById('cmt-stat').textContent = cmtCount + ' comments';
}

/* COMMENT MODAL */
function openCmtModal() { document.getElementById('cmt-modal').classList.add('open'); }
function closeOv(id) { document.getElementById(id).classList.remove('open'); }
function ovClose(e, id) { if (e.target === document.getElementById(id)) closeOv(id); }

function setCmtTone(btn, tone) {
  document.querySelectorAll('#cmt-tones .tp').forEach(b => b.classList.remove('on'));
  btn.classList.add('on');
  curCmtTone = tone;
  document.getElementById('cmt-ta').value = CD[tone];
}
function genCmt() {
  const btn = document.getElementById('cmt-gen-btn');
  btn.innerHTML = '<div class="spin"></div> Generating…';
  btn.disabled = true;
  setTimeout(() => {
    document.getElementById('cmt-ta').value = CD[curCmtTone];
    btn.innerHTML = '✨ Regenerate'; btn.disabled = false;
    toast('✨', 'Comment draft ready');
  }, 1000);
}
function useCmtDraft() {
  const txt = document.getElementById('cmt-ta').value.trim();
  if (!txt) return;
  const inp = document.getElementById('cmt-inp');
  inp.value = txt; ar(inp); ts(inp);
  closeOv('cmt-modal');
  inp.focus();
  toast('↗️', 'Draft loaded — review and post');
}

/* MESSAGE DRAFT */
function setMsgTone(btn, tone) {
  document.querySelectorAll('#msg-tones .tp').forEach(b => b.classList.remove('on'));
  btn.classList.add('on');
  curMsgTone = tone;
  document.getElementById('msg-ta').value = MD[tone];
}
function genMsg() {
  const btn = document.getElementById('msg-gen-btn');
  btn.innerHTML = '<div class="spin"></div> Generating…';
  btn.disabled = true;
  setTimeout(() => {
    document.getElementById('msg-ta').value = MD[curMsgTone];
    btn.innerHTML = '✨ Regenerate'; btn.disabled = false;
    toast('✨', 'Message draft updated');
  }, 1100);
}
function saveMsg() { toast('📤', 'Saved to Message Drafts'); }

/* UTILS */
function cp(id) {
  navigator.clipboard.writeText(document.getElementById(id).value)
    .then(() => toast('📋', 'Copied to clipboard'));
}
function esc(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function toast(icon, msg) {
  const c = document.getElementById('toasts');
  const t = document.createElement('div');
  t.className = 'toast';
  t.innerHTML = `<span>${icon}</span>${msg}`;
  c.appendChild(t);
  setTimeout(() => { t.style.transition = 'opacity .3s'; t.style.opacity = '0'; }, 2500);
  setTimeout(() => t.remove(), 2900);
}

/* BACKEND LEAD DETAIL */
let hmLead = null;
let hmLastMessageDraftId = null;
let hmLastCommentDraftId = null;

function hmToken() { return localStorage.getItem('hm_token') || ''; }
function hmApiBase() { return window.location.origin && window.location.origin.startsWith('http') ? window.location.origin : 'http://localhost:8000'; }
async function hmApi(path, options) {
  const headers = Object.assign({ 'Content-Type': 'application/json' }, (options && options.headers) || {});
  if (hmToken()) headers.Authorization = 'Bearer ' + hmToken();
  const res = await fetch(hmApiBase() + path, Object.assign({}, options || {}, { headers }));
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.ok === false) throw new Error(data.error || 'Request failed');
  return data;
}
function hmEsc(s) {
  return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function hmLeadId() {
  const params = new URLSearchParams(window.location.search);
  return params.get('id') || localStorage.getItem('hm_selected_lead_id') || '';
}
function hmTimeAgo(iso) {
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return 'recently';
  const minutes = Math.max(1, Math.floor((Date.now() - dt.getTime()) / 60000));
  if (minutes < 60) return minutes + ' min ago';
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return hours + ' hrs ago';
  return Math.floor(hours / 24) + ' days ago';
}
function hmTempBadge(temp) {
  const label = temp === 'hot' ? '🔥 Hot' : temp === 'warm' ? '🌡 Warm' : '❄ Cold';
  const cls = temp === 'hot' ? 'b-hot' : temp === 'warm' ? 'b-warm' : 'b-cold';
  return `<span class="badge ${cls}">${label}</span>`;
}
function hmInitials(name) {
  return (name || 'HM').split(/\s+/).filter(Boolean).slice(0, 2).map(p => p[0]).join('').toUpperCase() || 'HM';
}
function hmSetText(selector, value) {
  const el = document.querySelector(selector);
  if (el) el.textContent = value || 'Not specified';
}
function hmSetHtml(selector, value) {
  const el = document.querySelector(selector);
  if (el) el.innerHTML = value;
}
function hmFormatPost(text) {
  const safe = hmEsc(text || 'No post content was extracted.');
  return safe.split(/\n+/).map(p => `<p>${p}</p>`).join('');
}
async function hmLoadLeadDetail() {
  if (!hmToken()) {
    toast('⚠', 'Please login first');
    setTimeout(() => { location.href = 'login.html'; }, 800);
    return;
  }
  const id = hmLeadId();
  if (!id) {
    toast('⚠', 'No lead selected');
    return;
  }
  try {
    const data = await hmApi('/api/leads/' + encodeURIComponent(id));
    hmLead = data.lead;
    localStorage.setItem('hm_selected_lead_id', String(hmLead.id));
    hmRenderLeadDetail(hmLead);
    await hmGenerateBackendDraft('message', curMsgTone || 'Professional', false);
    await hmGenerateBackendDraft('comment', curCmtTone || 'Engaging', false);
  } catch (err) {
    toast('⚠', err.message);
  }
}
function hmRenderLeadDetail(lead) {
  hmSetText('.co-name', lead.company);
  hmSetHtml('.co-sub', `Posted by <strong>${hmEsc(lead.author_name || lead.company)}</strong> · ${hmEsc(lead.author_title || 'LinkedIn Jobs')}`);
  hmSetHtml('.meta-row', `
    <span class="mi">${hmEsc(hmTimeAgo(lead.posted_at))}</span>
    <span class="mdot"></span>
    <span class="mi">🌐 LinkedIn</span>
    <span class="mdot"></span>
    <span class="mi">📍 ${hmEsc(lead.location || 'Not specified')}</span>
  `);
  hmSetHtml('.post-hdr .badge', hmTempBadge(lead.temperature));
  hmSetHtml('.post-body', `
    <p><strong>${hmEsc(lead.role_title)}</strong></p>
    ${hmFormatPost(lead.post_text)}
    ${lead.post_url ? `<p><a class="see-more" href="${hmEsc(lead.post_url)}" target="_blank" rel="noopener">Open original LinkedIn result</a></p>` : ''}
  `);
  const tags = Array.isArray(lead.tags) ? lead.tags : [];
  hmSetHtml('.post-tags', tags.map(tag => `<span class="tag">${hmEsc(tag)}</span>`).join('') || '<span class="tag">LinkedIn</span>');
  hmSetHtml('.rxn-lbl', `${Number(lead.likes || 0)} reactions`);
  const extractedComments = Array.isArray(lead.comment_items) ? lead.comment_items : [];
  const commentCount = Number(lead.comments || extractedComments.length || 0);
  hmSetText('#cmt-stat', `${commentCount} comments`);
  const repostEl = document.querySelector('.rxn-right .stat-pill:last-child');
  if (repostEl) repostEl.lastChild.textContent = ' ' + Number(lead.reposts || 0) + ' reposts';
  hmRenderExtractedComments(extractedComments, lead.lead_kind);
  const logo = document.querySelector('.co-logo');
  if (logo) logo.textContent = hmInitials(lead.company);
  const detailValues = document.querySelectorAll('.il .ival');
  const values = [
    lead.company,
    lead.role_title,
    lead.work_type,
    lead.location,
    lead.employment_type,
    lead.experience,
    lead.salary,
  ];
  detailValues.forEach((el, i) => { el.textContent = values[i] || 'Not specified'; });
  const score = Math.max(0, Math.min(100, Number(lead.score || 0)));
  hmSetText('.mc-inner', score + '%');
  const ring = document.querySelector('.mc-ring');
  if (ring) ring.style.background = `conic-gradient(var(--accent) 0% ${score}%,var(--border) ${score}% 100%)`;
  const sbarWrap = document.querySelector('.sbars');
  if (sbarWrap) {
    sbarWrap.innerHTML = tags.slice(0, 4).map(tag => {
      const pct = Math.max(35, Math.min(96, score - Math.floor(Math.random() * 18)));
      return `<div class="sbr"><span class="sbn">${hmEsc(tag)}</span><div class="sbt"><div class="sbf" style="width:${pct}%"></div></div><span class="sbp">${pct}%</span></div>`;
    }).join('') || `<div class="sbr"><span class="sbn">Profile</span><div class="sbt"><div class="sbf" style="width:${score}%"></div></div><span class="sbp">${score}%</span></div>`;
  }
}
function hmRenderExtractedComments(comments, kind) {
  const list = document.getElementById('cmt-list');
  if (!list) return;
  if (!comments || comments.length === 0) {
    list.innerHTML = `
      <div class="ci fin">
        <div class="c-body">
          <div class="c-bub" style="width:100%;">
            <div class="c-name">No extracted LinkedIn comments</div>
            <div class="c-txt">${kind === 'job'
              ? 'This lead came from LinkedIn Jobs, so public post comments are not available. The content above is the live job description/details extracted from LinkedIn.'
              : 'No visible comments were returned for this post during the safe sync. If the post requires login or LinkedIn hides comments, HireMate leaves this empty instead of showing fake comments.'}</div>
          </div>
        </div>
      </div>`;
    return;
  }
  list.innerHTML = comments.map((comment, index) => {
    const author = comment.author || 'LinkedIn member';
    const initials = hmInitials(author);
    const text = comment.text || comment;
    return `
      <div class="ci fin" style="animation-delay:${index * 0.04}s">
        <div class="c-av" style="background:linear-gradient(135deg,var(--accent),#1e88e5)">${hmEsc(initials)}</div>
        <div class="c-body">
          <div class="c-bub">
            <div class="c-name">${hmEsc(author)}</div>
            <div class="c-sub">Extracted from LinkedIn</div>
            <div class="c-txt">${hmEsc(text)}</div>
          </div>
        </div>
      </div>`;
  }).join('');
}
async function hmGenerateBackendDraft(type, tone, notify) {
  if (!hmLead) return;
  const data = await hmApi('/api/drafts/generate', {
    method: 'POST',
    body: JSON.stringify({ lead_id: hmLead.id, draft_type: type, tone: tone })
  });
  if (type === 'message') {
    hmLastMessageDraftId = data.draft.id;
    document.getElementById('msg-ta').value = data.draft.content;
  } else {
    hmLastCommentDraftId = data.draft.id;
    document.getElementById('cmt-ta').value = data.draft.content;
  }
  if (notify) toast('✨', `${type === 'message' ? 'Message' : 'Comment'} draft generated from this lead`);
}

const staticSetMsgTone = setMsgTone;
setMsgTone = function(btn, tone) {
  document.querySelectorAll('#msg-tones .tp').forEach(b => b.classList.remove('on'));
  btn.classList.add('on');
  curMsgTone = tone;
  hmGenerateBackendDraft('message', tone, true).catch(() => staticSetMsgTone(btn, tone));
};
genMsg = function() {
  const btn = document.getElementById('msg-gen-btn');
  btn.innerHTML = '<div class="spin"></div> Generating…';
  btn.disabled = true;
  hmGenerateBackendDraft('message', curMsgTone, true)
    .catch(err => toast('⚠', err.message))
    .finally(() => { btn.innerHTML = '✨ Regenerate'; btn.disabled = false; });
};
saveMsg = function() {
  const id = hmLastMessageDraftId;
  if (!id) { toast('📤', 'Draft is already saved'); return; }
  hmApi('/api/drafts/' + id, {
    method: 'PATCH',
    body: JSON.stringify({ status: 'approved', content: document.getElementById('msg-ta').value })
  }).then(() => toast('📤', 'Saved to Message Drafts')).catch(err => toast('⚠', err.message));
};
const staticSetCmtTone = setCmtTone;
setCmtTone = function(btn, tone) {
  document.querySelectorAll('#cmt-tones .tp').forEach(b => b.classList.remove('on'));
  btn.classList.add('on');
  curCmtTone = tone;
  hmGenerateBackendDraft('comment', tone, true).catch(() => staticSetCmtTone(btn, tone));
};
genCmt = function() {
  const btn = document.getElementById('cmt-gen-btn');
  btn.innerHTML = '<div class="spin"></div> Generating…';
  btn.disabled = true;
  hmGenerateBackendDraft('comment', curCmtTone, true)
    .catch(err => toast('⚠', err.message))
    .finally(() => { btn.innerHTML = '✨ Regenerate'; btn.disabled = false; });
};

document.addEventListener('DOMContentLoaded', hmLoadLeadDetail);

