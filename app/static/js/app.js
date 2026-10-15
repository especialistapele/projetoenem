
// Supabase Auth
const SUPABASE_URL = 'https://evqbhkrjguramcphdjtk.supabase.co';
const SUPABASE_ANON_KEY = window.SUPABASE_ANON_KEY || 'sb_publishable_89zLuZCB-G6wNTSsth1FuA_lRRiIzXk';
window.supabaseClient = null;

async function initAuth(){
  const status = document.getElementById('authStatus');
  if(!window.supabase || !SUPABASE_ANON_KEY){
    if(status) status.textContent = 'Configure SUPABASE_ANON_KEY no .env/build para ativar o login.';
    return;
  }
  window.supabaseClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
  const refresh = async (session) => {
    if(status) status.textContent = session ? ('Conectado: '+(session.user.email||'')) : 'Não autenticado';
  };
  const {data}=await window.supabaseClient.auth.getSession();
  await refresh(data.session);
  window.dispatchEvent(new CustomEvent('supabase-auth-changed'));
  window.supabaseClient.auth.onAuthStateChange((_event, session)=>{ refresh(session); window.dispatchEvent(new CustomEvent('supabase-auth-changed')); });
}
document.getElementById('loginBtn')?.addEventListener('click', async ()=>{
  const email=document.getElementById('loginEmail').value.trim();
  const password=document.getElementById('loginPassword').value;
  if(!window.supabaseClient) return alert('Configure a SUPABASE_ANON_KEY antes de entrar.');
  const {error}=await window.supabaseClient.auth.signInWithPassword({email,password});
  if(error) alert(error.message);
});
document.getElementById('logoutBtn')?.addEventListener('click', async ()=>{
  if(window.supabaseClient) await window.supabaseClient.auth.signOut();
});
initAuth();

const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
let topics=[], programs=[], areas=[], subjects=[], ranking=[];
const api=async(path,opts={})=>{
  opts.headers=opts.headers||{};
  if(window.supabaseClient){
    const {data}=await window.supabaseClient.auth.getSession();
    if(data.session) opts.headers.Authorization='Bearer '+data.session.access_token;
  }
  const r=await fetch(path,opts);if(!r.ok){let msg=await r.text();try{msg=JSON.parse(msg).detail||msg}catch{}throw new Error(msg)}return r.json()};
