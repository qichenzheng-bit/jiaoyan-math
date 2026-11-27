// The versioned representation is shared by manual entry, AI review and resource editing.
export type Method={name?:string;body:string;recommended?:boolean}
export type QuestionData={version:1;stem:string;options?:{label:string;content:string}[];correct_options?:string[];subquestions?:{number:number;content:string;answer:string;methods:Method[]}[];blanks?:{number:number;answer:string}[];answer?:string;methods?:Method[];warnings?:string[];legacy_digest?:string|null}
type Legacy={content:string;answer:string;solution:string}
const cn=["一","二","三","四","五","六","七","八","九","十","十一","十二","十三","十四","十五","十六","十七","十八","十九","二十"]
export function methodText(methods:Method[]=[]){
 const rows=methods.filter(m=>m.body.trim()).map(m=>({...m,body:(m.name?m.name+'\n'+m.body:m.body).trim()}))
 if(!rows.length)return ''
 if(rows.length===1)return rows[0].body
 const selected=rows.findIndex(m=>m.recommended)
 return rows.map((m,i)=>'### '+(i===(selected<0?0:selected)?'※ ':'')+'方法'+(cn[i]??String(i+1))+'\n'+m.body).join('\n\n')
}
export function projectQuestion(d:QuestionData):Legacy{
 let content=d.stem,answer=d.answer??'',solution=methodText(d.methods)
 if(d.options?.length){content=[content,...d.options.map(o=>o.label+'. '+o.content)].join('\n').trim();if(d.correct_options?.length)answer=d.correct_options.join('')}
 if(d.subquestions?.length){content=[content,...d.subquestions.map(p=>'('+p.number+')'+(p.content?' '+p.content:''))].join('\n').trim();answer=d.subquestions.filter(p=>p.answer).map(p=>'('+p.number+') '+p.answer).join('\n');solution=d.subquestions.filter(p=>methodText(p.methods)).map(p=>'('+p.number+') '+methodText(p.methods)).join('\n')}
 if(d.blanks?.length)answer=d.blanks.length===1?d.blanks[0].answer:d.blanks.filter(p=>p.answer).map(p=>'('+p.number+') '+p.answer).join('\n')
 return {content,answer,solution}
}
export function currentQuestionData(data:QuestionData|null|undefined,value:Legacy){
 if(!data||data.version!==1||data.warnings?.length)return undefined
 const p=projectQuestion(data)
 return p.content===value.content&&p.answer===value.answer&&p.solution===value.solution?data:undefined
}
