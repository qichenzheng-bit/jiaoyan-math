import {Icon} from './Icon'
export function SaveStatus({dirty,saving=false,error='',archived=false}:{dirty:boolean;saving?:boolean;error?:string;archived?:boolean}){
 const state=archived?'archived':saving?'saving':error?'error':dirty?'dirty':'saved'
 const text=state==='archived'?'已归档':state==='saving'?'保存中…':state==='error'?'保存失败 · 修改仍保留':state==='dirty'?'未保存':'已保存'
 return <span className={'workspace-save-state '+state} role="status"><Icon name={state==='saved'?'check':state==='saving'?'clock':state==='error'?'alert':'more'} size={13}/><span>{text}</span></span>
}
export function WorkspaceFeedback({state,title,detail,onRetry,className=''}:{state:'loading'|'empty'|'error';title:string;detail?:string;onRetry?:()=>void;className?:string}){
 return <div className={'workspace-feedback '+state+' '+className} role={state==='error'?'alert':'status'} aria-busy={state==='loading'||undefined}>
 {state==='loading'?<><span className="workspace-feedback-skeleton" aria-hidden="true"/><span className="workspace-feedback-skeleton short" aria-hidden="true"/></>:<Icon name={state==='error'?'refresh':'files'} size={24}/>}
 <strong>{title}</strong>{detail&&<small>{detail}</small>}{onRetry&&state==='error'&&<button type="button" onClick={onRetry}>重新加载</button>}</div>
}
