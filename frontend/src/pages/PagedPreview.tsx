import {useEffect,useRef,useState} from 'react'
import type {CSSProperties,ReactNode} from 'react'
import {dimensions,layoutError} from './documentLayout'
import type {Layout} from './documentLayout'
import {paginateDocument,pageVariables} from './documentPagination'
import type {PaginationResult} from './documentPagination'
import './document-layout.css'

export default function PagedPreview({layout,title,subject,children,version,onResult}:{layout:Layout;title:string;subject:string;children:ReactNode;version:unknown;onResult?:(result:PaginationResult)=>void}){
 const source=useRef<HTMLDivElement>(null),target=useRef<HTMLDivElement>(null),report=useRef(onResult)
 report.current=onResult
 const [status,setStatus]=useState<PaginationResult>({pages:0,error:''})
 const [built,setBuilt]=useState<{version:unknown;layout:Layout;title:string;subject:string}|null>(null)
 const measuring=built?.version!==version||built?.layout!==layout||built?.title!==title||built?.subject!==subject
 useEffect(()=>{
  let live=true
  setStatus({pages:0,error:''});report.current?.({pages:0,error:''})
  target.current?.replaceChildren()
  const err=layoutError(layout)
  if(err){setStatus({pages:0,error:err});setBuilt({version,layout,title,subject});report.current?.({pages:0,error:err});return}
  async function build(){
   try{
    await document.fonts.ready
    if(!live||!source.current||!target.current)return
    const images=Array.from(source.current.querySelectorAll('img'))
    for(const image of images)image.loading='eager'
    const decoded=await Promise.allSettled(images.map(img=>img.decode()))
    if(!live||!source.current||!target.current)return
    const result=decoded.some(x=>x.status==='rejected')?{pages:0,error:'存在图片加载失败，不能导出。'}:await paginateDocument(source.current,target.current,layout,title,subject,()=>!live)
    if(live){setStatus(result);setBuilt({version,layout,title,subject});report.current?.(result)}
   }catch(e){if(live){const result={pages:0,error:e instanceof Error?e.message:'分页失败'};setStatus(result);setBuilt({version,layout,title,subject});report.current?.(result)}}
  }
  void build()
  return()=>{live=false}
 },[layout,title,subject,version])
 const [w,h]=dimensions(layout)
 const style={...pageVariables(layout,w,h),'--layout-title-size':layout.titleSize+'pt','--layout-heading-size':layout.headingSize+'pt'} as CSSProperties
 return <div className="layout-work" style={style} data-pdf-state={measuring?'pending':status.error?'failed':status.pages?'ready':'pending'} data-pdf-pages={status.pages}>
  <style>{'@page{size:'+w+'mm '+h+'mm;margin:0}'}</style>
  {measuring&&<div className="layout-measure" aria-hidden="true" ref={source}>{children}</div>}
  <div className="layout-pages" data-ready={!measuring&&!status.error?"1":"0"} ref={target}/>
  {status.error&&<p className="print-controls" role="alert">{status.error}</p>}
  {!status.pages&&!status.error&&<p className="print-controls muted">正在计算页面…</p>}
 </div>
}
