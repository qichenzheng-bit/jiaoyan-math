import {MathFormula} from './MathFormula'
import {inlineImage,inlineImagePattern} from './inlineImages'
import type {ReactNode} from 'react'
type Token={kind:'text'|'math'|'bold'|'code'|'pre'|'image';value:string;display?:boolean}
// Explicit math delimiters, including bare AMS environments. Never guess at ordinary prose.
const pattern=/(\x60{3}[\s\S]*?(?:\x60{3}|$)|(?<!\\)\$\$[\s\S]+?(?<!\\)\$\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)|(?<![\\$])\$(?!\$)[^\n]+?(?<!\\)\$(?!\$)|\\begin\{(aligned|align\*?|gathered|gather\*?|cases|[pbBvV]?matrix|split|equation\*?)\}[\s\S]+?\\end\{\2\}|\*\*[^*\n]+\*\*|\x60[^\x60\n]+\x60)/g
const richPattern=new RegExp(pattern.source+'|'+inlineImagePattern.source,'g')
export function mathTokens(content:string):Token[]{
 const result:Token[]=[];let pos=0
 for(const m of content.matchAll(richPattern)){
  const t=m[0],start=m.index??0
  if(start>pos)result.push({kind:'text',value:content.slice(pos,start)})
  let token:Token
  if(inlineImage(t))token={kind:'image',value:t}
  else if(t.startsWith(String.fromCharCode(96).repeat(3))){
   const match=t.match(/^\x60{3}(?:latex|tex|math)\s*\n([\s\S]*?)\x60{3}$/i)
   token=match?{kind:'math',value:match[1].trim(),display:true}:{kind:'pre',value:t.replace(/^\x60{3}[^\n]*\n?/,'').replace(/\x60{3}$/,'')}
  }else if(t.startsWith('$$')||t.startsWith('\\['))token={kind:'math',value:t.slice(2,-2),display:true}
  else if(t.startsWith('\\('))token={kind:'math',value:t.slice(2,-2)}
  else if(t.startsWith('$'))token={kind:'math',value:t.slice(1,-1)}
  else if(t.startsWith('\\begin'))token={kind:'math',value:t,display:true}
  else if(t.startsWith('**'))token={kind:'bold',value:t.slice(2,-2)}
  else token={kind:'code',value:t.slice(1,-1)}
  result.push(token);pos=start+t.length
 }
 if(pos<content.length)result.push({kind:'text',value:content.slice(pos)})
 return result
}
function textNodes(value:string,compact:boolean):ReactNode[]{
 // Legacy pure-LaTeX lines sometimes omit delimiters. Only recognize explicit mathematical commands on a non-prose line.
 return value.split(/(\n)/).map((line,i)=>{
  const s=line.trim()
  if(s&&/\\(?:frac|dfrac|tfrac|lim|sum|prod|int|iint|iiint|sqrt|infty|partial|alpha|beta|gamma|theta|lambda|pi|sin|cos|tan|ln|log|leq|geq|neq|to|cdot|times|begin|left|right|mathbb|mathbf|vec|overline)\b/.test(s)&&!/[^\x00-\x7f]/.test(s)&&!/(?:https?:|\\(?:text|href|url)\b)/.test(s)){
   return <MathFormula key={i} latex={s} display={!compact}/>
  }
  return <span key={i}>{line}</span>
 })
}
function nodes(content:string,compact:boolean):ReactNode[]{return mathTokens(content).map((t,i)=>{
 if(t.kind==='math'){
  // AMS display wrappers are normalized for KaTeX without changing the stored formula.
  const latex=t.value
  return <MathFormula key={i} latex={latex} display={!compact&&Boolean(t.display)} />
 }
 if(t.kind==='image'){const image=inlineImage(t.value);return image?<span key={i} className={'stored-inline-image'+(compact?' compact':'')} style={{width:compact?undefined:image.width+'%'}}><img src={image.url} alt="配图" loading="lazy"/></span>:<span key={i}>{t.value}</span>}
 if(t.kind==='bold')return <strong key={i}>{nodes(t.value,compact)}</strong>
 if(t.kind==='code')return <code key={i}>{t.value}</code>
 if(t.kind==='pre')return compact?<code key={i}>{t.value}</code>:<pre key={i}><code>{t.value}</code></pre>
 return <span key={i}>{textNodes(t.value,compact)}</span>
})}
export function MathText({content,compact=false}:{content?:string|null;compact?:boolean}){
 return compact?<span className="math-text-inline">{nodes(content??'',true)}</span>:<div className="chat-rich math-text-block">{nodes(content??'',false)}</div>
}
// Native option elements cannot display KaTeX HTML. Use this controlled picker for mathematical names.
export function MathChoice({value,onChange,options,disabled=false,label='选择',placeholder='请选择'}:{value:string;onChange:(v:string)=>void;options:{value:string;label:string}[];disabled?:boolean;label?:string;placeholder?:string}){
 const chosen=options.find(o=>o.value===value)
 return <details className="math-choice" onToggle={e=>{if(disabled)e.currentTarget.open=false}}><summary aria-label={label} aria-disabled={disabled} tabIndex={disabled?-1:0} onClick={e=>{if(disabled)e.preventDefault()}}><MathText compact content={chosen?.label??placeholder}/></summary><div className="math-choice-options" role="group" aria-label={label}>{options.map(o=><button type="button" key={o.value} aria-pressed={value===o.value} disabled={disabled} onClick={e=>{onChange(o.value);e.currentTarget.closest('details')?.removeAttribute('open')}}><MathText compact content={o.label}/></button>)}</div></details>
}
