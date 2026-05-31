// ========== TOAST ==========
function showToast(type, message) {
  const cont = document.getElementById('toasts');
  if (!cont) return;
  const icons = { success: '&check;', error: '&times;', warning: '!', info: 'i' };
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `<span class="toast-icon">${icons[type] || '&bull;'}</span><span class="toast-msg">${message}</span>`;
  cont.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(20px)';
    toast.style.transition = 'all 0.3s';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// ========== CONFIRM DIALOG ==========
function showConfirm(icon, title, sub, yesLabel, yesClass, onYes) {
  const overlay = document.getElementById('confirm-overlay');
  if (!overlay) return;
  document.getElementById('confirm-icon').textContent = icon;
  document.getElementById('confirm-title').textContent = title;
  document.getElementById('confirm-sub').textContent = sub;
  const yesBtn = document.getElementById('confirm-yes');
  yesBtn.textContent = yesLabel;
  yesBtn.className = `btn ${yesClass}`;
  yesBtn.onclick = () => { closeConfirm(); onYes(); };
  document.getElementById('confirm-no').onclick = closeConfirm;
  overlay.classList.add('open');
}
function closeConfirm() {
  const overlay = document.getElementById('confirm-overlay');
  if (overlay) overlay.classList.remove('open');
}

// ========== MODAL ==========
function closeModal() {
  const m = document.getElementById('modal');
  if (m) m.classList.remove('open');
}
function showUserModal() {
  document.getElementById('modal-content').innerHTML = `
    <div class="modal-title">Edit User Account</div>
    <div class="modal-sub">Update account details or change account status.</div>
    <div style="display:flex;flex-direction:column;gap:14px;margin-bottom:20px;">
      <div class="form-group"><label class="form-label">Full Name</label><input class="form-input" value="Areeba Syed"></div>
      <div class="form-group"><label class="form-label">Email</label><input class="form-input" value="areeba.syed@iiui.edu.pk"></div>
      <div class="form-group"><label class="form-label">Account Status</label>
        <select class="form-select"><option>Active</option><option>Inactive</option></select>
      </div>
    </div>
    <div style="display:flex;gap:10px;">
      <button class="btn btn-ghost" style="flex:1;" onclick="closeModal()">Cancel</button>
      <button class="btn btn-primary" style="flex:1;" onclick="closeModal();showToast('success','User updated successfully!')">Save Changes</button>
    </div>`;
  document.getElementById('modal').classList.add('open');
}

// ========== VALIDATION HELPERS ==========
function isValidEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}
function setFieldError(inputId, msgId, msg) {
  const input = document.getElementById(inputId);
  const msgEl = document.getElementById(msgId);
  if (input) { input.classList.add('is-error'); input.classList.remove('is-valid'); }
  if (msgEl) msgEl.textContent = msg;
}
function setFieldValid(inputId, msgId) {
  const input = document.getElementById(inputId);
  const msgEl = document.getElementById(msgId);
  if (input) { input.classList.remove('is-error'); input.classList.add('is-valid'); }
  if (msgEl) msgEl.textContent = '';
}
function clearField(inputId, msgId) {
  const input = document.getElementById(inputId);
  const msgEl = document.getElementById(msgId);
  if (input) { input.classList.remove('is-error', 'is-valid'); }
  if (msgEl) msgEl.textContent = '';
}

// ========== PASSWORD STRENGTH ==========
function checkPasswordStrength(pw) {
  let score = 0;
  if (pw.length >= 8) score++;
  if (/[A-Z]/.test(pw)) score++;
  if (/[a-z]/.test(pw)) score++;
  if (/[0-9]/.test(pw)) score++;
  if (/[^A-Za-z0-9]/.test(pw)) score++;
  return score;
}
function renderStrength(pw, barId, labelId) {
  const bar = document.getElementById(barId);
  const label = document.getElementById(labelId);
  if (!bar || !label) return;
  const score = checkPasswordStrength(pw);
  const levels = [
    { w: '0%', color: 'transparent', text: '' },
    { w: '25%', color: 'var(--hot)', text: 'Weak' },
    { w: '50%', color: 'var(--warm)', text: 'Fair' },
    { w: '75%', color: 'var(--cold)', text: 'Good' },
    { w: '100%', color: 'var(--accent)', text: 'Strong' },
  ];
  const lvl = levels[Math.min(score, 4)];
  bar.style.width = lvl.w;
  bar.style.background = lvl.color;
  label.textContent = lvl.text;
  label.style.color = lvl.color;
}
function updateValidationChecks(pw, checksId) {
  const el = document.getElementById(checksId);
  if (!el) return;
  const checks = el.querySelectorAll('li');
  const rules = [
    pw.length >= 8,
    /[A-Z]/.test(pw),
    /[a-z]/.test(pw),
    /[0-9]/.test(pw),
    /[^A-Za-z0-9]/.test(pw),
  ];
  checks.forEach((li, i) => {
    if (rules[i] !== undefined) li.classList.toggle('ok', rules[i]);
  });
}

// ========== TOGGLE PASSWORD ==========
function togglePw(btnId, inputId) {
  const btn = document.getElementById(btnId);
  const input = document.getElementById(inputId);
  if (!btn || !input) return;
  const isText = input.type === 'text';
  input.type = isText ? 'password' : 'text';
  btn.textContent = isText ? 'Show' : 'Hide';
}

// ========== AUTH HANDLERS ==========
const ADMIN_PIN = '7391';
const ADMIN_FAIL_KEY = 'hm_admin_fail_count';
const ADMIN_LOCK_KEY = 'hm_admin_lock_until';
const ADMIN_MAX_ATTEMPTS = 5;
const ADMIN_LOCK_MS = 5 * 60 * 1000;

function getAdminLockRemainingMs() {
  const until = Number(localStorage.getItem(ADMIN_LOCK_KEY) || 0);
  return Math.max(0, until - Date.now());
}
function registerAdminFailure() {
  const next = Number(localStorage.getItem(ADMIN_FAIL_KEY) || 0) + 1;
  localStorage.setItem(ADMIN_FAIL_KEY, String(next));
  if (next >= ADMIN_MAX_ATTEMPTS) {
    localStorage.setItem(ADMIN_LOCK_KEY, String(Date.now() + ADMIN_LOCK_MS));
    localStorage.setItem(ADMIN_FAIL_KEY, '0');
  }
}
function clearAdminFailures() {
  localStorage.removeItem(ADMIN_FAIL_KEY);
  localStorage.removeItem(ADMIN_LOCK_KEY);
}

function handleRegister(e) {
  e.preventDefault();
  let valid = true;
  const fname = document.getElementById('reg-fname');
  const lname = document.getElementById('reg-lname');
  const email = document.getElementById('reg-email');
  const pw = document.getElementById('reg-pw');
  const cookie = document.getElementById('reg-cookie');

  if (!fname || !fname.value.trim()) { setFieldError('reg-fname','reg-fname-err','First name is required'); valid = false; } else setFieldValid('reg-fname','reg-fname-err');
  if (!lname || !lname.value.trim()) { setFieldError('reg-lname','reg-lname-err','Last name is required'); valid = false; } else setFieldValid('reg-lname','reg-lname-err');
  if (!email || !email.value.trim()) { setFieldError('reg-email','reg-email-err','Email is required'); valid = false; }
  else if (!isValidEmail(email.value)) { setFieldError('reg-email','reg-email-err','Enter a valid email (e.g. user@example.com)'); valid = false; }
  else setFieldValid('reg-email','reg-email-err');
  if (!pw || pw.value.length < 8 || !/[A-Z]/.test(pw.value) || !/[a-z]/.test(pw.value) || !/[0-9]/.test(pw.value) || !/[^A-Za-z0-9]/.test(pw.value)) { setFieldError('reg-pw','reg-pw-err','Please complete the password checklist.'); valid = false; }
  else setFieldValid('reg-pw','reg-pw-err');
  if (!cookie || !cookie.value.trim()) { setFieldError('reg-cookie','reg-cookie-err','LinkedIn session cookie is required'); valid = false; }
  else if (!cookie.value.startsWith('li_at=')) { setFieldError('reg-cookie','reg-cookie-err','Paste a valid LinkedIn session cookie value.'); valid = false; }
  else setFieldValid('reg-cookie','reg-cookie-err');

  if (!valid) { showToast('error', 'Please fix the errors above before continuing.'); return; }
  showToast('success', 'Account created! Welcome to HireMate.');
  setTimeout(() => { window.location.href = 'dashboard.html'; }, 900);
}

function handleLogin(e) {
  e.preventDefault();
  let valid = true;
  const email = document.getElementById('login-email');
  const pw = document.getElementById('login-pw');

  if (!email || !email.value.trim()) { setFieldError('login-email','login-email-err','Email is required'); valid = false; }
  else if (!isValidEmail(email.value)) { setFieldError('login-email','login-email-err','Enter a valid email address (must contain @ and domain)'); valid = false; }
  else setFieldValid('login-email','login-email-err');

  if (!pw || !pw.value) { setFieldError('login-pw','login-pw-err','Password is required'); valid = false; }
  else if (pw.value.length < 8) { setFieldError('login-pw','login-pw-err','Password must be at least 8 characters'); valid = false; }
  else setFieldValid('login-pw','login-pw-err');

  if (!valid) { showToast('error', 'Please check your credentials and try again.'); return; }
  showToast('success', 'Signed in successfully!');
  setTimeout(() => { window.location.href = 'dashboard.html'; }, 700);
}

function handleAdminLogin(e) {
  e.preventDefault();
  const lockRemaining = getAdminLockRemainingMs();
  if (lockRemaining > 0) {
    const mins = Math.ceil(lockRemaining / 60000);
    setFieldError('admin-pin', 'admin-pin-err', `Too many failed attempts. Try again in ${mins} minute(s).`);
    showToast('error', 'Admin login is temporarily locked.');
    return;
  }

  let valid = true;
  const email = document.getElementById('admin-email');
  const pw = document.getElementById('admin-pw');
  const pin = document.getElementById('admin-pin');

  if (!email || !email.value.trim()) { setFieldError('admin-email','admin-email-err','Admin email is required'); valid = false; }
  else if (!isValidEmail(email.value)) { setFieldError('admin-email','admin-email-err','Enter a valid email address'); valid = false; }
  else setFieldValid('admin-email','admin-email-err');
  if (!pw || !pw.value) { setFieldError('admin-pw','admin-pw-err','Password is required'); valid = false; }
  else setFieldValid('admin-pw','admin-pw-err');
  if (!pin || !pin.value.trim()) { setFieldError('admin-pin','admin-pin-err','Security PIN is required'); valid = false; }
  else if (!/^\d{4}$/.test(pin.value.trim())) { setFieldError('admin-pin','admin-pin-err','PIN must be exactly 4 digits'); valid = false; }
  else setFieldValid('admin-pin','admin-pin-err');

  if (!valid) { showToast('error', 'Invalid credentials. Please try again.'); return; }
  if (pin.value.trim() !== ADMIN_PIN) {
    registerAdminFailure();
    const left = Number(localStorage.getItem(ADMIN_FAIL_KEY) || 0);
    if (left === 0 && getAdminLockRemainingMs() > 0) {
      setFieldError('admin-pin', 'admin-pin-err', 'Too many failed attempts. Login locked for 5 minutes.');
      showToast('error', 'Too many failed attempts. Login locked.');
      return;
    }
    setFieldError('admin-pin', 'admin-pin-err', `Incorrect PIN. ${Math.max(0, ADMIN_MAX_ATTEMPTS - left)} attempt(s) left.`);
    showToast('error', 'Invalid admin PIN.');
    return;
  }

  clearAdminFailures();
  sessionStorage.setItem('hm_admin_auth', 'ok');
  showToast('success', 'Admin access granted.');
  setTimeout(() => { window.location.href = 'secure/ops-portal-7h9k.html'; }, 700);
}

// ========== DRAFTS ==========
function regenDraft(type) {
  const id = type === 'msg' ? 'msg-draft' : 'cmt-draft';
  const el = document.getElementById(id);
  if (!el) return;
  el.style.opacity = '0.4';
  el.disabled = true;
  setTimeout(() => { el.style.opacity = '1'; el.disabled = false; showToast('success', 'New draft generated!'); }, 1200);
}
function copyDraft(id) {
  const el = document.getElementById(id);
  if (!el) return;
  navigator.clipboard.writeText(el.value).then(() => showToast('success', 'Copied to clipboard!')).catch(() => {
    const ta = document.createElement('textarea');
    ta.value = el.value; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); ta.remove();
    showToast('success', 'Copied to clipboard!');
  });
}
function approveDraft() {
  showToast('success', 'Draft approved! Copy it to send on LinkedIn.');
}
function generateDraft(type) {
  const btn = event.currentTarget;
  const origText = btn.innerHTML;
  btn.innerHTML = '<span class="spinner"></span> Generating...';
  btn.disabled = true;
  setTimeout(() => {
    btn.innerHTML = origText;
    btn.disabled = false;
    showToast('success', `${type === 'msg' ? 'Message' : 'Comment'} draft generated successfully!`);
  }, 1800);
}

// ========== PROFILE / SKILLS ==========
function addSkill() {
  const input = document.getElementById('skill-input');
  if (!input) return;
  const val = input.value.trim();
  if (!val) { showToast('warning', 'Please enter a skill name.'); return; }
  const cont = document.getElementById('skills-container');
  const tag = document.createElement('div');
  tag.className = 'skill-tag';
  tag.innerHTML = `${val} <button onclick="removeSkill(this)" title="Remove skill">&times;</button>`;
  cont.appendChild(tag);
  input.value = '';
  input.focus();
}
function removeSkill(btn) { btn.parentElement.remove(); }
function addInterest() {
  const input = document.getElementById('interest-input');
  if (!input) return;
  const val = input.value.trim();
  if (!val) { showToast('warning', 'Please enter an interest.'); return; }
  const cont = document.getElementById('interests-container');
  const tag = document.createElement('div');
  tag.className = 'interest-tag';
  tag.innerHTML = `${val} <button onclick="this.parentElement.remove()" style="background:none;border:none;color:rgba(74,255,160,0.5);cursor:pointer;margin-left:4px;font-size:13px;" title="Remove">&times;</button>`;
  cont.appendChild(tag);
  input.value = '';
  input.focus();
}

// ========== FILTER LEADS ==========
function filterLeads(type) {
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  const btn = document.getElementById('filter-' + type);
  if (btn) btn.classList.add('active');
}

