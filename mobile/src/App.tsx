import {useCallback,useEffect,useRef,useState} from 'react';
import {ArrowRight,ArrowUpRight,Check,ChevronLeft,ChevronRight,Clock3,Download,FileJson2,FileUp,History,Languages,Loader2,Monitor,RefreshCw,ShieldCheck,SlidersHorizontal,Unplug,Upload,WifiOff,X,AlertCircle,BookOpen,FolderOpen} from 'lucide-react';
import * as api from './api';
import type {Health,Job,LocalFile,Options,Preview} from './api';

const initialOptions:Options={target:'en',include:[],exclude:[],strict_tokens:false,glossary:null};
const navigate=(path:string)=>{location.hash=path;window.scrollTo({top:0});};
const readable=(error:unknown)=>String(error).replace(/^Error:\s*/,'');
const fileSize=(size:number)=>size<1024?`${size} octets`:size<1024*1024?`${(size/1024).toFixed(1)} Ko`:`${(size/1024/1024).toFixed(1)} Mo`;

export default function App(){
  const [route,setRoute]=useState(location.hash.slice(1)||'/translate');
  const [health,setHealth]=useState<Health|null>(null);
  const [online,setOnline]=useState(false);
  const [jobs,setJobs]=useState<Job[]>([]);
  const [code,setCode]=useState('');
  const [endpoint,setEndpoint]=useState('');
  const [busy,setBusy]=useState('');
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [file,setFile]=useState<LocalFile|null>(null);
  const [options,setOptions]=useState<Options>(initialOptions);
  const [includeText,setIncludeText]=useState('');
  const [excludeText,setExcludeText]=useState('');
  const [preview,setPreview]=useState<Preview|null>(null);
  const [advanced,setAdvanced]=useState(false);
  const [glossaryName,setGlossaryName]=useState('');
  const [requestId,setRequestId]=useState(crypto.randomUUID());
  const hydrated=useRef(false),polling=useRef(false),session=useRef(false);
  const selected=route.startsWith('/job/')?jobs.find(j=>j.id===route.slice(5)):null;
  const tab=route.startsWith('/job/')?'/history':route;

  useEffect(()=>{const change=()=>setRoute(location.hash.slice(1)||'/translate');window.addEventListener('hashchange',change);return()=>window.removeEventListener('hashchange',change);},[]);
  useEffect(()=>{setPreview(null);setRequestId(crypto.randomUUID());},[file,options]);
  useEffect(()=>{if(!notice)return;const timer=setTimeout(()=>setNotice(''),6000);return()=>clearTimeout(timer);},[notice]);

  const refresh=useCallback(async()=>{
    if(polling.current||!session.current)return;
    polling.current=true;
    try{const latest=await api.remote<Job[]>('list');setJobs(latest);setOnline(true);}
    catch{setOnline(false);}finally{polling.current=false;}
  },[]);
  const connectPC=useCallback(async(pairing:string,address:string,save=true)=>{
    setBusy('connect');setError('');
    try{
      const status=await api.connect(pairing,address);session.current=true;setHealth(status);setOnline(true);
      setCode(pairing);setEndpoint(address);
      if(save)await api.native('savePairing',{code:pairing,endpoint:address});
      await refresh();
      if(save){setNotice('PC connecté. Tout est prêt.');navigate('/translate');}
    }catch(e){setError(readable(e));setOnline(false);}finally{setBusy('');}
  },[refresh]);
  useEffect(()=>{
    if(hydrated.current)return;hydrated.current=true;
    api.native<{code:string;endpoint:string}>('loadPairing').then(saved=>{
      if(saved.code){setCode(saved.code);setEndpoint(saved.endpoint);void connectPC(saved.code,saved.endpoint,false);}
    }).catch(e=>setError(readable(e)));
  },[connectPC]);
  useEffect(()=>{const timer=setInterval(()=>{if(!document.hidden)void refresh();},2500);
    const visible=()=>{if(!document.hidden)void refresh();};document.addEventListener('visibilitychange',visible);
    return()=>{clearInterval(timer);document.removeEventListener('visibilitychange',visible);};},[refresh]);

  async function pick(kind:'source'|'glossary'|'pairing'){
    setBusy('pick');setError('');
    try{
      const picked=await api.native<LocalFile>('pickFile',{kind});if(picked.cancelled)return;
      if(kind==='source'){setFile(picked);setPreview(null);}
      else if(kind==='pairing'){const value=api.decode(picked.data).trim();if(!value.startsWith('KTB1.'))throw new Error('Choisis le fichier pairing.txt fourni par le PC.');setCode(value);setNotice('Code importé. Tu peux connecter le PC.');}
      else{const value=JSON.parse(api.decode(picked.data));if(!value||Array.isArray(value)||typeof value!=='object'||Object.values(value).some(v=>typeof v!=='string'))throw new Error('Le glossaire doit associer chaque texte japonais à une traduction.');setOptions(o=>({...o,glossary:value}));setGlossaryName(picked.filename);}
    }catch(e){setError(readable(e));}finally{setBusy('');}
  }
  function body(){return {request_id:requestId,filename:file!.filename,data:file!.data,file_id:file!.file_id,options};}
  async function inspect(){setBusy('preview');setError('');try{setPreview(await api.remote<Preview>('preview',undefined,body()));}catch(e){setError(readable(e));}finally{setBusy('');}}
  async function launch(){setBusy('submit');setError('');try{const job=await api.remote<Job>('submit',undefined,body());setJobs(list=>[job,...list.filter(j=>j.id!==job.id)]);navigate(`/job/${job.id}`);setFile(null);setPreview(null);}catch(e){setError(readable(e));}finally{setBusy('');}}
  async function action(job:Job,op:'cancel'|'retry'){setBusy(op);setError('');try{const result=await api.remote<Job>(op,job.id);await refresh();if(op==='retry')navigate(`/job/${result.id}`);}catch(e){setError(readable(e));}finally{setBusy('');}}
  async function save(job:Job,report=false){setBusy('save');setError('');try{
    const result=await api.remote<{path:string}>(report?'report':'result',job.id);
    const filename=report?`${job.filename.replace(/\.json$/i,'')}.rapport.json`:`${job.filename.replace(/\.json$/i,'')}.${job.options.target||'en'}.json`;
    const saved=await api.native<{cancelled?:boolean}>('saveFile',{filename,path:result.path});
    if(!saved.cancelled)setNotice('Fichier enregistré sur le téléphone.');
  }catch(e){setError(readable(e));}finally{setBusy('');}}
  async function forget(){await api.native('savePairing',{code:'',endpoint:''});await api.disconnect();session.current=false;setHealth(null);setOnline(false);setJobs([]);setCode('');setEndpoint('');setNotice('Connexion supprimée de ce téléphone.');}
  const running=jobs.find(api.active);
  const busyIcon=<Loader2 className="spin" size={19} aria-hidden="true"/>;
  return <div className="app-shell">
    <header className="topbar"><button className="brand" onClick={()=>navigate('/translate')} aria-label="Kotoba, accueil"><span className="brand-mark"><BookOpen size={23}/></span>Kotoba</button>
      <button className={`connection-chip ${online?'connected':''}`} onClick={()=>navigate('/connection')}><span className="status-dot"/>{online?'PC connecté':busy==='connect'?'Connexion…':'Connecter le PC'}<ChevronRight size={15}/></button></header>
    <main id="main">
      {error&&<div className="message error" role="alert"><AlertCircle size={20}/><p>{error}</p><button className="icon-button" onClick={()=>setError('')} aria-label="Fermer l’erreur"><X size={19}/></button></div>}
      {health&&!online&&<div className="message warning" role="status"><WifiOff size={20}/><p>PC injoignable. Les tâches continuent sur le PC. La liste se mettra à jour à la reconnexion.</p></div>}
      {route==='/translate'&&<>
        <section className="page-heading"><h1>Une nouvelle<br/>traduction.</h1><p>Les mots voyagent.<br/>Ton fichier reste intact.</p></section>
        <div className="language-line"><div><span className="language-symbol" lang="ja">あ</span><span>Japonais<small>Langue source</small></span></div><ArrowRight size={20} aria-hidden="true"/><label><span className="sr-only">Langue de traduction</span><select value={options.target} onChange={e=>setOptions(o=>({...o,target:e.target.value}))}><option value="en">Anglais</option><option value="fr">Français</option></select><small>Traduire vers</small></label></div>
        <section className={`document-surface ${file?'has-file':''}`} aria-label="Fichier à traduire">
          {!file?<button className="import-area" onClick={()=>pick('source')} disabled={!!busy}><span className="document-icon"><FileJson2 size={38} strokeWidth={1.4}/></span><strong>Choisir un fichier JSON</strong><span>Depuis ton téléphone · 50 Mo max.</span><span className="import-link"><Upload size={16}/>Importer un fichier</span></button>:<>
            <div className="file-heading"><FileJson2 size={30}/><div><strong>{file.filename}</strong><span>{fileSize(file.size)} · Original préservé</span></div><button className="icon-button" aria-label="Retirer le fichier" onClick={()=>setFile(null)} disabled={!!busy}><X size={20}/></button></div>
            <div className="file-analysis">{preview?<><span className="count">{preview.total}</span><div><strong>textes à traduire</strong><span>{preview.total?'Sélection vérifiée sur le PC':'Aucun texte japonais dans les champs sélectionnés'}</span></div></>:<><ShieldCheck size={23}/><p>Vérifie les champs avant de lancer la traduction.</p></>}</div>
          </>}
        </section>
        <div className="integrity-note"><ShieldCheck size={18}/><p>Structure JSON, variables et codes reconnus conservés. Le PC s’occupe de la traduction.</p></div>
        <button className="settings-toggle" aria-expanded={advanced} onClick={()=>setAdvanced(!advanced)}><SlidersHorizontal size={19}/>Options de traduction<ChevronRight className={advanced?'rotated':''} size={18}/></button>
        {advanced&&<section className="options" aria-label="Options de traduction">
          <label className="field">Champs à inclure<textarea rows={2} placeholder="/dialogues/*/text" value={includeText} onChange={e=>{setIncludeText(e.target.value);setOptions(o=>({...o,include:e.target.value.split('\n').map(s=>s.trim()).filter(Boolean)}));}}/><small>Un chemin par ligne. Vide = tous les textes japonais hors champs techniques.</small></label>
          <label className="field">Champs à exclure<textarea rows={2} placeholder="*/speaker" value={excludeText} onChange={e=>{setExcludeText(e.target.value);setOptions(o=>({...o,exclude:e.target.value.split('\n').map(s=>s.trim()).filter(Boolean)}));}}/></label>
          <label className="switch-row"><span><strong>Codes stricts</strong><small>Arrêter si le modèle altère un code, sans traduction par fragments.</small></span><input type="checkbox" checked={options.strict_tokens} onChange={e=>setOptions(o=>({...o,strict_tokens:e.target.checked}))}/></label>
          <button className="secondary" onClick={()=>pick('glossary')} disabled={!!busy}><BookOpen size={18}/>{glossaryName||'Ajouter un glossaire JSON'}</button>
          {glossaryName&&<button className="text-button" onClick={()=>{setGlossaryName('');setOptions(o=>({...o,glossary:null}));}}>Retirer le glossaire</button>}
        </section>}
        {preview&&preview.preview.length>0&&<details className="preview"><summary>Voir les champs sélectionnés</summary>{preview.preview.map((line,i)=><p key={i}>{line.replace(/^input\.json\s+/,'')}</p>)}{preview.total>8&&<small>8 premiers champs sur {preview.total}.</small>}</details>}
        {!online?<button className="primary" onClick={()=>navigate('/connection')}><Monitor size={20}/>Connecter mon PC<ArrowRight size={18}/></button>:file&&!preview?<button className="primary" disabled={!!busy||!health?.model_ready} onClick={inspect}>{busy==='preview'?busyIcon:<ShieldCheck size={20}/>}Vérifier le fichier<ArrowRight size={18}/></button>:file&&preview?<button className="primary" disabled={!!busy||!preview.total||!health?.model_ready} onClick={launch}>{busy==='submit'?busyIcon:<Languages size={20}/>}Lancer la traduction<ArrowRight size={18}/></button>:<p className="idle-hint">Choisis un JSON pour commencer.</p>}
        {online&&!health?.model_ready&&<p className="model-warning">Le modèle n’est pas prêt. Sur le PC, lance setup-ollama.ps1 puis reconnecte l’application.</p>}
        {running&&<section className="current-job"><div className="section-heading"><h2>Sur ton PC</h2><button className="text-button" onClick={()=>navigate('/history')}>Tout voir</button></div><JobRow job={running} onClick={()=>navigate(`/job/${running.id}`)}/></section>}
      </>}
      {route==='/history'&&<>
        <section className="page-heading"><h1>Ton historique.</h1><p>Les traductions restent sur ton PC.<br/>Retrouve-les quand tu veux.</p></section>
        <div className="section-heading"><h2>{jobs.length} traduction{jobs.length!==1?'s':''}</h2><button className="icon-button" aria-label="Actualiser l’historique" onClick={()=>refresh()} disabled={!health}><RefreshCw size={20}/></button></div>
        {jobs.length?<div className="job-list">{jobs.map(job=><JobRow key={job.id} job={job} onClick={()=>navigate(`/job/${job.id}`)}/>)}</div>:<div className="empty-state"><History size={38} strokeWidth={1.3}/><h2>Tout commence par un fichier.</h2><p>{online?'Tes traductions apparaîtront ici, même après avoir fermé l’application.':'Connecte le PC pour retrouver tes traductions.'}</p><button className="secondary" onClick={()=>navigate(online?'/translate':'/connection')}>{online?'Choisir un JSON':'Connecter le PC'}<ArrowRight size={18}/></button></div>}
      </>}
      {route.startsWith('/job/')&&<>
        <button className="back-button" onClick={()=>navigate('/history')}><ChevronLeft size={21}/>Historique</button>
        {!selected?<div className="empty-state"><Loader2 className="spin"/><p>{online?'Chargement de la traduction…':'Connecte le PC pour retrouver cette traduction.'}</p></div>:<>
          <section className="page-heading job-title"><span className={`state-label ${selected.status}`}>{api.active(selected)?<Loader2 className="spin" size={16}/>:selected.status==='completed'?<Check size={16}/>:<Clock3 size={16}/>} {api.statusLabel(selected.status)}</span><h1>{selected.filename}</h1><p>Japonais <ArrowRight size={15}/> {selected.options.target==='fr'?'Français':'Anglais'}</p></section>
          <section className="progress-surface"><div className="progress-heading"><strong>{selected.done}<span> / {selected.total}</span></strong><span>textes traduits</span></div><progress value={selected.done} max={Math.max(selected.total,1)} aria-label="Progression de la traduction"/><p role="status">{selected.message}</p></section>
          {api.active(selected)&&<p className="integrity-note"><Monitor size={19}/>Tu peux fermer l’app. Le PC continue de traduire.</p>}
          {!!selected.reviews.length&&<section className="review-block"><h2><AlertCircle size={19}/>À relire</h2><p>{selected.reviews.length} passage{selected.reviews.length>1?'s ont':' a'} été traduit{selected.reviews.length>1?'s':''} par fragments pour préserver les codes. Vérifie la fluidité dans le jeu.</p><details><summary>Voir les passages</summary>{selected.reviews.map((r,i)=><p key={i} className="code-line">{r.replace(/^REVIEW input\.json\s+/,'')}</p>)}</details></section>}
          {selected.status==='completed'&&<button className="primary" disabled={!!busy||!online} onClick={()=>save(selected)}>{busy==='save'?busyIcon:<Download size={20}/>}Enregistrer le JSON</button>}
          {api.active(selected)?<button className="secondary" disabled={!!busy||!online} onClick={()=>action(selected,'cancel')}>Annuler la traduction</button>:<button className="secondary" disabled={!!busy||!online} onClick={()=>action(selected,'retry')}><RefreshCw size={18}/>Relancer avec le cache</button>}
          {['completed','failed'].includes(selected.status)&&<button className="text-button full" disabled={!!busy||!online} onClick={()=>save(selected,true)}>Enregistrer le rapport<ArrowUpRight size={16}/></button>}
          <div className="job-facts"><span>Demandée le</span><strong>{new Date(selected.created_at*1000).toLocaleString('fr-FR',{dateStyle:'medium',timeStyle:'short'})}</strong><span>Moteur</span><strong>TranslateGemma 12B</strong><span>Fichier source</span><strong>Conservé sur le PC</strong></div>
        </>}
      </>}
      {route==='/connection'&&<>
        <section className="page-heading"><h1>Ton PC.<br/>À portée de main.</h1><p>La puissance reste chez toi.<br/>Tu gardes le contrôle, où que tu sois.</p></section>
        <section className="pc-status"><span className="pc-icon"><Monitor size={30} strokeWidth={1.5}/></span><div><strong>{online?'PC connecté':'Connexion au PC'}</strong><p>{online?health?.model:'Wi-Fi ou VPN à distance'}</p></div><span className={`status-dot ${online?'on':''}`}/></section>
        <p className="connection-help">Lance <strong>Démarrer Kotoba PC</strong> sur ton ordinateur, puis importe son fichier de connexion ou colle son code ici.</p>
        <button className="secondary" onClick={()=>pick('pairing')} disabled={!!busy}><FolderOpen size={19}/>Importer le fichier de connexion</button>
        <label className="field">Code de connexion<textarea className="pairing-input" rows={3} autoComplete="off" autoCorrect="off" spellCheck={false} value={code} onChange={e=>setCode(e.target.value)} placeholder="KTB1.…"/><small>Ce code est privé. Il autorise l’accès à tes traductions.</small></label>
        <details className="address-details"><summary>Adresse du PC (facultatif)</summary><label className="field">Adresse HTTPS<input inputMode="url" type="url" autoCapitalize="none" autoCorrect="off" value={endpoint} onChange={e=>setEndpoint(e.target.value)} placeholder="Adresse incluse dans le code"/><small>Pour une autre adresse déjà présente dans le certificat : réseau local, VPN ou adresse distante configurée.</small></label></details>
        <button className="primary" disabled={!code.trim()||!!busy} onClick={()=>connectPC(code.trim(),endpoint.trim())}>{busy==='connect'?busyIcon:<Monitor size={20}/>}Connecter le PC<ArrowRight size={18}/></button>
        <div className="integrity-note"><ShieldCheck size={18}/><p>Connexion HTTPS. La clé est chiffrée dans le stockage sécurisé Android.</p></div>
        {health&&<><dl className="connection-details"><div><dt>Adresse</dt><dd>{health.endpoint}</dd></div><div><dt>Ollama</dt><dd>{health.ollama?'Disponible':'À démarrer sur le PC'}</dd></div><div><dt>Modèle</dt><dd>{health.model_ready?'Prêt à traduire':'À installer sur le PC'}</dd></div></dl><button className="text-button danger" disabled={!!busy} onClick={()=>forget().catch(e=>setError(readable(e)))}><Unplug size={18}/>Oublier ce PC</button></>}
        <details className="remote-help"><summary>Se connecter en 4G / 5G</summary><p>Le PC doit être allumé, le compagnon lancé et son adresse accessible depuis ton téléphone. Utilise le VPN de ton réseau ou l’accès distant configuré avec le compagnon. Ollama reste privé sur le PC.</p></details>
      </>}
    </main>
    {notice&&<div className="snackbar" role="status"><Check size={18}/><span>{notice}</span><button className="icon-button" onClick={()=>setNotice('')} aria-label="Fermer"><X size={18}/></button></div>}
    <nav className="bottom-nav" aria-label="Navigation principale">{[{path:'/translate',label:'Traduire',Icon:Languages},{path:'/history',label:'Historique',Icon:History},{path:'/connection',label:'Mon PC',Icon:Monitor}].map(({path,label,Icon})=><button key={path} aria-current={tab===path?'page':undefined} onClick={()=>navigate(path)}><span><Icon size={23}/></span>{label}</button>)}</nav>
  </div>;
}

function JobRow({job,onClick}:{job:Job;onClick:()=>void}){
  return <button className="job-row" onClick={onClick}><span className="job-icon"><FileJson2 size={23}/></span><span className="job-row-text"><strong>{job.filename}</strong><span>{api.statusLabel(job.status)}{job.status==='running'?` · ${job.done}/${job.total}`:` · ${new Date(job.created_at*1000).toLocaleString('fr-FR',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit',second:'2-digit'})}`}{` · ${job.options.target==='fr'?'Français':'Anglais'}`}{job.reviews.length?' · À relire':''}</span>{api.active(job)&&<progress max={Math.max(job.total,1)} value={job.done} aria-label={`${job.done} textes traduits sur ${job.total}`}/>}</span><ChevronRight size={19}/></button>;
}
