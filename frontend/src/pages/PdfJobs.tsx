import {useEffect,useRef,useState} from 'react'
import {api} from '../auth'
import {WorkspaceLink as Link} from '../components/WorkspaceNavigation'
import {WrapArt,wrapDefaults,wrapDimensions,wrapError} from './PrintWrap'
import type {WrapSettings} from './PrintWrap'
import type {Layout} from './documentLayout'

function validateRanges(raw:string,total:number){
 if(!raw.trim())return ''
 if(!total)return '请先完成分页预览'
 for(const part of raw.split(/[,，、]/)){
  const m=part.match(/^\s*(\d{1,5})(?:\s*-\s*(\d{1,5}))?\s*$/)
  if(!m)return '请输入有效页码，例如 1-3,5'
  const first=Number(m[1]),last=Number(m[2]??m[1])
  if(first<1||last<first||last>total)return '页码超出范围，共 '+total+' 页'
 }
 return ''
}
type Job={id:string;state:'queued'|'running'|'ready'|'failed'|'cancelled';stage:string;detail:string;filename:string;pages:number;bytes:number;total_pages?:number;page_ranges?:string;work_id?:string|null;work_version?:number|null;work_error?:string}
export default function PdfJobs({path,request,canExport,pageCount,layout,title}:{path:string;request:Record<string,unknown>;canExport:boolean;pageCount:number;layout:Layout;title:string}){
 const [jobs,setJobs]=useState<Job[]>([]),[error,setError]=useState(''),[busy,setBusy]=useState(false)
 const [ranges,setRanges]=useState('')
 const [wrap,setWrap]=useState<WrapSettings>({...wrapDefaults})
 const [wrapOpen,setWrapOpen]=useState(false),[wrapConfirmed,setWrapConfirmed]=useState(false)
 const [caliper,setCaliper]=useState(.1)
 const wrapInvalid=wrapError(layout,wrap),geometry=wrapDimensions(layout,wrap)
 const patchWrap=(v:Partial<WrapSettings>)=>{setWrap(old=>({...old,...v}));setWrapConfirmed(false)}
 const rangeError=validateRanges(ranges,pageCount)
 const [reviewed,setReviewed]=useState<Record<string,boolean>>({})
 const active=useRef(path);active.current=path
 useEffect(()=>{
  let live=true
  async function refresh(){
   try{const list=await api<Job[]>(path+'/jobs');if(live&&Array.isArray(list))setJobs(list)}
   catch(e){if(live)setError(e instanceof Error?e.message:'无法读取 PDF 任务')}
  }
  setJobs([]);setReviewed({});setRanges('');setWrap({...wrapDefaults});setWrapOpen(false);setWrapConfirmed(false);setError('');setBusy(false);void refresh()
  const timer=window.setInterval(()=>void refresh(),2500)
  return()=>{live=false;window.clearInterval(timer)}
 },[path])
 useEffect(()=>{setWrapConfirmed(false)},[layout,pageCount])
 async function generate(cover=false){
  if(!canExport||busy||(cover?!!wrapInvalid||!wrapConfirmed:!!rangeError))return
  setBusy(true);setError('')
  try{const job=await api<Job>(path,{method:'POST',body:JSON.stringify({...request,page_ranges:cover?'':ranges,preview_pages:pageCount,...(cover?{wrap,filename:title+'-印刷书衣'}:{})})});if(active.current!==path)return;setJobs(old=>[job,...old.filter(j=>j.id!==job.id)])}
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
  <div className="button-row"><strong>PDF 文件生成</strong><button className="primary" disabled={!canExport||busy||!!rangeError} onClick={()=>void generate()}>{busy?'提交中…':'生成 PDF'}</button></div>
  <label>指定 PDF 页码（留空导出全部）<input aria-label="指定 PDF 页码" value={ranges} maxLength={2000} placeholder="例如 1-3,5" onChange={e=>setRanges(e.target.value)}/></label>
  {rangeError&&<small role="alert">{rangeError}</small>}
  <small className="muted">指定页码以完整预览为准，保留原来的页眉、页脚和页号。</small>
  <small className="muted">后台生成任务可离开本页。成品需打开最终 PDF 检查后再下载；临时文件保留 6 小时，服务重启后未完成任务会重新生成。</small>
  {!!layout.coverFileId&&!!layout.backCoverFileId&&<details open={wrapOpen} onToggle={e=>setWrapOpen(e.currentTarget.open)}><summary>独立印刷书衣 PDF（封底＋书脊＋封面）</summary>
   {wrapOpen&&<><div className="layout-fields">
    <label>书脊宽度 (mm)<input type="number" min={0} max={150} step={.1} value={wrap.spine} onChange={e=>patchWrap({spine:e.currentTarget.valueAsNumber})}/></label>
    <label>出血 (mm)<input type="number" min={0} max={20} step={.1} value={wrap.bleed} onChange={e=>patchWrap({bleed:e.currentTarget.valueAsNumber})}/></label>
    <label>单张纸厚度 (mm)<input type="number" min={.01} max={1} step={.01} value={caliper} onChange={e=>setCaliper(e.currentTarget.valueAsNumber)}/></label>
    <button type="button" disabled={!pageCount||!Number.isFinite(caliper)||caliper<.01||caliper>1} onClick={()=>patchWrap({spine:Math.min(150,Math.round(Math.ceil(Math.max(0,pageCount-2)/2)*caliper*10)/10)})}>按正文纸张厚度估算书脊</button>
    <label>书脊文字<input maxLength={200} value={wrap.spineText} onChange={e=>patchWrap({spineText:e.target.value})}/></label>
    <button type="button" onClick={()=>patchWrap({spineText:title})}>使用文档名称</button>
    <label>书衣底色<input type="color" value={wrap.background} onChange={e=>patchWrap({background:e.target.value})}/></label>
    <label>书脊文字颜色<input type="color" value={wrap.foreground} onChange={e=>patchWrap({foreground:e.target.value})}/></label>
   </div><small>成品尺寸 {geometry.totalWidth.toFixed(1)} × {geometry.totalHeight.toFixed(1)} mm。书脊估算不含胶层或装订附加厚度，请以印厂确认值为准。图片完整显示，出血由底色填充，不自动延展原图。</small>
   {wrapInvalid?<p role="alert">{wrapInvalid}</p>:<><div className="layout-wrap-preview"><WrapArt layout={layout} wrap={wrap}/></div><label><input type="checkbox" checked={wrapConfirmed} onChange={e=>setWrapConfirmed(e.target.checked)}/>已核对书衣尺寸与预览</label><button disabled={!canExport||busy||!wrapConfirmed} onClick={()=>void generate(true)}>生成印刷书衣 PDF</button></>}
   </>}
  </details>}
  {error&&<p role="alert">{error}</p>}
  {jobs.map(job=><article className="layout-pdf-job" key={job.id}>
   <strong>{job.filename}</strong><small>{job.stage}{job.pages?' · '+job.pages+' 页':''}{job.bytes?' · '+(job.bytes/1_000_000).toFixed(2)+' MB':''}</small>
   {job.detail&&<p role="alert">{job.detail}</p>}
   {job.state==='queued'||job.state==='running'?<button onClick={()=>void action(job,'cancel')}>取消任务</button>:<button onClick={()=>void action(job,'delete')}>清理记录</button>}
   {job.state==='ready'&&<>{job.work_error?<p role="alert">{job.work_error}</p>:job.work_id?<small>{job.work_version===0?'书衣已保存，等待匹配正文':'已自动保存教学作品 · V'+job.work_version}　<Link to={'/works?work='+encodeURIComponent(job.work_id)}>查看作品</Link></small>:null}<a className="button-link" target="_blank" rel="noopener" href={'/api/document-pdf/jobs/'+job.id+'/file'}>打开最终 PDF 预览</a>
    {job.page_ranges&&<small>原文页码：{job.page_ranges}（完整文档 {job.total_pages} 页）</small>}
    {pageCount>0&&(job.total_pages??job.pages)!==pageCount&&<small className="muted">与当前工作台页数不同，请以本任务生成的 PDF 为准重新核对。</small>}
    <label><input type="checkbox" checked={!!reviewed[job.id]} onChange={e=>setReviewed(old=>({...old,[job.id]:e.target.checked}))}/>已检查该 PDF，确认无误</label>
    {reviewed[job.id]?<a className="button-link primary" href={'/api/document-pdf/jobs/'+job.id+'/file?download=true'}>下载 PDF</a>:<button disabled>下载 PDF</button>}
   </>}
  </article>)}
 </section>
}
