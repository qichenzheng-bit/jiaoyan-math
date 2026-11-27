import {useEffect,useState} from 'react'
import {PrintableDocument} from './DocumentPrint'
import type {PrintDoc} from './DocumentPrint'
import {sanitizeLayout} from './documentLayout'
import type {Layout} from './documentLayout'
import PagedPreview from './PagedPreview'

type Payload={doc:PrintDoc;layout:Layout;stem:boolean;answerOnly:boolean;source:boolean}
// This route has no production data endpoint. The isolated PDF worker supplies
// a single authorized snapshot through its private, intercepted browser route.
export default function PdfRender(){
 const [payload,setPayload]=useState<Payload>(),[error,setError]=useState('')
 useEffect(()=>{
  const controller=new AbortController()
  fetch('/api/layout-payload',{signal:controller.signal}).then(async response=>{
   if(!response.ok)throw Error('没有可用于排版的快照')
   const value=await response.json() as Payload
   if(!controller.signal.aborted)setPayload({...value,layout:sanitizeLayout(value.layout)})
  }).catch(e=>{if(!controller.signal.aborted)setError(e instanceof Error?e.message:'快照读取失败')})
  return()=>controller.abort()
 },[])
 if(error)return <div data-pdf-state="failed" role="alert">{error}</div>
 if(!payload)return <div data-pdf-state="pending"/>
 const {doc,layout,stem,answerOnly,source}=payload
 return <PagedPreview layout={layout} title={doc.title} subject={doc.subject??''} version={payload}>
  <PrintableDocument doc={doc} layout={layout} stem={stem} answerOnly={answerOnly} source={source}/>
 </PagedPreview>
}
