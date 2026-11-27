import {useEffect,useRef,useState,type ReactNode} from 'react'

const frameMarkup='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data: blob:; font-src data: blob:; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'"><style>html,body{margin:0;background:#e8e5df;color:#222}body{overflow:auto}#word-preview-content{min-height:100vh;box-sizing:border-box}#word-preview-content .wg-docx-page-wrapper{align-items:flex-start;padding:8px;min-width:max-content}#word-preview-content section.wg-docx-page{margin:0 auto 10px!important;box-sizing:border-box}a{pointer-events:none}</style></head><body><main id="word-preview-content"></main></body></html>'

/** Read a selected File directly; stored attachments use the authenticated original.
 * The document is rendered in a script-disabled, network-restricted frame.
 * Word pagination uses saved and explicit page breaks, not Microsoft Word's engine.
 */
export default function WordLayoutPreview({file,url,fallback}:{file?:File;url?:string;fallback?:ReactNode}){
 const frame=useRef<HTMLIFrameElement>(null),pages=useRef<HTMLElement[]>([]),fit=useRef(1),zoomRef=useRef(1)
 const [ready,setReady]=useState(0),[retry,setRetry]=useState(0),[loading,setLoading]=useState(true),[error,setError]=useState(''),[total,setTotal]=useState(0),[current,setCurrent]=useState(1),[zoom,setZoom]=useState(1),[showFallback,setShowFallback]=useState(false)
 function applyZoom(){const root=frame.current?.contentDocument?.getElementById('word-preview-content');if(root)root.style.zoom=String(fit.current*zoomRef.current)}
 function go(n:number){const page=pages.current[n-1],win=frame.current?.contentWindow;if(!page||!win)return;win.scrollTo({top:Math.max(0,page.getBoundingClientRect().top+win.scrollY-8),behavior:'instant'});setCurrent(n)}
 useEffect(()=>{
  const doc=frame.current?.contentDocument,root=doc?.getElementById('word-preview-content'),win=frame.current?.contentWindow
  if(!ready||!doc||!root||!win||showFallback)return
  const controller=new AbortController();let resize:ResizeObserver|undefined
  const preventLink=(event:Event)=>{if((event.target as Element|null)?.closest?.('a'))event.preventDefault()}
  const syncPage=()=>{const list=pages.current;if(!list.length)return;let next=0;for(let i=0;i<list.length;i++){if(list[i].getBoundingClientRect().top<=Math.max(32,win.innerHeight*.22))next=i;else break}setCurrent(next+1)}
  doc.addEventListener('click',preventLink,true);doc.addEventListener('auxclick',preventLink,true);win.addEventListener('scroll',syncPage,{passive:true})
  setLoading(true);setError('');setTotal(0);setCurrent(1);setZoom(1);zoomRef.current=1;pages.current=[];root.replaceChildren();root.style.zoom='1'
  const styles=doc.createElement('div'),content=doc.createElement('div');root.append(styles,content)
  async function load(){
   try{
    let blob=file
    if(!blob){if(!url)throw Error('未找到 Word 原件');const response=await fetch(url,{credentials:'same-origin',signal:controller.signal});if(!response.ok)throw Error('Word 原件读取失败');blob=await response.blob() as File}
    if(blob.size>200*1024*1024)throw Error('单文件不能超过200 MB')
    const {renderAsync}=await import('docx-preview')
    if(controller.signal.aborted)return
    await renderAsync(blob,content,styles,{className:'wg-docx-page',breakPages:true,ignoreLastRenderedPageBreak:false,ignoreWidth:false,ignoreHeight:false,ignoreFonts:false,renderHeaders:true,renderFooters:true,renderFootnotes:true,renderEndnotes:true,renderAltChunks:false,useBase64URL:true})
    if(controller.signal.aborted)return
    const list=Array.from(content.querySelectorAll<HTMLElement>('section.wg-docx-page'));if(!list.length)throw Error('未读取到可预览的 Word 页面')
    pages.current=list
    const refit=()=>{const width=Math.max(...list.map(el=>el.offsetWidth));fit.current=Math.min(1,Math.max(.1,((frame.current?.clientWidth??width)-16)/Math.max(1,width)));applyZoom()}
    refit();resize=new ResizeObserver(refit);if(frame.current)resize.observe(frame.current)
    setTotal(list.length);setLoading(false)
   }catch(e){if(!controller.signal.aborted){setError(e instanceof Error?e.message:'Word 版式读取失败');setLoading(false)}}
  }
  void load()
  return()=>{controller.abort();resize?.disconnect();win.removeEventListener('scroll',syncPage);doc.removeEventListener('click',preventLink,true);doc.removeEventListener('auxclick',preventLink,true);styles.remove();content.remove();pages.current=[]}
 },[file,url,ready,retry,showFallback])
 function changeZoom(value:number){zoomRef.current=value;setZoom(value);applyZoom()}
 if(showFallback)return <section className="wg-word-fallback"><button type="button" onClick={()=>{setReady(0);setShowFallback(false)}}>返回 Word 版式预览</button>{fallback}</section>
 return <section className="wg-word-viewer" aria-label="Word 版式预览"><div className="wg-word-toolbar"><button type="button" disabled={loading||current<=1||!!error} onClick={()=>go(current-1)}>上一页</button><span>{total?current+' / '+total:'Word 预览'}</span><button type="button" disabled={loading||current>=total||!!error} onClick={()=>go(current+1)}>下一页</button></div><div className="wg-word-toolbar"><button type="button" aria-label="缩小 Word" disabled={loading||zoom<=1||!!error} onClick={()=>changeZoom(Math.max(1,zoom-.5))}>−</button><button type="button" disabled={loading||!!error} onClick={()=>changeZoom(1)}>{zoom===1?'适合屏幕':Math.round(zoom*100)+'%'}</button><button type="button" aria-label="放大 Word" disabled={loading||zoom>=3||!!error} onClick={()=>changeZoom(Math.min(3,zoom+.5))}>+</button>{fallback&&<button type="button" onClick={()=>setShowFallback(true)}>正文模式</button>}</div><small className="wg-word-note">{file?'本地预览 · 尚未上传':'原始文件版式预览'} · 复杂排版及自动分页可能与 Word 有差异</small>{loading&&<p role="status">正在读取 Word 版式…</p>}{error&&<div className="wg-word-error" role="alert"><p>{error}</p><button type="button" onClick={()=>setRetry(n=>n+1)}>重试</button>{fallback&&<button type="button" onClick={()=>setShowFallback(true)}>查看提取正文</button>}</div>}<iframe ref={frame} title="Word 页面" sandbox="allow-same-origin" srcDoc={frameMarkup} onLoad={()=>{if(frame.current?.contentDocument?.getElementById('word-preview-content'))setReady(v=>v+1)}} style={{visibility:loading||error?'hidden':'visible'}}/></section>
}