function esc(v=''){return String(v).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]))}
function setView(name){$$('.view').forEach(v=>v.classList.toggle('active',v.id===name));$$('nav button,[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===name));const names={dashboard:'Visão geral',ranking:'Ranking de prioridade',topics:'Temas',questions:'Banco de questões',graph:'Relações entre temas',validation:'Validação contínua',calibration:'Calibração do modelo',classification:'Classificação',predictions:'Previsões',study:'Plano de estudo',modelAdmin:'Administração do modelo',performance:'Meu desempenho',importer:'Importador ENEM',userManagement:'Usuários e professores'};$('#pageTitle').textContent=names[name]||name}
$$('[data-view]').forEach(b=>b.onclick=()=>setView(b.dataset.view));
function rankingHTML(items,limit=items.length){if(!items?.length)return '<div class="empty">Ainda não há dados suficientes para gerar este ranking.</div>';const max=Math.max(...items.map(x=>Number(x.priority)||0),1);return items.slice(0,limit).map((x,i)=>`<div class="rank-row"><div class="rank-num">${i+1}</div><div><strong>${esc(x.topic_name)}</strong><small class="rank-meta">freq ${Number(x.frequency_score).toFixed(2)} · recência ${Number(x.recency_score).toFixed(2)} · tendência ${Number(x.trend_score).toFixed(2)}</small><div class="bar"><i style="width:${Math.min(100,(Number(x.priority)/max)*100)}%"></i></div></div><div class="rank-score">${Number(x.priority).toFixed(2)}</div></div>`).join('')}
function renderModelSummary(){const top=ranking[0];if(!top){$('#modelSummary').innerHTML='<div class="empty">Selecione um curso para interpretar o ranking.</div>';return}$('#modelSummary').innerHTML=[['Frequência histórica',Number(top.frequency_score).toFixed(2),'média de questões por ano'],['Recência',Number(top.recency_score).toFixed(2),'anos recentes recebem mais peso'],['Tendência',Number(top.trend_score).toFixed(2),'crescimento recente sobre o histórico'],['Peso do curso',Number(top.area_weight).toFixed(2),'priorização da área no curso']].map(x=>`<article><b>${x[1]}</b><strong>${x[0]}</strong><span>${x[2]}</span></article>`).join('')}
async function loadRanking(){
  const id=$('#programSelect').value;
  if(!id){ranking=[];$('#rankingContent').innerHTML='<div class="empty">Selecione um curso para calcular o ranking.</div>';$('#featuredRanking').innerHTML='';$('#topScore').innerHTML='—<small>maior prioridade</small>';renderModelSummary();return}
  try{
    const qs=new URLSearchParams({program_id:id,recency_weight:$('#recencyWeight')?.value||'0.35',trend_weight:$('#trendWeight')?.value||'0.15',recency_decay:$('#recencyDecay')?.value||'0.35'});
    ranking=await api(`/scoring/priority?${qs}`);$('#rankingContent').innerHTML=rankingHTML(ranking);$('#featuredRanking').innerHTML=rankingHTML(ranking,5);$('#topScore').innerHTML=ranking[0]?`${Number(ranking[0].priority).toFixed(2)}<small>${esc(ranking[0].topic_name)}</small>`:'—<small>sem dados</small>';renderModelSummary()
  }catch(e){$('#rankingContent').innerHTML=`<div class="empty">${esc('Não foi possível carregar o ranking: '+e.message)}</div>`}
}

async function loadCatalog(){[areas,subjects]=await Promise.all([api('/catalog/areas'),api('/catalog/subjects')]);$('#areaFilter').innerHTML='<option value="">Todas as áreas</option>'+areas.map(a=>`<option value="${a.id}">${esc(a.name)}</option>`).join('');$('#subjectFilter').innerHTML='<option value="">Todas as disciplinas</option>'+subjects.map(s=>`<option value="${s.id}">${esc(s.name)}</option>`).join('')}
async function loadTopics(){try{topics=await api('/topics');$('#topicsCount').textContent=topics.length;$('#graphTopic').innerHTML='<option value="">Selecione um tema</option>'+topics.map(t=>`<option value="${t.id}">${esc(t.name)}</option>`).join('');renderTopics();fillQuestionFilters()}catch(e){$('#topicsGrid').innerHTML=`<div class="empty">Erro ao carregar temas: ${esc(e.message)}</div>`}}
function renderTopics(){const q=$('#topicSearch').value.toLowerCase(),area=$('#areaFilter').value,subject=$('#subjectFilter').value;const areaBySubject=Object.fromEntries(subjects.map(s=>[s.id,s.knowledge_area_id]));const items=topics.filter(t=>t.name.toLowerCase().includes(q)&&(!area||String(areaBySubject[t.subject_id])===area)&&(!subject||String(t.subject_id)===subject));$('#topicsGrid').innerHTML=items.map(t=>`<article class="card"><small>Tema #${t.id}</small><h3>${esc(t.name)}</h3><p>${esc(t.description||'Tema classificado no histórico disponível.')}</p><div class="card-actions"><button onclick="showTopic(${t.id})">Ver frequência</button><button onclick="openGraph(${t.id})">Relações</button></div></article>`).join('')||'<div class="empty">Nenhum tema encontrado.</div>'}
window.showTopic=async id=>{try{const [rows,analytics]=await Promise.all([api(`/topics/${id}/frequency`),api(`/analytics/topics/${id}`)]);const name=topics.find(t=>t.id===id)?.name||'Tema';$('#topicsGrid').insertAdjacentHTML('afterbegin',`<div class="frequency-panel"><div><strong>${esc(name)}</strong><button onclick="this.parentElement.parentElement.remove()">Fechar</button></div><div class="mini-chart">${rows.map(r=>`<div title="${r.year}: ${r.question_count}" style="height:${Math.max(8,Number(r.question_count)*18)}px"><span>${r.year}</span></div>`).join('')}</div><div class="topic-metrics"><span>Frequência ${Number(analytics.frequency||0).toFixed(2)}</span><span>Recência ${Number(analytics.recency||0).toFixed(2)}</span><span>Tendência ${Number(analytics.trend||0).toFixed(2)}</span></div></div>`)}catch(e){alert('Não foi possível carregar a análise do tema: '+e.message)}};
window.openGraph=id=>{$('#graphTopic').value=String(id);setView('graph');loadGraph()};
async function loadPrograms(){try{programs=await api('/programs');$('#programsCount').textContent=programs.length;$('#programSelect').innerHTML='<option value="">Selecione um curso</option>'+programs.map(p=>`<option value="${p.id}">${esc(p.institution?.name||'Instituição')} · ${esc(p.name)}</option>`).join('')}catch(e){$('#programSelect').innerHTML='<option>Erro ao carregar cursos</option>'}}
async function loadQuestionStats(){try{const data=await api('/api/stats');$('#questionsCount').textContent=data.questions}catch(e){$('#questionsCount').textContent='—'}}
let questionPage=0, questionTotal=0, questionPageSize=20;
function fillQuestionFilters(){
  const years=[...new Set((window.__questionYears||[]))].sort((a,b)=>b-a);
  $('#questionYear').innerHTML='<option value="">Todos os anos</option>'+years.map(y=>`<option value="${y}">${y}</option>`).join('');
  $('#questionSubject').innerHTML='<option value="">Todas as disciplinas</option>'+subjects.map(x=>`<option value="${x.id}">${esc(x.name)}</option>`).join('');
  $('#questionTopic').innerHTML='<option value="">Todos os temas</option>'+topics.map(x=>`<option value="${x.id}">${esc(x.name)}</option>`).join('');
}
async function loadQuestions(page=0){
  questionPage=page; const term=$('#questionSearch').value.trim(), params=new URLSearchParams({limit:String(questionPageSize),offset:String(page*questionPageSize)});
  if($('#questionYear').value)params.set('year',$('#questionYear').value); if($('#questionSubject').value)params.set('subject_id',$('#questionSubject').value); if($('#questionTopic').value)params.set('topic_id',$('#questionTopic').value);
  $('#questionsList').innerHTML='<div class="empty">Carregando questões…</div>';
  try{
    let data;
    if(term && !$('#questionYear').value && !$('#questionSubject').value && !$('#questionTopic').value){const rows=await api(`/questions/search?term=${encodeURIComponent(term)}&limit=${questionPageSize}`); data={items:rows,total:rows.length,limit:questionPageSize,offset:0,search:true}}
    else {if(term)params.set('term',term); data=await api(`/questions?${params}`);}
    questionTotal=Number(data.total||0); const items=data.items||[];
    $('#questionsList').innerHTML=items.map(x=>`<article class="question"><small>Questão ${x.number} · ${x.year||x.exam?.year||'—'} · ${data.search?'relevância '+Number(x.rank||0).toFixed(2):'ID '+x.id}</small><p>${esc(x.statement_text)}</p><button class="question-open" data-id="${x.id}">Abrir questão</button></article>`).join('')||'<div class="empty">Nenhuma questão encontrada.</div>';
    $$('.question-open').forEach(b=>b.onclick=()=>openQuestion(Number(b.dataset.id)));
    renderQuestionPager(Boolean(data.search));
  }catch(e){$('#questionsList').innerHTML=`<div class="empty">Erro: ${esc(e.message)}</div>`;$('#questionPager').innerHTML=''}
}
function renderQuestionPager(search=false){if(search||questionTotal<=questionPageSize){$('#questionPager').innerHTML=questionTotal?`<span>${questionTotal} resultado(s)</span>`:'';return}const pages=Math.ceil(questionTotal/questionPageSize);$('#questionPager').innerHTML=`<button ${questionPage===0?'disabled':''} onclick="loadQuestions(${questionPage-1})">← Anterior</button><span>Página ${questionPage+1} de ${pages}</span><button ${questionPage>=pages-1?'disabled':''} onclick="loadQuestions(${questionPage+1})">Próxima →</button>`}
async function openQuestion(id){try{const d=await api(`/questions/${id}`),q=d.question||{};const topicsText=(d.topics||[]).map(t=>`#${t.topic_id}`).join(', ')||'Nenhum';const alts=(q.alternatives||[]).map(a=>`<div class="alternative"><b>${esc(a.letter)}</b><span>${esc(a.text)}</span></div>`).join('');const el=document.createElement('div');el.className='modal-backdrop';el.innerHTML=`<div class="modal"><button class="modal-close">×</button><p class="eyebrow">QUESTÃO ${q.number} · ${q.exam?.year||'—'}</p><h2>${esc(q.statement_text)}</h2><p class="note">Temas vinculados: ${esc(topicsText)}</p><div class="alternatives">${alts||'<div class="empty">Alternativas não disponíveis.</div>'}</div><div class="actions">${(q.alternatives||[]).map(a=>`<button data-answer="${esc(a.letter)}">Responder ${esc(a.letter)}</button>`).join('')}</div></div>`;document.body.appendChild(el);el.querySelector('.modal-close').onclick=()=>el.remove();el.querySelectorAll('[data-answer]').forEach(btn=>btn.onclick=async()=>{try{const r=await api('/student/attempts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question_id:id,selected_letter:btn.dataset.answer})});btn.textContent=r.is_correct?'✓ Correta':'✕ Incorreta';btn.disabled=true;loadPerformance()}catch(e){alert(e.message)}});el.onclick=e=>{if(e.target===el)el.remove()}}catch(e){alert('Não foi possível abrir a questão: '+e.message)}}
function searchQuestions(){loadQuestions(0)}

async function loadGraph(){const id=$('#graphTopic').value;if(!id)return;$('#graphContent').innerHTML='<div class="empty">Carregando relações...</div>';try{const edges=await api(`/topics/${id}/edges`);const topic=topics.find(t=>t.id==id);if(!edges.length){$('#graphContent').innerHTML='<div class="empty">Este tema não possui relações registradas.</div>';return}const nodes=[{id:Number(id),name:topic?.name||`Tema #${id}`,center:true}];edges.forEach(e=>{const other=e.topic_a_id==id?e.topic_b_id:e.topic_a_id;if(!nodes.some(n=>n.id===other))nodes.push({id:other,name:topics.find(t=>t.id===other)?.name||`Tema #${other}`})});const w=760,h=420,cx=380,cy=205,r=155;const pos=nodes.map((n,i)=>({...n,x:n.center?cx:cx+r*Math.cos((i-1)*2*Math.PI/(nodes.length-1)-Math.PI/2),y:n.center?cy:cy+r*Math.sin((i-1)*2*Math.PI/(nodes.length-1)-Math.PI/2)}));const lines=edges.map(e=>{const a=pos.find(n=>n.id===e.topic_a_id),b=pos.find(n=>n.id===e.topic_b_id);return a&&b?`<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="currentColor" stroke-opacity=".25" stroke-width="${Math.max(1,Math.min(6,Number(e.weight)||1))}"/>`:''}).join('');const circles=pos.map(n=>`<g><circle cx="${n.x}" cy="${n.y}" r="${n.center?30:24}" class="node ${n.center?'node-center':''}"/><text x="${n.x}" y="${n.y+4}" text-anchor="middle">${esc(n.name.length>18?n.name.slice(0,16)+'…':n.name)}</text></g>`).join('');$('#graphContent').innerHTML=`<div class="graph-wrap"><svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Grafo de relações de ${esc(topic?.name||'tema')}">${lines}${circles}</svg><div class="graph-legend"><strong>${esc(topic?.name||'Tema')}</strong><span>${edges.length} relações · pesos representam força da conexão</span></div></div>`}catch(e){$('#graphContent').innerHTML=`<div class="empty">Erro: ${esc(e.message)}</div>`}}
async function runBacktest(){const id=$('#programSelect').value;$('#backtestContent').innerHTML='<div class="empty">Calculando...</div>';try{const qs=new URLSearchParams({top_k:'5',min_years:'2'});if(id)qs.set('program_id',id);const d=await api(`/analytics/backtest?${qs}`);const hybrid=d.hybrid||{};const baseline=d.baseline||{};$('#backtestContent').innerHTML=`<div class="backtest-score"><b>${(Number(hybrid.hit_rate||d.hit_rate||0)*100).toFixed(1)}%</b><span>hit rate híbrido · top ${d.top_k}</span></div><div class="backtest-metrics"><span>Baseline ${(Number(baseline.hit_rate||0)*100).toFixed(1)}%</span><span>Precision@K ${(Number(hybrid.precision_at_k||0)*100).toFixed(1)}%</span><span>Recall@K ${(Number(hybrid.recall_at_k||0)*100).toFixed(1)}%</span></div><div class="backtest-years">${d.results.map(r=>`<div><strong>${r.year}</strong><span class="${r.hybrid?.hit?'hit':'miss'}">${r.hybrid?.hit?'acerto':'sem acerto'}</span></div>`).join('')||'<div class="empty">Dados insuficientes para avaliar.</div>'}</div><p class="note">${esc(d.note)}</p>`}catch(e){$('#backtestContent').innerHTML=`<div class="empty">Erro: ${esc(e.message)}</div>`}}
async function health(){try{const h=await api('/api/health');$('#apiStatus').textContent=h.database?'● API conectada':'● API sem banco';$('#apiHealth').textContent=h.database?'OK':'DEGRADED'}catch(e){$('#apiStatus').textContent='● API indisponível';$('#apiHealth').textContent='OFF'}}
async function runCalibration(){
  $('#calibrationContent').innerHTML='<div class="empty">Testando combinações de pesos…</div>';
  try{
    const d=await api('/analytics/calibrate?top_k=5&min_years=2');
    const b=d.best;
    if(!b){$('#calibrationContent').innerHTML='<div class="empty">Dados insuficientes para calibrar.</div>';return}
    const rows=(d.candidates||[]).slice(0,8).map(x=>`<div><strong>recência ${Number(x.recency_weight).toFixed(2)}</strong><span>tendência ${Number(x.trend_weight).toFixed(2)} · hit rate ${(Number(x.hit_rate)*100).toFixed(1)}%</span></div>`).join('');
    $('#calibrationContent').innerHTML=`<div class="backtest-score"><b>${(Number(b.hit_rate)*100).toFixed(1)}%</b><span>melhor hit rate · ${b.evaluated_years} ano(s) avaliados</span></div><div class="backtest-metrics"><span>Recência ${Number(b.recency_weight).toFixed(2)}</span><span>Tendência ${Number(b.trend_weight).toFixed(2)}</span><span>Top ${5}</span></div><div class="backtest-years">${rows}</div><p class="note">A calibração é exploratória e não altera os parâmetros automaticamente.</p>`;
  }catch(e){$('#calibrationContent').innerHTML=`<div class="empty">Erro: ${esc(e.message)}</div>`}
}
async function runDiagnostics(){
  $('#diagnosticsContent').innerHTML='<div class="empty">Verificando…</div>';
  try{const d=await api('/api/diagnostics');const c=d.checks||{};$('#diagnosticsContent').innerHTML=`<div class="backtest-metrics"><span>Banco: ${d.database?'OK':'FALHA'}</span><span>Provas ${c.exams??'—'}</span><span>Questões ${c.questions??'—'}</span><span>Temas ${c.topics??'—'}</span><span>Frequências ${c.topic_year_frequency??'—'}</span><span>Ranking ${c.ranking_inputs?'OK':'incompleto'}</span></div>${d.error?`<p class="note">${esc(d.error)}</p>`:''}`}catch(e){$('#diagnosticsContent').innerHTML=`<div class="empty">Erro: ${esc(e.message)}</div>`}
}
$('#runCalibration').onclick=runCalibration;$('#runDiagnostics').onclick=runDiagnostics;
$('#programSelect').onchange=async()=>{await loadRanking();try{await api('/student/program',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({program_id:Number($('#programSelect').value)||null})})}catch(e){console.warn(e)}}; $('#applyModel').onclick=loadRanking; ['recencyWeight','trendWeight','recencyDecay'].forEach(id=>{const el=$('#'+id);el?.addEventListener('input',()=>{const out={'recencyWeight':'recencyValue','trendWeight':'trendValue','recencyDecay':'decayValue'}[id];$('#'+out).textContent=Number(el.value).toFixed(2)})});$('#topicSearch').oninput=renderTopics;$('#areaFilter').onchange=renderTopics;$('#subjectFilter').onchange=renderTopics;$('#searchQuestions').onclick=searchQuestions;$('#questionSearch').addEventListener('keydown',e=>{if(e.key==='Enter')searchQuestions()});['questionYear','questionSubject','questionTopic'].forEach(id=>$('#'+id)?.addEventListener('change',()=>loadQuestions(0)));$('#loadGraph').onclick=loadGraph;$('#runBacktest').onclick=runBacktest;
Promise.all([health(),loadCatalog(),loadTopics(),loadPrograms(),loadQuestionStats()]).then(async()=>{try{const me=await api('/student/program');if(me.program_id)$('#programSelect').value=me.program_id;}catch(e){if(programs.length)$('#programSelect').value=programs[0].id}if($('#programSelect').value)loadRanking()});

/* Importador ENEM */
let importItems=[];
function initImportYears(){
  const opts=Array.from({length:28},(_,i)=>2025-i).map(y=>`<option value="${y}">${y}</option>`).join('');
  $('#importYearStart').innerHTML=opts; $('#importYearEnd').innerHTML=opts;
}
function formatBytes(v){const n=Number(v)||0; if(n<1024*1024)return (n/1024).toFixed(1)+' KB'; return (n/1024/1024).toFixed(2)+' MB';}
async function loadImportQuota(){
  const el=document.getElementById('importQuota'); if(!el)return;
  try{const q=await api('/enem-import/storage-quota');
    const used=formatBytes(q.used_bytes), limit=formatBytes(q.limit_bytes), remain=formatBytes(q.remaining_bytes);
    const state=q.status==='blocked'?'LIMITE ATINGIDO':q.status==='warning'?'ALERTA DE ESPAÇO':'ESPAÇO OK';
    el.innerHTML=`<strong>${used} / ${limit}</strong><span>${Number(q.usage_percent||0).toFixed(1)}% usado · ${remain} disponível · ${state}</span>`;
  }catch(e){el.textContent='Não foi possível consultar o espaço de importação.'}
}
function importItemHTML(x,i){
  const state=x.status==='available'?'disponível':x.status==='catalog'?'catálogo':'não encontrado';
  const cls=x.status==='available'?'ok':x.status==='catalog'?'catalog':'bad';
  const label=x.document_type==='catalog'?'Catálogo oficial':`${esc(x.document_type)} · ${esc(x.color||'—')}`;
  return `<div class="import-row ${cls}">
    <input type="checkbox" class="import-check" data-index="${i}" ${x.status==='available'?'checked':''} ${x.status!=='available'?'disabled':''}>
    <div><strong>${x.year}${x.day?` · Dia ${x.day}`:''}</strong><span>${label}</span></div>
    <div class="import-file">${esc(x.filename||'RIEP — seleção manual')}</div>
    <span class="import-status">${state}${x.special_version?' · versão especial':''}</span>
    <a href="${esc(x.source_url)}" target="_blank" rel="noopener">Fonte oficial ↗</a>
  </div>`
}
async function discoverImports(){
  const a=Number($('#importYearStart').value),b=Number($('#importYearEnd').value);
  const summary=$('#importSummary'); summary.textContent='Consultando o catálogo oficial...';
  $('#importFiles').innerHTML='<div class="empty">Buscando arquivos oficiais…</div>';
  try{
    const d=await api('/enem-import/discover',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({year_start:a,year_end:b,application:$('#importApplication').value})});
    importItems=d.items||[];
    if($('#onlyAvailable').checked) importItems=importItems.filter(x=>x.status==='available'||x.status==='catalog');
    $('#importFiles').innerHTML=importItems.map(importItemHTML).join('')||'<div class="empty">Nenhum arquivo encontrado.</div>';
    summary.textContent=`${importItems.length} item(ns) encontrado(s). 2025 possui URLs diretas; outros anos usam o catálogo RIEP para seleção segura.`;
  }catch(e){summary.textContent='Erro na busca';$('#importFiles').innerHTML=`<div class="empty">${esc(e.message)}</div>`}
}
async function downloadSelected(){
  const selected=[...document.querySelectorAll('.import-check:checked')].map(c=>importItems[Number(c.dataset.index)]).filter(x=>x?.status==='available' && x?.selectable!==false);
  if(!selected.length){alert('Selecione pelo menos um PDF disponível.');return}
  const btn=$('#downloadSelected');btn.disabled=true;btn.textContent='Baixando…';
  let done=0,errors=0;
  for(const item of selected){
    try{await api('/enem-import/download',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(item)});done++}
    catch(e){errors++}
  }
  btn.disabled=false;btn.textContent='⬇ Baixar selecionados';
  $('#importSummary').textContent=`Download concluído: ${done} arquivo(s), ${errors} erro(s).`;
  loadManifest();
}
async function parseSelected(){
  const d=await api('/enem-import/manifest'); const items=d.items||[];
  if(!items.length){alert('Baixe primeiro pelo menos um PDF.');return}
  const btn=$('#parseSelected');btn.disabled=true;btn.textContent='⚙ Extraindo…';
  let ok=0,errors=0;
  for(const item of items){
    try{await api('/enem-import/parse',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({storage_path:item.storage_path,document_type:item.document_type})});ok++}
    catch(e){errors++}
  }
  btn.disabled=false;btn.textContent='⚙ Extrair selecionados';
  $('#importSummary').textContent=`Extração concluída: ${ok} arquivo(s), ${errors} erro(s).`;
  loadManifest();
}
async function loadManifest(){
  try{
    const d=await api('/enem-import/manifest');
    await loadImportQuota();\n    $('#importManifest').innerHTML=(d.items||[]).map(x=>`<div class="manifest-row"><div><strong>${esc(x.original_filename||x.filename)}</strong><span>${x.year} · dia ${x.day||'—'} · ${esc(x.color||'—')} · ${esc(x.document_type)} · ${esc(x.status||'')}</span></div><code>${esc(x.sha256||'')}</code><span>${((Number(x.file_size_bytes)||0)/1024/1024).toFixed(2)} MB${x.special_version?' · especial':''}</span></div>`).join('')||'<div class="empty">Nenhum arquivo baixado.</div>';
  }catch(e){$('#importManifest').innerHTML=`<div class="empty">${esc(e.message)}</div>`}
}
$('#discoverImports').onclick=discoverImports;
$('#downloadSelected').onclick=downloadSelected;
$('#refreshManifest').onclick=loadManifest;
$('#parseSelected').onclick=parseSelected;
initImportYears(); loadImportQuota();


async function preflightImport(){
  const box=$('#preparedImport'); box.innerHTML='<div class="empty">Auditando staging…</div>';
  try{
    const d=await api('/enem-import/preflight',{method:'POST'});
    const groups=d.groups||[];
    box.innerHTML=`<div class="backtest-metrics"><span>Status ${esc(d.status)}</span><span>Grupos ${d.count}</span><span>Prontos ${groups.filter(g=>g.status==='ready').length}</span><span>Revisão ${groups.filter(g=>g.status!=='ready').length}</span></div>${groups.map(g=>`<div class="manifest-row"><div><strong>${esc(String(g.key))}</strong><span>${g.provas} prova(s) · ${g.gabaritos} gabarito(s) · ${g.questions} questões · ${g.answers} respostas</span></div><span>${esc(g.status)}</span></div>`).join('')||'<div class="empty">Nenhum PDF parseado no staging.</div>'}`;
  }catch(e){box.innerHTML=`<div class="empty">Erro: ${esc(e.message)}</div>`}
}
$('#preflightImport').onclick=preflightImport;

/* Pipeline de staging -> lote -> banco */
async function prepareImport(){
  $('#preparedImport').innerHTML='<div class="empty">Consolidando cadernos e gabaritos…</div>';
  try{
    const d=await api('/enem-import/prepare',{method:'POST'});
    const groups=d.groups||[];
    $('#preparedImport').innerHTML=`<div class="backtest-metrics"><span>Grupos ${d.groups}</span><span>Questões ${d.questions}</span><span>Com gabarito ${d.questions_with_answer}</span><span>Sem gabarito ${d.questions_without_answer}</span></div>${groups.map(g=>`<div class="manifest-row"><div><strong>${g.year} · dia ${g.day||'—'} · ${esc(g.color||'—')}</strong><span>${g.questions} questões · ${g.answers} respostas · ${g.matched_answers} associadas</span></div><span>${esc(g.status)}</span></div>`).join('')||'<div class="empty">Nenhum caderno parseado encontrado.</div>'}`;
  }catch(e){$('#preparedImport').innerHTML=`<div class="empty">Erro: ${esc(e.message)}</div>`}
}
async function importPrepared(dry){
  const btn=dry?$('#dryRunImport'):$('#commitImport'); btn.disabled=true; btn.textContent=dry?'Simulando…':'Gravando…';
  try{
    const r=await api('/enem-import/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({dry_run:dry})});
    $('#preparedImport').insertAdjacentHTML('afterbegin',`<p class="note">${dry?'Simulação concluída':'Importação concluída'} para ${esc(r.dataset_path)}.</p>`);
    if(!dry){await loadQuestionStats();await loadTopics();}
  }catch(e){alert(e.message)}finally{btn.disabled=false;btn.textContent=dry?'🔍 Simular importação':'💾 Gravar no banco'}
}
$('#prepareImport').onclick=prepareImport;
$('#dryRunImport').onclick=()=>importPrepared(true);
$('#commitImport').onclick=()=>importPrepared(false);

/* Classificação auditável */
async function loadClassification(){
  try{
    const status=$('#candidateStatus')?.value||'';
    const d=await api('/classification/candidates'+(status?'?status='+encodeURIComponent(status):''));
    $('#classificationList').innerHTML=(d.items||[]).map(c=>`<div class="question-card"><div><strong>Questão #${c.question_id} · confiança ${Math.round(Number(c.confidence||0)*100)}%</strong><p>${esc(c.statement||'')}</p><span>${esc(c.area||'Sem área')} · ${esc(c.discipline||'Sem disciplina')} · ${esc(c.status)}</span></div><div class="actions"><button onclick="decideClassification(${c.id},'accepted')">✓ Aceitar</button><button onclick="decideClassification(${c.id},'rejected')">✕ Rejeitar</button><button onclick="decideClassification(${c.id},'review')">Revisar</button></div></div>`).join('')||'<div class="empty">Nenhum candidato encontrado.</div>';
    const m=await api('/classification/coverage');
    $('#classificationMetrics').innerHTML=`<span>Questões ${m.total_questions}</span><span>Classificadas ${Math.round(m.classification_rate*100)}%</span><span>Alta confiança ${Math.round(m.high_confidence_rate*100)}%</span><span>Modo ${esc(m.mode)}</span>`;
  }catch(e){$('#classificationList').innerHTML=`<div class="empty">${esc(e.message)}</div>`}
}
async function generateCandidates(){
  const b=$('#generateCandidates');b.disabled=true;b.textContent='Gerando…';
  try{const r=await api('/classification/generate-candidates?limit=1000',{method:'POST'});alert(`Processadas ${r.processed}. Novos candidatos: ${r.created}.`);await loadClassification()}catch(e){alert(e.message)}finally{b.disabled=false;b.textContent='Gerar candidatos'}
}
async function decideClassification(id,status){
  try{await api('/classification/candidates/'+id,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({status})});await loadClassification()}catch(e){alert(e.message)}
}
$('#generateCandidates').onclick=generateCandidates;$('#refreshCandidates').onclick=loadClassification;$('#candidateStatus').onchange=loadClassification;

/* Motor preditivo */
function renderPredictions(items){
  if(!items?.length) return '<div class="empty">Ainda não há previsão disponível para este curso.</div>';
  return items.map(x=>{const p=Number(x.probability||0)*100,f=x.factors||{};return `<div class="rank-row"><div class="rank-num">${x.rank}</div><div><strong>${esc(x.topic_name||'Tema')}</strong><small class="rank-meta">probabilidade ${p.toFixed(2)}% · score ${Number(x.score||0).toFixed(3)}</small><div class="bar"><i style="width:${Math.min(100,p)}%"></i></div><small class="rank-meta">freq ${Number(f.frequency||0).toFixed(2)} · recência ${Number(f.recency||0).toFixed(2)} · tendência ${Number(f.trend||0).toFixed(2)} · grafo ${Number(f.graph_score||0).toFixed(2)}</small></div><div class="rank-score">${p.toFixed(1)}%</div></div>`}).join('')
}
async function generatePredictions(){
  const id=$('#programSelect').value; if(!id){alert('Selecione um curso primeiro.');return}
  const b=$('#generatePredictions');b.disabled=true;b.textContent='Calculando…';$('#predictionList').innerHTML='<div class="empty">Calculando previsão…</div>';
  try{const q=new URLSearchParams({program_id:id,recency_weight:$('#recencyWeight')?.value||'0.35',trend_weight:$('#trendWeight')?.value||'0.15',recency_decay:$('#recencyDecay')?.value||'0.35'});const items=await api('/scoring/predict?'+q,{method:'POST'});$('#predictionList').innerHTML=renderPredictions(items);$('#predictionSummary').innerHTML=`<span>${items.length} temas previstos</span><span>Modelo ${esc(items[0]?.model_version||'predictor-v2')}</span><span>Top ${items[0]?(Number(items[0].probability)*100).toFixed(2):'0.00'}%</span>`}catch(e){$('#predictionList').innerHTML=`<div class="empty">Erro: ${esc(e.message)}</div>`}finally{b.disabled=false;b.textContent='Gerar previsão'}
}
$('#generatePredictions').onclick=generatePredictions;


/* Plano de estudo */
function renderStudyPlan(items){if(!items?.length)return '<div class="empty">Gere uma previsão primeiro para montar o plano.</div>';return items.map(x=>`<div class="question-card"><div><strong>#${x.rank} · ${esc(x.topic_name||'Tema')}</strong><span>${(Number(x.prediction_probability)*100).toFixed(2)}% previsão · ${(Number(x.student_accuracy)*100).toFixed(1)}% desempenho · ${esc(x.recommendation)}</span><div class="question-list">${(x.questions||[]).map(q=>`<div class="question"><small>${q.year} · questão ${q.number}</small><p>${esc(q.statement)}</p><button class="question-open" onclick="openQuestion(${q.id})">Abrir questão</button></div>`).join('')||'<div class="empty">Ainda não há questões vinculadas.</div>'}</div></div></div>`).join('')}
async function loadStudyPlan(){const id=$('#programSelect').value;if(!id){alert('Selecione um curso primeiro.');return}try{const items=await api(`/student/study-plan?program_id=${id}&limit=10`);$('#studyList').innerHTML=renderStudyPlan(items);$('#studySummary').innerHTML=`<span>${items.length} prioridades</span><span>Curso selecionado</span><span>Questões sugeridas por tema</span>`}catch(e){$('#studyList').innerHTML=`<div class="empty">Erro: ${esc(e.message)}</div>`}}
$('#loadStudyPlan').onclick=loadStudyPlan;
async function loadAdminUsers(){
  try{
    const [users,teachers]=await Promise.all([api('/admin/users'),api('/admin/teachers')]);
    const students=users.filter(u=>u.role==='student');
    $('#adminUsersList').innerHTML=users.map(u=>`<div><strong>${esc(u.display_name||u.email)}</strong><span>${esc(u.email)} · ${u.role} · curso ${u.program_id||'—'}</span></div>`).join('')||'<div class="empty">Nenhum usuário cadastrado.</div>';
    $('#adminTeacherSelect').innerHTML='<option value="">Selecione um professor</option>'+teachers.map(t=>`<option value="${t.user_id}">${esc(t.display_name||t.email)} · ${t.student_count} aluno(s)</option>`).join('');
    $('#adminStudentSelect').innerHTML='<option value="">Selecione um aluno</option>'+students.map(t=>`<option value="${t.user_id}">${esc(t.display_name||t.email)}</option>`).join('');
    $('#adminUserProgram').innerHTML='<option value="">Sem curso</option>'+programs.map(p=>`<option value="${p.id}">${esc(p.name)}</option>`).join('');
  }catch(e){$('#adminUsersList').innerHTML=`<div class="empty">${esc(e.message)}</div>`}
}
async function loadAssignments(){const tid=$('#adminTeacherSelect')?.value;if(!tid)return;try{const rows=await api('/admin/teachers/'+tid+'/students');$('#teacherAssignments').innerHTML=rows.map(r=>`<div><strong>${esc(r.display_name||r.email)}</strong><span>${esc(r.email)}</span><button onclick="unassignStudent('${tid}','${r.user_id}')">Remover</button></div>`).join('')||'<div class="empty">Nenhum aluno vinculado.</div>'}catch(e){$('#teacherAssignments').innerHTML=`<div class="empty">${esc(e.message)}</div>`}}
window.unassignStudent=async(t,s)=>{try{await api(`/admin/teachers/${t}/students/${s}`,{method:'DELETE'});await loadAssignments();await loadAdminUsers()}catch(e){alert(e.message)}};
$('#refreshAdminUsers')?.addEventListener('click',loadAdminUsers);
$('#adminTeacherSelect')?.addEventListener('change',loadAssignments);
$('#assignStudent')?.addEventListener('click',async()=>{const t=$('#adminTeacherSelect').value,s=$('#adminStudentSelect').value;if(!t||!s)return alert('Selecione professor e aluno.');try{await api(`/admin/teachers/${t}/students`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({student_id:s,active:true})});await loadAssignments();await loadAdminUsers()}catch(e){alert(e.message)}});
$('#createAdminUser')?.addEventListener('click',async()=>{const payload={email:$('#adminUserEmail').value.trim(),password:$('#adminUserPassword').value,role:$('#adminUserRole').value,display_name:$('#adminUserName').value.trim(),program_id:$('#adminUserProgram').value?Number($('#adminUserProgram').value):null};try{await api('/admin/users',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});alert('Conta criada com sucesso.');$('#adminUserPassword').value='';await loadAdminUsers()}catch(e){alert(e.message)}});


/* Desempenho do estudante */
async function loadPerformance(){
  try{
    const d=await api('/student/performance');
    const s=d.summary||{};
    $('#performanceSummary').innerHTML=`<span>${s.attempts||0} respostas</span><span>${s.correct||0} acertos</span><span>${(Number(s.accuracy||0)*100).toFixed(1)}% de aproveitamento</span>`;
    const rows=d.topics||[];
    $('#performanceList').innerHTML=rows.map(x=>`<div class="rank-row"><div class="rank-num">${Math.round(Number(x.accuracy||0)*100)}%</div><div><strong>${esc(x.topic_name||'Tema')}</strong><small class="rank-meta">${x.attempt_count} tentativa(s) · ${x.correct_count} acerto(s)</small><div class="bar"><i style="width:${Math.min(100,Number(x.accuracy||0)*100)}%"></i></div></div><div class="rank-score">${Number(x.accuracy||0)*100<50?'Reforçar':'Manter'}</div></div>`).join('')||'<div class="empty">Você ainda não respondeu questões.</div>';
  }catch(e){$('#performanceList').innerHTML=`<div class="empty">${esc(e.message)}</div>`}
}
$('#refreshPerformance').onclick=loadPerformance;

/* Administração do modelo */
async function loadModels(){try{const [configs,runs]=await Promise.all([api('/model/configs'),api('/model/runs')]);$('#modelList').innerHTML=configs.map(c=>`<div class="question-card"><div><strong>${esc(c.name)} · ${esc(c.version)}</strong><p>Freq ${c.frequency_weight.toFixed(2)} · Rec ${c.recency_weight.toFixed(2)} · Tend ${c.trend_weight.toFixed(2)} · Grafo ${c.graph_weight.toFixed(2)}</p><span>${c.active?'● Ativo':'Inativo'}</span></div>${c.active?'':'<button onclick="activateModel('+c.id+')">Ativar</button>'}</div>`).join('')||'<div class="empty">Nenhum modelo cadastrado.</div>';$('#modelRuns').innerHTML=runs.map(r=>`<div class="question-card"><strong>Execução #${r.id} · ${esc(r.model_version)}</strong><span>Status: ${esc(r.status)} · temas ${r.topic_count} · questões ${r.question_count}</span></div>`).join('')||'<div class="empty">Nenhuma execução registrada.</div>'}catch(e){$('#modelList').innerHTML=`<div class="empty">${esc(e.message)}</div>`}}
window.activateModel=async id=>{try{await api(`/model/configs/${id}/activate`,{method:'POST'});loadModels()}catch(e){alert(e.message)}};
$('#refreshModels').onclick=loadModels;$('#createModel').onclick=async()=>{const payload={name:$('#modelName').value.trim(),version:$('#modelVersion').value.trim(),frequency_weight:Number($('#modelFrequency').value),recency_weight:Number($('#modelRecency').value),trend_weight:Number($('#modelTrend').value),graph_weight:Number($('#modelGraph').value),active:false};try{await api('/model/configs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});await loadModels();alert('Modelo criado.')}catch(e){alert(e.message)}};
loadModels();

if(window.supabaseClient) loadPerformance();

/* Simulados, redação e evolução */
const lineChart=(items,valueKey,labelKey)=>{
  if(!items?.length || !items.some(x=>x[valueKey]!=null)) return '<div class="empty">Ainda não há resultados.</div>';
  const vals=items.map(x=>Number(x[valueKey]||0)); const max=Math.max(...vals,1), w=520,h=190,p=28;
  const pts=items.map((x,i)=>`${p+i*((w-2*p)/Math.max(items.length-1,1))},${h-p-(Number(x[valueKey]||0)/max)*(h-2*p)}`).join(' ');
  return `<svg viewBox="0 0 ${w} ${h}" class="chart-svg" preserveAspectRatio="none"><polyline points="${pts}" fill="none" stroke="url(#g)" stroke-width="3"/><defs><linearGradient id="g" x1="0" x2="1"><stop offset="0" stop-color="#22d3ee"/><stop offset="1" stop-color="#8b5cf6"/></linearGradient></defs>${items.map((x,i)=>{const cx=p+i*((w-2*p)/Math.max(items.length-1,1)),cy=h-p-(Number(x[valueKey]||0)/max)*(h-2*p);return `<circle cx="${cx}" cy="${cy}" r="4" fill="#22d3ee"/><text x="${cx}" y="${h-8}" text-anchor="middle">${esc(x[labelKey]||i+1)}</text><text x="${cx}" y="${Math.max(14,cy-9)}" text-anchor="middle">${Number(x[valueKey]||0).toFixed(0)}</text>`}).join('')}</svg>`;
};
async function loadDashboardHistory(){try{const d=await api('/learning/dashboard/history');$('#simulationChart').innerHTML=lineChart(d.simulations,'estimated_score','sequence');$('#essayChart').innerHTML=lineChart(d.essays,'score','title')}catch(e){if($('#simulationChart'))$('#simulationChart').innerHTML='<div class="empty">Entre para acompanhar sua evolução.</div>'}}
async function loadSimulations(){try{const rows=await api('/learning/simulations');$('#simulationCards').innerHTML=rows.map(s=>`<article class="card"><small>Simulado ${s.sequence}</small><h3>${esc(s.title)}</h3><p>${s.question_count} questões · ${esc(s.status)}</p><button onclick="openSimulation(${s.id})">Abrir</button></article>`).join('')||'<div class="empty">Nenhum simulado cadastrado.</div>'}catch(e){$('#simulationCards').innerHTML='<div class="empty">'+esc(e.message)+'</div>'}}
window.openSimulation=async id=>{try{const d=await api(`/learning/simulations/${id}/questions`);$('#simulationResult').style.display='block';$('#simulationResult').innerHTML=`<h3>Simulado</h3>${d.length?d.slice(0,1).map(q=>`<div class="question-card"><strong>Questão ${q.number}</strong><p>${esc(q.statement_text||'')}</p>${q.alternatives.map(a=>`<button onclick="answerSimulation(${id},${q.question_id},'${a.letter}')">${a.letter}) ${esc(a.text)}</button>`).join('')}</div>`).join(''):'<div class="empty">O simulado ainda não foi gerado pelo administrador.</div>'}`}catch(e){alert(e.message)}};
window.answerSimulation=async(sid,qid,letter)=>{try{await api(`/learning/simulations/${sid}/answer`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question_id:qid,selected_letter:letter})});alert('Resposta registrada.');}catch(e){alert(e.message)}};
$('#seedSimulations')?.addEventListener('click',async()=>{try{await api('/learning/simulations/seed',{method:'POST'});await loadSimulations();}catch(e){alert('Somente o administrador pode criar o ciclo: '+e.message)}});
async function loadEssays(){try{const rows=await api('/learning/essays');$('#essayHistory').innerHTML=rows.map(e=>`<div><strong>${esc(e.title)}</strong><span>${new Date(e.submitted_at).toLocaleDateString('pt-BR')} · ${esc(e.status)}${e.score!=null?' · nota '+e.score:''}</span></div>`).join('')||'<div class="empty">Você ainda não enviou uma redação.</div>'}catch(e){$('#essayHistory').innerHTML='<div class="empty">'+esc(e.message)+'</div>'}}
$('#submitEssay')?.addEventListener('click',async()=>{try{await api('/learning/essays',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:$('#essayTitle').value,content_text:$('#essayText').value})});alert('Redação enviada. O prazo de correção é de até 7 dias.');$('#essayText').value='';await loadEssays();await loadDashboardHistory()}catch(e){alert(e.message)}});
let teacherEssayId=null;
async function loadTeacherEssays(){try{const rows=await api('/learning/teacher/essays');$('#teacherEssayList').innerHTML=rows.map(e=>`<div><strong>${esc(e.title)}</strong><span>Enviada ${new Date(e.submitted_at).toLocaleDateString('pt-BR')} · ${esc(e.status)} · prazo ${e.deadline_days} dia(s)</span><button onclick="openTeacherEssay(${e.id})">Abrir</button></div>`).join('')||'<div class="empty">Nenhuma redação na fila.</div>'}catch(e){$('#teacherEssayList').innerHTML='<div class="empty">'+esc(e.message)+'</div>'}}
window.openTeacherEssay=async id=>{try{const e=await api('/learning/teacher/essays/'+id);teacherEssayId=id;$('#teacherEssayEditor').style.display='block';$('#teacherEssayText').textContent=e.content_text;['reviewScore','reviewC1','reviewC2','reviewC3','reviewC4','reviewC5'].forEach(x=>$('#'+x).value='');$('#reviewFeedback').value='';$('#reviewStrengths').value='';$('#reviewImprovements').value='';}catch(e){alert(e.message)}};
$('#refreshTeacherEssays')?.addEventListener('click',loadTeacherEssays);$('#saveReview')?.addEventListener('click',async()=>{if(!teacherEssayId)return;try{await api(`/learning/teacher/essays/${teacherEssayId}/review`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({score:Number($('#reviewScore').value),competency_1:Number($('#reviewC1').value),competency_2:Number($('#reviewC2').value),competency_3:Number($('#reviewC3').value),competency_4:Number($('#reviewC4').value),competency_5:Number($('#reviewC5').value),feedback:$('#reviewFeedback').value,strengths:$('#reviewStrengths').value,improvements:$('#reviewImprovements').value})});alert('Correção devolvida ao aluno.');await loadTeacherEssays();}catch(e){alert(e.message)}});

