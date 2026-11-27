import {AttachmentStrip,AttachmentMenu} from '../components/ComposerAttachments'
import {usePhoneLayout} from '../hooks/usePhoneLayout'
import ExecutionTrace from '../components/ExecutionTrace'
import {MathText} from '../components/MathText'
import {createPortal} from 'react-dom'
import {useEffect,useLayoutEffect,useRef,useState,type FormEvent} from 'react'
import {useLocation,useNavigate,useSearchParams} from 'react-router-dom'
import {WorkspaceFeedback} from '../components/WorkspaceFeedback'
import {AiHomeHeading,AiHomeShortcuts} from '../components/AiHome'
import {readModeDraft,useModeDraft} from '../components/modeDrafts'
import {WorkspaceLink as Link,useWorkspaceGuard} from '../components/WorkspaceNavigation'
import {confirmAction} from '../components/WorkspaceConfirm'
import {api} from '../auth'
import {getModelCatalog,modelChoice,rememberModelChoice} from '../components/modelCatalog'
import {Icon} from '../components/Icon'
import ChatText from './ChatText'
import {RichChat,ResourceCards} from '../components/RichChat'
import {validModelChoice,type ModelCatalog,type ModelPreferences} from '../components/ReasoningEffort'
import ComposerInference from '../components/ComposerInference'
type Session={id:string;title:string;project:string;pinned:boolean;archived:boolean;updated_at:number}
type Attachment={id:string;name:string}
type ResourceRef={id:string;code:string;kind:string;title:string}
type Message={tool_trace?:{tool:string;state:string;detail:string}[];id:string;role:string;content:string;state:string;detail:string;model:string;created_at?:number;effort?:string;finished_at?:number;attachments:Attachment[];resource_refs?:ResourceRef[];intake_intent?:'question'|'knowledge'|'document'|'mixed'|null}
type Detail=Session&{messages:Message[]}
type Catalog=ModelCatalog
type ChatDraft={draft:string;files:Attachment[];refs:ResourceRef[];retrieve:string;edit?:string;search:string;picker:boolean}
export default function Chat(){
 const phone=usePhoneLayout(),plus=useRef<HTMLButtonElement>(null)
 const [params]=useSearchParams(),navigate=useNavigate(),location=useLocation()
 const route=location.pathname+location.search,previousRoute=useRef('')
 const [restored]=useState(()=>readModeDraft<ChatDraft>('chat',route,location.state))
 const [refs,setRefs]=useState<ResourceRef[]>(restored?.refs??[]),[search,setSearch]=useState(restored?.search??''),[matches,setMatches]=useState<ResourceRef[]>([]),[picker,setPicker]=useState(restored?.picker??false),[retrieve,setRetrieve]=useState(restored?.retrieve??'')
 const [active,setActive]=useState<Detail>(),[copied,setCopied]=useState(''),[toolsOpen,setToolsOpen]=useState(false),[showJump,setShowJump]=useState(false),[readyChecked,setReadyChecked]=useState(false),[loadingSession,setLoadingSession]=useState(Boolean(params.get('session'))),[sessionError,setSessionError]=useState(''),[pollError,setPollError]=useState('')
 const composerRef=useRef<HTMLFormElement>(null),inputRef=useRef<HTMLTextAreaElement>(null)
 const [draft,setDraft]=useState(restored?.draft??''),[files,setFiles]=useState<Attachment[]>(restored?.files??[]),[model,setModel]=useState('Auto'),[options,setOptions]=useState<Catalog['models']>([]),[catalog,setCatalog]=useState<Catalog>(),[effort,setEffort]=useState('default')
 const [ready,setReady]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[edit,setEdit]=useState<string|undefined>(restored?.edit),[rename,setRename]=useState(false),[title,setTitle]=useState(''),[project,setProject]=useState('')
 const fileInput=useRef<HTMLInputElement>(null),scroll=useRef<HTMLDivElement>(null),nearBottom=useRef(true),activeId=useRef(''),sending=useRef(false),opening=useRef<AbortController|undefined>(undefined),mounted=useRef(true),copyTimer=useRef<number|undefined>(undefined)
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;opening.current?.abort();if(opening.current){activeId.current='';previousRoute.current=''}window.clearTimeout(copyTimer.current)}},[])
 useEffect(()=>{if(previousRoute.current===route)return;const resume=Boolean(!previousRoute.current&&restored);previousRoute.current=route;const id=params.get('session');if(id){if(activeId.current!==id)void open(id,resume)}else if(!resume&&(params.has('new')||!params.has('history')&&activeId.current))resetChat()},[route,params])
 useEffect(()=>{if(!picker||!search.trim()){setMatches([]);return}const controller=new AbortController();setMatches([]);const timer=window.setTimeout(()=>api<ResourceRef[]>('/chat/resource-search?q='+encodeURIComponent(search),{signal:controller.signal}).then(v=>{if(!controller.signal.aborted)setMatches(v)}).catch(e=>{if(!controller.signal.aborted)setError(e.message)}),180);return()=>{window.clearTimeout(timer);controller.abort()}},[picker,search])
 const running=Boolean(active?.messages.some(m=>m.state==='running')),sessionUnavailable=loadingSession||Boolean(sessionError)||Boolean(params.get('session')&&!active)
 useEffect(()=>{const el=inputRef.current;if(el){el.style.height='0px';el.style.height=Math.min(Math.max(el.scrollHeight,30),144)+'px'}},[draft])
 useEffect(()=>{if(!toolsOpen||phone)return;const outside=(e:PointerEvent)=>{if(!composerRef.current?.contains(e.target as Node))setToolsOpen(false)};const escape=(e:KeyboardEvent)=>{if(e.key==='Escape')setToolsOpen(false)};document.addEventListener('pointerdown',outside);document.addEventListener('keydown',escape);return()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',escape)}},[toolsOpen,phone])
 useModeDraft('chat',route,{draft,files,refs,retrieve,edit,search,picker})
 useWorkspaceGuard({busy,preserveOnModeSwitch:true,dirty:Boolean(draft.trim()||files.length||refs.length||retrieve),message:'当前输入尚未发送，确认离开？',allow:path=>path==='/chat?session='+encodeURIComponent(activeId.current)})
 useEffect(()=>{const reset=()=>void fresh();window.addEventListener('wg-chat-new',reset);return()=>window.removeEventListener('wg-chat-new',reset)},[draft,busy,files,refs,running,retrieve])
 function failure(e:unknown){if(mounted.current)setError(e instanceof Error?e.message:'请求失败')}
 function markCopied(id:string){setCopied(id);window.clearTimeout(copyTimer.current);copyTimer.current=window.setTimeout(()=>setCopied(''),1600)}
 async function copyMessage(id:string,content:string){
  try{if(navigator.clipboard&&window.isSecureContext){await navigator.clipboard.writeText(content);markCopied(id);return}}catch{/* fallback for HTTP */}
  const field=document.createElement('textarea');field.value=content;field.readOnly=true;field.style.cssText='position:fixed;left:0;top:0;opacity:0;pointer-events:none';document.body.appendChild(field);field.select();field.setSelectionRange(0,content.length);try{if(!document.execCommand('copy'))throw new Error('复制失败，请长按正文复制');markCopied(id)}catch(e){failure(e)}finally{field.remove()}
 }
 useEffect(()=>{const update=(e:Event)=>{const session=(e as CustomEvent<Session>).detail;if(!session?.id)return;setActive(current=>current?.id===session.id?{...current,...session}:current)};window.addEventListener('wg-chat-session-updated',update);return()=>window.removeEventListener('wg-chat-session-updated',update)},[])
 useEffect(()=>{const deleted=(e:Event)=>{if((e as CustomEvent<string>).detail===activeId.current)resetChat()};window.addEventListener('wg-chat-session-deleted',deleted);return()=>window.removeEventListener('wg-chat-session-deleted',deleted)},[])
 function list(){window.dispatchEvent(new Event('wg-recent-changed'))}
 useEffect(()=>{const c=new AbortController();Promise.all([getModelCatalog(),api<ModelPreferences>('/qoder/preferences',{signal:c.signal}),api<{chat_available?:boolean}>('/qoder/status',{signal:c.signal})]).then(([m,p,s])=>{if(!c.signal.aborted){setOptions(m.models);setCatalog(m);const saved=modelChoice('chat',p.model,p.effort??'default');setModel(saved.model);setEffort(saved.effort);setReady(Boolean(s.chat_available));setReadyChecked(true)}}).catch(e=>{if(!c.signal.aborted){setReadyChecked(true);failure(e)}});return()=>c.abort()},[])

 async function open(id:string,resume=false){
  opening.current?.abort();const controller=new AbortController();opening.current=controller
  activeId.current=id;setActive(undefined);setError('');setSessionError('');setPollError('');setLoadingSession(true)
  if(!resume){setDraft('');setFiles([]);setRefs([]);setRetrieve('');setEdit(undefined);setPicker(false);setSearch('')}
  setRename(false);nearBottom.current=true;setShowJump(false)
  try{const d=await api<Detail>('/chat/sessions/'+encodeURIComponent(id),{signal:controller.signal});if(!controller.signal.aborted&&activeId.current===id)setActive(d)}
  catch(e){if(!controller.signal.aborted&&activeId.current===id)setSessionError(e instanceof Error?e.message:'会话读取失败')}
  finally{if(opening.current===controller){opening.current=undefined;if(!controller.signal.aborted)setLoadingSession(false)}}
 }
 function resetChat(){opening.current?.abort();opening.current=undefined;setLoadingSession(false);setSessionError('');setPollError('');nearBottom.current=true;setShowJump(false);activeId.current='';setActive(undefined);setDraft('');setFiles([]);setRefs([]);setRetrieve('');setEdit(undefined);setRename(false);setError('');setPicker(false);setToolsOpen(false)}
 async function fresh(){if(busy||running)return;if((draft.trim()||files.length||refs.length||retrieve)&&!await confirmAction('当前输入尚未发送，确认新建对话？'))return;resetChat();if(!params.has('new'))navigate('/chat?new=1')}
 useEffect(()=>{if(!running||!active?.id)return;const id=active.id,controller=new AbortController();let inFlight=false
  const tick=async()=>{if(inFlight)return;inFlight=true;try{const d=await api<Detail>('/chat/sessions/'+encodeURIComponent(id),{signal:controller.signal});if(!controller.signal.aborted&&activeId.current===id){setActive(d);setPollError('')}}catch(e){if(!controller.signal.aborted)setPollError(e instanceof Error?e.message:'状态读取失败')}finally{inFlight=false}}
  const t=window.setInterval(tick,900);return()=>{controller.abort();window.clearInterval(t)}
 },[running,active?.id])
 useLayoutEffect(()=>{const el=scroll.current;if(!el||!active?.messages.length)return
  const follow=()=>{if(nearBottom.current){el.scrollTop=el.scrollHeight;setShowJump(false)}}
  follow()
  const observer=new ResizeObserver(follow);observer.observe(el);el.querySelectorAll('.chat-message').forEach(node=>observer.observe(node))
  return()=>observer.disconnect()
 },[active?.messages])
 function useShortcut(kind:'ask'|'search'){if(busy||running)return;if(kind==='search'){setPicker(true);setToolsOpen(false)}else if(!draft.trim())setDraft('帮我分析这道数学题：');inputRef.current?.focus()}
 function jumpToLatest(){const el=scroll.current;if(!el)return;nearBottom.current=true;el.scrollTop=el.scrollHeight;setShowJump(false)}
 async function transferToIntake(content:string,origin:'draft'|'user'|'assistant',hasAttachments=false,messageId?:string,intent?:string){
  if(busy||running||!content.trim())return
  if(content.length>24000){setError('正文超过录入任务的24000字上限，请复制并分批录入。');return}
  if(hasAttachments&&!await confirmAction('本次只转入正文，不包含附件或题库引用。请在录入工作台重新导入需要的原文。继续？'))return
  if(origin==='assistant'&&!await confirmAction('这段内容由 AI 生成，不是原始资料。将作为待人工核对的整理草稿转入，继续？'))return
  if(messageId){if((draft.trim()||files.length||refs.length||retrieve)&&!await confirmAction('当前还有未发送草稿，转录入后将离开当前对话，确认继续？','离开当前页面','离开'))return;navigate('/work?'+new URLSearchParams({from:messageId,intent:intent??'mixed'}))}
  else navigate('/work',{state:{intakeDraft:{text:content,origin}}})
 }
 async function sendTurn(input:{content:string;attachments:Attachment[];resources:ResourceRef[];query:string;rewind?:string}){
  if(sending.current||busy||running||sessionUnavailable||!input.content.trim()||!ready||!validModelChoice(catalog,model,effort))return
  sending.current=true;setBusy(true);setError('');setPollError('')
  try{
   let id=active?.id
   if(!id){const s=await api<Session>('/chat/sessions',{method:'POST',body:JSON.stringify({})});id=s.id;activeId.current=id;setActive({...s,messages:[]});navigate('/chat?session='+encodeURIComponent(id),{replace:true});list()}
   const d=await api<Detail>('/chat/sessions/'+encodeURIComponent(id)+'/turn',{method:'POST',body:JSON.stringify({content:input.content,model,effort,attachments:input.attachments.map(f=>f.id),resource_ids:input.resources.map(r=>r.id),retrieval_query:input.query,rewind_id:input.rewind??null})})
   activeId.current=d.id;setActive(d);setDraft('');setFiles([]);setRefs([]);setRetrieve('');setEdit(undefined);setPicker(false);setSearch('');nearBottom.current=true;list();navigate('/chat?session='+encodeURIComponent(d.id),{replace:true})
  }catch(e){failure(e)}finally{sending.current=false;if(mounted.current)setBusy(false)}
 }
 async function send(e:FormEvent){e.preventDefault();await sendTurn({content:draft,attachments:files,resources:refs,query:retrieve,rewind:edit})}
 async function regenerate(original:Message){
  if(busy||running||sending.current||sessionUnavailable||!ready||!validModelChoice(catalog,model,effort))return
  const note=draft.trim()||files.length||refs.length||retrieve?'当前未发送草稿会被清除。':''
  if(!await confirmAction('使用当前模型重新回答原问题，将创建新分支并保留原对话。原文、附件和已保存的题库引用会复用；原检索词未保存。'+note,'重新生成回答','创建分支'))return
  await sendTurn({content:original.content,attachments:original.attachments,resources:original.resource_refs??[],query:'',rewind:original.id})
 }
 async function editOriginal(m:Message){
  if(busy||running)return
  if((draft.trim()||files.length||refs.length||retrieve)&&!await confirmAction('用这条历史消息替换当前未发送草稿？','编辑历史消息','替换'))return
  setEdit(m.id);setDraft(m.content);setFiles(m.attachments);setRefs(m.resource_refs??[]);setRetrieve('');setPicker(false);setSearch('');inputRef.current?.focus()
 }
 async function stop(){if(!active)return;setBusy(true);try{setActive(await api<Detail>('/chat/sessions/'+active.id+'/stop',{method:'POST'}))}catch(e){failure(e)}finally{setBusy(false)}}
 async function deleteChat(){if(!active||busy||running||!await confirmAction('删除此对话及其全部消息？删除后不可恢复。','删除会话','删除'))return;setBusy(true);try{await api('/chat/sessions/'+encodeURIComponent(active.id),{method:'DELETE'});resetChat();navigate('/chat?new=1',{replace:true});list()}catch(e){failure(e)}finally{setBusy(false)}}
 async function patch(values:Partial<Session>){if(!active)return;setBusy(true);try{const s=await api<Session>('/chat/sessions/'+active.id,{method:'PATCH',body:JSON.stringify(values)});setActive({...active,...s});setRename(false);list()}catch(e){failure(e)}finally{setBusy(false)}}
 async function upload(list:FileList|null){if(!list?.length)return;setError('');if(list.length>4-files.length){setError('聊天最多添加4份附件，请分次发送。');return}if(Array.from(list).some(f=>f.size>200*1024*1024)){setError('单文件不能超过200 MB');return}setBusy(true);try{const added:Attachment[]=[];for(const f of Array.from(list).slice(0,4-files.length)){if(!/\.(txt|tex|md|csv|pdf|docx|png|jpe?g|webp|gif)$/i.test(f.name))throw new Error('不支持的附件格式');const response=await fetch('/api/files?name='+encodeURIComponent(f.name),{method:'POST',body:f,credentials:'same-origin'});if(!response.ok)throw new Error('附件上传失败');added.push(await response.json())}setFiles(prev=>[...prev,...added].filter((f,i,a)=>a.findIndex(x=>x.id===f.id)===i))}catch(e){failure(e)}finally{setBusy(false);if(fileInput.current)fileInput.current.value=''}}
 const toolbar=document.getElementById('chat-session-actions'),home=!sessionUnavailable&&!active?.messages.length
 return <section className={'chat-workbench clean-chat chat-main-area'+(home?' chat-empty ai-home':' chat-conversation')} aria-label="AI 对话" data-chat-layout="v3">
   
   {active&&toolbar&&createPortal(<><span className="chat-session-name" title={active.title}><MathText compact content={active.title}/></span><button disabled={busy||running} onClick={()=>{setTitle(active.title);setProject(active.project);setRename(!rename)}}>管理</button><button disabled={busy||running} onClick={()=>void patch({pinned:!active.pinned})}>{active.pinned?'取消置顶':'置顶'}</button></>,toolbar)}
   {rename&&active&&<form className="chat-rename" onSubmit={e=>{e.preventDefault();void patch({title,project})}}><input required maxLength={160} aria-label="会话名称" value={title} onChange={e=>setTitle(e.target.value)}/><input maxLength={100} aria-label="项目名称" placeholder="项目名称（可选）" value={project} onChange={e=>setProject(e.target.value)}/><button disabled={busy}>保存</button><button type="button" disabled={busy||running} onClick={()=>void deleteChat()}>删除会话</button></form>}
   {readyChecked&&!ready&&<p className="chat-warning" role="status">Qoder 执行服务尚未就绪或需要升级。<Link to="/qoder" className="text-link">账号与模型</Link></p>}
   {error&&<p className="chat-warning inline-error" role="alert">{error}</p>}{pollError&&<p className="chat-warning" role="status">状态读取失败，正在重新连接：{pollError}</p>}
   <div className="chat-scroll" ref={scroll} onScroll={()=>{const el=scroll.current;if(el){nearBottom.current=el.scrollHeight-el.scrollTop-el.clientHeight<100;setShowJump(!nearBottom.current)}}}>
    {sessionUnavailable?<WorkspaceFeedback state={sessionError?'error':'loading'} title={sessionError?'会话读取失败':'正在读取会话…'} detail={sessionError||undefined} onRetry={()=>{const id=params.get('session');if(id)void open(id,true)}}/>:!active?.messages.length?<AiHomeHeading mode="chat"/>:active.messages.map((m,index)=><article className={'chat-message '+m.role} key={m.id}><div className="chat-message-label chat-role-label">{m.role==='user'?'你':'微光数学 · '+m.model}</div><div className="chat-message-body"><>{m.role==='assistant'?<><ExecutionTrace state={m.state} model={m.model} detail={m.detail} startedAt={m.created_at} finishedAt={m.finished_at} effort={m.effort} hasOutput={Boolean(m.content)}/>{!!m.tool_trace?.length&&<details className="agent-historical"><summary>真实资料查询 · {m.tool_trace.length} 步</summary>{m.tool_trace.map((step,i)=><p key={i}>{step.state==='done'?'已查询':'查询失败'} · {step.tool} · {step.detail}</p>)}</details>}<RichChat content={m.content} complete={m.state==='done'}/></>:<ChatText content={m.content}/>}</>{m.resource_refs?.map(r=><Link className="chat-file" key={r.id} to={(r.kind==='source'?'/sources':r.kind==='knowledge'?'/knowledge-library':'/resources')+'?q='+encodeURIComponent(r.code)}><MathText compact content={r.code+' '+r.title}/></Link>)}<AttachmentStrip items={m.attachments.map(f=>({key:f.id,id:f.id,name:f.name}))}/>{m.role==='assistant'&&m.state==='done'&&<ResourceCards refs={[...(active.messages[index-1]?.resource_refs??[]),...(m.resource_refs??[])].filter((r,i,a)=>a.findIndex(v=>v.id===r.id)===i).slice(0,10)}/>}{m.role==='assistant'&&['failed','stopped'].includes(m.state)&&<div className="chat-turn-failure" role="status"><strong>{m.state==='failed'?'生成失败':'已停止生成'}</strong>{m.detail&&<small>{m.detail}</small>}<small>原问题与已返回内容仍保留，可重新生成到新分支。</small></div>}</div>{m.role==='assistant'&&m.state==='done'&&m.intake_intent&&<div className="chat-intake-suggestion"><Icon name="intake" size={20}/><div><strong>AI 建议：{({question:'题目录入',knowledge:'知识单元录入',document:'整套资料录入',mixed:'混合资料录入'} as Record<string,string>)[m.intake_intent]}</strong><p>选择正文作为待整理草稿，确认后再提取，不会自动入库。</p><div className="button-row">{(()=>{const index=active.messages.indexOf(m),original=active.messages[index-1];return original?.role==='user'&&original.state==='done'?<button type="button" disabled={busy||running} onClick={()=>transferToIntake(original.content,'user',Boolean(original.attachments.length||original.resource_refs?.length),original.id,m.intake_intent??undefined)}>使用本次用户原文</button>:null})()}<button type="button" disabled={busy||running||!m.content.trim()} onClick={()=>transferToIntake(m.content,'assistant',false,m.id,m.intake_intent??undefined)}>使用 AI 回复草稿</button></div></div></div>}<div className="chat-message-actions"><button type="button" aria-label="复制" title={copied===m.id?'已复制':'复制'} onClick={()=>void copyMessage(m.id,m.content)}><Icon name={copied===m.id?'check':'copy'} size={18}/></button>{m.state==='done'&&m.content.trim()&&<button type="button" aria-label="转为录入草稿" title="转为录入草稿" disabled={busy||running} onClick={()=>transferToIntake(m.content,m.role==='assistant'?'assistant':'user',Boolean(m.attachments.length||m.resource_refs?.length),m.id)}><Icon name="intake" size={18}/></button>}{m.role==='user'&&!running&&<button type="button" aria-label="编辑并创建分支" title="编辑并创建分支" disabled={busy} onClick={()=>void editOriginal(m)}><Icon name="research" size={18}/></button>}{m.role==='assistant'&&['done','failed','stopped'].includes(m.state)&&active.messages[index-1]?.role==='user'&&<button type="button" aria-label="重新生成回答" title="重新生成回答（创建分支）" disabled={busy||running||!ready||!validModelChoice(catalog,model,effort)} onClick={()=>void regenerate(active.messages[index-1])}><Icon name="refresh" size={18}/></button>}</div></article>)}
   </div>
   {showJump&&Boolean(active?.messages.length)&&<div className="chat-jump-anchor"><button type="button" className="chat-jump" aria-label="返回最新消息" title="返回最新消息" onClick={jumpToLatest}><Icon name="down" size={20}/></button></div>}
   {<form className="chat-composer compact-composer" ref={composerRef} onSubmit={send}>
    {edit&&<div className="chat-edit">正在编辑历史消息，将保留原会话并创建分支。<button type="button" onClick={()=>{setEdit(undefined);setDraft('');setFiles([]);setRefs([]);setRetrieve('')}}>取消</button></div>}
    <AttachmentStrip items={files.map(f=>({key:f.id,id:f.id,name:f.name}))} disabled={busy||running} onRemove={id=>setFiles(v=>v.filter(x=>x.id!==id))}/>
    {retrieve&&!picker&&<div className="chat-attachments"><span>检索：{retrieve}<button type="button" aria-label="移除检索词" onClick={()=>setRetrieve('')}>×</button></span></div>}{refs.length>0&&<div className="chat-attachments">{refs.map(r=><span key={r.id}><MathText compact content={r.code+' '+r.title}/><button type="button" disabled={busy||running} onClick={()=>setRefs(v=>v.filter(x=>x.id!==r.id))}>×</button></span>)}</div>}{picker&&<div className="chat-reference-picker"><input aria-label="检索题库编号、标题或正文" placeholder="检索题库编号、标题或正文" value={search} onChange={e=>setSearch(e.target.value)}/>{matches.map(r=><button type="button" key={r.id} disabled={busy||running||refs.length>=10||refs.some(x=>x.id===r.id)} onClick={()=>setRefs(v=>[...v,r])}><MathText compact content={r.code+' '+r.title}/></button>)}<button type="button" disabled={!search.trim()||busy||running} onClick={()=>{setRetrieve(search.trim().slice(0,200));setPicker(false);if(!draft.trim())setDraft('请根据本次题库检索结果介绍相关教学资源。');inputRef.current?.focus()}}>使用当前检索词</button><label>可选：本次额外检索词<input value={retrieve} maxLength={200} onChange={e=>setRetrieve(e.target.value)} placeholder="仅检索本地题库"/></label><button type="button" onClick={()=>setPicker(false)}>关闭</button></div>}<textarea ref={inputRef} aria-label="输入消息" rows={1} maxLength={12000} placeholder="询问微光数学…" value={draft} onChange={e=>setDraft(e.target.value)} disabled={busy||running||sessionUnavailable} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing&&!running&&!busy){e.preventDefault();e.currentTarget.form?.requestSubmit()}}}/>
    <div className="chat-compose-tools compact-tools"><input ref={fileInput} type="file" multiple accept=".txt,.tex,.md,.csv,.pdf,.docx,.png,.jpg,.jpeg,.webp,.gif" hidden onChange={e=>void upload(e.target.files)}/><button ref={plus} type="button" className="composer-plus" aria-label="添加与工具" disabled={busy||running||sessionUnavailable} aria-expanded={toolsOpen} onClick={()=>setToolsOpen(v=>!v)}><Icon name="plus" size={25}/></button><ComposerInference models={options} catalog={catalog} model={model} effort={effort} onModel={v=>{if(v!==model){setModel(v);setEffort('default');rememberModelChoice('chat',v,'default')}}} onEffort={v=>{setEffort(v);rememberModelChoice('chat',model,v)}} onCatalog={m=>{setCatalog(m);setOptions(m.models)}} disabled={busy||running||sessionUnavailable} effortDisabled={!ready} onOpen={()=>setToolsOpen(false)}/>{toolsOpen&&phone&&<AttachmentMenu anchor={plus.current} onClose={()=>setToolsOpen(false)} onFiles={list=>void upload(list)} filesDisabled={files.length>=4} onQuestions={()=>setPicker(p=>!p)} disabled={busy||running||sessionUnavailable}><button type="button" className="wg-attachment-choice" disabled={!draft.trim()} onClick={()=>{setToolsOpen(false);void transferToIntake(draft,'draft',Boolean(files.length||refs.length))}}><Icon name="intake"/><span>转录入<small>将当前输入整理为待审核资料</small></span><Icon name="chevron"/></button>{active?.id&&<button type="button" className="wg-attachment-choice" onClick={()=>{setToolsOpen(false);navigate('/work?chatSession='+encodeURIComponent(active.id),{state:{workInstruction:draft}})}}><Icon name="research"/><span>进入工作<small>保留本次对话上下文</small></span><Icon name="chevron"/></button>}</AttachmentMenu>}{toolsOpen&&!phone&&<div className="composer-popover" role="group" aria-label="聊天工具"><button type="button" disabled={busy||running||files.length>=4} onClick={()=>{setToolsOpen(false);fileInput.current?.click()}}><Icon name="upload" size={18}/> 添加资料附件</button><button type="button" disabled={busy||running} onClick={()=>{setToolsOpen(false);setPicker(p=>!p)}}><Icon name="resources" size={18}/> 引用题库</button><button type="button" disabled={busy||running||!draft.trim()} onClick={()=>{setToolsOpen(false);transferToIntake(draft,'draft',Boolean(files.length||refs.length))}}><Icon name="intake" size={18}/> 转录入</button>{active?.id&&<button type="button" disabled={busy||running} onClick={()=>{setToolsOpen(false);navigate('/work?chatSession='+encodeURIComponent(active.id),{state:{workInstruction:draft}})}}>带着本次对话进入工作</button>}</div>}{running?<button type="button" className="primary chat-stop" disabled={busy} onClick={()=>void stop()} aria-label="停止生成" title="停止生成"><Icon name="stop" size={20}/></button>:<button className="primary composer-send" disabled={busy||sessionUnavailable||!draft.trim()||!ready||!validModelChoice(catalog,model,effort)} aria-label="发送消息"><Icon name="send-up" size={21}/></button>}</div>
   </form>}
   {home&&<AiHomeShortcuts><button type="button" onClick={()=>useShortcut('ask')}><Icon name="formulas" size={17}/> 数学答疑</button><button type="button" onClick={()=>useShortcut('search')}><Icon name="search" size={17}/> 检索题库</button></AiHomeShortcuts>}
 </section>
}
