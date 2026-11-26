import {api} from '../auth'
import type {ModelCatalog} from './ReasoningEffort'

// Shared in-memory catalog. No authentication credentials or persisted catalog.
let current:ModelCatalog|undefined,updated=0,generation=0
let pending:{force:boolean;promise:Promise<ModelCatalog>;controller:AbortController}|undefined
const choices=new Map<'chat'|'work'|'video',{model:string;effort:string}>()
export function clearModelChoices(){choices.clear()}
export function rememberModelChoice(scope:'chat'|'work'|'video',model:string,effort:string){choices.set(scope,{model,effort})}
export function modelChoice(scope:'chat'|'work'|'video',model:string,effort:string){return choices.get(scope)??{model,effort}}
export function invalidateModelCatalog(){
 generation++;current=undefined;updated=0;pending?.controller.abort();pending=undefined;clearModelChoices()
}
export function getModelCatalog(force=false,fresh=false):Promise<ModelCatalog>{
 if(pending){
  if(!force||pending.force)return pending.promise
  // A manual refresh must really call POST, even if a GET is in flight.
  const revision=generation
  return pending.promise.catch(()=>undefined).then(()=>{if(revision!==generation)throw Error('模型清单已失效，请重新获取。');return getModelCatalog(true,true)})
 }
 if(!force&&!fresh&&current&&Date.now()-updated<1500)return Promise.resolve(current)
 const revision=generation,controller=new AbortController()
 const timeout=window.setTimeout(()=>controller.abort(),force?55000:10000)
 const promise=api<ModelCatalog>(force?'/qoder/models/refresh':'/qoder/models',{...(force?{method:'POST',body:'{}'}:{}),signal:controller.signal}).then(r=>{
  if(revision!==generation)throw Error('模型清单已失效，请重新获取。')
  if(!Array.isArray(r.models))throw Error('模型清单格式有误')
  current=r;updated=Date.now();return r
 }).finally(()=>{window.clearTimeout(timeout);if(pending?.controller===controller)pending=undefined})
 pending={force,promise,controller};return promise
}
