import {useState} from 'react'
import type {Layout,SectionPage} from './documentLayout'
import {sanitizeSection} from './documentLayout'
import type {PrintDoc} from './DocumentPrint'

export default function SectionPageEditor({doc,layout,onChange}:{doc:PrintDoc;layout:Layout;onChange:(v:Partial<Layout>)=>void}){
 const chapters=doc.blocks.filter(b=>b.kind==='heading'&&b.heading_level===1)
 const [selected,setSelected]=useState('')
 const key=chapters.some(b=>b.uid===selected)?selected:chapters[0]?.uid??''
 const rule=layout.sectionPages[key]??{}
 const change=(patch:Partial<SectionPage>)=>{if(key)onChange({sectionPages:{...layout.sectionPages,[key]:sanitizeSection({...rule,...patch})}})}
 const num=(name:string,field:'width'|'height'|'top'|'bottom'|'left'|'right'|'gap',min:number,max:number)=><label>{name}<input type="number" min={min} max={max} placeholder="继承全局" value={rule[field]??''} onChange={e=>{const v=e.currentTarget.valueAsNumber;change({[field]:Number.isFinite(v)?Math.max(min,Math.min(max,v)):undefined})}}/></label>
 if(!chapters.length)return null
 return <details><summary>章节独立页面设置</summary><div className="layout-fields">
  <label>章节<select aria-label="分节目标" value={key} onChange={e=>setSelected(e.target.value)}>{chapters.map(b=><option key={b.uid} value={b.uid}>{b.title||b.content}</option>)}</select></label>
  <label>纸张<select aria-label="分节纸张" value={rule.paper??''} onChange={e=>change({paper:(e.target.value||undefined) as SectionPage['paper']})}><option value="">继承全局</option>{['A4','A3','A5','B5','A6','custom'].map(p=><option key={p} value={p}>{p==='custom'?'自定义':p}</option>)}</select></label>
  <label>方向<select value={rule.landscape===undefined?'':String(rule.landscape)} onChange={e=>change({landscape:e.target.value===''?undefined:e.target.value==='true'})}><option value="">继承全局</option><option value="false">纵向</option><option value="true">横向</option></select></label>
  <label>分栏<select value={rule.columns??''} onChange={e=>change({columns:e.target.value?Number(e.target.value) as 1|2|3:undefined})}><option value="">继承全局</option>{[1,2,3].map(n=><option key={n} value={n}>{n} 栏</option>)}</select></label>
  {(rule.paper??layout.paper)==='custom'&&<>{num('分节宽度 (mm)','width',50,1000)}{num('分节高度 (mm)','height',50,1000)}</>}
  {num('分节上边距 (mm)','top',0,100)}{num('分节下边距 (mm)','bottom',0,100)}{num('分节左边距 (mm)','left',0,100)}{num('分节右边距 (mm)','right',0,100)}{num('分节栏间距 (mm)','gap',3,30)}
  <button type="button" onClick={()=>onChange({sectionPages:Object.fromEntries(Object.entries(layout.sectionPages).filter(([id])=>id!==key))})}>恢复本章全局页面设置</button>
 </div><small>设置不同纸型的章节会另起一页。目录沿用全局纸张，模板不会保存特定章节编号。</small></details>
}
