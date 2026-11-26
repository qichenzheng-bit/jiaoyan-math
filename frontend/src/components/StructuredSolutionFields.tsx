import {useEffect,useState} from 'react'
import InlineMathEditor from './InlineMathEditor'
import {confirmAction} from './WorkspaceConfirm'
type Method={body:string;recommended:boolean}
const header=/^###\s*(※\s*)?(?:解法|方法)[一二三四五六七八九十\d]+[：:]?\s*$/
const numerals=['一','二','三','四','五','六','七','八','九','十']
function read(raw:string):Method[]{
 const rows:Method[]=[];let current:Method|undefined
 for(const line of raw.split('\n')){
  const m=line.match(header)
  if(m){current={body:'',recommended:!!m[1]};rows.push(current)}
  else if(current)current.body+=(current.body?'\n':'')+line
  else if(line.trim()){current={body:line,recommended:true};rows.push(current)}
 }
 return rows.length?rows:[{body:'',recommended:true}]
}
function write(rows:Method[]){
 if(rows.length===1)return rows[0].body
 return rows.map((m,i)=>'### '+(m.recommended?'※ ':'')+'方法'+(numerals[i]??String(i+1))+'\n'+m.body).join('\n\n')
}
export function SolutionFields({label,value,locked,onChange}:{label:string;value:string;locked:boolean;onChange:(v:string)=>void}){
 const [rows,setRows]=useState(()=>read(value)),[raw,setRaw]=useState(false)
 useEffect(()=>{setRows(old=>write(old)===value?old:read(value))},[value])
 function update(next:Method[]){setRows(next);onChange(write(next))}
 if(raw)return <div><InlineMathEditor label={label} value={value} rows={5} locked={locked} onChange={onChange}/><button type="button" onClick={()=>setRaw(false)}>使用多解法编辑</button></div>
 return <div className="manual-options"><strong>{label}</strong>{rows.map((m,i)=><div key={i} className="manual-subquestion"><InlineMathEditor label={i===0?label:label+' · 解法 '+(i+1)} value={m.body} rows={5} locked={locked} onChange={v=>update(rows.map((x,j)=>j===i?{...x,body:v}:x))}/>{rows.length>1&&<div className="button-row"><button type="button" disabled={locked} aria-pressed={m.recommended} onClick={()=>update(rows.map((x,j)=>({...x,recommended:j===i})))}>推荐解法</button><button type="button" disabled={locked} onClick={async()=>{if(m.body.trim()&&!await confirmAction('移除此解法？'))return;const next=rows.filter((_,j)=>j!==i);if(!next.some(x=>x.recommended))next[0]={...next[0],recommended:true};update(next)}}>移除解法</button></div>}</div>)}<div className="button-row"><button type="button" disabled={locked||rows.length>=30} onClick={()=>update([...rows,{body:'',recommended:false}])}>＋ 添加其他解法</button><button type="button" onClick={()=>setRaw(true)}>编辑原始解析</button></div></div>
}
