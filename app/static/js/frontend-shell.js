(function(){
  const show=(id,on)=>{const el=document.getElementById(id); if(el) el.classList.toggle('is-hidden',!on)};
  const setRoleUI=(session,me)=>{
    const logged=!!session; show('loginScreen',!logged); show('appShell',logged);
    if(!logged)return;
    const role=((me&&me.role)||((session.user.app_metadata||{}).role)||((session.user.user_metadata||{}).role)||'student').toLowerCase();
    document.body.classList.toggle('is-admin',role==='admin'); document.body.classList.toggle('is-teacher',role==='teacher'); document.body.classList.toggle('is-student',role!=='admin'&&role!=='teacher');
    const email=session.user.email||'Usuário';
    const e=document.getElementById('userEmailLabel'); if(e)e.textContent=email;
    const a=document.getElementById('userAvatar'); if(a)a.textContent=email[0].toUpperCase();
    const r=document.getElementById('userRoleSmall'); if(r)r.textContent=role==='admin'?'Administrador':(role==='teacher'?'Professor':'Estudante');
    const rl=document.getElementById('roleLabel'); if(rl)rl.textContent=role==='admin'?'Área administrativa':'Área do estudante';
    const se=document.getElementById('sectionEyebrow'); if(se)se.textContent=role==='admin'?'CENTRAL DE ADMINISTRAÇÃO':(role==='teacher'?'CENTRAL DO PROFESSOR':'PAINEL DO ESTUDANTE');
    // remove admin views from student DOM navigation and prevent direct access
    if(role!=='admin'){ ['ranking','graph','validation','calibration','classification','modelAdmin','importer'].forEach(v=>{const el=document.getElementById(v); if(el)el.dataset.adminOnly='true'}); }
    if(role!=='teacher'&&role!=='admin'){ const el=document.getElementById('teacherEssays'); if(el)el.dataset.teacherOnly='true'; }
  };
  async function refreshShell(){
    try{
      if(!window.supabaseClient){setRoleUI(null,null);return;}
      const {data}=await window.supabaseClient.auth.getSession();
      if(!data.session){setRoleUI(null,null);return;}
      let me=null; try{me=await fetch('/api/auth/me',{headers:{Authorization:'Bearer '+data.session.access_token}}).then(r=>r.ok?r.json():null)}catch{}
      setRoleUI(data.session,me);
    }catch{setRoleUI(null,null)}
  }
  window.addEventListener('load',()=>setTimeout(refreshShell,120));
  window.addEventListener('supabase-auth-changed',refreshShell);
  document.getElementById('sidebarLogout')?.addEventListener('click',()=>document.getElementById('logoutBtn')?.click());
  document.getElementById('mobileLogout')?.addEventListener('click',()=>document.getElementById('logoutBtn')?.click());
  document.getElementById('forgotPasswordBtn')?.addEventListener('click',async()=>{
    const email=document.getElementById('loginEmail')?.value.trim();
    if(!email)return alert('Digite seu e-mail primeiro.');
    if(!window.supabaseClient)return alert('Supabase Auth não configurado.');
    const {error}=await window.supabaseClient.auth.resetPasswordForEmail(email,{redirectTo:window.location.origin});
    alert(error?error.message:'Enviamos as instruções de recuperação para seu e-mail.');
  });
})();
