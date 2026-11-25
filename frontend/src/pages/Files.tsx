import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../auth'
import { Icon } from '../components/Icon'

type Stored = { id: string; name: string; media_type: string; size_bytes: number; archived: boolean; previewable: boolean; duplicate?: boolean }
type Listing = { items: Stored[]; total: number }
type Stats = { count: number; bytes: number; max_file_bytes: number }
function formatSize(size: number) {
  return size < 1024 ? size + ' B' : size < 1048576 ? (size/1024).toFixed(1)+' KB' : (size/1048576).toFixed(1)+' MB'
}
export default function Files() {
  const [data,setData]=useState<Listing>({items:[],total:0})
  const [stats,setStats]=useState<Stats>()
  const [archived,setArchived]=useState(false)
  const [page,setPage]=useState(0)
  const [message,setMessage]=useState('')
  const [busy,setBusy]=useState(false)
  const [preview,setPreview]=useState<Stored>()
  const input=useRef<HTMLInputElement>(null)
  const refresh=useCallback(async(signal?:AbortSignal)=>{
    const [list,summary]=await Promise.all([
      api<Listing>('/files?archived='+archived+'&offset='+page*50,{signal}),
      api<Stats>('/files/stats',{signal})
    ])
    if(!signal?.aborted){setData(list);setStats(summary)}
  },[archived,page])
  useEffect(()=>{const c=new AbortController();refresh(c.signal).catch(e=>{if(!c.signal.aborted)setMessage(e.message)});return()=>c.abort()},[refresh])
  async function upload(file:File){
    setBusy(true);setMessage('')
    try{
      const response=await fetch('/api/files?name='+encodeURIComponent(file.name),{method:'POST',body:file,credentials:'same-origin',headers:{'Content-Type':'application/octet-stream'}})
      const item=await response.json()
      if(!response.ok)throw new Error(typeof item.detail==='string'?item.detail:'上传失败')
      setMessage(item.duplicate?'已存在相同内容，复用原文件。':'上传成功')
      if(archived||page!==0){setArchived(false);setPage(0)}else{await refresh()}
    }catch(e){setMessage(e instanceof Error?e.message:'上传失败')}
    finally{setBusy(false);if(input.current)input.current.value=''}
  }
  async function change(item:Stored){
    if(!item.archived&&!window.confirm('归档此文件？文件内容仍会保留。'))return
    setBusy(true);setMessage('')
    try{
      await api('/files/'+item.id+(item.archived?'/restore':'/archive'),{method:'POST'})
      await refresh()
      setMessage(item.archived?'已恢复':'已归档')
    }catch(e){setMessage(e instanceof Error?e.message:'操作失败')}
    finally{setBusy(false)}
  }
  return <><div className="page-heading"><div className="eyebrow">基础工具 / FILES</div><h1>文件管理</h1><p className="muted">集中存储教学资料、图片及文档。归档不会永久删除文件。</p></div>
    <section className="panel"><div className="file-stats">{[{label:'文件总数',value:stats?String(stats.count):'—'},{label:'内容占用',value:stats?formatSize(stats.bytes):'—'},{label:'单文件上限',value:stats?formatSize(stats.max_file_bytes):'—'}].map(x=><div key={x.label}><small>{x.label}</small><strong>{x.value}</strong></div>)}</div></section>
    <section className="panel" style={{marginTop:16}}>
    <div className="button-row"><button className="primary" disabled={busy} onClick={()=>input.current?.click()}><Icon name="upload" size={18}/>{busy?"处理中…":"上传文件"}</button>
      <input type="file" hidden ref={input} accept=".png,.jpg,.jpeg,.gif,.webp,.pdf,.docx,.xlsx,.pptx,.txt,.tex,.md,.csv" onChange={e=>{const f=e.target.files?.[0];if(f)void upload(f)}}/>
      <button aria-pressed={!archived} onClick={()=>{setArchived(false);setPage(0)}}>现有文件</button><button aria-pressed={archived} onClick={()=>{setArchived(true);setPage(0)}}>已归档</button>
    </div>
    {message&&<p role="status">{message}</p>}
    <div className="file-list">{data.items.length===0&&<div className="empty-state"><span className="soft-icon"><Icon name="files" size={24}/></span><strong>暂无文件</strong><p>上传教学资料，即可在这里管理。</p></div>}
      {data.items.map(item=><article key={item.id} className="file-item"><div className="file-info"><span className="soft-icon"><Icon name="files"/></span><div><strong>{item.name}</strong><div className="muted">{formatSize(item.size_bytes)}</div></div></div>
        <div className="button-row">{item.previewable&&<button onClick={()=>setPreview(item)}>预览</button>}
          <a className="button-link" href={'/api/files/'+item.id+'/download'}>下载</a>
          <button disabled={busy} onClick={()=>void change(item)}>{item.archived?'恢复':'归档'}</button>
        </div></article>)}
    </div>
    <div className="button-row"><button disabled={page===0} onClick={()=>setPage(page-1)}>上一页</button><span>{page+1} / {Math.max(1,Math.ceil(data.total/50))}</span><button disabled={(page+1)*50>=data.total} onClick={()=>setPage(page+1)}>下一页</button></div>
    </section>{preview&&<div className="preview-overlay" role="dialog" aria-modal="true" aria-label="图片预览"><button onClick={()=>setPreview(undefined)}>关闭预览</button><img src={'/api/files/'+preview.id+'/preview'} alt={preview.name}/></div>}
  </>
}