const _oldSetView=setView;
setView=function(name){_oldSetView(name);if(name==='simulations')loadSimulations();if(name==='userManagement')loadAdminUsers();if(name==='essays')loadEssays();if(name==='teacherEssays')loadTeacherEssays();if(name==='dashboard')loadDashboardHistory();};
setTimeout(()=>{loadDashboardHistory();},500);

/* Painel geral + TRI estimativa */
async function loadAdminOverview(){try{const d=await api('/admin/overview');const u=d.users,c=d.content,l=d.learning,t=d.tri,a=d.assignments;$('#adminOverviewStats').innerHTML=[['Usuários',u.total],['Alunos',u.students],['Professores',u.teachers],['Questões',c.questions],['Temas',c.topics],['Vínculos ativos',a.active]].map(x=>`<article><b>${x[1]}</b><span>${x[0]}</span></article>`).join('');$('#adminLearningMetrics').innerHTML=`<span>${l.attempts} respostas</span><span>${l.simulations} simulados</span><span>${l.simulation_answers} respostas em simulados</span><span>${l.essays} redações</span><span>${l.pending_essays} pendentes</span><span>${l.reviewed_essays} corrigidas</span>`;$('#adminTriMetrics').innerHTML=`<span>${t.items_with_parameters} itens com parâmetros</span><span>${t.calibrated_items} calibrados</span><span>${t.estimated_items} estimados</span><span>TRI: estimativa</span>`}catch(e){if($('#adminOverviewStats'))$('#adminOverviewStats').innerHTML='<div class="empty">'+esc(e.message)+'</div>'}}
async function loadTriEstimate(){try{const d=await api('/learning/proficiency/estimate');$('#triSummary').innerHTML=(d.areas||[]).map(x=>`<span>${esc(x.area_name)} · θ ${x.theta} · estimativa ${x.estimated_score}</span>`).join('')||'<span>Ainda não há respostas suficientes para estimar proficiência.</span>'}catch(e){$('#triSummary').innerHTML='<span>'+esc(e.message)+'</span>'}}
$('#refreshAdminOverview')?.addEventListener('click',loadAdminOverview);$('#refreshTri')?.addEventListener('click',loadTriEstimate);
const _oldSetView2=setView;setView=function(name){_oldSetView2(name);if(name==='adminOverview')loadAdminOverview();if(name==='performance')loadTriEstimate();};

