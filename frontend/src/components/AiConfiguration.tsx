import {useEffect,useState} from 'react'
import {api} from '../auth'
type Scope='global'|'chat'|'work'|'intake'|'document'|'video'|'cover'
type Memory={id:string;scope:Scope;text:string;enabled:boolean}
type MemoryState={revision:number;items:Memory[]}
type PromptState={revision:number;text:string;history:{revision:number;text:string;at:number}[]}
const scopes:Record<Scope,string>={global:'全局',chat:'聊天',work:'工作',intake:'录入',document:'文档',video:'视频',cover:'封面'}
export default function AiConfiguration(){
 const [open,setOpen]=useState(false),[memory,setMemory]=useState<MemoryState>(),[scope,setScope]=useState<Scope>('work'),[prompt,setPrompt]=useState<PromptState>(),[text,setText]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('')
 useEffect(()=>{if(!open)return;const c=new AbortController();api<MemoryState>('/ai-settings/memory',{signal:c.signal}).then(v=>{if(!c.signal.aborted)setMemory(v)}).catch(e=>{if(!c.signal.aborted)setError(e.message)});return()=>c.abort()},[open])
 useEffect(()=>{if(!open)return;const c=new AbortController();setPrompt(undefined);api<PromptState>('/ai-settings/prompts/'+scope,{signal:c.signal}).then(v=>{if(!c.signal.aborted){setPrompt(v);setText(v.text)}}).catch(e=>{if(!c.signal.aborted)setError(e.message)});return()=>c.abort()},[open,scope])
 const change=(id:string,patch:Partial<Memory>)=>setMemory(old=>old&&({...old,items:old.items.map(m=>m.id===id?{...m,...patch}:m)}))
 async function saveMemory(){if(!memory)return;setBusy(true);setError('');setNotice('');try{setMemory(await api<MemoryState>('/ai-settings/memory',{method:'PUT',body:JSON.stringify(memory)}));setNotice('记忆已保存')}catch(e){setError(e instanceof Error?e.message:'保存失败')}finally{setBusy(false)}}
 async function savePrompt(){if(!prompt)return;setBusy(true);setError('');setNotice('');try{const p=await api<PromptState>('/ai-settings/prompts/'+scope,{method:'PUT',body:JSON.stringify({revision:prompt.revision,text})});setPrompt(p);setText(p.text);setNotice('提示词已保存')}catch(e){setError(e instanceof Error?e.message:'保存失败')}finally{setBusy(false)}}
 return <div className="ai-config"><button type="button" aria-expanded={open} onClick={()=>setOpen(v=>!v)}>{open?'收起 AI 记忆与提示词':'AI 记忆与提示词管理'}</button>{open&&<>
 {error&&<p role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
 <h3>长期偏好</h3><p className="muted">按范围保存教学要求。当前明确指令优先，安全权限和审核规则不能由提示词覆盖。</p>
 {memory?.items.map(m=><div key={m.id} className="panel"><label>适用范围<select value={m.scope} disabled={busy} onChange={e=>change(m.id,{scope:e.target.value as Scope})}>{Object.entries(scopes).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label><textarea rows={3} maxLength={1000} value={m.text} disabled={busy} onChange={e=>change(m.id,{text:e.target.value})}/><label><input type="checkbox" checked={m.enabled} disabled={busy} onChange={e=>change(m.id,{enabled:e.target.checked})}/> 启用</label><button type="button" disabled={busy} onClick={()=>setMemory(old=>old&&({...old,items:old.items.filter(x=>x.id!==m.id)}))}>删除</button></div>)}
 <div className="button-row"><button disabled={busy||!memory||memory.items.length>=50} type="button" onClick={()=>setMemory(old=>old&&({...old,items:[...old.items,{id:crypto.randomUUID(),scope:'global',text:'',enabled:true}]}))}>新增记忆</button><button disabled={busy||!memory||memory.items.some(m=>!m.text.trim())} type="button" onClick={()=>void saveMemory()}>保存记忆</button></div>
 <h3>业务提示词补充</h3><p className="muted">聊天、工作、录入和文档编辑会加载对应范围的补充要求。保留现有内置提示词，清空补充内容即可恢复默认。</p>
 <label>提示词范围<select disabled={busy} value={scope} onChange={e=>setScope(e.target.value as Scope)}>{Object.entries(scopes).filter(([k])=>['global','chat','work','intake','document'].includes(k)).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label>
 <textarea aria-label="业务提示词" rows={10} maxLength={16000} disabled={!prompt||busy} value={text} onChange={e=>setText(e.target.value)}/>
 <div className="button-row"><button type="button" disabled={busy||!prompt} onClick={()=>setText('')}>恢复默认补充</button><button type="button" disabled={!prompt||busy||text===prompt.text} onClick={()=>void savePrompt()}>保存提示词</button></div>
 {prompt?.history.length? <details><summary>最近历史版本</summary>{prompt.history.map(p=><div key={p.revision}><small>版本 {p.revision}</small><pre style={{whiteSpace:'pre-wrap'}}>{p.text||'无补充内容'}</pre><button type="button" disabled={busy} onClick={()=>setText(p.text)}>恢复到编辑区</button></div>)}</details>:null}
 </>}</div>
}
