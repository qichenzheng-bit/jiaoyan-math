import {useEffect,useRef,useState} from 'react'
import type {CSSProperties} from 'react'
import type {Layout} from './documentLayout'
import {dimensions} from './documentLayout'
import {MathText} from '../components/MathText'
import './document-layout.css'

export type WrapSettings={spine:number;bleed:number;spineText:string;background:string;foreground:string}
export const wrapDefaults:WrapSettings={spine:10,bleed:3,spineText:'',background:'#ffffff',foreground:'#222222'}
export function wrapDimensions(layout:Layout,wrap:WrapSettings){
 const [w,h]=dimensions(layout)
 return {w,h,totalWidth:2*w+wrap.spine+2*wrap.bleed,totalHeight:h+2*wrap.bleed}
}
export function wrapError(layout:Layout,wrap:WrapSettings){
 if(!layout.coverFileId||!layout.backCoverFileId)return '请先选择封面与封底。'
 if(Object.keys(layout.sectionPages).length)return '混合纸型的资料请先确认统一成品开本，再制作书衣。'
 if(!Number.isFinite(wrap.spine)||wrap.spine<0||wrap.spine>150||!Number.isFinite(wrap.bleed)||wrap.bleed<0||wrap.bleed>20)return '书脊或出血尺寸无效。'
 if(!/^#[0-9a-f]{6}$/i.test(wrap.background)||!/^#[0-9a-f]{6}$/i.test(wrap.foreground))return '颜色格式无效。'
 if(wrap.spineText.trim()&&wrap.spine<4)return '书脊不足 4 mm，请删除书脊文字或调整宽度。'
 return ''
}
export function WrapArt({layout,wrap}:{layout:Layout;wrap:WrapSettings}){
 const {w,h,totalWidth,totalHeight}=wrapDimensions(layout,wrap)
 const style={width:totalWidth+'mm',height:totalHeight+'mm',padding:wrap.bleed+'mm',background:wrap.background,color:wrap.foreground,'--wrap-width':w+'mm','--wrap-height':h+'mm','--wrap-spine':wrap.spine+'mm'} as CSSProperties
 return <article className="layout-wrap-art" style={style}>
  <div className="layout-wrap-panel"><img src={'/api/files/'+layout.backCoverFileId+'/preview'} alt="封底"/></div>
  <div className="layout-wrap-spine">{wrap.spine>0&&wrap.spineText&&<div className="layout-wrap-spine-text" style={{fontSize:Math.min(12,wrap.spine*1.8)+'pt'}}><MathText compact content={wrap.spineText}/></div>}</div>
  <div className="layout-wrap-panel"><img src={'/api/files/'+layout.coverFileId+'/preview'} alt="封面"/></div>
 </article>
}
export function WrapPdf({layout,wrap}:{layout:Layout;wrap:WrapSettings}){
 const root=useRef<HTMLDivElement>(null),[status,setStatus]=useState('pending'),[error,setError]=useState('')
 const {totalWidth,totalHeight}=wrapDimensions(layout,wrap)
 useEffect(()=>{
  let live=true
  async function verify(){
   try{
    const invalid=wrapError(layout,wrap);if(invalid)throw Error(invalid)
    await document.fonts.ready
    await Promise.all(Array.from(root.current?.querySelectorAll('img')??[]).map(img=>img.decode()))
    if(!live)return
    const spine=root.current?.querySelector<HTMLElement>('.layout-wrap-spine-text')
    if(root.current?.querySelector('.formula-error,.katex-error'))throw Error('书脊文字含无效公式')
    if(spine&&(spine.scrollHeight>spine.clientHeight+2||spine.scrollWidth>spine.clientWidth+2))throw Error('书脊文字超出可用空间')
    setStatus('ready')
   }catch(e){if(live){setError(e instanceof Error?e.message:'书衣检查失败');setStatus('failed')}}
  }
  void verify();return()=>{live=false}
 },[layout,wrap])
 return <div ref={root} className="layout-wrap-pdf" data-pdf-state={status} data-pdf-pages={status==='ready'?1:0}>
  <style>{'@page{size:'+totalWidth+'mm '+totalHeight+'mm;margin:0}'}</style>
  <WrapArt layout={layout} wrap={wrap}/>
  {error&&<p role="alert">{error}</p>}
 </div>
}
