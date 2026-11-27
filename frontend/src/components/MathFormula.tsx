import {useMemo} from 'react'
import {renderMathHtml,mathError} from './mathRendering'
import 'katex/dist/katex.min.css'

export function MathFormula({latex,display=true}:{latex:string;display?:boolean}){
 const result=useMemo(()=>{
  try{return {html:renderMathHtml(latex,display)}}
  catch{return {error:mathError(latex)}}
 },[latex,display])
 if(result.error)return <span className={'formula-error '+(display?'formula-block':'formula-inline')} role="status" title={result.error}><span className="formula-error-label">{result.error}</span><code className="formula-error-source">{latex}</code></span>
 return <span className={display?'formula-block':'formula-inline'} dangerouslySetInnerHTML={{__html:result.html??''}}/>
}
