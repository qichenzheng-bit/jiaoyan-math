import {useEffect,useRef,useState} from 'react'
import {api} from '../auth'
import QoderUsage from '../components/QoderUsage'
import './Checkin.css'

type Claim={round:string;state:string;earned:number|null;at:number;mode:string}
type Pack={kind:string;label:string;remaining:number;total:number|null;used:number|null}
type Change={at:number;from_at:number;delta:number;balance:number}
type State={enabled:boolean;configured:boolean;reason:string|null;round:string;next_round:string;current:Claim|null;history:Claim[];quota?:{balance:number;at:number;packs:Pack[]}|null;quota_error?:string;changes?:Change[];daily?:{day:string;increase:number;decrease:number;intervals:number}|null}
type Legacy={accounts:{id:string;name:string;recent:{id:string;data:{day:string;state:string;earned?:number|null;balance?:number|null}}[]}[]}
const labels:Record<string,string>={claimed:'领取成功',already_claimed:'本轮已领取',pending:'等待核验',not_claimable:'当前不可领取',no_verified_campaign:'未找到本轮活动',ambiguous_campaign:'活动不明确',authorization_denied:'授权被拒绝',endpoint_unavailable:'接口不可用',upstream_rejected:'平台拒绝请求',pat_missing:'未配置 PAT',pat_invalid:'PAT 格式不正确',pat_permissions:'PAT 权限异常',unexpected_response:'平台数据无法识别',claim_unconfirmed:'结果尚未核实',rate_limited:'平台限流',upstream_unavailable:'平台暂不可用'}
const label=(s:string)=>labels[s]??'未知状态'
const fmt=(v:number|null|undefined)=>v==null?'—':v.toLocaleString('zh-CN',{maximumFractionDigits:6})
const date=(v:number)=>new Date(v*1000).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false})
export default function Checkin(){
 const [state,setState]=useState<State>(),[legacy,setLegacy]=useState<Legacy>(),[busy,setBusy]=useState(''),[error,setError]=useState(''),[message,setMessage]=useState(''),[settings,setSettings]=useState(false),[pat,setPat]=useState(''),[filter,setFilter]=useState<'all'|'in'|'out'>('all')
 const active=useRef(false)
 async function load(){if(active.current)return;try{setState(await api<State>('/qiandao/state'));setError('')}catch(e){setError(e instanceof Error?e.message:'签到服务不可用')}}
 useEffect(()=>{void load();const refresh=()=>{if(document.visibilityState==='visible')void load()};const timer=window.setInterval(refresh,30000);document.addEventListener('visibilitychange',refresh);window.addEventListener('focus',refresh);void api<Legacy>('/studio/qoder-checkin').then(setLegacy).catch(()=>{});return()=>{window.clearInterval(timer);document.removeEventListener('visibilitychange',refresh);window.removeEventListener('focus',refresh)}},[])
 async function act(name:string,fn:()=>Promise<State>){if(active.current)return;active.current=true;setBusy(name);setError('');setMessage('');try{const next=await fn();setState(next);if(name==='pat'){setPat('');setSettings(false);setMessage('PAT 已保存，正在读取积分。')}else if(name==='remove'){setPat('');setSettings(false);setMessage('PAT 已删除，自动领取已关闭。')}}catch(e){setError(e instanceof Error?e.message:'操作失败')}finally{active.current=false;setBusy('')}}
 const post=(path:string,body:unknown={})=>api<State>(path,{method:'POST',body:JSON.stringify(body),signal:AbortSignal.timeout(60000)})
 const valid=!!state?.configured, quota=state?.quota, daily=state?.daily
 const changes=(state?.changes??[]).filter(x=>filter==='all'||(filter==='in'?x.delta>0:x.delta<0))
 const claimed=['claimed','already_claimed'].includes(state?.current?.state??'')
 return <div className="checkin-clean">
 <header className="checkin-header"><div><strong>Qoder CN</strong><small className="muted">{state?(valid?'已配置 PAT':'未配置 PAT'):'读取中'}</small></div><button aria-expanded={settings} onClick={()=>{setSettings(!settings);setPat('')}}>{settings?'收起设置':valid?'账号设置':'配置 PAT'}</button></header>
 {error&&<p className="inline-error" role="alert">{error}</p>}{message&&<p className="notice" role="status">{message}</p>}
 {settings&&<section className="checkin-settings"><form onSubmit={e=>{e.preventDefault();if(valid&&!window.confirm('更换 PAT 将关闭自动领取，并为新凭据建立独立积分记录。继续？'))return;void act('pat',()=>post('/qiandao/pat',{pat:pat.trim()}))}}><label>Qoder CN PAT<input aria-label="Qoder CN PAT" type="password" autoComplete="off" spellCheck={false} maxLength={4096} required placeholder={valid?'粘贴新 PAT':'粘贴 PAT（pt- 开头）'} value={pat} onChange={e=>setPat(e.target.value)}/></label><div className="button-row"><button className="primary" disabled={!!busy||!pat.trim()}>{busy==='pat'?'验证中…':'验证并保存'}</button>{valid&&<button type="button" disabled={!!busy} onClick={()=>{if(window.confirm('删除 PAT 并关闭自动领取？'))void act('remove',()=>api<State>('/qiandao/pat',{method:'DELETE'}))}}>删除授权</button>}<a href="https://qoder.com.cn/" target="_blank" rel="noopener noreferrer">获取 PAT</a></div></form><small className="muted">PAT 保存在服务器，不回显。</small></section>}
 <section className="checkin-balance">
 <div className="checkin-stats"><div><span className="muted">余额</span><strong>{valid?fmt(quota?.balance):'—'}</strong></div><div><span className="muted">今日增加</span><strong className="checkin-in">{valid&&daily?.intervals?'+'+fmt(daily.increase):'—'}</strong></div><div><span className="muted">今日减少</span><strong className="checkin-out">{valid&&daily?.intervals?'−'+fmt(daily.decrease):'—'}</strong></div></div>
 <div className="checkin-row checkin-meta"><small className="muted">{!valid?'请配置 PAT':state?.quota_error?'查询异常：'+label(state.quota_error)+(quota?' · 历史余额':''):quota?'更新于 '+date(quota.at):'等待首次查询'}</small><button disabled={!!busy||!valid} onClick={()=>void act('refresh',()=>post('/qiandao/quota/refresh'))}>{busy==='refresh'?'刷新中…':'刷新'}</button></div>
 <div className="checkin-controls"><span title={state?.round??''}>签到：{state?.current?label(state.current.state):'尚未执行'}{state?.current?.earned!=null?' · +'+fmt(state.current.earned):''}</span><label className="checkin-switch" title="北京时间每日 10:05"><input aria-label="自动领取" type="checkbox" checked={!!state?.enabled} disabled={!!busy||(!valid&&!state?.enabled)} onChange={e=>{const enabled=e.target.checked;void act('auto',()=>post('/qiandao/auto',{enabled}))}}/><span>自动领取</span></label><button className="primary" disabled={!!busy||!valid||claimed} onClick={()=>void act('run',()=>post('/qiandao/run'))}>{busy==='run'?'领取中…':claimed?'已领取':'立即领取'}</button></div>
 {valid&&!!quota?.packs.length&&<details><summary>额度明细</summary>{quota.packs.map(p=><div className="checkin-row" key={p.kind}><span>{p.label}</span><strong>{fmt(p.remaining)}</strong></div>)}</details>}
 </section>
 <section className="checkin-ledger"><div className="checkin-row"><h2>积分流水</h2><div className="checkin-filters">{(['all','in','out'] as const).map(f=><button key={f} aria-pressed={filter===f} onClick={()=>setFilter(f)}>{f==='all'?'全部':f==='in'?'增加':'减少'}</button>)}</div></div>
 <small className="muted">余额净变化 · 最近 200 条 · 减少含消耗或过期</small>
 {changes.length?<div className="checkin-table-wrap"><table className="checkin-table"><thead><tr><th>时间（北京时间）</th><th>变化</th><th>余额</th></tr></thead><tbody>{changes.map(x=><tr key={x.at}><td>{date(x.at)}</td><td className={x.delta>0?'checkin-in':'checkin-out'}>{x.delta>0?'+':'−'}{fmt(Math.abs(x.delta))}</td><td>{fmt(x.balance)}</td></tr>)}</tbody></table></div>:<p className="muted checkin-empty">暂无积分变化记录</p>}
 </section>
 <section className="checkin-history"><details><summary>签到历史（{state?.history.length??0}）</summary>{state?.history.map(h=><div className="checkin-event" key={h.round}><div>{h.round}<small className="muted checkin-block">{label(h.state)} · {h.mode==='auto'?'自动':'手动'}</small></div>{h.earned!=null&&<strong className="checkin-in">+{fmt(h.earned)}</strong>}</div>)}</details></section>
 {!!legacy?.accounts.length&&<section className="checkin-history"><details><summary>原手工签到历史</summary>{legacy.accounts.map(a=><div key={a.id}><strong>{a.name}</strong>{a.recent.map(r=><div className="checkin-event" key={r.id}><span>{r.data.day} · {r.data.state==='success'?'已确认':r.data.state==='failed'?'失败':'未领取'}</span><span>{r.data.earned!=null?'+'+fmt(r.data.earned):'—'}</span></div>)}</div>)}</details></section>}
 {!valid&&state&&<details className="checkin-sdk"><summary>AI 登录账号积分（独立查询）</summary><QoderUsage/></details>}
 <small className="muted checkin-footnote">自动领取为实验接口，仅限符合资格的账号。<a href="https://docs.qoder.cn/events/100credits" target="_blank" rel="noopener noreferrer">活动规则</a></small>
 </div>
}