/* Diagnóstico de proficiência e prioridades */
let proficiencyState={id:null,items:[],index:0};
async function startProficiency(){
  const n=Number($('#proficiencyCount').value||40);
  try{
    const d=await api('/learning/proficiency/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question_count:n})});
    proficiencyState={id:d.assessment_id,items:d.items||[],index:0};
    await loadProficiencyQuestions();
  }catch(e){alert(e.message)}
}
async function loadProficiencyQuestions(){
  try{
    const rows=await api(`/learning/proficiency/${proficiencyState.id}/questions`); proficiencyState.items=rows;
    renderProficiencyQuestion();
  }catch(e){alert(e.message)}
}
function renderProficiencyQuestion(){
  const q=proficiencyState.items[proficiencyState.index], box=$('#proficiencyQuestion');
  if(!q){box.innerHTML='<div class="empty">Teste concluído. Clique em finalizar diagnóstico.</div>';$('#finishProficiency').style.display='inline-block';return}
  const answered=proficiencyState.items.filter(x=>x.selected_letter).length;
  $('#proficiencyProgress').innerHTML=`<span>Questão ${proficiencyState.index+1} de ${proficiencyState.items.length}</span><span>Respondidas ${answered}</span><span>Diagnóstico individual</span>`;
  box.className='card'; box.innerHTML=`<strong>Questão ${q.number}</strong><p>${esc(q.statement_text||'')}</p><div class="actions">${q.alternatives.map(a=>`<button ${q.selected_letter===a.letter?'class="primary"':''} onclick="answerProficiency(${q.question_id},'${a.letter}')">${a.letter}) ${esc(a.text)}</button>`).join('')}</div>`;
}
window.answerProficiency=async(qid,letter)=>{
  try{await api(`/learning/proficiency/${proficiencyState.id}/answer`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question_id:qid,selected_letter:letter})});
    proficiencyState.items[proficiencyState.index].selected_letter=letter;
    if(proficiencyState.index<proficiencyState.items.length-1) proficiencyState.index++;
    renderProficiencyQuestion();
  }catch(e){alert(e.message)}
};
$('#startProficiency')?.addEventListener('click',startProficiency);
$('#finishProficiency')?.addEventListener('click',async()=>{try{const d=await api(`/learning/proficiency/${proficiencyState.id}/finish`,{method:'POST'});$('#proficiencyResult').innerHTML=(d.areas||[]).map(x=>`<article class="card"><strong>${esc(x.area_name)}</strong><h3>${x.estimated_score}</h3><span>θ ${x.theta} · acerto ${(Number(x.accuracy)*100).toFixed(1)}% · ${x.item_count} itens</span></article>`).join('');await loadDashboardHistory();}catch(e){alert(e.message)}});
async function loadPriorities(){try{const d=await api('/learning/priorities');$('#studyList').innerHTML=(d||[]).map(x=>`<div class="rank-row"><div class="rank-num">${x.priority_level==='urgent'?'!':'•'}</div><div><strong>${esc(x.topic_name||'Tema')}</strong><small class="rank-meta">${esc(x.priority_level)} · ${esc(x.rationale||'')}</small></div><button onclick="togglePriority(${x.id},${!x.completed})">${x.completed?'Reabrir':'Concluir'}</button></div>`).join('')||'<div class="empty">Ainda não há prioridades. Monte o plano para gerar o diagnóstico.</div>'}catch(e){$('#studyList').innerHTML='<div class="empty">'+esc(e.message)+'</div>'}}
window.togglePriority=async(id,completed)=>{try{await api(`/learning/priorities/${id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({completed})});loadPriorities()}catch(e){alert(e.message)}};
$('#loadStudyPlan')?.addEventListener('click',async()=>{try{await api('/learning/priorities/rebuild',{method:'POST'});await loadPriorities();}catch(e){alert(e.message)}});
const _setViewFinal=setView; setView=function(name){_setViewFinal(name);if(name==='proficiency')loadProficiencyQuestions().catch(()=>{});if(name==='study')loadPriorities();};
async function loadCognitiveMap(){try{const d=await api('/learning/cognitive-map');$('#cognitiveMap').innerHTML=(d.nodes||[]).map(a=>`<article class="card"><strong>${esc(a.name)}</strong>${(a.children||[]).map(s=>`<div class="topic-card"><strong>${esc(s.name)}</strong><span>${(s.children||[]).map(t=>`${esc(t.name)} · ${Math.round(t.accuracy*100)}% · ${esc(t.priority_level)}`).join('<br>')||'Sem conteúdos cadastrados'}</span></div>`).join('')}</article>`).join('')||'<div class="empty">Taxonomia ainda não alimentada.</div>'}catch(e){$('#cognitiveMap').innerHTML='<div class="empty">'+esc(e.message)+'</div>'}}
$('#loadCognitiveMap')?.addEventListener('click',loadCognitiveMap);
const _setViewUltimate=setView;setView=function(name){_setViewUltimate(name);if(name==='study')loadCognitiveMap();};
