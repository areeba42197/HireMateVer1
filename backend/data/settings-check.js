
function showSettingsPanel(id) {
  document.querySelectorAll('.settings-panel').forEach(function(p){p.classList.remove('active');});
  document.querySelectorAll('.settings-nav-item').forEach(function(i){i.classList.remove('active');});
  var p = document.getElementById('sp-'+id), n = document.getElementById('sn-'+id);
  if(p) p.classList.add('active');
  if(n) n.classList.add('active');
}
function savePersonalInfo(e) {
  e.preventDefault();
  var fname = document.getElementById('set-fname'), lname = document.getElementById('set-lname'), email = document.getElementById('set-email');
  var valid = true;
  if(!fname.value.trim()){document.getElementById('set-fname-err').textContent='First name required';fname.classList.add('is-error');valid=false;}else{document.getElementById('set-fname-err').textContent='';fname.classList.remove('is-error');fname.classList.add('is-valid');}
  if(!lname.value.trim()){document.getElementById('set-lname-err').textContent='Last name required';lname.classList.add('is-error');valid=false;}else{document.getElementById('set-lname-err').textContent='';lname.classList.remove('is-error');}
  if(!email.value||!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value)){document.getElementById('set-email-err').textContent='Enter a valid email address';email.classList.add('is-error');valid=false;}else{document.getElementById('set-email-err').textContent='';email.classList.remove('is-error');}
  if(!valid){showToast('error','Please fix the errors above.');return;}
  showToast('success','Personal information saved!');
}
function savePassword(e) {
  e.preventDefault();
  var curr=document.getElementById('curr-pw'), nw=document.getElementById('new-pw'), conf=document.getElementById('conf-pw');
  var valid=true;
  if(!curr.value){document.getElementById('curr-pw-err').textContent='Current password is required';curr.classList.add('is-error');valid=false;}else{document.getElementById('curr-pw-err').textContent='';curr.classList.remove('is-error');}
  if(!nw.value||nw.value.length<8){document.getElementById('new-pw-err').textContent='Password must be at least 8 characters';nw.classList.add('is-error');valid=false;}
  else if(!/[A-Z]/.test(nw.value)){document.getElementById('new-pw-err').textContent='Add at least one uppercase letter';nw.classList.add('is-error');valid=false;}
  else if(!/[a-z]/.test(nw.value)){document.getElementById('new-pw-err').textContent='Add at least one lowercase letter';nw.classList.add('is-error');valid=false;}
  else if(!/[0-9]/.test(nw.value)){document.getElementById('new-pw-err').textContent='Add at least one number';nw.classList.add('is-error');valid=false;}
  else if(!/[^A-Za-z0-9]/.test(nw.value)){document.getElementById('new-pw-err').textContent='Add at least one special character';nw.classList.add('is-error');valid=false;}
  else{document.getElementById('new-pw-err').textContent='';nw.classList.remove('is-error');}
  if(!conf.value||conf.value!==nw.value){document.getElementById('conf-pw-err').textContent='Passwords do not match';conf.classList.add('is-error');valid=false;}else{document.getElementById('conf-pw-err').textContent='';conf.classList.remove('is-error');}
  if(!valid){showToast('error','Please fix the errors above.');return;}
  showToast('success','Password updated successfully!');
  curr.value='';nw.value='';conf.value='';
}
function onNewPw(pw){
  renderStrength(pw,'set-str-bar','set-str-lbl');
  var m={'sp-chk-len':pw.length>=8,'sp-chk-upper':/[A-Z]/.test(pw),'sp-chk-lower':/[a-z]/.test(pw),'sp-chk-num':/[0-9]/.test(pw),'sp-chk-special':/[^A-Za-z0-9]/.test(pw)};
  Object.entries(m).forEach(function(e){var el=document.getElementById(e[0]);if(el)el.classList.toggle('ok',e[1]);});
}
async function updateCookieSettings(e) {
  e.preventDefault();
  var val=document.getElementById('set-cookie').value.trim();
  var err=document.getElementById('set-cookie-err');
  if(!val){err.textContent='Cookie is required';document.getElementById('set-cookie').classList.add('is-error');return;}
  if(!val.includes('li_at=') && val.includes('=')){err.textContent='Cookie must include li_at=';document.getElementById('set-cookie').classList.add('is-error');return;}
  err.textContent='';
  document.getElementById('set-cookie').classList.remove('is-error');
  try {
    await hmSaveLinkedInCookie(val);
    showToast('success','LinkedIn session cookie encrypted and saved!');
    document.getElementById('set-cookie').value='';
    if (window.hmLoadCookieStatus) hmLoadCookieStatus();
    try {
      showToast('info','Testing LinkedIn session with a slow post-first sync...');
      await hmSyncAfterCookieSave();
      if (window.hmLoadCookieStatus) hmLoadCookieStatus();
    } catch(syncErr) {
      showToast('error', syncErr.message || 'Cookie saved, but LinkedIn sync failed.');
    }
  } catch(ex) {
    err.textContent=ex.message || 'Unable to save cookie';
    document.getElementById('set-cookie').classList.add('is-error');
    showToast('error',err.textContent);
  }
}
async function hmLoadCookieStatus(){
  if(!window.hmApi || !hmToken()) return;
  try{
    var data = await hmApi('/api/linkedin/cookie');
    var c = data.cookie || {};
    var box = document.getElementById('cookie-status-box');
    var row = document.getElementById('saved-cookie-row');
    var mask = document.getElementById('saved-cookie-mask');
    if(c.connected){
      box.innerHTML = '<span>&#x2705;</span><div><strong style="color:var(--accent)">Session Cookie Saved</strong><br>Encrypted in SQLite. Future LinkedIn syncs will use post/content search first.</div>';
      row.style.display = 'block';
      mask.value = c.masked || 'li_at=••••••';
    } else {
      box.innerHTML = '<span>&#x26A0;</span><div><strong style="color:var(--warm)">No Session Cookie Saved</strong><br>Add your LinkedIn session cookie to enable post-first sync.</div>';
      row.style.display = 'none';
      mask.value = '';
    }
  }catch(e){}
}
document.addEventListener('DOMContentLoaded', function(){ setTimeout(hmLoadCookieStatus, 200); });
function showDeleteModal() {
  document.getElementById('modal-content').innerHTML = '<div class="modal-title" style="color:var(--hot)">&#x1F5D1; Delete Account</div><div class="modal-sub">This is permanent and cannot be undone. All your data will be erased.</div><div class="warning-box" style="margin-bottom:20px;"><span>&#x26A0;&#xFE0F;</span><span>Type <strong style="color:var(--text)">DELETE</strong> to confirm.</span></div><div class="form-group" style="margin-bottom:20px;"><label class="form-label">Confirmation</label><input class="form-input" placeholder="Type DELETE here" id="del-confirm" autocomplete="off"><span class="form-error-msg" id="del-err"></span></div><div style="display:flex;gap:10px;"><button class="btn btn-ghost" style="flex:1;" onclick="closeModal()">Cancel</button><button class="btn btn-danger" style="flex:1;" onclick="confirmDelete()">Delete My Account</button></div>';
  document.getElementById('modal').classList.add('open');
}
function confirmDelete() {
  var v=document.getElementById('del-confirm').value;
  if(v==='DELETE'){closeModal();showToast('success','Account deleted.');setTimeout(function(){window.location.href='landing.html';},1200);}
  else{document.getElementById('del-err').textContent='Type DELETE exactly (all caps)';document.getElementById('del-confirm').classList.add('is-error');}
}

