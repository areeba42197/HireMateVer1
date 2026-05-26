

  /* CLOSE MODAL */
  function closeModal(){
    document.getElementById("modal").classList.remove("open");
  }
  
  /* TOAST FIX (safe fallback) */
  function showToast(type,msg){
    if(window.showToastExternal){
      window.showToastExternal(type,msg);
    } else {
      alert(msg);
    }
  }
  
  /* ================= PROFILE MODAL ================= */
  function showEditProfileModal() {
    document.getElementById('modal-content').innerHTML =
      '<div class="modal-title">Edit Profile</div>' +
      '<div class="modal-sub">Update your basic profile information.</div>' +
  
      '<div style="display:flex;flex-direction:column;gap:14px;margin-bottom:20px;">' +
      '<input id="ep-name" class="form-input" value="'+document.querySelector(".profile-name").innerText+'">' +
      '<input id="ep-headline" class="form-input" value="'+document.querySelector(".profile-headline").innerText+'">' +
      '<input id="ep-location" class="form-input" value="'+document.querySelector(".profile-location").innerText.replace("📍","").trim()+'">' +
      '</div>' +
  
      '<div style="display:flex;gap:10px;">' +
      '<button class="btn btn-ghost" style="flex:1;" onclick="closeModal()">Cancel</button>' +
      '<button class="btn btn-primary" style="flex:1;" onclick="saveProfile()">Save</button>' +
      '</div>';
  
    document.getElementById("modal").classList.add("open");
  }
  
  /* SAVE PROFILE FIX */
  function saveProfile(){
    let name=document.getElementById("ep-name").value;
    let headline=document.getElementById("ep-headline").value;
    let location=document.getElementById("ep-location").value;
  
    document.querySelector(".profile-name").innerText=name;
    document.querySelector(".profile-headline").innerText=headline;
    document.querySelector(".profile-location").innerText="📍 "+location;
  
    localStorage.setItem("hm_name",name);
    localStorage.setItem("hm_headline",headline);
    localStorage.setItem("hm_location",location);
  
    closeModal();
    showToast("success","Profile updated!");
  }
  
  /* ================= ABOUT ================= */
  function toggleEdit(section){
    let v=document.getElementById(section+"-view");
    let e=document.getElementById(section+"-edit");
  
    if(v && e){
      v.style.display = (v.style.display==="none") ? "block":"none";
      e.style.display = (e.style.display==="none") ? "block":"none";
    }
  }
  
  /* ================= SKILLS FIX ================= */
  function addSkill(){
    let input=document.getElementById("skill-input");
    let val=input.value.trim();
    if(!val){showToast("error","Enter skill");return;}
  
    let div=document.createElement("div");
    div.className="skill-tag";
    div.innerHTML=val+' <button onclick="removeSkill(this)">×</button>';
  
    document.getElementById("skills-container").appendChild(div);
    input.value="";
  }
  
  function removeSkill(btn){
    btn.parentElement.remove();
  }
  
  /* ================= INTEREST FIX ================= */
  function addInterest(){
    let input=document.getElementById("interest-input");
    let val=input.value.trim();
    if(!val){showToast("error","Enter interest");return;}
  
    let div=document.createElement("div");
    div.className="interest-tag";
    div.innerHTML=val+' <button onclick="this.parentElement.remove()">×</button>';
  
    document.getElementById("interests-container").appendChild(div);
    input.value="";
  }
  
  /* ================= ABOUT ================= */
  function saveAbout(){
    let text=document.getElementById("about-text").value.trim();
    if(!text){showToast("error","About empty");return;}
  
    document.getElementById("about-view").innerText=text;
    toggleEdit("about");
    showToast("success","Saved!");
  }
  
  /* ================= EXPERIENCE ================= */
  function showAddExperience(){
    document.getElementById("modal-content").innerHTML=
      '<div class="modal-title">Add Experience</div>'+
      '<input id="exp-title" class="form-input" placeholder="Title">'+
      '<input id="exp-company" class="form-input" placeholder="Company">'+
      '<button class="btn btn-primary" onclick="saveExperience()">Save</button>';
  
    document.getElementById("modal").classList.add("open");
  }
  
  function saveExperience(){
    let t=document.getElementById("exp-title").value;
    let c=document.getElementById("exp-company").value;
  
    if(!t||!c){showToast("error","Fill all");return;}
  
    showToast("success","Experience added!");
    closeModal();
  }
  
  /* ================= COOKIE FIX (MAIN ISSUE FIXED) ================= */
  async function saveCookie(){
    let input=document.getElementById("cookie-input");
    let err=document.getElementById("cookie-err");
    let val=input.value.trim();
  
    err.textContent="";
  
    if(!val){
      err.textContent="Cookie required";
      showToast("error","Enter cookie");
      return;
    }
  
    if(!val.includes("li_at=") && !val.includes("=")){ val="li_at="+val; }
    if(!val.includes("li_at=")){ err.textContent="Cookie must include li_at="; showToast("error","Cookie must include li_at="); return; }
  
    if(val.length<30){
      err.textContent="Invalid cookie";
      showToast("error","Invalid cookie");
      return;
    }
  
    try {
      await hmSaveLinkedInCookie(val);
      showToast("success","Cookie encrypted and saved in backend!");
      input.value="";
      toggleEdit("cookie");
      if(window.hmLoadProfileCookieStatus) hmLoadProfileCookieStatus();
      try{
        showToast("info","Testing LinkedIn session with a slow post-first sync...");
        await hmSyncAfterCookieSave();
        if(window.hmLoadProfileCookieStatus) hmLoadProfileCookieStatus();
      }catch(syncErr){
        showToast("error", syncErr.message || "Cookie saved, but LinkedIn sync failed.");
      }
    } catch(e) {
      err.textContent=e.message || "Unable to save cookie";
      showToast("error",err.textContent);
    }
  }
  
  /* LOAD */
  window.onload=function(){};
  async function hmLoadProfileCookieStatus(){
    if(!window.hmApi || !hmToken()) return;
    try{
      let data = await hmApi('/api/linkedin/cookie');
      let c = data.cookie || {};
      let box = document.getElementById('profile-cookie-status');
      let row = document.getElementById('profile-saved-cookie-row');
      let mask = document.getElementById('profile-saved-cookie-mask');
      if(c.connected){
        box.innerHTML='<span>&#x2705;</span><div><strong style="color:var(--accent)">Session Cookie Saved</strong><br><span>Encrypted in SQLite. LinkedIn sync will prioritize posts.</span></div>';
        row.style.display='block';
        mask.value=c.masked || 'li_at=••••••';
      } else {
        box.innerHTML='<span>&#x26A0;</span><div><strong style="color:var(--warm)">No Session Cookie Saved</strong><br><span>Add your LinkedIn cookie to enable post-first sync.</span></div>';
        row.style.display='none';
        mask.value='';
      }
    }catch(e){}
  }
  document.addEventListener('DOMContentLoaded', function(){ setTimeout(hmLoadProfileCookieStatus, 200); });
  /* ================= ADD EDUCATION ================= */
