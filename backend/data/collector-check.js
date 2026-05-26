
function buildCollectorScript() {
  var token = localStorage.getItem('hm_token') || '';
  if (!token) return '// Please login to HireMate first, then reload this page.';
  return `(function(){
  const API = 'http://localhost:8000';
  const TOKEN = '${token.replace(/'/g, "\\'")}';
  const HIRING = /(hiring|we are hiring|we're hiring|looking for|job opening|vacancy|internship|developer|engineer|remote|apply|send your cv|dm me)/i;
  const seen = window.__hiremateSeenPosts || new Set();
  window.__hiremateSeenPosts = seen;
  function clean(s){ return (s || '').replace(/\\s+/g, ' ').trim(); }
  function countNear(text, word){
    const m = text.match(new RegExp('(\\\\d[\\\\d,]*)\\\\s+' + word, 'i'));
    return m ? Number(m[1].replace(/,/g,'')) : 0;
  }
  function postUrl(card){
    const a = card.querySelector('a[href*="/feed/update/"], a[href*="activity-"], a[href*="/posts/"]');
    return a ? a.href.split('?')[0] : '';
  }
  function companyOrAuthor(card){
    const el = card.querySelector('.update-components-actor__title, .feed-shared-actor__title, [data-test-id*="actor"]');
    return clean(el ? el.innerText : '') || 'LinkedIn Post';
  }
  async function collect(){
    const cards = Array.from(document.querySelectorAll('[data-urn*="activity"], .feed-shared-update-v2, article, div[data-id*="activity"]'));
    const posts = [];
    for (const card of cards) {
      const text = clean(card.innerText);
      if (text.length < 90 || !HIRING.test(text)) continue;
      const url = postUrl(card);
      const key = url || text.slice(0, 180);
      if (seen.has(key)) continue;
      seen.add(key);
      const author = companyOrAuthor(card);
      posts.push({
        source_post_id: 'linkedin-browser-' + btoa(unescape(encodeURIComponent(key))).replace(/[^a-zA-Z0-9]/g,'').slice(0,24),
        lead_kind: 'post',
        company: author,
        role_title: 'LinkedIn Hiring Post',
        author_name: author,
        author_title: 'LinkedIn',
        post_text: text,
        post_url: url,
        likes: countNear(text, 'reactions?') || countNear(text, 'likes?'),
        comments: countNear(text, 'comments?'),
        reposts: countNear(text, 'reposts?'),
        posted_at: new Date().toISOString(),
        comment_items: []
      });
    }
    if (!posts.length) { console.log('[HireMate] No new visible hiring posts found. Scroll LinkedIn and it will try again.'); return; }
    const res = await fetch(API + '/api/linkedin/collect-visible', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + TOKEN },
      body: JSON.stringify({ posts })
    });
    const data = await res.json();
    console.log('[HireMate] Imported visible LinkedIn posts:', data);
  }
  collect();
  clearInterval(window.__hiremateCollectorTimer);
  window.__hiremateCollectorTimer = setInterval(collect, 120000);
  alert('HireMate collector is running. Scroll LinkedIn posts; visible hiring posts will sync every 2 minutes.');
})();`;
}
function copyCollector(){
  var code = document.getElementById('collector-code').value;
  navigator.clipboard.writeText(code).then(function(){ showToast('success','Collector script copied. Paste it in LinkedIn Console.'); });
}
document.addEventListener('DOMContentLoaded', function(){
  document.getElementById('collector-code').value = buildCollectorScript();
});

