/* ui_patch_show_game.js
   Drop-in patch for the older circular Archetype Validator UI.
   Add this after the existing app.js in index.html:
     <script src="ui_patch_show_game.js"></script>
   It does not reveal internal suggested archetypes. It only displays the game title,
   character/role, and a warning for weak/role-only records.
*/
(function(){
  let items = [];
  const css = `
    #gameCharacterPanel{max-width:820px;margin:10px auto 8px auto;padding:12px 18px;border-radius:18px;background:rgba(255,255,255,.76);box-shadow:0 6px 24px rgba(0,0,0,.08);text-align:center;font-family:inherit;color:#0e1a2b;}
    #gameCharacterPanel .gcpGame{font-weight:900;font-size:clamp(18px,2.4vw,28px);line-height:1.1;margin-bottom:4px;}
    #gameCharacterPanel .gcpChar{font-weight:800;font-size:clamp(16px,2vw,23px);line-height:1.15;}
    #gameCharacterPanel .gcpRole{font-size:13px;opacity:.75;margin-top:6px;max-width:760px;margin-left:auto;margin-right:auto;}
    #gameCharacterPanel .gcpWarn{margin-top:8px;color:#8a4b00;background:#fff4d9;border:1px solid #f0c36d;border-radius:10px;padding:6px 10px;font-size:13px;}
    #gameCharacterPanel .gcpSource{font-size:12px;margin-top:5px;opacity:.72;}
    #gameCharacterPanel a{color:#2454a6;text-decoration:underline;}
  `;
  function addCss(){
    if(document.getElementById('gcpStyle')) return;
    const st=document.createElement('style'); st.id='gcpStyle'; st.textContent=css; document.head.appendChild(st);
  }
  function getIndexFromPage(){
    const text=document.body.innerText || '';
    const total = items.length;
    const patterns=[
      new RegExp('(?:^|\s)(\d+)\s*/\s*'+total+'(?:\s|$)'),
      /(\d+)\s*\/\s*(\d+)/
    ];
    for(const p of patterns){
      const m=text.match(p);
      if(m){
        const n=parseInt(m[1],10);
        const t=m[2] ? parseInt(m[2],10) : total;
        if(Number.isFinite(n) && n>=1 && n<=total && (!m[2] || t===total)) return n-1;
      }
    }
    return 0;
  }
  function ensurePanel(){
    let panel=document.getElementById('gameCharacterPanel');
    if(panel) return panel;
    panel=document.createElement('div'); panel.id='gameCharacterPanel';
    const header=document.querySelector('header') || document.querySelector('h1')?.parentElement || document.body;
    if(header && header.parentElement){
      header.parentElement.insertBefore(panel, header.nextSibling);
    } else document.body.insertBefore(panel, document.body.firstChild);
    return panel;
  }
  function updatePanel(){
    if(!items.length) return;
    addCss();
    const idx=getIndexFromPage();
    const it=items[idx] || items[0];
    const game=it.game || it.game_name || it.gameTitle || it.title || 'Unknown game';
    const character=it.character || it.character_name || it.name || 'Unknown character / role';
    const role=it.protagonist_role || '';
    const status=it.known_status || '';
    const source=it.source_url || '';
    let warn='';
    if(status === 'role_only') warn='This is a player role rather than a named character. Classify only if the role is meaningful in this game.';
    if(status === 'unknown') warn='This item has no confirmed protagonist yet. Prefer Skip / insufficient info.';
    const panel=ensurePanel();
    panel.innerHTML = `<div class="gcpGame">${escapeHtml(game)}</div>`+
      `<div class="gcpChar">${escapeHtml(character)}</div>`+
      (role ? `<div class="gcpRole">${escapeHtml(role)}</div>` : '')+
      (warn ? `<div class="gcpWarn">${escapeHtml(warn)}</div>` : '')+
      (source ? `<div class="gcpSource"><a href="${escapeAttr(source)}" target="_blank" rel="noopener">source</a></div>` : '');
  }
  function escapeHtml(s){return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
  function escapeAttr(s){return String(s).replace(/["<>]/g, '');}
  fetch('characters.json?game_patch=' + Date.now())
    .then(r=>r.json())
    .then(data=>{items=(typeof window.prepareArchetypeCharactersForValidation==='function'?window.prepareArchetypeCharactersForValidation(data):data); updatePanel(); setInterval(updatePanel, 300);})
    .catch(e=>console.warn('Game display patch failed:', e));
})();