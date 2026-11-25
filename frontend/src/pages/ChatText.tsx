import {MathFormula} from '../components/MathFormula'
import type {ReactNode} from 'react'
// Render plain text safely, with bounded formula and code parsing. No raw HTML.
const pattern=/(\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\\([^\n]+?\\\)|(?<!\\)\$[^\n$]+?(?<!\\)\$|\*\*[^*\n]+\*\*|`[^`\n]+`)/g
function inline(value:string){
 return value.split(pattern).map((t,i)=>{
  if(t.startsWith('$$')&&t.endsWith('$$'))return <MathFormula key={i} latex={t.slice(2,-2)} display/>
  if(t.startsWith('\\[')&&t.endsWith('\\]'))return <MathFormula key={i} latex={t.slice(2,-2)} display/>
  if(t.startsWith('\\(')&&t.endsWith('\\)'))return <MathFormula key={i} latex={t.slice(2,-2)} display={false}/>
  if(t.startsWith('$')&&t.endsWith('$')&&t.length>2)return <MathFormula key={i} latex={t.slice(1,-1)} display={false}/>
  if(t.startsWith('**')&&t.endsWith('**'))return <strong key={i}>{t.slice(2,-2)}</strong>
  if(t.startsWith('`')&&t.endsWith('`'))return <code key={i}>{t.slice(1,-1)}</code>
  return <span key={i}>{t}</span>
 })
}
export default function ChatText({content}:{content:string}){
 const blocks:ReactNode[]=[]
 const parts=content.split(/(```[\s\S]*?(?:```|$))/g)
 for(const [i,t] of parts.entries()){
  if(!t)continue
  if(t.startsWith('```')){blocks.push(<pre key={i}><code>{t.replace(/^```[^\n]*\n?/,'').replace(/```$/,'')}</code></pre>);continue}
  blocks.push(<div key={i} className="chat-prose">{inline(t)}</div>)
 }
 return <div className="chat-rich">{blocks}</div>
}