function showAddEducation(){

document.getElementById('modal-content').innerHTML =
  '<div class="modal-title">Add Education</div>'+
  '<div class="modal-sub">Add new education entry</div>'+

  '<div style="display:flex;flex-direction:column;gap:12px;margin-bottom:20px;">'+
    '<input id="edu-title-in" class="form-input" placeholder="Degree (e.g. BS Software Engineering)">'+
    '<input id="edu-school-in" class="form-input" placeholder="University (e.g. IIUI)">'+
    '<textarea id="edu-desc-in" class="form-textarea" placeholder="Description"></textarea>'+
  '</div>'+

  '<div style="display:flex;gap:10px;">'+
    '<button class="btn btn-ghost" style="flex:1;" onclick="closeModal()">Cancel</button>'+
    '<button class="btn btn-primary" style="flex:1;" onclick="saveEducation()">Add</button>'+
  '</div>';

document.getElementById("modal").classList.add("open");
}

/* SAVE EDUCATION */
function saveEducation(){

let title = document.getElementById('edu-title-in').value;
let school = document.getElementById('edu-school-in').value;
let desc = document.getElementById('edu-desc-in').value;

if(!title || !school){
  showToast("error","Please fill required fields");
  return;
}

let container = document.querySelectorAll(".section-card")[2]; // education card

let div = document.createElement("div");
div.className = "exp-item";

div.innerHTML =
  '<div class="exp-icon">🎓</div>'+
  '<div style="flex:1;">'+
    '<div class="exp-title">'+title+'</div>'+
    '<div class="exp-sub">'+school+'</div>'+
    '<div class="exp-desc">'+desc+'</div>'+
  '</div>';

container.appendChild(div);

closeModal();
showToast("success","Education added!");
}
  
