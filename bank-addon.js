(()=>{
  'use strict';
  const BANK_PAGE_SIZE=40;
  const bankState={chapter:'全部章節',query:'',page:0};

  function injectStyle(){
    if(document.getElementById('onlineBankStyle')) return;
    const st=document.createElement('style');
    st.id='onlineBankStyle';
    st.textContent=`
      .mode.bankMode{border-color:#8fc5e7;background:#f2f9fd}
      .bankPage{max-width:760px;margin:0 auto;padding:18px 16px 40px}
      .bankIntro{background:#fff;border:1px solid #e0e7ea;border-radius:16px;padding:16px 18px;margin-bottom:14px;box-shadow:var(--shadow)}
      .bankIntro h2{margin:0 0 7px;font-size:20px}.bankIntro p{margin:0;color:#687b85;line-height:1.65;font-size:14px}
      .bankTools{position:sticky;top:56px;z-index:5;background:#f7f9fa;border:1px solid #dfe7eb;border-radius:15px;padding:12px;margin-bottom:14px;box-shadow:0 5px 14px rgba(30,55,68,.07)}
      .bankToolRow{display:flex;gap:8px}.bankSearch,.bankSelect{width:100%;box-sizing:border-box;border:1px solid #ccd8de;background:#fff;border-radius:11px;padding:11px 12px;font-size:16px;color:#34434b}
      .bankSearchBtn,.bankClear,.bankPager button{border:0;border-radius:10px;padding:10px 14px;background:#2e91c7;color:#fff;font-weight:700;white-space:nowrap}
      .bankSelect{margin-top:8px}.bankSummary{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-top:9px;color:#70818a;font-size:13px}.bankClear{background:#eef3f5;color:#51646e;padding:8px 10px}
      .bankList{display:grid;gap:12px}.bankCard{background:#fff;border:1px solid #dde6ea;border-radius:16px;padding:16px;box-shadow:var(--shadow)}
      .bankTop{display:flex;justify-content:space-between;gap:12px;margin-bottom:11px}.bankNo{font-weight:800;color:#2a8bc0}.bankMeta{text-align:right;color:#7b8d96;font-size:12px;line-height:1.45}
      .bankQuestion{font-size:17px;font-weight:700;line-height:1.62;margin-bottom:12px}.bankOptions{display:grid;gap:7px}.bankOption{border:1px solid #e1e7ea;border-radius:10px;padding:10px 11px;line-height:1.5;background:#fafcfd}.bankOption.correct{border-color:#85c987;background:#eff9ef;color:#28723b;font-weight:700}
      .bankAnswer{margin-top:12px;border-left:4px solid #62b36d;background:#f2faf3;border-radius:8px;padding:10px 12px;font-weight:800;color:#2b6f38;line-height:1.5}.bankEmpty{text-align:center;padding:35px 10px;color:#778991}
      .bankPager{display:flex;align-items:center;justify-content:center;gap:13px;margin-top:18px}.bankPager button:disabled{opacity:.35}.bankPageInfo{font-size:13px;color:#70818a}
      @media(max-width:520px){.bankPage{padding:12px 10px 34px}.bankTools{top:53px}.bankToolRow{gap:6px}.bankSearchBtn{padding:10px 12px}.bankCard{padding:14px}.bankTop{display:block}.bankMeta{text-align:left;margin-top:4px}.bankQuestion{font-size:16px}}
    `;
    document.head.appendChild(st);
  }

  function filtered(){
    const query=String(bankState.query||'').trim().toLowerCase();
    return QUESTION_BANK.filter(q=>{
      if(bankState.chapter!=='全部章節'&&q.chapter!==bankState.chapter) return false;
      if(!query) return true;
      const correct=q.options[LETTERS.indexOf(q.answer)]||'';
      return [q.chapter,q.section,q.question,...q.options,q.answer,correct].join(' ').toLowerCase().includes(query);
    });
  }

  function bankHtml(){
    const list=filtered();
    const pages=Math.max(1,Math.ceil(list.length/BANK_PAGE_SIZE));
    bankState.page=Math.min(Math.max(0,bankState.page),pages-1);
    const start=bankState.page*BANK_PAGE_SIZE;
    const rows=list.slice(start,start+BANK_PAGE_SIZE);
    const chapterOptions=['全部章節',...CHAPTERS].map(ch=>`<option value="${escapeHtml(ch)}" ${bankState.chapter===ch?'selected':''}>${escapeHtml(ch)}</option>`).join('');
    const cards=rows.map((q,i)=>{
      const correctText=q.options[LETTERS.indexOf(q.answer)]||'';
      const opts=q.options.map((x,j)=>{const L=LETTERS[j];return `<div class="bankOption ${L===q.answer?'correct':''}">${L}. ${escapeHtml(x)}</div>`}).join('');
      return `<article class="bankCard" data-question-id="${escapeHtml(String(q.id||''))}"><div class="bankTop"><div class="bankNo">第 ${start+i+1} / ${list.length} 題</div><div class="bankMeta">${escapeHtml(q.chapter)}<br>${escapeHtml(q.section)}｜題號 ${q.num}</div></div><div class="bankQuestion">${escapeHtml(q.question)}</div><div class="bankOptions">${opts}</div><div class="bankAnswer">正確答案：${q.answer}. ${escapeHtml(correctText)}</div></article>`;
    }).join('');
    const range=list.length?`${start+1}–${Math.min(start+BANK_PAGE_SIZE,list.length)}`:'0';
    return `${header('線上題庫')}<div class="bankPage"><div class="bankIntro"><h2>全部題庫與答案</h2><p>閱讀模式不計入作答紀錄。可依章節篩選或搜尋題目、選項與答案；正確選項會直接標示。</p></div><div class="bankTools"><div class="bankToolRow"><input id="bankQuery" class="bankSearch" type="search" inputmode="search" placeholder="搜尋題目、關鍵字或答案" value="${escapeHtml(bankState.query)}"><button id="bankSearchBtn" class="bankSearchBtn">搜尋</button></div><select id="bankChapter" class="bankSelect">${chapterOptions}</select><div class="bankSummary"><span>共 ${list.length} 題，目前顯示 ${range}</span><button id="bankClearBtn" class="bankClear">清除篩選</button></div></div><div class="bankList">${cards||'<div class="bankEmpty">找不到符合條件的題目。</div>'}</div><div class="bankPager"><button id="bankPrevBtn" ${bankState.page===0?'disabled':''}>‹ 上一頁</button><div class="bankPageInfo">第 ${bankState.page+1} / ${pages} 頁</div><button id="bankNextBtn" ${bankState.page>=pages-1?'disabled':''}>下一頁 ›</button></div></div>`;
  }

  function bindBank(){
    const close=document.getElementById('closeBtn'); if(close) close.onclick=()=>home();
    const menu=document.getElementById('menuBtn'); if(menu) menu.onclick=()=>toggleDrawer(true);
    const query=document.getElementById('bankQuery');
    const run=()=>{bankState.query=query?query.value.trim():'';bankState.page=0;showBank();};
    if(query) query.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();run();}};
    const search=document.getElementById('bankSearchBtn'); if(search) search.onclick=run;
    const chapter=document.getElementById('bankChapter'); if(chapter) chapter.onchange=()=>{bankState.chapter=chapter.value;bankState.page=0;showBank();};
    const clear=document.getElementById('bankClearBtn'); if(clear) clear.onclick=()=>{bankState.chapter='全部章節';bankState.query='';bankState.page=0;showBank();};
    const prev=document.getElementById('bankPrevBtn'); if(prev) prev.onclick=()=>{bankState.page--;showBank();};
    const next=document.getElementById('bankNextBtn'); if(next) next.onclick=()=>{bankState.page++;showBank();};
  }

  function showBank(){
    cleanTimer();
    state.screen='bank';
    const app=document.getElementById('app');
    app.innerHTML=bankHtml();
    bindBank();
    addDrawerEntry();
    window.scrollTo({top:0,behavior:'instant'});
  }

  function addHomeEntry(){
    if(state.screen!=='home'||document.getElementById('bankBtn')) return;
    const grid=document.querySelector('.modeGrid'); if(!grid) return;
    const btn=document.createElement('button');
    btn.className='mode bankMode';btn.id='bankBtn';
    btn.innerHTML='<strong>線上題庫</strong><span>直接閱讀全部題目與正確答案，可搜尋與依章節篩選。</span>';
    btn.onclick=()=>{bankState.page=0;showBank();};
    const practice=grid.querySelector('[data-start="practice"]');
    if(practice&&practice.nextSibling) grid.insertBefore(btn,practice.nextSibling); else grid.appendChild(btn);
  }

  function addDrawerEntry(){
    const box=document.querySelector('#drawer [data-menu]')?.parentElement || document.querySelector('.drawer');
    if(!box||box.querySelector('[data-menu="bank"]')) return;
    const first=box.querySelector('[data-menu]'); if(!first) return;
    const btn=document.createElement('button');btn.dataset.menu='bank';btn.textContent='線上題庫';
    btn.onclick=()=>{toggleDrawer(false);bankState.page=0;showBank();};
    first.insertAdjacentElement('afterend',btn);
  }

  injectStyle();
  const oldRender=render;
  render=function(){
    if(state.screen==='bank'){showBank();return;}
    oldRender();
    addHomeEntry();
    addDrawerEntry();
  };
  addHomeEntry();
  addDrawerEntry();
})();