// ========== SETTINGS ==========
function showSettingsPanel(id) {
  document.querySelectorAll('.settings-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.settings-nav-item').forEach(i => i.classList.remove('active'));
  const panel = document.getElementById('sp-' + id);
  const nav = document.getElementById('sn-' + id);
  if (panel) panel.classList.add('active');
  if (nav) nav.classList.add('active');
}

// ========== LOGOUT ==========
function confirmLogout() {
  showConfirm('Logout', 'Confirm logout?', 'Are you sure you want to sign out of HireMate?', 'Yes, Logout', 'btn-danger', async () => {
    try {
      if (hmToken()) await hmApi('/api/auth/logout', { method: 'POST', body: '{}' });
    } catch (e) {}
    localStorage.removeItem('hm_token');
    localStorage.removeItem('hm_user');
    sessionStorage.removeItem('hm_admin_auth');
    showToast('success', 'Signed out.');
    setTimeout(() => { window.location.href = 'landing.html'; }, 1200);
  });
}

// ========== DELETE ACCOUNT ==========
function showDeleteModal() {
  document.getElementById('modal-content').innerHTML = `
    <div class="modal-title" style="color:var(--hot)">Delete Account</div>
    <div class="modal-sub">This action is permanent and cannot be undone. All your leads, drafts, and data will be permanently removed.</div>
    <div class="warning-box" style="margin-bottom:20px;"><span>!</span><span>Type <strong style="color:var(--text)">DELETE</strong> in the field below to confirm this action.</span></div>
    <div class="form-group" style="margin-bottom:20px;">
      <label class="form-label">Confirmation</label>
      <input class="form-input" placeholder="Type DELETE here" id="delete-confirm" autocomplete="off">
      <span class="form-error-msg" id="delete-err"></span>
    </div>
    <div style="display:flex;gap:10px;">
      <button class="btn btn-ghost" style="flex:1;" onclick="closeModal()">Cancel</button>
      <button class="btn btn-danger" style="flex:1;" onclick="confirmDelete()">Delete My Account</button>
    </div>`;
  document.getElementById('modal').classList.add('open');
}
async function confirmDelete() {
  const v = document.getElementById('delete-confirm').value;
  if (v !== 'DELETE') {
    document.getElementById('delete-err').textContent = 'You must type DELETE exactly (all caps) to confirm.';
    document.getElementById('delete-confirm').classList.add('is-error');
    return;
  }
  try {
    await hmApi('/api/account', { method: 'DELETE' });
    localStorage.clear();
    sessionStorage.clear();
    closeModal();
    showToast('success', 'Account permanently deleted.');
    setTimeout(() => { window.location.href = 'landing.html'; }, 900);
  } catch (err) {
    document.getElementById('delete-err').textContent = err.message || 'Account could not be deleted. Please try again.';
    document.getElementById('delete-confirm').classList.add('is-error');
  }
}

// ========== SCROLL ==========
function scrollTo2(id) {
  const el = document.getElementById(id);
  if (el) el.scrollIntoView({ behavior: 'smooth' });
}

// ========== MODAL OUTSIDE CLICK ==========
document.addEventListener('DOMContentLoaded', () => {
  const modal = document.getElementById('modal');
  if (modal) modal.addEventListener('click', e => { if (e.target === modal) closeModal(); });
  const confirm = document.getElementById('confirm-overlay');
  if (confirm) confirm.addEventListener('click', e => { if (e.target === confirm) closeConfirm(); });
});

// ========== BACKEND INTEGRATION ==========
const HM_BACKEND_ORIGIN = 'http://localhost:8000';
function hmApiBase() {
  if (window.location.origin && window.location.origin.startsWith('http')) {
    const current = new URL(window.location.origin);
    if (current.port === '8000') return window.location.origin;
    if (!['localhost', '127.0.0.1'].includes(current.hostname)) return window.location.origin;
  }
  return HM_BACKEND_ORIGIN;
}

function hmToken() { return localStorage.getItem('hm_token') || ''; }
function hmSetSession(data) {
  if (!data || !data.token) return;
  localStorage.setItem('hm_token', data.token);
  localStorage.setItem('hm_user', JSON.stringify(data.user || {}));
  hmApplyNavAvatar(data.user || {});
}
const hmApiInFlight = {};
const hmApiCacheVersion = 'v3';
function hmCacheUserKey() {
  const user = hmCurrentUser();
  return String(user.id || user.email || hmToken().slice(0, 18) || 'guest');
}
function hmCacheKey(path) {
  return 'hm_api_cache:' + hmApiCacheVersion + ':' + hmCacheUserKey() + ':' + path;
}
function hmReadCache(path, maxAgeMs) {
  try {
    const raw = localStorage.getItem(hmCacheKey(path));
    if (!raw) return null;
    const cached = JSON.parse(raw);
    const age = Date.now() - Number(cached.t || 0);
    if (maxAgeMs && age > maxAgeMs) return null;
    return cached.v || null;
  } catch (e) {
    return null;
  }
}
function hmWriteCache(path, value) {
  try {
    localStorage.setItem(hmCacheKey(path), JSON.stringify({ t: Date.now(), v: value }));
  } catch (e) {}
}
function hmRememberLeadCache(lead) {
  if (!lead || !lead.id) return;
  hmWriteCache('/api/leads/' + encodeURIComponent(lead.id), { ok: true, lead });
}
function hmCachedLeadPool() {
  const byId = {};
  try {
    const prefix = 'hm_api_cache:' + hmApiCacheVersion + ':' + hmCacheUserKey() + ':';
    Object.keys(localStorage).forEach(key => {
      if (key.indexOf(prefix) !== 0) return;
      const payload = JSON.parse(localStorage.getItem(key) || '{}').v || {};
      if (payload.lead && payload.lead.id) byId[payload.lead.id] = payload.lead;
      (payload.leads || []).forEach(lead => { if (lead && lead.id) byId[lead.id] = lead; });
      const recent = payload.data && payload.data.recent_leads ? payload.data.recent_leads : [];
      recent.forEach(lead => { if (lead && lead.id) byId[lead.id] = lead; });
    });
  } catch (e) {}
  return Object.values(byId).sort((a, b) => {
    const ac = new Date(String(a.created_at || a.posted_at || '').replace(' ', 'T')).getTime() || 0;
    const bc = new Date(String(b.created_at || b.posted_at || '').replace(' ', 'T')).getTime() || 0;
    return bc - ac;
  });
}
function hmCachedLeadSubset() {
  let leads = hmCachedLeadPool();
  if (hmLeadsState.status) leads = leads.filter(lead => lead.status === hmLeadsState.status);
  if (hmLeadsState.filter && hmLeadsState.filter !== 'all') leads = leads.filter(lead => lead.temperature === hmLeadsState.filter);
  if (hmLeadsState.kind && hmLeadsState.kind !== 'all') leads = leads.filter(lead => lead.lead_kind === hmLeadsState.kind);
  if (hmLeadsState.search) {
    const q = hmLeadsState.search.toLowerCase();
    leads = leads.filter(lead => [lead.company, lead.role_title, lead.post_text, (lead.tags || []).join(' ')].join(' ').toLowerCase().includes(q));
  }
  return leads;
}
function hmClearApiCache(prefix) {
  try {
    const userPrefix = 'hm_api_cache:' + hmApiCacheVersion + ':' + hmCacheUserKey() + ':' + (prefix || '');
    Object.keys(localStorage).forEach(key => {
      if (key.indexOf(userPrefix) === 0) localStorage.removeItem(key);
    });
  } catch (e) {}
}
async function hmApi(path, options) {
  const headers = Object.assign({ 'Content-Type': 'application/json' }, (options && options.headers) || {});
  if (hmToken()) headers.Authorization = 'Bearer ' + hmToken();
  const method = String((options && options.method) || 'GET').toUpperCase();
  const inFlightKey = method + ':' + path;
  if (method === 'GET' && hmApiInFlight[inFlightKey]) return hmApiInFlight[inFlightKey];
  const request = fetch(hmApiBase() + path, Object.assign({}, options || {}, { headers }))
    .then(async res => {
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.ok === false) {
    const err = new Error(data.error || 'Request failed');
    err.status = res.status;
    throw err;
  }
      if (method !== 'GET') hmClearApiCache('/api/');
  return data;
    })
    .finally(() => { delete hmApiInFlight[inFlightKey]; });
  if (method === 'GET') hmApiInFlight[inFlightKey] = request;
  return request;
}
async function hmCachedApi(path, maxAgeMs) {
  const cached = hmReadCache(path, maxAgeMs || 120000);
  if (cached) return cached;
  const data = await hmApi(path);
  hmWriteCache(path, data);
  return data;
}
function hmRefreshCache(path, onFresh) {
  return hmApi(path).then(data => {
    hmWriteCache(path, data);
    if (onFresh) onFresh(data);
    return data;
  });
}
function hmCurrentUser() { try { return JSON.parse(localStorage.getItem('hm_user') || '{}'); } catch (e) { return {}; } }
function hmProfileComplete(user) {
  const account = user || hmCurrentUser();
  if (account.profile_complete === true) return true;
  const skills = String(account.skills || '').trim();
  const roles = String(account.target_roles || '').trim();
  const context = [
    account.headline,
    account.about,
    account.education,
    account.experience_detail,
    account.interests
  ].some(value => String(value || '').trim());
  return Boolean((skills || roles) && (roles || context));
}
function hmProfileRequiredCard() {
  return '<div class="section-card empty-state"><strong>Complete your profile first.</strong><br>Add your skills and target roles so HireMate can find opportunities that match your background.<br><button class="btn btn-primary" style="margin-top:14px;" onclick="window.location.href=&quot;onboarding.html&quot;">Complete Profile</button></div>';
}
function hmFinishDataBoot() {
  if (document.body) document.body.classList.remove('hm-data-booting');
}
function hmPageIs(name) {
  return document.title.includes(name);
}
function hmIsAppPage() {
  return ['Dashboard', 'Leads', 'Drafts', 'Analytics', 'Profile', 'Settings'].some(name => hmPageIs(name));
}
function hmLeadUrl(id) { localStorage.setItem('hm_selected_lead_id', String(id)); return 'lead-detail.html?id=' + encodeURIComponent(id); }
function hmDraftUrl(id) { return 'draft-detail.html?id=' + encodeURIComponent(id); }
function hmEscape(s) { return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
function hmUserInitials(user) {
  const fullName = [user.first_name, user.last_name].filter(Boolean).join(' ').trim();
  const source = fullName || user.name || user.email || 'HM';
  return source.split(/\s+/).map(part => part[0]).join('').slice(0, 2).toUpperCase();
}
function hmApplyNavAvatar(user) {
  const account = user || hmCurrentUser();
  const image = String(account.avatar_image || '').trim();
  const initials = hmUserInitials(account);
  document.querySelectorAll('.nav-actions > .avatar, .nav-r > .avatar').forEach(avatar => {
    avatar.classList.toggle('has-image', Boolean(image));
    avatar.style.backgroundImage = '';
    if (image) {
      avatar.innerHTML = '<img src="' + hmEscape(image) + '" alt="Profile picture">';
    } else {
      avatar.textContent = initials;
    }
  });
}
function hmParseDate(value) {
  const raw = String(value || '').trim();
  if (!raw) return null;
  let normalized = raw.replace(/^(.{10})\s+(\d{2}:\d{2}:\d{2})/, '$1T$2');
  normalized = normalized.replace(/\.(\d{3})\d+/, '.$1');
  normalized = normalized.replace(/([+-]\d{2})(\d{2})$/, '$1:$2');
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(normalized) && !/(Z|[+-]\d{2}:?\d{2})$/i.test(normalized)) {
    normalized += 'Z';
  }
  const dt = new Date(normalized);
  return Number.isNaN(dt.getTime()) ? null : dt;
}
function hmTimeAgo(iso) {
  const raw = String(iso || '').trim();
  const dt = hmParseDate(raw);
  if (!dt) return '';
  const diffMs = Math.max(0, Date.now() - dt.getTime());
  const minutes = Math.floor(diffMs / 60000);
  if (minutes < 1) return 'Just now';
  if (minutes < 60) return minutes + ' min ago';
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return hours + ' hrs ago';
  return Math.floor(hours / 24) + ' days ago';
}
function hmRelativeLabelToIso(label, baseIso) {
  const text = String(label || '').toLowerCase();
  const match = text.match(/(\d+)\s+(minute|minutes|hour|hours|day|days|week|weeks|month|months)\s+ago/);
  if (!match) return baseIso || '';
  const amount = Number(match[1] || 0);
  const unit = match[2];
  const multipliers = { minute: 60000, minutes: 60000, hour: 3600000, hours: 3600000, day: 86400000, days: 86400000, week: 604800000, weeks: 604800000, month: 2592000000, months: 2592000000 };
  return new Date(Date.now() - amount * (multipliers[unit] || 0)).toISOString();
}
function hmBadge(temp) {
  const label = temp === 'hot' ? 'Hot' : temp === 'warm' ? 'Warm' : 'Cold';
  return `<span class="badge badge-${hmEscape(temp)}">${label}</span>`;
}

