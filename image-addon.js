(()=>{
  'use strict';

  const bundle=window.__MOTORBOAT_IMAGE_MAP__||{};
  const byId=bundle.byId||{};
  const byKey=bundle.byKey||{};
  if(!Object.keys(byId).length&&!Object.keys(byKey).length) return;

  function imageKey(value){
    return String(value||'').normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]/gu,'');
  }

  function mediaForQuestion(q){
    if(!q) return null;
    return byId[String(q.id||'')]||byKey[imageKey(q.question)]||null;
  }

  function injectStyle(){
    if(document.getElementById('imageQuestionStyle')) return;
    const st=document.createElement('style');
    st.id='imageQuestionStyle';
    st.textContent=`
      .imageAddonQuestionWrap{margin:14px 0 16px;text-align:center}
      .imageAddonQuestion{display:block;max-width:100%;max-height:390px;width:auto;height:auto;object-fit:contain;margin:0 auto;border-radius:10px;background:#fff;border:1px solid #e1e8eb;padding:6px;box-sizing:border-box}
      .option.imageAddonHasMedia{flex-wrap:wrap}
      .option.imageAddonHasMedia>span:nth-child(2){flex:1 1 0;min-width:0}
      .imageAddonOptionWrap{flex:1 0 100%;width:100%;text-align:center;padding:8px 0 0 66px;box-sizing:border-box}
      .imageAddonOption{display:block;max-width:100%;max-height:300px;width:auto;height:auto;object-fit:contain;margin:0 auto;border-radius:9px;background:#fff;border:1px solid #e1e8eb;padding:5px;box-sizing:border-box}
      .imageAddonBankWrap{margin:12px 0;text-align:center}
      .imageAddonBank{display:block;max-width:100%;max-height:340px;width:auto;height:auto;object-fit:contain;margin:0 auto;border-radius:9px;background:#fff;border:1px solid #e1e8eb;padding:5px;box-sizing:border-box}
      .imageAddonBankOptionWrap{margin-top:8px;text-align:center}
      .imageAddonBankOption{display:block;max-width:100%;max-height:260px;width:auto;height:auto;object-fit:contain;margin:0 auto;border-radius:8px;background:#fff;border:1px solid #e1e8eb;padding:4px;box-sizing:border-box}
      @media(max-width:600px){
        .imageAddonQuestion{max-height:300px}
        .imageAddonOptionWrap{padding-left:0}
        .imageAddonOption{max-height:250px}
        .imageAddonBank{max-height:280px}
        .imageAddonBankOption{max-height:230px}
      }
    `;
    document.head.appendChild(st);
  }

  function makeImage(src,className,alt,lazy=true){
    const img=document.createElement('img');
    img.className=className;
    img.src=src;
    img.alt=alt;
    img.decoding='async';
    if(lazy) img.loading='lazy';
    return img;
  }

  function decorateQuiz(){
    if(typeof state==='undefined'||state.screen!=='quiz'||!state.questions||!state.questions.length) return;
    const q=state.questions[state.index];
    const media=mediaForQuestion(q);
    if(!media) return;
    const main=document.querySelector('#app .main');
    if(!main) return;

    if(media.question&&!main.querySelector('[data-image-addon="question"]')&&!main.querySelector('.questionImageWrap')){
      const question=main.querySelector('.question');
      if(question){
        const wrap=document.createElement('div');
        wrap.className='imageAddonQuestionWrap';
        wrap.dataset.imageAddon='question';
        wrap.appendChild(makeImage(media.question,'imageAddonQuestion',`題號 ${q.num||''} 圖片`,false));
        question.insertAdjacentElement('afterend',wrap);
      }
    }

    const options=main.querySelectorAll('.options [data-answer]');
    (media.options||[]).forEach((src,index)=>{
      const option=options[index];
      if(!src||!option||option.querySelector('[data-image-addon="option"]')) return;
      option.classList.add('imageAddonHasMedia');
      const wrap=document.createElement('div');
      wrap.className='imageAddonOptionWrap';
      wrap.dataset.imageAddon='option';
      wrap.appendChild(makeImage(src,'imageAddonOption',`選項 ${String.fromCharCode(65+index)} 圖片`,false));
      option.appendChild(wrap);
    });
  }

  function decorateBank(){
    document.querySelectorAll('#app .bankCard').forEach(card=>{
      const questionEl=card.querySelector('.bankQuestion');
      if(!questionEl) return;
      const media=byKey[imageKey(questionEl.textContent)];
      if(!media) return;

      if(media.question&&!card.querySelector('[data-image-addon="bank-question"]')){
        const wrap=document.createElement('div');
        wrap.className='imageAddonBankWrap';
        wrap.dataset.imageAddon='bank-question';
        wrap.appendChild(makeImage(media.question,'imageAddonBank','題目圖片'));
        questionEl.insertAdjacentElement('afterend',wrap);
      }

      const options=card.querySelectorAll('.bankOption');
      (media.options||[]).forEach((src,index)=>{
        const option=options[index];
        if(!src||!option||option.querySelector('[data-image-addon="bank-option"]')) return;
        const wrap=document.createElement('div');
        wrap.className='imageAddonBankOptionWrap';
        wrap.dataset.imageAddon='bank-option';
        wrap.appendChild(makeImage(src,'imageAddonBankOption',`選項 ${String.fromCharCode(65+index)} 圖片`));
        option.appendChild(wrap);
      });
    });
  }

  function decorate(){
    injectStyle();
    decorateQuiz();
    decorateBank();
  }

  let queued=false;
  function schedule(){
    if(queued) return;
    queued=true;
    requestAnimationFrame(()=>{
      queued=false;
      decorate();
    });
  }

  const app=document.getElementById('app');
  if(app){
    new MutationObserver(schedule).observe(app,{childList:true,subtree:true});
  }
  window.addEventListener('load',schedule,{once:true});
  schedule();
})();
