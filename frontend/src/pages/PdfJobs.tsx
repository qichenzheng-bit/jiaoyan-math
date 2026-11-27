import {useEffect,useRef,useState} from 'react'
import {api} from '../auth'

type Job={id:string;state:'queued'|'running'|'ready'|'failed'|'cancelled';stage:string;detail:string;filename:string;pages:number;bytes:number}
export default function PdfJobs({path,request,canExport,pageCount}:{path:string;request:unknown;canExport:boolean;pageCount:number}){
 const [jobs,setJobs]=useState<Job[]>([]),[error,setError]=useState(''),[busy,setBusy]=useState(false)
 const [reviewed,setReviewed]=useState<Record<string,boolean>>({})
 const active=useRef(path);active.current=path
 useEffect(()=>{
  let live=true
  async function refresh(){
   try{const list=await api<Job[]>(path+'/jobs');if(live&&Array.isArray(list))setJobs(list)}
   catch(e){if(live)setError(e instanceof Error?e.message:'无法读取 PDF 任务')}
  }
  setJobs([]);setReviewed({});setError('');setBusy(false);void refresh()
  const timer=window.setInterval(()=>void refresh(),2500)
  return()=>{live=false;window.clearInterval(timer)}
 },[path])
 async function generate(){
  if(!canExport||busy)return
  setBusy(true);setError('')
  try{const job=await api<Job>(path,{method:'POST',body:JSON.stringify(request)});if(active.current!==path)return;setJobs(old=>[job,...old.filter(j=>j.id!==job.id)])}
  catch(e){if(active.current===path)setError(e instanceof Error?e.message:'PDF 提交失败')}
  finally{if(active.current===path)setBusy(false)}
 }
 async function action(job:Job,kind:'cancel'|'delete'){
  try{
   if(kind==='cancel'){const value=await api<Job>('/document-pdf/jobs/'+job.id+'/cancel',{method:'POST'});if(active.current===path)setJobs(old=>old.map(j=>j.id===job.id?value:j))}
   else{await api('/document-pdf/jobs/'+job.id,{method:'DELETE'});if(active.current===path)setJobs(old=>old.filter(j=>j.id!==job.id))}
  }catch(e){if(active.current===path)setError(e instanceof Error?e.message:'任务操作失败')}
 }
 return <section className="print-controls layout-settings layout-pdf-jobs">
  <div className="button-row"><strong>PDF 文件生成</strong><button className="primary" disabled={!canExport||busy} onClick={()=>void generate()}>{busy?'提交中…':'生成 PDF'}</button></div>
  <small className="muted">后台生成任务可离开本页。成品需打开最终 PDF 检查后再下载；临时文件保留 6 小时，服务器重启后任务可能失效。</small>
  {error&&<p role="alert">{error}</p>}
  {jobs.map(job=><article className="layout-pdf-job" key={job.id}>
   <strong>{job.filename}</strong><small>{job.stage}{job.pages?' · '+job.pages+' 页':''}{job.bytes?' · '+(job.bytes/1_000_000).toFixed(2)+' MB':''}</small>
   {job.detail&&<p role="alert">{job.detail}</p>}
   {job.state==='queued'||job.state==='running'?<button onClick={()=>void action(job,'cancel')}>取消任务</button>:<button onClick={()=>void action(job,'delete')}>清理记录</button>}
   {job.state==='ready'&&<><a className="button-link" target="_blank" rel="noopener" href={'/api/document-pdf/jobs/'+job.id+'/file'}>打开最终 PDF 预览</a>
    {pageCount>0&&job.pages!==pageCount&&<small className="muted">与当前工作台页数不同，请以本任务生成的 PDF 为准重新核对。</small>}
    <label><input type="checkbox" checked={!!reviewed[job.id]} onChange={e=>setReviewed(old=>({...old,[job.id]:e.target.checked}))}/>已检查该 PDF，确认无误</label>
    {reviewed[job.id]?<a className="button-link primary" href={'/api/document-pdf/jobs/'+job.id+'/file?download=true'}>下载 PDF</a>:<button disabled>下载 PDF</button>}
   </>}
  </article>)}
 </section>
}
