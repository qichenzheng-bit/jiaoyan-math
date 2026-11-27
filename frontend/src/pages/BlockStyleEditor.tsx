import {useState} from 'react'
import type {BlockStyle,Layout,Role} from './documentLayout'
import {sanitizeRule} from './documentLayout'
import type {PrintDoc} from './DocumentPrint'

const roles:Record<Role,string>={normal:'普通内容',knowledge:'知识点',definition:'定义',theorem:'定理',lemma:'引理',corollary:'推论',proof:'证明',example:'例题',exercise:'练习',method:'方法',warning:'易错点',summary:'小结'}
const types=[['question','全部题目'],['knowledge','知识点'],['text','正文'],['heading','标题'],['image','图片'],['选择题','选择题'],['单选题','单选题'],['多选题','多选题'],['填空题','填空题'],['解答题','解答题'],...Object.entries(roles).filter(([key])=>key!=='normal').map(([key,name])=>['role:'+key,name])]
type Scope='typeStyles'|'chapterStyles'|'blockStyles'
export default function BlockStyleEditor({doc,layout,onChange,picked}:{doc:PrintDoc;layout:Layout;onChange:(v:Partial<Layout>)=>void;picked:string}){
 const [scope,setScope]=useState<Scope>('blockStyles'),[key,setKey]=useState(''),[seen,setSeen]=useState('')
 if(picked&&picked!==seen){setSeen(picked);setScope('blockStyles');setKey(picked)}
 const choices=scope==='typeStyles'?types:doc.blocks.filter(b=>scope!=='chapterStyles'||b.kind==='heading'&&b.heading_level===1).map((b,i)=>[b.uid,(i+1)+'. '+((b.snapshot??b).title||(b.snapshot??b).content?.slice(0,55)||b.kind)])
 const active=choices.some(x=>x[0]===key)?key:choices[0]?.[0]??''
 const rule=layout[scope][active]??{}
 function change(values:Partial<BlockStyle>){
  if(!active)return
  onChange({[scope]:{...layout[scope],[active]:sanitizeRule({...rule,...values})}})
 }
 function reset(){
  onChange({[scope]:Object.fromEntries(Object.entries(layout[scope]).filter(([k])=>k!==active))})
 }
 const num=(name:string,field:'size'|'lineHeight'|'paragraphGap'|'answerSpace',min:number,max:number,step:number)=><label>{name}<input type="number" aria-label={name} min={min} max={max} step={step} placeholder="继承上级" value={rule[field]??''} onChange={e=>{const n=e.currentTarget.valueAsNumber;change({[field]:Number.isFinite(n)?Math.max(min,Math.min(max,n)):undefined})}}/></label>
 return <details open={!!picked}><summary>局部排版与内容引用</summary>
  <div className="layout-fields">
   <label>应用范围<select aria-label="局部排版范围" value={scope} onChange={e=>{setScope(e.target.value as Scope);setKey('')}}><option value="typeStyles">同类内容</option><option value="chapterStyles">当前章</option><option value="blockStyles">单个内容</option></select></label>
   <label>目标<select aria-label="局部排版目标" value={active} onChange={e=>setKey(e.target.value)}>{choices.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
   {num('局部字号 (pt)','size',6,36,.5)}{num('局部行距','lineHeight',1,3,.1)}{num('局部段后间距 (pt)','paragraphGap',0,50,.5)}{num('局部答题留白 (mm)','answerSpace',0,180,5)}
   <label>对齐方式<select aria-label="局部对齐" value={rule.align??''} onChange={e=>change({align:(e.target.value||undefined) as BlockStyle['align']})}><option value="">继承</option>{[['left','左对齐'],['center','居中'],['right','右对齐'],['justify','两端对齐']].map(([v,t])=><option key={v} value={v}>{t}</option>)}</select></label>
   <label>字重<select value={rule.bold===undefined?'':String(rule.bold)} onChange={e=>change({bold:e.target.value===''?undefined:e.target.value==='true'})}><option value="">继承</option><option value="true">加粗</option><option value="false">普通</option></select></label>
   <label>内容样式<select value={rule.frame??''} onChange={e=>change({frame:(e.target.value||undefined) as BlockStyle['frame']})}><option value="">继承</option>{[['none','无边框'],['border','边框'],['accent','侧边线'],['fill','浅色背景']].map(([v,t])=><option key={v} value={v}>{t}</option>)}</select></label>
   <label>教学角色<select value={rule.role??''} onChange={e=>change({role:(e.target.value||undefined) as Role|undefined})}><option value="">继承</option>{Object.entries(roles).map(([v,t])=><option key={v} value={v}>{t}</option>)}</select></label>
   <label>分页规则<select value={rule.pageBreak??''} onChange={e=>change({pageBreak:(e.target.value||undefined) as BlockStyle['pageBreak']})}><option value="">继承</option><option value="auto">自动</option><option value="before">之前分页</option><option value="after">之后分页</option><option value="alone">独占页面</option></select></label>
   <label>标题层级<select value={rule.headingLevel??''} onChange={e=>change({headingLevel:e.target.value?Number(e.target.value) as BlockStyle['headingLevel']:undefined})}><option value="">继承</option>{[1,2,3,4,5,6].map(n=><option key={n} value={n}>{n} 级</option>)}</select></label>
   <label>局部选项排列<select value={rule.optionColumns??''} onChange={e=>change({optionColumns:e.target.value===''?undefined:e.target.value==='auto'?'auto':Number(e.target.value) as 1|2|4})}><option value="">继承</option><option value="auto">自动</option><option value="1">竖排</option><option value="2">双列</option><option value="4">四列</option></select></label>
   <button type="button" disabled={!active} onClick={reset}>清除所选局部格式</button>
  </div>
  <small>全局 → 同类内容 → 当前章 → 单个内容。单击预览中的内容可快速定位；此设置不修改原题。</small>
  {scope==='blockStyles'&&active&&<label>内容引用标记（可复制到正文）<input readOnly value={'[[ref:'+active+']]'} onFocus={e=>e.currentTarget.select()}/></label>}
 </details>
}
