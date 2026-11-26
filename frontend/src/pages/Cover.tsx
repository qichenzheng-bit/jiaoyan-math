import {useEffect,useLayoutEffect,useRef,useState} from 'react'
import {Link} from 'react-router-dom'
import {api} from '../auth'
import {MathText} from '../components/MathText'
import {toBlob} from 'html-to-image'
import './CoverWorkspace.css'
const logo=new URL('../assets/logo.svg',import.meta.url).href
type Presets=Record<string,number[]>
const groups=[
 {id:'bilibili',name:'B站',formats:[['bilibili','4:3 · 列表封面'],['bilibili_wide','16:9 · 播放页']]},
 {id:'douyin',name:'抖音',formats:[['douyin','3:4 · 竖封面'],['douyin_wide','4:3 · 横封面'],['douyin_full','9:16 · 全屏素材']]},
 {id:'xiaohongshu',name:'小红书',formats:[['xiaohongshu','3:4 · 笔记封面']]},
 {id:'wechat_channels',name:'视频号',formats:[['wechat_channels','6:7 · 竖封面'],['wechat_channels_wide','16:9 · 横封面']]},
 {id:'wechat_top',name:'公众号',formats:[['wechat_top','2.35:1 · 首图'],['wechat_sub','1:1 · 次条']]},
]
const palettes=[['#ffffff','#ffffff','#232220'],['#fbf7ee','#f1e9d6','#232220'],['#0d231d','#163a30','#ffffff'],['#122030','#1d364d','#ffffff']]
const defaultTitle='每日一题'
export default function Cover(){
 const [presets,setPresets]=useState<Presets>({}),[group,setGroup]=useState('xiaohongshu'),[format,setFormat]=useState('xiaohongshu'),[title,setTitle]=useState(defaultTitle),[subtitle,setSubtitle]=useState('考研数学'),[palette,setPalette]=useState(0),[size,setSize]=useState(100),[align,setAlign]=useState<'left'|'center'|'right'>('center'),[vertical,setVertical]=useState<'start'|'center'|'end'>('center'),[safe,setSafe]=useState(true),[error,setError]=useState(''),[busy,setBusy]=useState(false),[saved,setSaved]=useState(false),[scale,setScale]=useState(0.2),[overflow,setOverflow]=useState(false),[logoReady,setLogoReady]=useState(false)
 const viewport=useRef<HTMLDivElement>(null),canvas=useRef<HTMLDivElement>(null),logoRef=useRef<HTMLImageElement>(null),copy=useRef<HTMLDivElement>(null),textArea=useRef<HTMLDivElement>(null),p=presets[format]
 const current=groups.find(g=>g.id===group)??groups[2]
 const w=p?.[0]??1080,h=p?.[1]??1440,short=Math.min(w,h),wide=w/h>=1.5
 const compact=format==='wechat_top'
 const base=short*(compact?.085:wide?.095:.075)*size/100
 useEffect(()=>{const c=new AbortController();api<Presets>('/studio/presets',{signal:c.signal}).then(setPresets).catch(e=>{if(!c.signal.aborted)setError(e.message)});return()=>c.abort()},[])
 useEffect(()=>{setSaved(false)},[format,title,subtitle,palette,size,align,vertical])
 useLayoutEffect(()=>{const el=viewport.current;if(!el)return;const resize=()=>setScale(Math.min(1,Math.max(.01,el.clientWidth/w),480/h));const ro=new ResizeObserver(resize);ro.observe(el);resize();return()=>ro.disconnect()},[w,h])
 function fit(){
  const el=copy.current,area=textArea.current;if(!el||!area)return false
  let font=base
  const minimum=Math.min(base,short*.023)
  const fits=()=>el.scrollWidth<=area.clientWidth+1&&el.offsetHeight<=area.clientHeight+1
  el.style.fontSize=font+'px'
  while(!fits()&&font>minimum){font=Math.max(minimum,font*.92);el.style.fontSize=font+'px'}
  const ok=fits();setOverflow(!ok);return ok
 }
 useLayoutEffect(()=>{let active=true;fit();void document.fonts.ready.then(()=>{if(active)fit()});return()=>{active=false}},[p,title,subtitle,base,align,vertical,logoReady])
 function resetLayout(){setSize(100);setAlign('center');setVertical('center')}
 function selectGroup(id:string){const next=groups.find(g=>g.id===id);if(!next)return;setGroup(id);setFormat(next.formats[0][0]);resetLayout();setError('')}
 function selectFormat(id:string){setFormat(id);resetLayout();setError('')}
 async function png(){
  const el=canvas.current;if(!el||!p||!logoReady||!logoRef.current)throw Error('封面尚未就绪')
  await document.fonts.ready;await logoRef.current.decode()
  if(el.querySelector('.formula-error'))throw Error('封面公式存在语法错误，请先修正')
  if(!fit())throw Error('内容超出排版区域，请精简文字或缩小字号')
  const blob=await toBlob(el,{width:w,height:h,canvasWidth:w,canvasHeight:h,pixelRatio:1,cacheBust:false})
  if(!blob)throw Error('导出失败')
  const bitmap=await createImageBitmap(blob);const correct=bitmap.width===w&&bitmap.height===h;bitmap.close()
  if(!correct)throw Error('导出尺寸校验失败')
  return blob
 }
 async function save(download=false){
  setBusy(true);setError('')
  try{
   const blob=await png(),filename=format+'-'+w+'x'+h+'-cover.png'
   if(download){const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);return}
   const f=await fetch('/api/files?name='+encodeURIComponent(filename),{method:'POST',body:blob,credentials:'same-origin'})
   if(!f.ok)throw Error('PNG 保存失败')
   const r=await f.json()
   await api('/studio',{method:'POST',body:JSON.stringify({kind:'work',title:title.trim()||'封面',data:{category:'cover',file_id:r.id,content:JSON.stringify({platform:format,group,width:w,height:h,title,subtitle,palette,size,align,vertical}),note:'平台封面 '+w+'×'+h}})})
   setSaved(true)
  }catch(e){setError(e instanceof Error?e.message:'保存失败')}finally{setBusy(false)}
 }
 return <div className="cover-workspace">
  <nav className="cover-platforms" aria-label="发布平台">{groups.map(g=><button key={g.id} disabled={busy} aria-pressed={group===g.id} onClick={()=>selectGroup(g.id)}>{g.name}</button>)}</nav>
  <div className="cover-format-row"><label>封面比例 <select aria-label="封面比例" disabled={busy} value={format} onChange={e=>selectFormat(e.target.value)}>{current.formats.map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label><small className="muted">{p?w+' × '+h+' px':'正在读取尺寸…'}</small></div>
  {error&&<p className="inline-error" role="alert">{error}</p>}
  <div className="cover-work-grid">
   <section className="cover-work-preview"><div className="cover-preview-top"><strong>实时预览</strong><label><input type="checkbox" checked={safe} onChange={e=>setSafe(e.target.checked)}/> 安全区</label></div>
    <div ref={viewport} className="cover-viewport">{p&&<div className="cover-canvas cover-scaled" style={{width:w*scale,height:h*scale,aspectRatio:w+'/'+h}}><div className="cover-native-frame" style={{width:w,height:h,transform:'scale('+scale+')'}}>
     <div ref={canvas} className="math-cover-art cover-native-art" style={{width:w,height:h,background:'linear-gradient(135deg,'+palettes[palette][0]+','+palettes[palette][1]+')',color:palettes[palette][2]}}>
      <div className="cover-content-area" style={{top:p[2]+'%',bottom:p[3]+'%',left:p[4]+'%',right:p[5]+'%',gap:short*(compact?.02:.045)}}>
       <div className="cover-brand-row" style={{justifyContent:wide&&!compact?'flex-start':'center'}}><img ref={logoRef} onLoad={()=>setLogoReady(true)} onError={()=>setError('原系统 Logo 加载失败')} src={logo} alt="微光数学" style={{width:Math.min(short*(compact?.55:.38),w*(1-(p[4]+p[5])/100)*.75),maxHeight:short*(compact?.13:.12),objectFit:'contain',background:palette>=2?'#fff':'transparent',borderRadius:short*.006}}/></div>
       <div ref={textArea} className="cover-copy-area" style={{justifyContent:vertical==='start'?'flex-start':vertical==='end'?'flex-end':'center'}}>
        <div ref={copy} className="cover-copy-fit" style={{fontSize:base,textAlign:align}}>
         <div className="math-cover-title"><MathText content={title}/></div>
         {subtitle&&<div className="math-cover-subtitle"><MathText content={subtitle}/></div>}
        </div>
       </div>
      </div>
     </div>
     {safe&&<div className="cover-safe cover-native-safe" style={{top:p[2]+'%',bottom:p[3]+'%',left:p[4]+'%',right:p[5]+'%'}}/>}
    </div></div>}</div>
    {overflow&&<small className="inline-error">文字过长，已达到最小自动字号，请精简内容。</small>}
    <div className="button-row"><button disabled={busy||!p||!logoReady||overflow} onClick={()=>void save(true)}>下载 PNG</button><button className="primary" disabled={busy||!p||!logoReady||overflow||saved} onClick={()=>void save()}>{saved?'已保存':'保存至作品库'}</button><Link to="/works" className="text-link">查看作品</Link></div>
   </section>
   <section className="cover-work-settings"><strong>封面内容</strong><label>主标题<textarea rows={4} maxLength={500} disabled={busy} value={title} onChange={e=>setTitle(e.target.value)}/></label><label>副标题<input maxLength={160} disabled={busy} value={subtitle} onChange={e=>setSubtitle(e.target.value)}/></label><label>配色<select disabled={busy} value={palette} onChange={e=>setPalette(Number(e.target.value))}>{['极简素白','学术暖纸','深林微光','靛青板书'].map((v,i)=><option key={v} value={i}>{v}</option>)}</select></label>
    <details><summary>排版微调</summary><label>字号 {size}%<input type="range" min={60} max={150} value={size} disabled={busy} onChange={e=>setSize(Number(e.target.value))}/></label><label>水平对齐<select value={align} disabled={busy} onChange={e=>setAlign(e.target.value as typeof align)}><option value="center">居中</option><option value="left">左对齐</option><option value="right">右对齐</option></select></label><label>垂直位置<select value={vertical} disabled={busy} onChange={e=>setVertical(e.target.value as typeof vertical)}><option value="center">居中</option><option value="start">靠上</option><option value="end">靠下</option></select></label><button type="button" disabled={busy} onClick={resetLayout}>恢复默认排版</button></details>
    <small className="muted">切换比例时保留文字和配色，自动适配排版。支持 LaTeX。安全区为排版参考线，不进入导出图片。</small>
   </section>
  </div>
 </div>
}