function hmCompactKey(value) {
  return String(value || '').toLowerCase().replace(/https?:\/\/\S+/g, '').replace(/[^a-z0-9+#.\s-]/g, ' ').replace(/\s+/g, ' ').trim();
}

function hmJobRoleFamily(value) {
  const stop = new Set(['entry', 'level', 'entrylevel', 'junior', 'senior', 'sr', 'jr', 'remote', 'fully', 'virtual', 'admin', 'administrator', 'assistant', '100', 'percent', 'full', 'time', 'part', 'onsite', 'hybrid', 'intern', 'internship', 'associate', 'specialist', 'i', 'ii', 'iii', 'iv', 'v', '1', '2', '3', '4', '5']);
  const tokens = hmCompactKey(value).replace(/%/g, ' percent ').split(/[\s/-]+/).map(t => t.replace(/[.,_()[\]{}]/g, '')).filter(t => t && !stop.has(t));
  return Array.from(new Set(tokens)).slice(0, 6).join(' ');
}

function hmLeadRenderKey(lead) {
  const kind = lead && lead.lead_kind === 'post' ? 'post' : 'job';
  const url = hmCompactKey((lead && lead.post_url) || '').split('?')[0];
  if (kind === 'post') return url ? 'post:url:' + url : 'post:text:' + hmCompactKey((lead && lead.post_text) || '').slice(0, 700);
  const company = hmCompactKey((lead && lead.company) || '');
  const family = hmJobRoleFamily((lead && lead.role_title) || '');
  if (company && family) return 'job:family:' + company + ':' + family;
  return url ? 'job:url:' + url : 'job:id:' + company + ':' + hmCompactKey((lead && lead.role_title) || '') + ':' + hmCompactKey((lead && lead.location) || '');
}

function hmUniqueLeads(leads) {
  const seen = new Set();
  const unique = [];
  (leads || []).forEach(lead => {
    const key = hmLeadRenderKey(lead);
    if (seen.has(key)) return;
    seen.add(key);
    unique.push(lead);
  });
  return unique;
}

const hmLeadsState = {
  offset: 0,
  limit: 8,
  filter: 'all',
  loading: false,
  done: false,
  total: 0,
  status: '',
  kind: 'all',
  search: ''
};
let hmLeadsRequestSeq = 0;

function hmLeadCard(lead, compact) {
  const temp = lead.temperature || 'cold';
  const kind = lead.lead_kind === 'job' ? 'Job' : 'Post';
  const bodyLimit = compact ? 180 : 260;
  const body = hmEscape(lead.post_text || '').slice(0, bodyLimit);
  const reaction = lead.reaction_items || {};
  const postedIso = hmRelativeLabelToIso(reaction.posted_label, lead.posted_at);
  const postedLabel = postedIso ? hmTimeAgo(postedIso) : hmTimeAgo(lead.posted_at);
  const applicantText = reaction.applicant_text || (Number(lead.comments || 0) ? Number(lead.comments || 0) + ' applicants' : 'Applicants not shown');
  const clockIcon = '<svg class="lead-meta-clock" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"></circle><path d="M12 7v5l3 2"></path></svg>';
  const meta = lead.lead_kind === 'job'
    ? `<span class="lead-meta">${clockIcon}${hmEscape(postedLabel)}</span><span class="lead-meta">${hmEscape(applicantText)}</span>`
    : `<span class="lead-meta">${clockIcon}${hmEscape(hmTimeAgo(lead.posted_at))}</span><span class="lead-meta">&#x2764; ${Number(lead.likes || 0)}</span><span class="lead-meta">&#x1F4AC; ${Number(lead.comments || 0)}</span>`;
  const removeSaved = lead.status === 'saved'
    ? `<button class="btn btn-sm btn-ghost" title="Remove saved lead" onclick="hmRemoveSavedLead(${lead.id}, event)">&times;</button>`
    : '';
  return `
    <div class="card card-${hmEscape(temp)} lead-card" data-temp="${hmEscape(temp)}" data-lead-id="${hmEscape(lead.id)}" data-lead-key="${hmEscape(hmLeadRenderKey(lead))}" onclick="window.location.href=hmLeadUrl(${lead.id})">
      <div class="lead-header">
        <div><div class="lead-company">${hmEscape(lead.company)}</div><div class="lead-role">${hmEscape(lead.role_title)}</div></div>
        <div class="lead-badge-stack">${hmBadge(temp)}<span class="lead-kind-pill">${kind}</span></div>
      </div>
      <div class="lead-body">${body}${body.length >= bodyLimit ? '...' : ''}</div>
      <div class="lead-footer">
        ${meta}
        <div class="lead-actions">
          ${removeSaved}
          <button class="btn btn-sm btn-primary" onclick="event.stopPropagation();window.location.href=hmLeadUrl(${lead.id})">View &#x2192;</button>
        </div>
      </div>
    </div>`;
}

function hmSavedLeadRow(lead) {
  const temp = lead.temperature || 'cold';
  return `
    <div class="saved-lead-row" onclick="window.location.href=hmLeadUrl(${lead.id})">
      <span class="saved-dot saved-dot-${hmEscape(temp)}"></span>
      <span class="saved-row-text"><strong>${hmEscape(lead.company)}</strong><small>${hmEscape(lead.role_title)}</small></span>
      <button class="saved-row-delete" title="Remove saved lead" onclick="hmRemoveSavedLead(${lead.id}, event)">&times;</button>
    </div>`;
}

async function hmRemoveSavedLead(id, event) {
  if (event) {
    event.preventDefault();
    event.stopPropagation();
  }
  showConfirm(
    '&times;',
    'Remove saved lead?',
    'This lead will leave your saved list, but it will stay available in your opportunities.',
    'Remove',
    'btn-danger',
    async function () {
      try {
        await hmApi('/api/leads/' + encodeURIComponent(id), {
          method: 'PATCH',
          body: JSON.stringify({ status: 'new' })
        });
        showToast('success', 'Lead removed from saved leads.');
        await hmLoadLeadStream({ reset: true, force: true });
        await hmLoadSavedLeadsPanel();
        await hmLoadSidebarCounts();
      } catch (err) {
        showToast('error', err.message);
      }
    }
  );
}

async function handleRegister(e) {
  e.preventDefault();
  let valid = true;
  const fname = document.getElementById('reg-fname');
  const lname = document.getElementById('reg-lname');
  const email = document.getElementById('reg-email');
  const pw = document.getElementById('reg-pw');
  const cookie = document.getElementById('reg-cookie');
  if (!fname || !fname.value.trim()) { setFieldError('reg-fname','reg-fname-err','First name is required'); valid = false; } else setFieldValid('reg-fname','reg-fname-err');
  if (!lname || !lname.value.trim()) { setFieldError('reg-lname','reg-lname-err','Last name is required'); valid = false; } else setFieldValid('reg-lname','reg-lname-err');
  if (!email || !email.value.trim()) { setFieldError('reg-email','reg-email-err','Email is required'); valid = false; }
  else if (!isValidEmail(email.value)) { setFieldError('reg-email','reg-email-err','Enter a valid email'); valid = false; } else setFieldValid('reg-email','reg-email-err');
  if (!pw || pw.value.length < 8 || !/[A-Z]/.test(pw.value) || !/[a-z]/.test(pw.value) || !/[0-9]/.test(pw.value) || !/[^A-Za-z0-9]/.test(pw.value)) { setFieldError('reg-pw','reg-pw-err','Please complete the password checklist.'); valid = false; } else setFieldValid('reg-pw','reg-pw-err');
  if (cookie && cookie.value.trim()) {
    const cv = cookie.value.trim();
    const okCookie = cv.includes('li_at=') || (!cv.includes('=') && cv.length >= 20);
    if (!okCookie) { setFieldError('reg-cookie','reg-cookie-err','Paste a valid LinkedIn session cookie value.'); valid = false; }
    else setFieldValid('reg-cookie','reg-cookie-err');
  } else if (cookie) setFieldValid('reg-cookie','reg-cookie-err');
  if (!valid) { showToast('error', 'Please fix the errors above before continuing.'); return; }
  try {
    const data = await hmApi('/api/auth/register', { method: 'POST', body: JSON.stringify({ first_name: fname.value.trim(), last_name: lname.value.trim(), email: email.value.trim(), password: pw.value, linkedin_cookie: cookie ? cookie.value.trim() : '' }) });
    hmSetSession(data);
    showToast('success', 'Account created. Welcome to HireMate.');
    setTimeout(() => { window.location.href = 'onboarding.html'; }, 700);
  } catch (err) { showToast('error', err.message); }
}

async function handleLogin(e) {
  e.preventDefault();
  let valid = true;
  const email = document.getElementById('login-email');
  const pw = document.getElementById('login-pw');
  if (!email || !email.value.trim()) { setFieldError('login-email','login-email-err','Email is required'); valid = false; }
  else if (!isValidEmail(email.value)) { setFieldError('login-email','login-email-err','Enter a valid email address'); valid = false; } else setFieldValid('login-email','login-email-err');
  if (!pw || !pw.value) { setFieldError('login-pw','login-pw-err','Password is required'); valid = false; } else setFieldValid('login-pw','login-pw-err');
  if (!valid) { showToast('error', 'Please check your credentials and try again.'); return; }
  try {
    const data = await hmApi('/api/auth/login', { method: 'POST', body: JSON.stringify({ email: email.value.trim(), password: pw.value }) });
    hmSetSession(data);
    showToast('success', 'Signed in successfully.');
    setTimeout(() => { window.location.href = 'dashboard.html'; }, 600);
  } catch (err) { showToast('error', err.message); }
}

async function hmGenerateDraft(leadId, type, tone) {
  try {
    await hmApi('/api/drafts/generate', { method: 'POST', body: JSON.stringify({ lead_id: leadId, draft_type: type || 'message', tone: tone || 'professional' }) });
    showToast('success', 'Draft generated. Review it in Drafts.');
  } catch (err) { showToast('error', err.message); }
}

async function hmLoadLeadsPage() {
  return hmLoadLeadStream({ reset: hmLeadsState.offset === 0 });
}

function hmLeadLoader(grid) {
  let loader = document.getElementById('hm-lead-loader');
  if (!loader && grid) {
    loader = document.createElement('div');
    loader.id = 'hm-lead-loader';
    loader.className = 'lead-stream-status';
    grid.appendChild(loader);
  }
  return loader;
}

function hmSetLeadLoader(text, active) {
  const loader = document.getElementById('hm-lead-loader');
  if (!loader) return;
  loader.classList.toggle('is-loading', !!active);
  loader.textContent = text || '';
}

function hmUpdateLeadCounts(data) {
  const counts = data.counts || {};
  const sub = document.querySelector('.page-sub');
  if (sub) {
    const filteredTotal = data.total || hmLeadsState.total || 0;
    const allTotal = counts.total || filteredTotal;
    const kindLabel = hmLeadsState.kind === 'job' ? 'job leads' : hmLeadsState.kind === 'post' ? 'post leads' : 'opportunities';
    sub.textContent = 'Showing ' + filteredTotal + ' of ' + allTotal + ' ' + kindLabel + ' based on your profile';
  }
  const all = document.getElementById('filter-all'); if (all) all.textContent = 'All';
  const hot = document.getElementById('filter-hot'); if (hot) hot.innerHTML = '&#x1F525; Hot';
  const warm = document.getElementById('filter-warm'); if (warm) warm.innerHTML = 'Warm';
  const cold = document.getElementById('filter-cold'); if (cold) cold.innerHTML = '&#x2744; Cold';
  const kindSelect = document.getElementById('lead-kind-filter');
  if (kindSelect) {
    const allOption = kindSelect.querySelector('option[value="all"]');
    const jobOption = kindSelect.querySelector('option[value="job"]');
    const postOption = kindSelect.querySelector('option[value="post"]');
    if (allOption) allOption.textContent = 'Jobs + Posts';
    if (jobOption) jobOption.textContent = 'Jobs';
    if (postOption) postOption.textContent = 'Posts';
    kindSelect.value = hmLeadsState.kind || 'all';
  }
}

async function hmLoadLeadStream(options) {
  const grid = document.querySelector('.leads-grid');
  if (!grid || !document.title.includes('Leads') || document.title.includes('Saved Leads')) return;
  if (!hmProfileComplete()) {
    grid.innerHTML = hmProfileRequiredCard();
    hmFinishDataBoot();
    return;
  }
  const opts = options || {};
  if (opts.force) hmLeadsState.loading = false;
  if (hmLeadsState.loading) return;
  const requestSeq = ++hmLeadsRequestSeq;
  const requestOffset = opts.reset ? 0 : hmLeadsState.offset;
  const params = new URLSearchParams({
    limit: String(hmLeadsState.limit),
    offset: String(requestOffset)
  });
  if (hmLeadsState.filter && hmLeadsState.filter !== 'all') params.set('temperature', hmLeadsState.filter);
  if (hmLeadsState.status) params.set('status', hmLeadsState.status);
  if (hmLeadsState.kind && hmLeadsState.kind !== 'all') params.set('kind', hmLeadsState.kind);
  if (hmLeadsState.search) params.set('search', hmLeadsState.search);
  const path = '/api/leads?' + params.toString();
  const cached = requestOffset === 0 && !opts.force ? hmReadCache(path, 5 * 60 * 1000) : null;
  if (opts.reset) {
    hmLeadsState.offset = 0;
    hmLeadsState.done = false;
    grid.innerHTML = '';
  }
  if (cached) {
    if (requestSeq !== hmLeadsRequestSeq) return;
    hmRenderLeadPageData(cached, true);
    hmSetLeadLoader('Refreshing quietly...', true);
    hmFinishDataBoot();
  } else if (requestOffset === 0) {
    const quickLeads = hmCachedLeadSubset().slice(0, hmLeadsState.limit);
    if (quickLeads.length) {
      if (requestSeq !== hmLeadsRequestSeq) return;
      hmRenderLeadPageData({
        ok: true,
        leads: quickLeads,
        total: quickLeads.length,
        next_offset: quickLeads.length,
        has_more: true,
        counts: {},
        today_counts: {}
      }, true);
      hmSetLeadLoader('Refreshing quietly...', true);
      hmFinishDataBoot();
    }
  }
  if (hmLeadsState.done && !cached) return;
  hmLeadsState.loading = true;
  const loader = hmLeadLoader(grid);
  hmSetLeadLoader(hmLeadsState.offset === 0 ? 'Loading leads...' : 'Loading more leads...', true);
  try {
    const data = await hmApi(path);
    if (requestSeq !== hmLeadsRequestSeq) return;
    if (requestOffset === 0) hmWriteCache(path, data);
    hmRenderLeadPageData(data, requestOffset === 0);
    hmSetLeadLoader(hmLeadsState.done ? 'All current leads loaded.' : 'Scroll for more leads', false);
  } catch (err) {
    if (err && err.status === 401) {
      showToast('warning', err.message || 'Please login again to load your saved data.');
      setTimeout(() => { window.location.href = 'login.html'; }, 900);
    } else {
      showToast('warning', 'HireMate is taking longer than expected. Please refresh and try again.');
    }
  }
  finally {
    if (requestSeq === hmLeadsRequestSeq) hmLeadsState.loading = false;
    hmFinishDataBoot();
  }
}

async function hmLoadSavedLeadsPage() {
  const grid = document.querySelector('.leads-grid');
  if (!grid || !document.title.includes('Saved Leads') || !hmToken()) return;
  hmLeadsState.status = 'saved';
  hmLeadsState.offset = 0;
  hmLeadsState.done = false;
  hmLeadsState.loading = true;
  grid.innerHTML = '';
  const loader = hmLeadLoader(grid);
  hmSetLeadLoader('Loading saved leads...', true);
  const pageSize = 30;
  let offset = 0;
  let allSaved = [];
  try {
    while (offset < 300) {
      const data = await hmApi('/api/leads?status=saved&limit=' + pageSize + '&offset=' + offset);
      allSaved = allSaved.concat(data.leads || []);
      if (!data.has_more) break;
      offset = Number(data.next_offset || allSaved.length);
      if (!offset || offset <= allSaved.length - (data.leads || []).length) break;
    }
    const unique = hmUniqueLeads(allSaved);
    unique.forEach(hmRememberLeadCache);
    hmWriteCache('/api/leads?status=saved&limit=' + pageSize + '&offset=0', {
      ok: true,
      leads: unique,
      total: unique.length,
      next_offset: unique.length,
      has_more: false,
      counts: { saved: unique.length },
      today_counts: { saved: unique.length }
    });
    loader.insertAdjacentHTML('beforebegin', unique.length ? unique.map(lead => hmLeadCard(lead, false)).join('') : hmLeadEmptyState());
    hmLeadsState.offset = unique.length;
    hmLeadsState.total = unique.length;
    hmLeadsState.done = true;
    hmSetLeadLoader(unique.length ? 'All saved leads loaded.' : '', false);
    hmUpdateLeadCounts({ counts: { saved: unique.length }, today_counts: { saved: unique.length } });
    hmUpdateSidebarCounts({ saved: unique.length });
    hmLoadSavedLeadsPanel();
  } catch (err) {
    loader.insertAdjacentHTML('beforebegin', '<div class="section-card empty-state"><strong>Saved leads could not be loaded.</strong><br>Please refresh after a moment.</div>');
    hmSetLeadLoader('', false);
  } finally {
    hmLeadsState.loading = false;
    hmFinishDataBoot();
  }
}

function hmRenderLeadPageData(data, replace) {
  const grid = document.querySelector('.leads-grid');
  if (!grid) return;
  if (data && data.profile_required) {
    grid.innerHTML = hmProfileRequiredCard();
    hmUpdateSidebarCounts(data.today_counts || {});
    hmFinishDataBoot();
    return;
  }
  let loader = hmLeadLoader(grid);
  if (replace) {
    grid.innerHTML = '';
    loader = hmLeadLoader(grid);
  }
  const leads = hmUniqueLeads((data && data.leads) || []);
  leads.forEach(hmRememberLeadCache);
  if (leads.length) {
    const existingIds = new Set(Array.from(grid.querySelectorAll('.lead-card')).map(card => card.getAttribute('data-lead-id')));
    const existingKeys = new Set(Array.from(grid.querySelectorAll('.lead-card')).map(card => card.getAttribute('data-lead-key')));
    const visible = leads.filter(lead => !existingIds.has(String(lead.id)) && !existingKeys.has(hmLeadRenderKey(lead)));
    loader.insertAdjacentHTML('beforebegin', visible.map(lead => hmLeadCard(lead, false)).join(''));
  } else if (hmLeadsState.offset === 0) {
    loader.insertAdjacentHTML('beforebegin', hmLeadEmptyState());
  }
  hmLeadsState.offset = Number(data.next_offset || (hmLeadsState.offset + leads.length));
  hmLeadsState.total = Number(data.total || 0);
  hmLeadsState.done = !data.has_more;
  hmUpdateLeadCounts(data);
  hmUpdateSidebarCounts(data.today_counts || {});
  hmLoadSavedLeadsPanel();
}

function hmPrependNewLeads(leads) {
  const incoming = (leads || []).filter(lead => lead && lead.id);
  if (!incoming.length) return;
  incoming.forEach(hmRememberLeadCache);
  const grid = document.querySelector('.leads-grid');
  if (!grid || !document.title.includes('Leads')) return;
  const existing = new Set(Array.from(grid.querySelectorAll('.lead-card')).map(card => card.getAttribute('data-lead-id')));
  const existingKeys = new Set(Array.from(grid.querySelectorAll('.lead-card')).map(card => card.getAttribute('data-lead-key')));
  const visible = incoming.filter(lead => {
    if (existing.has(String(lead.id))) return false;
    if (existingKeys.has(hmLeadRenderKey(lead))) return false;
    if (hmLeadsState.filter && hmLeadsState.filter !== 'all' && lead.temperature !== hmLeadsState.filter) return false;
    if (hmLeadsState.kind && hmLeadsState.kind !== 'all' && lead.lead_kind !== hmLeadsState.kind) return false;
    if (hmLeadsState.status && lead.status !== hmLeadsState.status) return false;
    return true;
  });
  if (!visible.length) return;
  const loader = hmLeadLoader(grid);
  loader.insertAdjacentHTML('beforebegin', visible.map(lead => hmLeadCard(lead, false)).join(''));
  hmLeadsState.offset += visible.length;
  hmLeadsState.total += visible.length;
}

function hmLeadEmptyState() {
  let title = 'Opportunities will appear here.';
  let message = 'Try finding new opportunities or adjust the filters.';
  if (hmLeadsState.status === 'saved') {
    title = 'Saved leads will appear here.';
    message = 'Save the leads you like and they will appear here.';
  } else if (hmLeadsState.search) {
    title = 'Search is ready for another keyword.';
    message = 'Try another company, role, or skill.';
  } else if (hmLeadsState.filter === 'hot') {
    title = 'Hot leads will appear here.';
    message = 'Strong matches will appear here when HireMate finds them.';
  } else if (hmLeadsState.filter === 'warm') {
    title = 'Warm leads will appear here.';
    message = 'Good-fit opportunities will appear here soon.';
  } else if (hmLeadsState.filter === 'cold') {
    title = 'Cold leads will appear here.';
    message = 'Lower-priority opportunities will appear here when available.';
  }
  return '<div class="section-card empty-state"><strong>' + hmEscape(title) + '</strong><br>' + hmEscape(message) + '</div>';
}
function hmShowAllLeadsView() {
  hmLeadsState.filter = 'all';
  hmLeadsState.status = '';
  hmLeadsState.kind = 'all';
  localStorage.removeItem('hm_lead_filter');
  localStorage.removeItem('hm_lead_status');
  localStorage.removeItem('hm_lead_kind');
  document.querySelectorAll('.filter-row .filter-btn').forEach(b => b.classList.remove('active'));
  const all = document.getElementById('filter-all');
  if (all) all.classList.add('active');
  const kindSelect = document.getElementById('lead-kind-filter');
  if (kindSelect) kindSelect.value = 'all';
}

async function hmLoadSavedLeadsPanel() {
  const list = document.getElementById('saved-leads-panel-list');
  if (!list || !hmToken()) return;
  const pageSize = document.title.includes('Saved Leads') ? 30 : 12;
  const firstPath = '/api/leads?status=saved&limit=' + pageSize + '&offset=0';
  const renderSaved = data => {
    const saved = (data && data.leads) || [];
    const sub = document.getElementById('saved-panel-sub');
    if (sub) sub.textContent = saved.length ? saved.length + ' saved leads' : 'Saved leads will appear here';
    list.innerHTML = saved.length
      ? saved.map(hmSavedLeadRow).join('')
      : '<div class="saved-empty">Save a lead to keep it here for later.</div>';
  };
  const cached = hmReadCache(firstPath, 10 * 60 * 1000);
  if (cached) renderSaved(cached);
  try {
    let data = cached ? await hmRefreshCache(firstPath, renderSaved) : await hmCachedApi(firstPath, 10 * 60 * 1000);
    let allSaved = (data.leads || []).slice();
    let nextOffset = Number(data.next_offset || allSaved.length);
    while (document.title.includes('Saved Leads') && data.has_more && nextOffset < 300) {
      data = await hmApi('/api/leads?status=saved&limit=' + pageSize + '&offset=' + nextOffset);
      allSaved = allSaved.concat(data.leads || []);
      nextOffset = Number(data.next_offset || allSaved.length);
    }
    const fullData = Object.assign({}, data, { leads: hmUniqueLeads(allSaved), has_more: false });
    hmWriteCache(firstPath, fullData);
    renderSaved(fullData);
  } catch (err) {
    if (!cached) list.innerHTML = '<div class="saved-empty">Saved leads could not be loaded.</div>';
  }
}

async function hmLoadSidebarCounts() {
  if (!hmToken() || !document.querySelector('.sidebar-item')) return;
  const path = '/api/leads?limit=1';
  try {
    const data = await hmApi(path);
    hmWriteCache(path, data);
    hmUpdateSidebarCounts(data.today_counts || {});
  } catch (err) {}
}

async function hmLoadDashboardPage() {
  if (!document.title.includes('Dashboard')) return;
  if (!hmProfileComplete()) {
    hmRenderDashboardData({ profile_required: true, data: { today_counts: {} } });
    hmFinishDataBoot();
    return;
  }
  const path = '/api/dashboard';
  const cached = hmReadCache(path, 10 * 60 * 1000);
  const snapshot = hmReadDashboardSnapshot();
  if (cached && hmDashboardHasUsefulData(cached)) {
    hmRenderDashboardData(cached);
    hmFinishDataBoot();
  } else if (snapshot) {
    hmRenderDashboardData(snapshot);
    hmFinishDataBoot();
  } else {
    hmRenderDashboardFromLocalCache();
    hmFinishDataBoot();
  }
  try {
    const data = cached ? await hmRefreshCache(path, hmRenderDashboardData) : await hmCachedApi(path, 10 * 60 * 1000);
    if (!cached) hmRenderDashboardData(data);
    let user = hmCurrentUser();
    const title = document.querySelector('.page-title');
    if (title) title.innerHTML = hmGreeting() + ', ' + hmEscape(user.first_name || 'there') + ' &#x1F44B;';
    setTimeout(async () => {
      try {
        const me = await hmCachedApi('/api/me', 30 * 60 * 1000);
        const freshUser = me.user || user;
        localStorage.setItem('hm_user', JSON.stringify(freshUser));
        hmApplyNavAvatar(freshUser);
        if (title) title.innerHTML = hmGreeting() + ', ' + hmEscape(freshUser.first_name || 'there') + ' &#x1F44B;';
      } catch (e) {}
    }, 1200);
  } catch (err) {} finally { hmFinishDataBoot(); }
}

function hmRenderDashboardInstant() {
  if (!document.title.includes('Dashboard')) return;
  const user = hmCurrentUser();
  const title = document.querySelector('.page-title');
  if (title) title.innerHTML = hmGreeting() + ', ' + hmEscape(user.first_name || 'there') + ' &#x1F44B;';
  const snapshot = hmReadDashboardSnapshot();
  if (snapshot) {
    hmRenderDashboardData(snapshot);
    return;
  }
  hmRenderDashboardFromLocalCache();
}

function hmDashboardSnapshotKey() {
  return 'hm_dashboard_snapshot:' + hmCacheUserKey();
}

function hmReadDashboardSnapshot() {
  try {
    const raw = localStorage.getItem(hmDashboardSnapshotKey());
    if (!raw) return null;
    const cached = JSON.parse(raw);
    if (Date.now() - Number(cached.t || 0) > 24 * 60 * 60 * 1000) return null;
    return cached.v || null;
  } catch (e) {
    return null;
  }
}

function hmWriteDashboardSnapshot(data) {
  try {
    localStorage.setItem(hmDashboardSnapshotKey(), JSON.stringify({ t: Date.now(), v: data }));
  } catch (e) {}
}

function hmDashboardHasUsefulData(data) {
  const d = (data && data.data) || {};
  const counts = d.today_counts || d.counts || {};
  return Boolean(
    Number(counts.total || 0) ||
    Number(counts.hot || 0) ||
    Number(d.pending_drafts || 0) ||
    Number(d.approved_drafts || 0) ||
    ((d.recent_leads || []).length)
  );
}

function hmRenderDashboardFromLocalCache() {
  const leads = hmUniqueLeads(hmCachedLeadPool());
  const drafts = hmReadCache('/api/drafts', 30 * 60 * 1000);
  const pending = ((drafts && drafts.drafts) || []).filter(d => d.status === 'pending').length;
  if (!leads.length && !drafts) return;
  const todayLeads = leads.filter(hmLeadIsToday);
  hmRenderDashboardData({
    data: {
      counts: {
        total: leads.length,
        hot: leads.filter(lead => lead.temperature === 'hot').length,
        warm: leads.filter(lead => lead.temperature === 'warm').length,
        cold: leads.filter(lead => lead.temperature === 'cold').length,
        saved: leads.filter(lead => lead.status === 'saved').length
      },
      today_counts: {
        total: todayLeads.length,
        hot: todayLeads.filter(lead => lead.temperature === 'hot').length,
        warm: todayLeads.filter(lead => lead.temperature === 'warm').length,
        cold: todayLeads.filter(lead => lead.temperature === 'cold').length,
        saved: todayLeads.filter(lead => lead.status === 'saved').length
      },
      pending_drafts: pending,
      approved_drafts: ((drafts && drafts.drafts) || []).filter(d => d.status === 'approved').length,
      approved_week_delta: 0,
      recent_leads: leads.slice(0, 3)
    }
  });
}

function hmRenderDashboardData(data) {
  if (data && data.profile_required) {
    const grid = document.querySelector('.leads-grid');
    document.querySelectorAll('.stat-card').forEach(card => card.classList.remove('hm-loading-card'));
    document.querySelectorAll('.stat-value').forEach(value => { value.textContent = '0'; });
    if (grid) grid.innerHTML = hmProfileRequiredCard();
    hmUpdateSidebarCounts((data.data && data.data.today_counts) || {});
    return;
  }
  const d = (data && data.data) || {};
  if (hmDashboardHasUsefulData(data)) hmWriteDashboardSnapshot(data);
  const grid = document.querySelector('.leads-grid');
  document.querySelectorAll('.stat-card').forEach(card => card.classList.remove('hm-loading-card'));
  const values = document.querySelectorAll('.stat-value');
  const counts = d.counts || {};
  const todayCounts = d.today_counts || counts;
  if (values[0]) values[0].textContent = todayCounts.total || 0;
  if (values[1]) values[1].textContent = todayCounts.hot || 0;
  if (values[2]) values[2].textContent = d.pending_drafts || 0;
  if (values[3]) values[3].textContent = d.approved_drafts || 0;
  const changes = document.querySelectorAll('.stat-change');
  if (changes[0]) changes[0].textContent = 'Today\'s new opportunities';
  if (changes[1]) changes[1].textContent = 'High priority today';
  if (changes[2]) changes[2].textContent = 'Awaiting your review';
  if (changes[3]) {
    const delta = Number(d.approved_week_delta || 0);
    changes[3].textContent = delta === 0
      ? 'Same as last week'
      : (delta > 0 ? '\u2191 ' + delta + ' more than last week' : '\u2193 ' + Math.abs(delta) + ' fewer than last week');
  }
  if (grid) {
    const leads = hmUniqueLeads(d.recent_leads || []);
    grid.innerHTML = leads.length
      ? leads.map(lead => hmLeadCard(lead, true)).join('')
      : '<div class="section-card empty-state"><strong>Recent leads will appear here.</strong><br>New opportunities will show after your next sync.</div>';
  }
}

function hmLeadIsToday(lead) {
  const raw = lead && (lead.created_at || lead.posted_at);
  if (!raw) return false;
  const dt = hmParseDate(raw);
  if (!dt) return false;
  const now = new Date();
  return dt.getFullYear() === now.getFullYear()
    && dt.getMonth() === now.getMonth()
    && dt.getDate() === now.getDate();
}

function hmGreeting(date) {
  const hour = (date || new Date()).getHours();
  if (hour >= 5 && hour < 12) return 'Good morning';
  if (hour >= 12 && hour < 17) return 'Good afternoon';
  if (hour >= 17 && hour < 21) return 'Good evening';
  return 'Good night';
}

async function hmLoadDraftsPage() {
  const list = document.querySelector('.drafts-list');
  if (!list || !document.title.includes('Drafts')) return;
  const path = '/api/drafts';
  const renderDrafts = data => {
    const type = localStorage.getItem('hm_draft_filter') || 'all';
    const drafts = ((data && data.drafts) || []).filter(d => type === 'all' || type === d.draft_type || type === d.status);
    list.innerHTML = drafts.map(d => `
      <div class="draft-item draft-item-pro" onclick="window.location.href=hmDraftUrl(${d.id})">
        <div class="draft-type-icon">${d.draft_type === 'message' ? '&#x2709;' : '&#x1F4AC;'}</div>
        <div class="draft-info">
          <div class="draft-kicker">${d.draft_type === 'message' ? 'Message draft' : 'Comment draft'}</div>
          <div class="draft-target">${hmEscape(d.company)} <span>/ ${hmEscape(d.role_title)}</span></div>
          <div class="draft-preview">${hmEscape(d.content).slice(0, 190)}${String(d.content || '').length > 190 ? '...' : ''}</div>
          <div class="draft-meta-row"><span class="badge ${d.status === 'approved' ? 'badge-approved' : 'badge-pending'}">${hmEscape(d.status)}</span><span>${hmTimeAgo(d.created_at)}</span></div>
        </div>
        <div class="draft-actions">
          <button class="btn btn-primary btn-sm" onclick="event.stopPropagation();window.location.href=hmDraftUrl(${d.id})">Review</button>
          <button class="btn btn-outline btn-sm" onclick="event.stopPropagation();navigator.clipboard.writeText(this.dataset.copy);showToast('success','Copied to clipboard!')" data-copy="${hmEscape(d.content)}">Copy</button>
          <button class="btn btn-danger btn-sm" onclick="event.stopPropagation();hmDeleteDraft(${d.id})">Delete</button>
        </div>
      </div>`).join('') || '<div class="section-card">Drafts will appear here after you generate them from a lead.</div>';
    const sub = document.querySelector('.page-sub'); if (sub) sub.textContent = drafts.length + ' drafts';
  };
  const cached = hmReadCache(path, 10 * 60 * 1000);
  if (cached) {
    renderDrafts(cached);
    hmFinishDataBoot();
  }
  try {
    const data = cached ? await hmRefreshCache(path, renderDrafts) : await hmCachedApi(path, 10 * 60 * 1000);
    if (!cached) renderDrafts(data);
  } catch (err) {} finally { hmFinishDataBoot(); }
}

function filterDrafts(type) {
  localStorage.setItem('hm_draft_filter', type || 'all');
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  const btn = document.querySelector('[data-draft-filter="' + (type || 'all') + '"]');
  if (btn) btn.classList.add('active');
  hmMarkSidebarDraftFilter(type || 'all');
  hmLoadDraftsPage();
}

async function hmDeleteDraft(id) {
  if (!id) return;
  showConfirm(
    '!',
    'Delete this draft?',
    'This will remove the draft from Drafts and from the lead detail page.',
    'Delete',
    'btn-danger',
    async function () {
      try {
        await hmApi('/api/drafts/' + encodeURIComponent(id), { method: 'DELETE' });
        showToast('success', 'Draft deleted.');
        hmLoadDraftsPage();
      } catch (err) {
        showToast('error', err.message);
      }
    }
  );
}

async function hmLoadAnalyticsPage() {
  if (!document.title.includes('Analytics') || !hmToken()) return;
  const path = '/api/analytics';
  const cached = hmReadCache(path, 10 * 60 * 1000);
  if (cached) {
    hmRenderAnalyticsData(cached);
    hmFinishDataBoot();
  }
  try {
    const data = cached ? await hmRefreshCache(path, hmRenderAnalyticsData) : await hmCachedApi(path, 10 * 60 * 1000);
    if (!cached) hmRenderAnalyticsData(data);
  } catch (err) {} finally { hmFinishDataBoot(); }
}

function hmRenderAnalyticsData(data) {
  const a = (data && data.data) || {};
  const values = document.querySelectorAll('.donut-card .donut-value');
  if (values[0]) values[0].textContent = a.leads_discovered || 0;
  if (values[1]) values[1].textContent = a.hot_leads || 0;
  if (values[2]) values[2].textContent = a.drafts_approved || 0;
  const labels = document.querySelectorAll('.donut-card .donut-note');
  if (labels[0]) labels[0].textContent = (a.post_leads || 0) + ' posts / ' + (a.job_leads || 0) + ' jobs';
  if (labels[1]) labels[1].textContent = (a.leads_discovered ? Math.round((a.hot_leads || 0) * 100 / a.leads_discovered) : 0) + '% of total';
  if (labels[2]) labels[2].textContent = (a.drafts_pending || 0) + ' pending drafts';
  hmRenderAnalyticsBars(a.daily || []);
  hmRenderAnalyticsSkills(a.top_skills || []);
  hmRenderDraftActivity(a);
}

function hmRenderAnalyticsBars(days) {
  const chart = document.querySelector('.bar-chart');
  if (!chart) return;
  const byDay = {};
  days.forEach(day => { byDay[day.day] = day; });
  const items = [];
  for (let i = 6; i >= 0; i--) {
    const d = new Date();
    d.setDate(d.getDate() - i);
    const key = d.toISOString().slice(0, 10);
    const label = d.toLocaleDateString(undefined, { weekday: 'short' });
    const row = byDay[key] || {};
    items.push({ label, hot: Number(row.hot || 0), warm: Number(row.warm || 0), cold: Number(row.cold || 0) });
  }
  const max = Math.max(1, ...items.flatMap(x => [x.hot, x.warm, x.cold]));
  chart.innerHTML = items.map(x => `
    <div class="bar-group"><div class="bar-wrapper">
      <div class="bar" style="height:${Math.max(8, x.hot / max * 110)}px;width:18px;background:var(--hot);"></div>
      <div class="bar" style="height:${Math.max(8, x.warm / max * 110)}px;width:18px;background:var(--warm);"></div>
      <div class="bar" style="height:${Math.max(8, x.cold / max * 110)}px;width:18px;background:var(--cold);"></div>
    </div><div class="bar-label">${x.label}</div></div>`).join('');
}

function hmRenderAnalyticsSkills(skills) {
  const cards = document.querySelectorAll('.chart-card');
  const box = cards[1] ? cards[1].querySelector('div[style*="flex-direction:column"]') : null;
  if (!box) return;
  const unique = [];
  const seen = new Set();
  (skills || []).forEach(item => {
    const skill = String(item.skill || '').trim();
    const key = skill.toLowerCase();
    if (skill && !seen.has(key)) {
      seen.add(key);
      unique.push({ skill, count: Number(item.count || 0) });
    }
  });
  if (!unique.length) {
    box.innerHTML = '<div class="empty-state" style="padding:14px;border:1px dashed var(--border);border-radius:10px;color:var(--text2);">Complete your profile skills to see matched strengths here.</div>';
    return;
  }
  const max = Math.max(1, ...unique.map(s => Number(s.count || 0)));
  box.innerHTML = unique.map(item => {
    const pct = Math.round((Number(item.count || 0) / max) * 100);
    return `<div><div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:4px;"><span>${hmEscape(item.skill)}</span><span style="color:var(--accent)">${pct}%</span></div><div class="progress-bar"><div class="progress-fill" style="width:${Math.max(8, pct)}%;background:var(--accent);"></div></div></div>`;
  }).join('');
}

function hmRenderDraftActivity(a) {
  const cards = document.querySelectorAll('.chart-card');
  const box = cards[2] ? cards[2].querySelector('div[style*="flex-direction:column"]') : null;
  if (!box) return;
  const rows = [
    [hmActivityIcon('message'), 'Messages Generated', a.drafts_messages || 0, 'var(--accent)'],
    [hmActivityIcon('comment'), 'Comments Generated', a.drafts_comments || 0, 'var(--cold)'],
    [hmActivityIcon('approved'), 'Approved', a.drafts_approved || 0, 'var(--warm)'],
    [hmActivityIcon('pending'), 'Pending Review', a.drafts_pending || 0, 'var(--hot)'],
  ];
  box.innerHTML = rows.map(row => `<div style="display:flex;align-items:center;justify-content:space-between;padding:12px 16px;background:var(--surface2);border-radius:10px;border:1px solid var(--border);"><span class="analytics-icon-row"><span class="analytics-icon-chip" style="color:${row[3]}">${row[0]}</span>${row[1]}</span><span style="font-family:'Syne',sans-serif;font-weight:700;font-size:18px;color:${row[3]}">${row[2]}</span></div>`).join('');
}

function hmActivityIcon(type) {
  const icons = {
    message: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16v12H4z"></path><path d="m4 7 8 6 8-6"></path></svg>',
    comment: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H9l-5 4v-4H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z"></path><path d="M8 10h8"></path><path d="M8 13h5"></path></svg>',
    approved: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="4"></rect><path d="m8 12.5 2.8 2.8L16.5 9"></path></svg>',
    pending: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8"></circle><path d="M12 8v5l3 2"></path></svg>'
  };
  return icons[type] || icons.pending;
}
async function hmImportSamplePosts() {
  try {
    const data = await hmApi('/api/linkedin/import-sample', { method: 'POST', body: '{}' });
    showToast('success', 'Imported ' + data.imported + ' LinkedIn-style posts.');
    hmLoadLeadStream({ reset: true }); hmLoadDashboardPage();
  } catch (err) { showToast('error', err.message); }
}

async function hmSyncLinkedIn() {
  const btn = document.getElementById('hm-sync-linkedin');
  const original = btn ? btn.innerHTML : '';
  if (btn) { btn.disabled = true; btn.innerHTML = hmInlineIcon('search') + '<span>Finding...</span>'; }
  try {
    const data = await hmApi('/api/linkedin/sync', { method: 'POST', body: '{}' });
    const checked = Number(data.checked_post_count || 0) + Number(data.checked_job_count || 0);
    const pages = Number(data.pages_scanned || 1);
    const detail = 'New posts: ' + (data.post_count || 0) + ', new jobs: ' + (data.job_count || 0);
    if (Number(data.imported || 0) === 0 && checked === 0) {
      showToast('info', 'This scan is complete. HireMate will continue with the next profile keywords.');
    } else if (Number(data.imported || 0) === 0 && checked > 0) {
      showToast('info', 'Scanned ' + checked + ' LinkedIn results across ' + pages + ' page(s); all were already saved, so the next scan will continue lower.');
    } else {
      showToast('success', 'Found ' + data.imported + ' new opportunities after scanning ' + pages + ' page(s). ' + detail);
    }
    hmShowAllLeadsView();
    hmPrependNewLeads(data.leads || []);
    if (!((data.leads || []).length)) await hmLoadLeadStream({ reset: true, background: true });
    await hmLoadSidebarCounts();
    await hmLoadSavedLeadsPanel();
    await hmLoadDashboardPage();
    await hmLoadSyncStatus();
  } catch (err) {
    showToast('error', err.message);
  } finally {
    if (btn) { btn.disabled = false; btn.innerHTML = original || (hmInlineIcon('search') + '<span>Find Opportunities</span>'); }
  }
}

async function hmCollectLinkedInPosts() {
  const btn = document.getElementById('hm-collect-posts');
  const original = btn ? btn.innerHTML : '';
  if (btn) { btn.disabled = true; btn.innerHTML = hmInlineIcon('posts') + '<span>Collecting...</span>'; }
  try {
    const batches = [];
    let totalImported = 0;
    let totalChecked = 0;
    let lastData = null;
    for (let batch = 1; batch <= 3; batch += 1) {
      if (btn) btn.innerHTML = hmInlineIcon('posts') + '<span>' + (batch === 1 ? 'Collecting...' : 'Checking next keywords...') + '</span>';
      const data = await hmApi('/api/linkedin/sync-posts', { method: 'POST', body: '{}' });
      lastData = data;
      batches.push(data);
      totalImported += Number(data.imported || 0);
      totalChecked += Number(data.checked_post_count || 0);
      if (Number(data.imported || 0) > 0) {
        hmPrependNewLeads(data.leads || []);
        await hmLoadSidebarCounts();
      }
      if (Number(data.imported || 0) > 0 || batch === 3) break;
      await new Promise(resolve => setTimeout(resolve, 1200));
    }
    let data = lastData || {};
    if (totalImported === 0 && totalChecked === 0) {
      const hint = hmPostSyncHint(data);
      showToast('warning', hint);
    } else if (totalImported > 0) {
      const used = batches.flatMap(item => item.keywords_used || []).slice(0, 6);
      const keywordText = used.length ? ' Keywords: ' + used.map(hmShortKeyword).join(', ') : '';
      showToast('success', 'Collected ' + totalImported + ' new LinkedIn post lead(s).' + keywordText);
    } else {
      showToast('info', 'Read ' + totalChecked + ' LinkedIn post result(s), but all were already saved.');
    }
    hmShowAllLeadsView();
    hmPrependNewLeads(batches.flatMap(item => item.leads || []));
    if (!totalImported) await hmLoadLeadStream({ reset: true, background: true });
    await hmLoadSidebarCounts();
    await hmLoadDashboardPage();
    await hmLoadSyncStatus();
  } catch (err) {
    showToast('error', err.message);
  } finally {
    if (btn) { btn.disabled = false; btn.innerHTML = original || (hmInlineIcon('posts') + '<span>Collect Posts</span>'); }
  }
}

function hmShortKeyword(value) {
  return String(value || '').replace(/^site:linkedin\.com\/(?:posts|feed\/update)\s*/i, '').replace(/"/g, '').slice(0, 42);
}

function hmPostSyncHint(data) {
  const errors = data && Array.isArray(data.errors) ? data.errors : [];
  const raw = errors.join(' | ').toLowerCase();
  if (raw.includes('0 readable posts') || raw.includes('0 readable post')) {
    return 'LinkedIn did not expose readable post HTML for this search. Try another keyword in your profile skills/interests, or collect from a visible LinkedIn posts page.';
  }
  if (raw.includes('logged-out') || raw.includes('fresh full cookie')) {
    return 'LinkedIn needs a fresh connection. Update your LinkedIn session cookie, then try collecting posts again.';
  }
  if (raw.includes('checkpoint') || raw.includes('captcha') || raw.includes('rate-limit')) {
    return 'LinkedIn slowed or blocked the post request. Wait a little before trying again.';
  }
  return errors[0] || 'This scan is complete. HireMate will continue with your current profile filters.';
}

async function hmLoadSyncStatus() {
  if (!hmToken()) return;
  const path = '/api/linkedin/sync-status';
  const renderStatus = data => {
    const status = (data && data.status) || {};
    const btn = document.getElementById('hm-sync-linkedin');
    if (btn && status.last_sync_at) {
      btn.title = 'Last sync: ' + status.last_sync_at + ' | Posts: ' + (status.post_count || 0) + ' | Jobs: ' + (status.job_count || 0);
    }
    const pill = document.getElementById('hm-sync-status-pill');
    if (pill) {
      const when = status.last_sync_at ? hmTimeAgo(status.last_sync_at) : 'waiting';
      const added = Number(status.imported || 0);
      pill.textContent = status.last_sync_at
        ? (added > 0 ? 'Updated ' + when + ' · ' + added + ' new' : 'Updated ' + when)
        : 'Ready to check';
      pill.title = 'HireMate checks LinkedIn quietly and adds new leads when it finds them.';
    }
  };
  const cached = hmReadCache(path, 2 * 60 * 1000);
  if (cached) renderStatus(cached);
  try {
    const data = cached ? await hmRefreshCache(path, renderStatus) : await hmCachedApi(path, 2 * 60 * 1000);
    if (!cached) renderStatus(data);
  } catch (err) {}
}

function hmSyncAgeMinutes(iso) {
  if (!iso) return Infinity;
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return Infinity;
  return Math.floor((Date.now() - dt.getTime()) / 60000);
}

async function hmMaybeAutoSyncLinkedIn() {
  if (!hmToken()) return;
  const isLivePage = ['Dashboard', 'Leads', 'Drafts', 'Analytics', 'Profile', 'Settings'].some(name => document.title.includes(name));
  if (!isLivePage) return;
  const throttleKey = 'hm_last_auto_sync_attempt';
  const lastAttempt = Number(localStorage.getItem(throttleKey) || 0);
  if (Date.now() - lastAttempt < 15 * 60 * 1000) return;
  try {
    const statusData = await hmApi('/api/linkedin/sync-status');
    const status = statusData.status || {};
    if (hmSyncAgeMinutes(status.last_sync_at) < 20) return;
    localStorage.setItem(throttleKey, String(Date.now()));
    const pill = document.getElementById('hm-sync-status-pill');
    if (pill) pill.textContent = 'Finding new leads...';
    const syncData = await hmApi('/api/linkedin/sync', { method: 'POST', body: '{}' });
    hmPrependNewLeads(syncData.leads || []);
    await hmLoadSyncStatus();
    await hmLoadDashboardPage();
    await hmLoadAnalyticsPage();
    await hmLoadProfilePage();
  } catch (err) {
    const pill = document.getElementById('hm-sync-status-pill');
    if (pill) pill.textContent = 'Waiting for LinkedIn';
  }
}

async function hmMaybeAutoSyncPublicPosts() {
  if (!hmToken()) return;
  const isLivePage = ['Dashboard', 'Leads', 'Drafts', 'Analytics', 'Profile', 'Settings'].some(name => document.title.includes(name));
  if (!isLivePage) return;
  const throttleKey = 'hm_last_auto_public_post_sync_attempt';
  const lastAttempt = Number(localStorage.getItem(throttleKey) || 0);
  if (Date.now() - lastAttempt < 60 * 60 * 1000) return;
  try {
    localStorage.setItem(throttleKey, String(Date.now()));
    const pill = document.getElementById('hm-sync-status-pill');
    if (pill) pill.textContent = 'Checking posts...';
    const syncData = await hmApi('/api/linkedin/sync-posts', { method: 'POST', body: '{}' });
    hmPrependNewLeads(syncData.leads || []);
    await hmLoadSyncStatus();
    await hmLoadDashboardPage();
    await hmLoadAnalyticsPage();
  } catch (err) {
    const pill = document.getElementById('hm-sync-status-pill');
    if (pill) pill.textContent = 'Waiting for LinkedIn';
  }
}

function hmStartLiveRefresh() {
  const isLivePage = ['Dashboard', 'Leads', 'Drafts', 'Analytics', 'Profile', 'Settings'].some(name => document.title.includes(name));
  if (!isLivePage || !hmToken()) return;
  setTimeout(hmMaybeAutoSyncLinkedIn, 30000);
  setTimeout(hmMaybeAutoSyncPublicPosts, 90000);
  setInterval(function () {
    hmLoadDashboardPage();
    hmLoadAnalyticsPage();
    hmLoadSavedLeadsPanel();
    hmLoadSyncStatus();
    hmMaybeAutoSyncLinkedIn();
    hmMaybeAutoSyncPublicPosts();
  }, 180000);
  setInterval(hmLoadSidebarCounts, 120000);
}

async function hmSaveLinkedInCookie(cookieValue) {
  let val = String(cookieValue || '').trim();
  if (!val) throw new Error('LinkedIn session cookie is required');
  if (!val.includes('li_at=') && !val.includes('=') && val.length >= 20) val = 'li_at=' + val;
  if (!val.includes('li_at=')) throw new Error('Please paste a valid LinkedIn session cookie value.');
  const data = await hmApi('/api/linkedin/cookie', {
    method: 'POST',
    body: JSON.stringify({ linkedin_cookie: val })
  });
  if (data.user) {
    localStorage.setItem('hm_user', JSON.stringify(data.user));
    hmApplyNavAvatar(data.user);
  }
  return data;
}

async function hmSyncAfterCookieSave() {
  const data = await hmApi('/api/linkedin/sync', { method: 'POST', body: '{}' });
  const posts = Number(data.post_count || 0);
  const jobs = Number(data.job_count || 0);
  if (posts > 0) {
    showToast('success', 'LinkedIn session cookie saved. Found ' + posts + ' post leads and ' + jobs + ' job leads.');
  } else if (jobs > 0) {
    showToast('warning', 'LinkedIn session cookie saved. Posts were limited, so HireMate found ' + jobs + ' job leads.');
  } else {
    showToast('warning', 'LinkedIn session cookie saved. HireMate will keep looking for matching leads.');
  }
  return data;
}

function filterLeads(type) {
  document.querySelectorAll('.filter-row .filter-btn').forEach(b => b.classList.remove('active'));
  const btn = document.getElementById('filter-' + type);
  if (btn) btn.classList.add('active');
  hmLeadsState.filter = type || 'all';
  localStorage.setItem('hm_lead_filter', type || 'all');
  hmMarkSidebarLeadFilter(type || 'all');
  hmLoadLeadStream({ reset: true });
}

function filterLeadKind(kind) {
  const value = ['job', 'post'].includes(kind) ? kind : 'all';
  const select = document.getElementById('lead-kind-filter');
  if (select) select.value = value;
  hmLeadsState.kind = value;
  localStorage.setItem('hm_lead_kind', value);
  hmLoadLeadStream({ reset: true });
}

function hmHandleLeadSearch(value) {
  clearTimeout(window.hmLeadSearchTimer);
  window.hmLeadSearchTimer = setTimeout(function () {
    hmLeadsState.search = String(value || '').trim();
    hmLoadLeadStream({ reset: true, force: true });
  }, 260);
}

function hmGoLeadFilter(type) {
  localStorage.setItem('hm_lead_filter', type || 'all');
  if (document.title.includes('Leads')) {
    filterLeads(type || 'all');
    return;
  }
  window.location.href = 'leads.html';
}

function hmGoSavedLeads() {
  localStorage.setItem('hm_lead_status', 'saved');
  window.location.href = 'saved-leads.html';
}

function hmClearSidebarActive() {
  document.querySelectorAll('.sidebar .sidebar-item').forEach(btn => btn.classList.remove('active'));
}

function hmMarkSidebarLeadFilter(type) {
  hmClearSidebarActive();
  if (!['hot', 'warm', 'cold'].includes(type)) return;
  document.querySelectorAll('.sidebar .sidebar-item').forEach(btn => {
    const text = (btn.textContent || '').toLowerCase();
    if (text.includes(type + ' leads')) btn.classList.add('active');
  });
}

function hmMarkSidebarDraftFilter(type) {
  hmClearSidebarActive();
  const label = type === 'message' ? 'message drafts' : type === 'comment' ? 'comment drafts' : '';
  if (!label) return;
  document.querySelectorAll('.sidebar .sidebar-item').forEach(btn => {
    if ((btn.textContent || '').toLowerCase().includes(label)) btn.classList.add('active');
  });
}

function hmSetupLeadInfiniteScroll() {
  if (!document.title.includes('Leads')) return;
  let ticking = false;
  window.addEventListener('scroll', function () {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(function () {
      ticking = false;
      const remaining = document.documentElement.scrollHeight - window.innerHeight - window.scrollY;
      if (remaining < 520) hmLoadLeadStream({ reset: false });
    });
  }, { passive: true });
}

document.addEventListener('DOMContentLoaded', function () {
  hmRequireAuthForAppPages();
  hmApplyNavAvatar();
  hmSetupSidebarFilters();
  hmUpdateSidebarCounts({});
  hmAddLinkedInSyncButton();
  hmFinishDataBoot();
  if (!hmToken() || !hmIsAppPage()) return;
  if (hmPageIs('Dashboard')) {
    hmRenderDashboardInstant();
    setTimeout(hmLoadDashboardPage, 900);
  }
  if (hmPageIs('Saved Leads')) {
    hmLoadSavedLeadsPage();
  } else if (hmPageIs('Leads')) {
    hmSetupLeadInfiniteScroll();
    hmLoadLeadStream({ reset: true });
  }
  if (hmPageIs('Drafts')) hmLoadDraftsPage();
  if (hmPageIs('Analytics')) hmLoadAnalyticsPage();
  if (hmPageIs('Profile')) {
    hmLoadProfilePage();
    setTimeout(hmLoadProfileCookieStatus, 900);
  }
  setTimeout(hmLoadSidebarCounts, 2200);
  setTimeout(hmLoadSyncStatus, 3000);
  setTimeout(hmStartLiveRefresh, 5000);
  if (hmPageIs('Dashboard') || hmPageIs('Leads')) setTimeout(hmLoadSavedLeadsPanel, 4200);
  setTimeout(hmFinishDataBoot, 3500);
});

function hmAddLinkedInSyncButton() {
  if (!hmToken()) return;
  const isProtected = ['Dashboard', 'Leads'].some(name => document.title.includes(name));
  if (!isProtected || document.getElementById('hm-sync-status-pill')) return;
  const panel = hmDiscoveryPanel();
  if (!panel) return;
  const btn = document.createElement('button');
  btn.id = 'hm-sync-linkedin';
  btn.className = 'btn btn-primary btn-sm discovery-btn';
  btn.innerHTML = hmInlineIcon('search') + '<span>Find Opportunities</span>';
  btn.onclick = hmSyncLinkedIn;
  panel.appendChild(btn);
  const postBtn = document.createElement('button');
  postBtn.id = 'hm-collect-posts';
  postBtn.className = 'btn btn-outline btn-sm discovery-btn';
  postBtn.innerHTML = hmInlineIcon('posts') + '<span>Collect Posts</span>';
  postBtn.onclick = hmCollectLinkedInPosts;
  panel.appendChild(postBtn);
  const pill = document.createElement('span');
  pill.id = 'hm-sync-status-pill';
  pill.className = 'sync-status-pill';
  pill.textContent = 'Looking for leads...';
  panel.appendChild(pill);
  if (document.title.includes('Leads')) hmAddSessionCookieHint(panel);
}

function hmAddSessionCookieHint(panel) {
  const host = panel && panel.parentElement ? panel.parentElement : panel;
  if (!host || document.getElementById('hm-session-cookie-hint')) return;
  const hint = document.createElement('div');
  hint.id = 'hm-session-cookie-hint';
  hint.className = 'session-cookie-hint';
  hint.innerHTML = "<span class=\"session-cookie-hint-icon\">" + hmProfileIcon('link') + "</span><span><strong>Tip:</strong> Add your encrypted LinkedIn session cookie, then use <strong>Collect Posts</strong> to find more relevant posts.</span><button type=\"button\" onclick=\"window.location.href='settings.html'\">Open Settings</button>";
  host.appendChild(hint);
}

function hmDiscoveryPanel() {
  const main = document.querySelector('.main-content');
  if (!main) return null;

  if (document.title.includes('Dashboard')) {
    const header = document.querySelector('.leads-header');
    if (!header) return null;
    const viewAll = header.querySelector('button[onclick*="leads.html"]');
    const group = document.createElement('div');
    group.className = 'dashboard-header-actions';
    const actions = document.createElement('div');
    actions.className = 'discovery-buttons dashboard-discovery-buttons';
    if (viewAll) {
      header.insertBefore(group, viewAll);
      group.appendChild(viewAll);
    } else {
      header.appendChild(group);
    }
    group.appendChild(actions);
    return actions;
  }

  if (!document.title.includes('Leads')) return null;
  const panel = document.createElement('div');
  panel.className = 'discovery-actions';
  const text = document.createElement('div');
  text.className = 'discovery-copy';
  text.innerHTML = '<strong>Opportunity discovery</strong><span>Search fresh jobs and hiring posts using your profile keywords.</span>';
  panel.appendChild(text);
  const actions = document.createElement('div');
  actions.className = 'discovery-buttons';
  panel.appendChild(actions);
  const header = document.querySelector('.leads-header');
  if (header && header.parentNode) header.insertAdjacentElement('afterend', panel);
  return actions;
}

function hmInlineIcon(type) {
  if (type === 'posts') return '<svg class="btn-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5h14v14H5z"></path><path d="M8 9h8"></path><path d="M8 13h6"></path><path d="M8 17h4"></path></svg>';
  return '<svg class="btn-icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"></circle><path d="M15.5 15.5 21 21"></path><path d="M10.5 7.5v6"></path><path d="M7.5 10.5h6"></path></svg>';
}

function hmProfileIcon(type, className) {
  const cls = className || 'btn-icon';
  const icons = {
    edit: '<path d="M4 20h4l10.5-10.5a2.1 2.1 0 0 0-3-3L5 17v3Z"></path><path d="M14 7l3 3"></path>',
    camera: '<path d="M4 8h3l1.5-2h7L17 8h3v11H4V8Z"></path><circle cx="12" cy="13.5" r="3.5"></circle>',
    note: '<path d="M6 4h9l3 3v13H6V4Z"></path><path d="M14 4v4h4"></path><path d="M8.5 12h7"></path><path d="M8.5 16h5"></path>',
    skills: '<path d="M12 3v4"></path><path d="M12 17v4"></path><path d="M4.2 7.5l3.4 2"></path><path d="M16.4 14.5l3.4 2"></path><path d="M19.8 7.5l-3.4 2"></path><path d="M7.6 14.5l-3.4 2"></path><circle cx="12" cy="12" r="4"></circle>',
    star: '<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3 6.4 20.2 7.5 14 3 9.6l6.2-.9L12 3Z"></path>',
    briefcase: '<path d="M10 6V5a2 2 0 0 1 2-2h0a2 2 0 0 1 2 2v1"></path><rect x="4" y="6" width="16" height="14" rx="2"></rect><path d="M4 12h16"></path>',
    education: '<path d="m3 8 9-4 9 4-9 4-9-4Z"></path><path d="M7 10.5V15c2.8 2 7.2 2 10 0v-4.5"></path>',
    link: '<path d="M10 13a5 5 0 0 0 7.1 0l2-2a5 5 0 0 0-7.1-7.1l-1.1 1.1"></path><path d="M14 11a5 5 0 0 0-7.1 0l-2 2A5 5 0 0 0 12 20.1l1.1-1.1"></path>',
    location: '<path d="M12 21s7-5.2 7-11a7 7 0 0 0-14 0c0 5.8 7 11 7 11Z"></path><circle cx="12" cy="10" r="2.5"></circle>',
    check: '<circle cx="12" cy="12" r="9"></circle><path d="m8 12 2.5 2.5L16 9"></path>',
    alert: '<path d="M12 3 2.8 20h18.4L12 3Z"></path><path d="M12 9v5"></path><path d="M12 17h.01"></path>',
    eye: '<path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z"></path><circle cx="12" cy="12" r="3"></circle>',
    warm: '<circle cx="12" cy="12" r="7"></circle><path d="M12 2v2"></path><path d="M12 20v2"></path><path d="M4.9 4.9l1.4 1.4"></path><path d="M17.7 17.7l1.4 1.4"></path><path d="M2 12h2"></path><path d="M20 12h2"></path><path d="M4.9 19.1l1.4-1.4"></path><path d="M17.7 6.3l1.4-1.4"></path>',
    cold: '<path d="M12 2v20"></path><path d="m5 5 14 14"></path><path d="M5 19 19 5"></path><path d="M2 12h20"></path>',
    mail: '<rect x="4" y="5" width="16" height="14" rx="2"></rect><path d="m4 7 8 6 8-6"></path>',
    settings: '<path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z"></path><path d="M19.4 15a1.8 1.8 0 0 0 .4 2l.1.1-2 3.4-.2-.1a1.8 1.8 0 0 0-2 .4l-.2.2h-4l-.2-.2a1.8 1.8 0 0 0-2-.4l-.2.1-2-3.4.1-.1a1.8 1.8 0 0 0 .4-2l-.1-.3-2.9-1.7V9l2.9-1.7.1-.3a1.8 1.8 0 0 0-.4-2l-.1-.1 2-3.4.2.1a1.8 1.8 0 0 0 2-.4l.2-.2h4l.2.2a1.8 1.8 0 0 0 2 .4l.2-.1 2 3.4-.1.1a1.8 1.8 0 0 0-.4 2l.1.3L22 9v4l-2.5 1.7-.1.3Z"></path>'
  };
  return '<svg class="' + cls + '" viewBox="0 0 24 24" aria-hidden="true">' + (icons[type] || icons.edit) + '</svg>';
}

function hmSetupSidebarFilters() {
  document.querySelectorAll('.sidebar-item').forEach(btn => {
    const text = (btn.textContent || '').toLowerCase();
    let type = '';
    if (text.includes('hot leads')) type = 'hot';
    if (text.includes('warm leads')) type = 'warm';
    if (text.includes('cold leads')) type = 'cold';
    if (type) {
      btn.setAttribute('data-lead-filter', type);
      btn.addEventListener('click', function (event) {
        event.preventDefault();
        event.stopImmediatePropagation();
        hmGoLeadFilter(type);
      }, true);
    }
    if (text.includes('message drafts')) {
      btn.addEventListener('click', function (event) {
        event.preventDefault();
        event.stopImmediatePropagation();
        localStorage.setItem('hm_draft_filter', 'message');
        window.location.href = 'drafts.html';
      }, true);
    }
    if (text.includes('comment drafts')) {
      btn.addEventListener('click', function (event) {
        event.preventDefault();
        event.stopImmediatePropagation();
        localStorage.setItem('hm_draft_filter', 'comment');
        window.location.href = 'drafts.html';
      }, true);
    }
    if (text.includes('saved leads')) {
      btn.addEventListener('click', function (event) {
        event.preventDefault();
        event.stopImmediatePropagation();
        hmGoSavedLeads();
      }, true);
    }
  });
  if (document.title.includes('Leads')) {
    const stored = localStorage.getItem('hm_lead_filter');
    if (stored) {
      localStorage.removeItem('hm_lead_filter');
      hmLeadsState.filter = stored;
      document.querySelectorAll('.filter-row .filter-btn').forEach(b => b.classList.remove('active'));
      const active = document.getElementById('filter-' + stored);
      if (active) active.classList.add('active');
    }
    hmMarkSidebarLeadFilter(hmLeadsState.filter || 'all');
    const storedKind = localStorage.getItem('hm_lead_kind') || 'all';
    hmLeadsState.kind = ['job', 'post'].includes(storedKind) ? storedKind : 'all';
    const kindSelect = document.getElementById('lead-kind-filter');
    if (kindSelect) kindSelect.value = hmLeadsState.kind;
    const searchInput = document.getElementById('lead-search-input');
    if (searchInput) hmLeadsState.search = searchInput.value.trim();
  }
  if (document.title.includes('Saved Leads')) {
    hmLeadsState.status = 'saved';
  }
  if (document.title.includes('Drafts')) {
    const storedDraft = localStorage.getItem('hm_draft_filter') || 'all';
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    const activeDraft = document.querySelector('[data-draft-filter="' + storedDraft + '"]');
    if (activeDraft) activeDraft.classList.add('active');
    hmMarkSidebarDraftFilter(storedDraft);
  }
}

function hmUpdateSidebarCounts(counts) {
  document.querySelectorAll('.sidebar-item').forEach(btn => {
    const text = (btn.textContent || '').toLowerCase();
    let value = null;
    if (text.includes('hot leads')) value = counts.hot || 0;
    if (text.includes('warm leads')) value = counts.warm || 0;
    if (text.includes('cold leads')) value = counts.cold || 0;
    if (text.includes('saved leads')) value = counts.saved || 0;
    if (value === null) return;
    let badge = btn.querySelector('.sidebar-badge');
    if (value <= 0) {
      if (badge) badge.remove();
      return;
    }
    if (!badge) {
      badge = document.createElement('span');
      badge.className = 'sidebar-badge';
      btn.appendChild(badge);
    }
    badge.textContent = value;
  });
}

function hmRequireAuthForAppPages() {
  const protectedTitles = ['Dashboard', 'Leads', 'Drafts', 'Analytics', 'Profile', 'Settings'];
  const isProtected = protectedTitles.some(name => document.title.includes(name));
  if (isProtected && !hmToken()) {
    showToast('warning', 'Please sign in first so HireMate can load your data.');
    setTimeout(() => { window.location.href = 'login.html'; }, 900);
  }
}

async function hmLoadProfilePage() {
  if (!document.title.includes('Profile') || !hmToken()) return;
  const cached = hmReadCache('/api/me', 10 * 60 * 1000);
  if (cached && cached.user) {
    hmRenderProfile(cached.user);
    hmFinishDataBoot();
  }
  try {
    const data = cached ? await hmRefreshCache('/api/me') : await hmCachedApi('/api/me', 10 * 60 * 1000);
    const user = data.user || {};
    hmRenderProfile(user);
  } catch (err) {} finally { hmFinishDataBoot(); }
}

function hmRenderProfile(user) {
    localStorage.setItem('hm_user', JSON.stringify(user));
    hmApplyNavAvatar(user);
    const fullName = [user.first_name, user.last_name].filter(Boolean).join(' ');
    const nameEl = document.querySelector('.profile-name');
    const headlineEl = document.querySelector('.profile-headline');
    const locationEl = document.querySelector('.profile-location');
    const aboutEl = document.getElementById('about-view');
    if (nameEl) nameEl.textContent = fullName || 'Add your name';
    if (headlineEl) headlineEl.textContent = user.headline || 'Add a headline';
    if (locationEl) locationEl.innerHTML = user.location ? hmProfileIcon('location') + ' ' + hmEscape(user.location) : '<span class="profile-empty-hint">Add your location</span>';
    if (aboutEl) aboutEl.innerHTML = user.about
      ? '<p style="font-size:15px;color:var(--text2);line-height:1.75;">' + hmEscape(user.about).replace(/\n/g, '<br>') + '</p>'
      : '<div class="profile-empty-hint">Add a short about section so HireMate can understand your background.</div>';
    const aboutText = document.getElementById('about-text');
    if (aboutText) aboutText.value = user.about || '';
    hmRenderProfileImages(user);
    hmRenderTags('skills-container', user.skills, 'skill-tag');
    hmRenderTags('interests-container', user.interests, 'interest-tag');
    hmRenderProfileLongField('experience-card', user.experience_detail, 'No experience added yet. Add projects, internships, freelance work, or academic work.', hmProfileIcon('briefcase'));
    hmRenderProfileLongField('education-card', user.education, 'No education added yet. Add your degree, university, and dates.', hmProfileIcon('education'));
}

function toggleEdit(section) {
  const view = document.getElementById(section + '-view');
  const edit = document.getElementById(section + '-edit');
  if (!view || !edit) return;
  const open = edit.style.display !== 'none';
  view.style.display = open ? 'block' : 'none';
  edit.style.display = open ? 'none' : 'block';
}

function hmRenderTags(id, csv, className) {
  const container = document.getElementById(id);
  if (!container) return;
  const values = String(csv || '').split(',').map(v => v.trim()).filter(Boolean);
  if (!values.length) {
    container.innerHTML = '<div class="profile-empty-hint">' + (id === 'skills-container' ? 'No skills added yet.' : 'No interests added yet.') + '</div>';
    return;
  }
  const removeAction = id === 'skills-container' ? 'removeSkill(this)' : 'removeInterest(this)';
  container.innerHTML = values.map(v => (
    `<div class="${className}">${hmEscape(v)} <button onclick="${removeAction}">&#xD7;</button></div>`
  )).join('');
}

function hmRenderProfileLongField(cardId, text, emptyText, icon) {
  const card = document.getElementById(cardId);
  if (!card) return;
  card.querySelectorAll('.exp-item').forEach(item => item.remove());
  const item = document.createElement('div');
  item.className = 'exp-item';
  item.innerHTML = '<div class="exp-icon">' + (icon || hmProfileIcon('briefcase')) + '</div><div style="flex:1;"><div class="exp-desc ' + (!text ? 'profile-empty-hint' : '') + '">' + hmEscape(text || emptyText).replace(/\n/g, '<br>') + '</div></div>';
  card.appendChild(item);
}

function hmRenderProfileImages(user) {
  const account = user || {};
  const avatar = document.querySelector('.profile-avatar-xl');
  const cover = document.querySelector('.profile-cover');
  const initials = hmUserInitials(account);
  if (avatar) {
    avatar.textContent = account.avatar_image ? '' : initials;
    avatar.style.backgroundImage = account.avatar_image ? 'url("' + account.avatar_image + '")' : '';
    avatar.style.backgroundSize = 'cover';
    avatar.style.backgroundPosition = 'center';
  }
  hmApplyNavAvatar(account);
  if (cover) {
    cover.style.backgroundImage = account.cover_image ? 'url("' + account.cover_image + '")' : '';
    cover.style.backgroundSize = 'cover';
    cover.style.backgroundPosition = 'center';
  }
}

function hmCollectProfilePatch(extra) {
  const user = hmCurrentUser();
  const name = (document.querySelector('.profile-name')?.textContent || '').trim();
  const parts = name.split(/\s+/).filter(Boolean);
  return Object.assign({
    first_name: parts[0] || user.first_name || '',
    last_name: parts.slice(1).join(' ') || user.last_name || '',
    headline: user.headline || '',
    location: user.location || '',
    about: user.about || '',
    skills: user.skills || '',
    interests: user.interests || '',
    target_roles: user.target_roles || '',
    preferred_locations: user.preferred_locations || '',
    work_modes: user.work_modes || '',
    experience_level: user.experience_level || '',
    education: user.education || '',
    experience_detail: user.experience_detail || '',
    avatar_image: user.avatar_image || '',
    cover_image: user.cover_image || ''
  }, extra || {});
}

function hmTagsToCsv(id) {
  const container = document.getElementById(id);
  if (!container) return '';
  return Array.from(container.children)
    .filter(el => !el.classList.contains('profile-empty-hint'))
    .map(el => (el.childNodes[0]?.textContent || el.textContent || '').replace('×', '').replace('&times;', '').trim())
    .filter(Boolean)
    .join(', ');
}

async function hmSaveProfilePatch(extra, message) {
  const data = await hmApi('/api/profile', { method: 'PATCH', body: JSON.stringify(hmCollectProfilePatch(extra)) });
  if (data.user) {
    localStorage.setItem('hm_user', JSON.stringify(data.user));
    hmApplyNavAvatar(data.user);
  }
  if (message) showToast('success', message);
  return data.user || {};
}

async function saveProfile() {
  const full = (document.getElementById('ep-name')?.value || '').trim();
  const parts = full.split(/\s+/).filter(Boolean);
  try {
    const user = await hmSaveProfilePatch({
      first_name: parts[0] || '',
      last_name: parts.slice(1).join(' '),
      headline: document.getElementById('ep-headline')?.value.trim() || '',
      location: document.getElementById('ep-location')?.value.trim() || ''
    }, 'Profile saved.');
    if (user.first_name || user.last_name) document.querySelector('.profile-name').textContent = [user.first_name, user.last_name].filter(Boolean).join(' ');
    if (user.headline) document.querySelector('.profile-headline').textContent = user.headline;
    if (user.location) document.querySelector('.profile-location').innerHTML = hmProfileIcon('location') + ' ' + hmEscape(user.location);
    hmRenderProfileImages(user);
    if (typeof closeModal === 'function') closeModal();
  } catch (err) { showToast('error', err.message); }
}

function showEditProfileModal() {
  const user = hmCurrentUser();
  const fullName = [user.first_name, user.last_name].filter(Boolean).join(' ');
  document.getElementById('modal-content').innerHTML =
    '<div class="modal-title">Edit Profile</div>' +
    '<div class="modal-sub">Update the details shown on your profile.</div>' +
    '<div style="display:flex;flex-direction:column;gap:14px;margin-bottom:20px;">' +
    '<input id="ep-name" class="form-input" placeholder="Full name" value="' + hmEscape(fullName) + '">' +
    '<input id="ep-headline" class="form-input" placeholder="Headline" value="' + hmEscape(user.headline || '') + '">' +
    '<input id="ep-location" class="form-input" placeholder="Location" value="' + hmEscape(user.location || '') + '">' +
    '</div>' +
    '<div style="display:flex;gap:10px;">' +
    '<button class="btn btn-ghost" style="flex:1;" onclick="closeModal()">Cancel</button>' +
    '<button class="btn btn-primary" style="flex:1;" onclick="saveProfile()">Save</button>' +
    '</div>';
  document.getElementById('modal').classList.add('open');
}

function hmOpenTagModal(type) {
  const isSkills = type === 'skills';
  const title = isSkills ? 'Edit Skills' : 'Edit Interests';
  const current = hmTagsToCsv(isSkills ? 'skills-container' : 'interests-container');
  document.getElementById('modal-content').innerHTML =
    '<div class="modal-title">' + title + '</div>' +
    '<div class="modal-sub">Write comma-separated values. Example: Python, NLP, React</div>' +
    '<textarea id="tag-modal-input" class="form-textarea" style="min-height:140px;">' + hmEscape(current) + '</textarea>' +
    '<div style="display:flex;gap:10px;margin-top:16px;">' +
    '<button class="btn btn-ghost" style="flex:1;" onclick="closeModal()">Cancel</button>' +
    '<button class="btn btn-primary" style="flex:1;" onclick="hmSaveTagModal(\'' + type + '\')">Save</button>' +
    '</div>';
  document.getElementById('modal').classList.add('open');
}

async function hmSaveTagModal(type) {
  const value = document.getElementById('tag-modal-input')?.value || '';
  try {
    const user = await hmSaveProfilePatch(type === 'skills' ? { skills: value } : { interests: value }, type === 'skills' ? 'Skills saved.' : 'Interests saved.');
    hmRenderTags(type === 'skills' ? 'skills-container' : 'interests-container', type === 'skills' ? user.skills : user.interests, type === 'skills' ? 'skill-tag' : 'interest-tag');
    closeModal();
  } catch (err) { showToast('error', err.message); }
}

async function saveAbout() {
  const text = document.getElementById('about-text')?.value.trim() || '';
  try {
    await hmSaveProfilePatch({ about: text }, text ? 'About saved.' : 'About cleared.');
    const view = document.getElementById('about-view');
    if (view) view.innerHTML = text
      ? '<p style="font-size:15px;color:var(--text2);line-height:1.75;">' + hmEscape(text).replace(/\n/g, '<br>') + '</p>'
      : '<div class="profile-empty-hint">Add a short about section so HireMate can understand your background.</div>';
    toggleEdit('about');
  } catch (err) { showToast('error', err.message); }
}

function addSkill() {
  hmOpenTagModal('skills');
}

function removeSkill(btn) {
  btn.parentElement.remove();
  hmSaveProfilePatch({ skills: hmTagsToCsv('skills-container') }, 'Skills updated.').catch(err => showToast('error', err.message));
}

function addInterest() {
  hmOpenTagModal('interests');
}

function removeInterest(btn) {
  btn.parentElement.remove();
  hmSaveProfilePatch({ interests: hmTagsToCsv('interests-container') }, 'Interests updated.').catch(err => showToast('error', err.message));
}

async function saveEducation() {
  const title = document.getElementById('edu-title-in')?.value.trim() || '';
  const school = document.getElementById('edu-school-in')?.value.trim() || '';
  const desc = document.getElementById('edu-desc-in')?.value.trim() || '';
  if (!title || !school) { showToast('error', 'Please fill degree and school.'); return; }
  const education = [title, school, desc].filter(Boolean).join('\n');
  try {
    const user = await hmSaveProfilePatch({ education }, 'Education saved.');
    hmRenderProfileLongField('education-card', user.education, '', hmProfileIcon('education'));
    if (typeof closeModal === 'function') closeModal();
  } catch (err) { showToast('error', err.message); }
}

function showAddExperience() {
  const user = hmCurrentUser();
  document.getElementById('modal-content').innerHTML =
    '<div class="modal-title">Edit Experience</div>' +
    '<div class="modal-sub">Add internships, projects, freelance work, or professional experience.</div>' +
    '<textarea id="exp-detail-in" class="form-textarea" style="min-height:170px;" placeholder="Example: Frontend Intern at ABC\\nBuilt React dashboards and integrated REST APIs.">' + hmEscape(user.experience_detail || '') + '</textarea>' +
    '<div style="display:flex;gap:10px;margin-top:16px;">' +
    '<button class="btn btn-ghost" style="flex:1;" onclick="closeModal()">Cancel</button>' +
    '<button class="btn btn-primary" style="flex:1;" onclick="hmSaveExperienceDetail()">Save</button>' +
    '</div>';
  document.getElementById('modal').classList.add('open');
}

async function hmSaveExperienceDetail() {
  const value = document.getElementById('exp-detail-in')?.value.trim() || '';
  try {
    const user = await hmSaveProfilePatch({ experience_detail: value }, 'Experience saved.');
    hmRenderProfileLongField('experience-card', user.experience_detail, 'No experience added yet. Add projects, internships, freelance work, or academic work.', hmProfileIcon('briefcase'));
    closeModal();
  } catch (err) { showToast('error', err.message); }
}

function showAddEducation() {
  const user = hmCurrentUser();
  document.getElementById('modal-content').innerHTML =
    '<div class="modal-title">Edit Education</div>' +
    '<div class="modal-sub">Add your degree, university, dates, and coursework.</div>' +
    '<textarea id="edu-detail-in" class="form-textarea" style="min-height:170px;" placeholder="Example: BS Software Engineering, IIUI\\n2021 - 2025">' + hmEscape(user.education || '') + '</textarea>' +
    '<div style="display:flex;gap:10px;margin-top:16px;">' +
    '<button class="btn btn-ghost" style="flex:1;" onclick="closeModal()">Cancel</button>' +
    '<button class="btn btn-primary" style="flex:1;" onclick="hmSaveEducationDetail()">Save</button>' +
    '</div>';
  document.getElementById('modal').classList.add('open');
}

async function hmSaveEducationDetail() {
  const value = document.getElementById('edu-detail-in')?.value.trim() || '';
  try {
    const user = await hmSaveProfilePatch({ education: value }, 'Education saved.');
    hmRenderProfileLongField('education-card', user.education, 'No education added yet. Add your degree, university, and dates.', hmProfileIcon('education'));
    closeModal();
  } catch (err) { showToast('error', err.message); }
}

function hmPickProfileImage(type) {
  const input = document.getElementById(type === 'cover' ? 'profile-cover-input' : 'profile-avatar-input');
  if (input) input.click();
}

async function hmUploadProfileImage(type, input) {
  const file = input && input.files ? input.files[0] : null;
  if (!file) return;
  if (!file.type.startsWith('image/')) { showToast('error', 'Please choose an image file.'); return; }
  if (file.size > 1100000) { showToast('error', 'Image must be under 1 MB.'); return; }
  const dataUrl = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
  try {
    const payload = type === 'cover' ? { cover_image: dataUrl } : { avatar_image: dataUrl };
    const user = await hmSaveProfilePatch(payload, type === 'cover' ? 'Cover photo saved.' : 'Profile photo saved.');
    hmRenderProfileImages(user);
  } catch (err) { showToast('error', err.message); }
  input.value = '';
}

async function saveCookie() {
  const input = document.getElementById('cookie-input');
  const err = document.getElementById('cookie-err');
  const value = input ? input.value.trim() : '';
  if (err) err.textContent = '';
  if (!value) {
    if (err) err.textContent = 'LinkedIn session cookie is required';
    showToast('error', 'Enter your LinkedIn session cookie.');
    return;
  }
  try {
    await hmSaveLinkedInCookie(value);
    showToast('success', 'LinkedIn session cookie encrypted and saved securely.');
    if (input) input.value = '';
    toggleEdit('cookie');
    await hmLoadProfileCookieStatus();
  } catch (e) {
    if (err) err.textContent = e.message || 'Unable to save LinkedIn session cookie';
    showToast('error', err ? err.textContent : 'Unable to save LinkedIn session cookie');
  }
}

async function hmLoadProfileCookieStatus() {
  if (!document.title.includes('Profile') || !hmToken()) return;
  try {
    const data = await hmApi('/api/linkedin/cookie');
    const cookie = data.cookie || {};
    const box = document.getElementById('profile-cookie-status');
    const row = document.getElementById('profile-saved-cookie-row');
    const mask = document.getElementById('profile-saved-cookie-mask');
    if (!box || !row || !mask) return;
    if (cookie.connected) {
      box.innerHTML = '<span>' + hmProfileIcon('check') + '</span><div><strong style="color:var(--accent)">LinkedIn session cookie saved</strong><br><span>Your LinkedIn session cookie is encrypted, saved securely, and ready for finding leads.</span></div>';
      row.style.display = 'block';
      mask.value = cookie.masked || 'li_at=******';
    } else {
      box.innerHTML = '<span>' + hmProfileIcon('alert') + '</span><div><strong style="color:var(--warm)">LinkedIn session cookie needed</strong><br><span>Add your LinkedIn session cookie so HireMate can find more relevant leads.</span></div>';
      row.style.display = 'none';
      mask.value = '';
    }
  } catch (e) {}
}

async function handleOnboarding(e) {
  e.preventDefault();
  if (!hmToken()) {
    showToast('error', 'Please create an account or login first.');
    setTimeout(() => { window.location.href = 'register.html'; }, 900);
    return;
  }
  const btn = document.getElementById('ob-submit');
  const original = btn ? btn.innerHTML : '';
  if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Saving profile...'; }
  const profile = {
    headline: document.getElementById('ob-headline').value.trim(),
    location: document.getElementById('ob-location').value.trim(),
    about: document.getElementById('ob-about').value.trim(),
    skills: document.getElementById('ob-skills').value.trim(),
    interests: document.getElementById('ob-interests').value.trim(),
    target_roles: document.getElementById('ob-roles').value.trim(),
    preferred_locations: document.getElementById('ob-locations').value.trim(),
    work_modes: document.getElementById('ob-work-modes').value,
    experience_level: document.getElementById('ob-experience').value,
    education: document.getElementById('ob-education').value.trim(),
    experience_detail: document.getElementById('ob-experience-detail').value.trim(),
    linkedin_cookie: document.getElementById('ob-cookie').value.trim()
  };
  if (!profile.skills || !profile.target_roles) {
    showToast('error', 'Skills and target roles are required.');
    if (btn) { btn.disabled = false; btn.innerHTML = original; }
    return;
  }
  try {
    const saved = await hmApi('/api/profile', { method: 'PATCH', body: JSON.stringify(profile) });
    localStorage.setItem('hm_user', JSON.stringify(saved.user || {}));
    hmApplyNavAvatar(saved.user || {});
    showToast('success', 'Profile saved. You can find opportunities from the dashboard when you are ready.');
    setTimeout(() => { window.location.href = 'dashboard.html'; }, 900);
  } catch (err) {
    showToast('error', err.message);
    if (btn) { btn.disabled = false; btn.innerHTML = original; }
  }
}

// ========== THEME TOGGLE ==========
function hmApplyThemeMode(mode) {
  var isLight = mode === 'light';
  document.documentElement.classList.toggle('light-mode', isLight);
  document.body.classList.toggle('light-mode', isLight);
  document.querySelectorAll('.theme-toggle').forEach(function (btn) {
    btn.innerHTML = hmThemeIcon(isLight);
    btn.title = isLight ? 'Light mode is active' : 'Dark mode is active';
    btn.setAttribute('aria-label', isLight ? 'Light mode is active' : 'Dark mode is active');
  });
}

function hmThemeIcon(isLight) {
  if (isLight) {
    return '<svg class="theme-icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4.5"></circle><path d="M12 2.5v2.2M12 19.3v2.2M4.7 4.7l1.6 1.6M17.7 17.7l1.6 1.6M2.5 12h2.2M19.3 12h2.2M4.7 19.3l1.6-1.6M17.7 6.3l1.6-1.6"></path></svg>';
  }
  return '<svg class="theme-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M20.2 15.3A8.2 8.2 0 0 1 8.7 3.8 8.8 8.8 0 1 0 20.2 15.3Z"></path></svg>';
}

(function () {
  try { hmApplyThemeMode(localStorage.getItem('hm-theme') || 'dark'); } catch (e) {}
})();

function toggleTheme() {
  var nextMode = document.body.classList.contains('light-mode') ? 'dark' : 'light';
  try { localStorage.setItem('hm-theme', nextMode); } catch (e) {}
  hmApplyThemeMode(nextMode);
}

document.addEventListener('DOMContentLoaded', function () {
  try { hmApplyThemeMode(localStorage.getItem('hm-theme') || (document.body.classList.contains('light-mode') ? 'light' : 'dark')); } catch (e) {}
});
















