'use strict';
const $ = (id) => document.getElementById(id);
const state = { projectId: null, ir: null, last: null, sourceReport: null };
const notice = (text, error=false) => { const n=$('notice'); n.textContent=text; n.classList.toggle('error',error); n.hidden=false; clearTimeout(notice.timer); notice.timer=setTimeout(()=>n.hidden=true,5500); };
async function api(path, payload) {
  const response = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  const result=await response.json();
  if(!response.ok) throw new Error(result.error||'Request failed');
  return result;
}
function currentProfile(){
  const behaviorNode=$('behaviorNode').value;
  return {version:'1.0',id:'client-resource-portal',components:{hero:'pageHeader',richText:'contentBody',image:'media',linkList:$('links').value,unknown:'reviewNote'},colors:{primary:$('primary').value,background:'#f2f4f5',surface:'#ffffff',text:'#24323d',link:'#176a87'},layout:{maxWidthPx:1080,gapPx:28},font:'system',labels:{resourcesHeading:$('resourceTitle').value||'Resources'},assetDirectory:'media',stylePolicy:$('stylePolicy').value,behaviorMappings:behaviorNode?[{nodeId:behaviorNode,interaction:$('behaviorType').value,headingLevel:2,initialIndex:0}]:[],urlMappings:[],rootMappings:['page','image','document'].map(kind=>({kind,sourcePrefix:$('sourceRoot').value.trim(),targetPrefix:$(kind==='page'?'pageRoot':kind==='image'?'imageRoot':'documentRoot').value.trim(),...(kind==='page'?{stripAspx:$('stripAspx').checked}:{})}))};
}
function setTab(tab){
  document.querySelectorAll('[data-tab]').forEach(b=>{const active=b.dataset.tab===tab;b.classList.toggle('selected',active);b.setAttribute('aria-selected',String(active));});
  for(const name of ['preview','ir','quality','mapping','presentation']) $(name+'Panel').hidden=name!==tab;
}
function fillResult(result){
  state.last=result;
  $('results').hidden=false;
  $('metricStatus').textContent=({blocked:'Blocked','review-required':'Review'})[result.quality.releaseDecision?.status]||'Review';
  $('qualityJson').textContent=JSON.stringify(result.quality,null,2);
  $('mappingJson').textContent=JSON.stringify(result.mappingReport,null,2);
  $('presentationJson').textContent=JSON.stringify(result.quality.presentation||{},null,2);
  $('preview').src=result.previewUrl;
  $('export').onclick=()=>{window.location.href=result.exportUrl;};
  setTab('preview');
}
async function analyze(){
  try{
    $('analyze').disabled=true; let payload;
    const file=$('sourceFile').files[0];
    if(file){
      if(file.size>3*1024*1024) throw new Error('File must be under 3 MB');
      payload={source:JSON.parse(await file.text())};
    } else {
      if(!$('sample').value)throw new Error('Select a public sample or upload JSON');
      payload={sampleId:$('sample').value};
    }
    const r=await api('/api/analyze',payload);
    state.projectId=r.projectId;state.ir=r.ir;state.sourceReport=r.sourceCheck;
    const choices=$('behaviorNode');choices.replaceChildren();
    const none=document.createElement('option');none.value='';none.textContent='Do not convert source behavior';choices.append(none);
    const pending=[r.ir.tree];
    while(pending.length){
      const node=pending.pop();
      if(node.kind==='richText'){
        const option=document.createElement('option');option.value=node.id;option.textContent='Rich-text node: '+node.id;
        choices.append(option);
      }
      for(const child of node.children||[])pending.push(child);
    }
    choices.value='';
    $('stageBadge').textContent='Source ready';$('projectTitle').textContent=r.label;
    $('metricNodes').textContent=r.nodeCount;$('metricWarnings').textContent=r.warningCount;
    $('metricPreserved').textContent=r.sourceCheck.summary?.preserved||0;
    $('irJson').textContent=JSON.stringify(r.ir,null,2);
    $('generate').disabled=false;
    notice('Source analyzed. Configure a target and generate the webpage.');
    await generate();
  }catch(e){notice(e.message,true);}finally{$('analyze').disabled=false;}
}
async function generate(){
  if(!state.projectId){return notice('Import source before generating',true);}
  try{
    $('generate').disabled=true;
    const mode=$('mode').value;
    const response=await api('/api/render',{projectId:state.projectId,mode,profile:mode==='client'?currentProfile():null});
    fillResult(response);
    const gate=response.quality.releaseDecision;
    notice(gate?.status==='blocked'?'Output has blocking content/asset issues.': 'Output generated. Manual review is required; supported-content checks are not visual fidelity.',gate?.status==='blocked');
  }catch(e){notice(e.message,true);}finally{$('generate').disabled=false;}
}
async function init(){
  try{
    const response=await fetch('/api/capabilities');
    if(response.ok){
      const caps=await response.json();
      const list=$('engineReadiness');list.replaceChildren();
      for(const item of caps.engineCapabilities){
        const li=document.createElement('li');
        const title=document.createElement('span');title.textContent=item.name;
        const maturity=document.createElement('em');maturity.textContent=item.maturity;
        li.append(title,maturity);list.append(li);
      }
    }
  }catch { /* Status remains labeled as prototype in sidebar. */ }
  try{
    const r=await fetch('/api/samples'); if(!r.ok)throw new Error('Cannot load samples');
    const data=await r.json();$('sample').replaceChildren();
    for(const sample of data.samples){const o=document.createElement('option');o.value=sample.id;o.textContent=sample.title+' — '+sample.description;$('sample').append(o);}
    $('sample').value='modern-demo';
  }catch(e){notice(e.message,true);}
  $('sample').addEventListener('change',()=>{
    if($('sample').value==='cdph-root-routing-demo'){
      $('sourceRoot').value='https://www.cdph.ca.gov/';
    }
  });
  $('analyze').addEventListener('click',analyze);
  $('generate').addEventListener('click',generate);
  $('rebuild').addEventListener('click',generate);
  $('mode').addEventListener('change',()=>{$('mappingControls').hidden=$('mode').value==='structural';});
  $('primary').addEventListener('input',()=>{$('colorLabel').textContent=$('primary').value;});
  $('sourceFile').addEventListener('change',()=>{$('fileName').textContent=$('sourceFile').files[0]?.name||'No custom file selected';});
  document.querySelectorAll('[data-tab]').forEach(b=>b.addEventListener('click',()=>setTab(b.dataset.tab)));
  $('reviewCss').addEventListener('click',async()=>{
    if(!state.projectId || !state.last) return notice('Generate a page first',true);
    const file=$('cssFile').files[0];
    if(!file || file.size>200000) return notice('Choose a CSS file smaller than 200 KB',true);
    try {
      const mapFile=$('selectorMapFile').files[0];
      if(mapFile && mapFile.size>16000) throw new Error('Selector mapping must be smaller than 16 KB');
      const selectorMap=mapFile?JSON.parse(await mapFile.text()):null;
      const result=await api('/api/css-workbench',{projectId:state.projectId,mode:state.last.mode,css:await file.text(),selectorMap});
      $('cssReviewJson').textContent=JSON.stringify(result.report,null,2);
      notice('CSS review complete. Candidates are included in export but NOT applied to the page.');
    }catch(error){notice(error.message,true);}
  });
  $('copyIr').addEventListener('click',async()=>{try{await navigator.clipboard.writeText($('irJson').textContent);notice('Canonical JSON copied');}catch{notice('Clipboard unavailable; select and copy the JSON manually',true);}});
}
document.addEventListener('DOMContentLoaded',init);
