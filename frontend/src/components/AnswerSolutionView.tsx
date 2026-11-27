import type {ReactNode} from 'react'
import {MathText} from './MathText'
import {currentQuestionData, type QuestionData} from './questionData'

type Value={content:string;answer?:string|null;solution?:string|null;question_type?:string;question_data?:QuestionData|null;generated_fields?:('answer'|'solution')[]}
type Field='answer'|'solution'
type Section={field:Field;content:string}
type Group={label?:string;sections:Section[]}
const numerals=['一','二','三','四','五','六','七','八','九','十','十一','十二','十三','十四','十五','十六','十七','十八','十九','二十']
/** Only remove an explicit field heading at the start. Never rewrite the math. */
export function fieldBody(value:string|null|undefined,field:Field){
 const name=field==='answer'?'(?:参考)?答案':'(?:参考)?解析'
 const head=new RegExp('^\\s*(?:【'+name+'】[：:]?|(?:#{1,6}\\s*)?'+name+'[：:]|\\*\\*'+name+'[：:]?\\*\\*[：:]?)\\s*')
 return (value??'').replace(head,'').trim()
}
export function displayAnswer(value:string|null|undefined,type?:string){
 const body=fieldBody(value,'answer')
 if(['单选题','多选题','选择题'].includes(type??'')&&/^[A-Z\\s,，、]+$/.test(body))return (body.match(/[A-Z]/g)??[]).join('、')
 return body
}
export function displaySolution(value:string|null|undefined){
 return fieldBody(value,'solution').replace(/^(?:#{1,4}\\s*)?(※\\s*)?(?:方法|解法)\\s*([一二三四五六七八九十\\d]+)\\s*[：:]?\\s*$/gm,(_,star,num)=>'解法'+num+(star?'（推荐解法）':''))
}
export function answerGroups(value:Value,answerOnly=false):Group[]{
 const answer=value.answer??'',solution=value.solution??'',data=currentQuestionData(value.question_data,{content:value.content,answer,solution})
 const sections=(a:string,s:string):Section[]=>[{field:'answer',content:displayAnswer(a,value.question_type)},...(!answerOnly?[{field:'solution' as const,content:displaySolution(s)}]:[])]
 if(data?.subquestions?.length){
  return data.subquestions.map(part=>({label:'第（'+part.number+'）问',sections:sections(part.answer,part.methods.filter(m=>m.body.trim()).map((m,i,all)=>(all.length>1?'解法'+(numerals[i]??String(i+1))+(m.name?'：'+m.name:'')+(i===(all.findIndex(x=>x.recommended)<0?0:all.findIndex(x=>x.recommended))?'（推荐解法）':'')+'\\n':m.name?m.name+'\\n':'')+fieldBody(m.body,'solution')).join('\\n\\n'))}))
 }
 const methods=data?.methods?.filter(m=>m.body.trim())
 const s=methods&&methods.length>1?methods.map((m,i)=>'解法'+(numerals[i]??String(i+1))+(m.name?'：'+m.name:'')+(i===(methods.findIndex(x=>x.recommended)<0?0:methods.findIndex(x=>x.recommended))?'（推荐解法）':'')+'\\n'+fieldBody(m.body,'solution')).join('\\n\\n'):solution
 return [{sections:sections(answer,s)}]
}
export function AnswerSolutionView({value,answerOnly=false,collapsible=false,showMissing=false,showOrigin=false,render=(content)=><MathText content={content}/>}:{value:Value;answerOnly?:boolean;collapsible?:boolean;showMissing?:boolean;showOrigin?:boolean;render?:(content:string)=>ReactNode}){
 return <div className="answer-solution-view">{answerGroups(value,answerOnly).map((group,i)=><section className="answer-solution-group" key={i}>{group.label&&<h4>{group.label}</h4>}{group.sections.filter(s=>showMissing||s.content).map(s=>{
  const label=s.field==='answer'?'答案':'解析',heading=<><strong>【{label}】</strong>{showOrigin&&<small className="muted">{value.generated_fields?.includes(s.field)?'AI 生成 · 待审核':s.content?'原文提取 / 已录入':'待人工补充'}</small>}</>,body=s.content?render(s.content):<small className="muted">未提供，请核对补充。</small>
  return collapsible?<details open className="answer-solution-field" key={s.field}><summary>{heading}</summary><div>{body}</div></details>:<section className="answer-solution-field" key={s.field}><div className="answer-solution-heading">{heading}</div>{body}</section>
 })}</section>)}</div>
}
