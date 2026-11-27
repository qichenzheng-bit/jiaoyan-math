import {useEffect,useRef,useState} from 'react'
import {Icon} from './Icon'
type Preview={url:string;name:string;video?:boolean;pages?:number;pageUrl?:string}
function readPosition(key:string,fallback:number){try{const n=Number(sessionStorage.getItem(key));return Number.isFinite(n)&&n>0?n:fallback}catch{return fallback}}
function remember(key:string,n:number){try{sessionStorage.setItem(key,String(n))}catch{}}
export default function FinishedMediaPreview({file,onClose}:{file:Preview;onClose:()=>void}){
 const root=useRef<HTMLElement>(null),key='wg-work-position:'+file.url
 const max=file.pages??1
 const [page,setPage]=useState(()=>Math.min(max,Math.max(1,Math.floor(readPosition(key,1))))),[jump,setJump]=useState(String(page)),[zoom,setZoom]=useState(100),[failed,setFailed]=useState(false),[retry,setRetry]=useState(0),[full,setFull]=useState(false)
 const [rate,setRate]=useState(1),video=useRef<HTMLVideoElement>(null)
 const [loading,setLoading]=useState(true)
 function move(n:number){const next=Math.max(1,Math.min(max,Math.floor(n)));setPage(next);setJump(String(next))}
 useEffect(()=>{setFailed(false);setLoading(true);if(!file.video)remember(key,page)},[page,retry,file.video,key])
 useEffect(()=>{if(video.current)video.current.playbackRate=rate},[rate])
 const source=file.pageUrl?file.pageUrl+'/'+page+'?dpi='+(zoom>140?180:120)+'&retry='+retry:''
 return <section className={'finished-preview panel'+(full?' finished-full':'')} ref={root}>
  <div className="finished-actions"><strong>{file.name}</strong><a className="button-link" href={file.url} target="_blank" rel="noopener noreferrer">原文件</a><a className="button-link" href={file.url+'?download=true'}>下载</a><button onClick={()=>setFull(v=>!v)}>{full?'退出全屏':'全屏'}</button><button onClick={onClose}><Icon name="close" size={17}/>关闭</button></div>
  {file.video?<><video ref={video} controls playsInline preload="metadata" src={file.url} onLoadedMetadata={e=>{const t=readPosition(key,0);if(t<e.currentTarget.duration)e.currentTarget.currentTime=t;e.currentTarget.playbackRate=rate}} onTimeUpdate={e=>remember(key,e.currentTarget.currentTime)}/><label>播放速度 <select value={rate} onChange={e=>setRate(Number(e.target.value))}>{[0.5,0.75,1,1.25,1.5,2].map(r=><option key={r} value={r}>{r}×</option>)}</select></label></>:file.pageUrl?<>
  <div className="finished-reader-bar"><button disabled={page===1} onClick={()=>move(page-1)} aria-label="上一页">‹</button><form onSubmit={e=>{e.preventDefault();const n=Number(jump);if(Number.isFinite(n))move(n)}}><input aria-label="跳转页码" type="number" min={1} max={max} value={jump} onChange={e=>setJump(e.target.value)}/><span> / {max}</span><button type="submit">跳转</button></form><button disabled={page===max} onClick={()=>move(page+1)} aria-label="下一页">›</button><button disabled={zoom<=60} onClick={()=>setZoom(z=>z-20)}>−</button><span>{zoom}%</span><button disabled={zoom>=220} onClick={()=>setZoom(z=>z+20)}>＋</button><button onClick={()=>setZoom(100)}>适宽</button></div>
  <div className="finished-reader-page" onTouchStart={e=>{if(e.touches.length===2){/* native browser pinch zoom remains available */}}}>{loading&&!failed&&<p className="muted" role="status">正在加载第 {page} 页…</p>}{failed?<div><p role="alert">页面加载失败，可重试或打开原 PDF。</p><button onClick={()=>setRetry(n=>n+1)}>重试</button></div>:<img key={source} src={source} alt={'PDF 第 '+page+' 页'} style={{width:zoom+'%',visibility:loading?'hidden':'visible'}} onLoad={()=>setLoading(false)} onError={()=>{setLoading(false);setFailed(true)}}/>}</div>
  <div className="finished-reader-bar"><input type="range" aria-label="阅读进度" min={1} max={max} value={page} onChange={e=>move(Number(e.target.value))}/><span>{page}/{max}</span></div>
  </>:<iframe title="成品 PDF 预览" src={file.url}/>}
 </section>
}
