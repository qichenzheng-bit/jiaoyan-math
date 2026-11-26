import {useLayoutEffect,useRef} from 'react'
type Mode='chat'|'work'
const drafts=new Map<Mode,{path:string;value:unknown}>()
export const MODE_SWITCH_EVENT='wg-preserve-mode-draft'
export function clearModeDrafts(){drafts.clear()}
export function readModeDraft<T>(mode:Mode,path:string,state:unknown):T|undefined{
 if(!(state as {resumeMode?:boolean}|null)?.resumeMode)return
 const stored=drafts.get(mode)
 return stored?.path===path?stored.value as T:undefined
}
export function useModeDraft<T>(mode:Mode,path:string,value:T){
 const latest=useRef(value);latest.current=value
 useLayoutEffect(()=>{
  // Only capture when an explicit mode switch was approved, not on ordinary navigation.
  drafts.delete(mode)
  const preserve=()=>drafts.set(mode,{path,value:latest.current})
  window.addEventListener(MODE_SWITCH_EVENT,preserve)
  return()=>window.removeEventListener(MODE_SWITCH_EVENT,preserve)
 },[mode,path])
}
