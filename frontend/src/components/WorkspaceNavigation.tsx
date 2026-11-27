import {useEffect,useLayoutEffect,useRef} from 'react'
import {Link,useBlocker,useLocation,useNavigate,useResolvedPath,type LinkProps} from 'react-router-dom'
import {confirmAction} from './WorkspaceConfirm'

type Guard={busy:boolean;dirty:boolean;message:string;preserveOnModeSwitch?:boolean;allow?:(path:string)=>boolean}
const guards=new Map<symbol,Guard>()
function affected(path:string){return [...guards.values()].filter(g=>!g.allow?.(path))}
function needsGuard(path:string,preserveDraft=false){return affected(path).some(g=>g.busy||g.dirty&&!(preserveDraft&&g.preserveOnModeSwitch))}
let pending=false
export async function guardNavigation(path:string,preserveDraft=false):Promise<boolean>{
 const active=affected(path)
 if(active.some(g=>g.busy)||pending)return false
 const dirty=active.find(g=>g.dirty&&!(preserveDraft&&g.preserveOnModeSwitch))
 if(!dirty)return true
 pending=true
 try{return await confirmAction(dirty.message,'离开当前页面','离开')}finally{pending=false}
}
export function useWorkspaceGuard(guard:Guard){
 const key=useRef(Symbol('workspace-guard'))
 useLayoutEffect(()=>{const id=key.current;guards.set(id,guard);return()=>{guards.delete(id)}},[guard.busy,guard.dirty,guard.message,guard.allow,guard.preserveOnModeSwitch])
 useEffect(()=>{if(!guard.dirty&&!guard.busy)return;const warn=(e:BeforeUnloadEvent)=>{e.preventDefault();e.returnValue=''};window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn)},[guard.busy,guard.dirty])
}
// Browser Back/Forward has no Link click; block only POP transitions here.
// Explicit save/submit navigation remains controlled by the owning page.
export function usePopNavigationGuard(){
 const blocker=useBlocker(({historyAction,nextLocation})=>historyAction==='POP'&&needsGuard(nextLocation.pathname+nextLocation.search+nextLocation.hash))
 const handling=useRef(false)
 useEffect(()=>{if(blocker.state!=='blocked'||handling.current)return;handling.current=true;const path=blocker.location.pathname+blocker.location.search+blocker.location.hash;void guardNavigation(path).then(ok=>{if(ok)blocker.proceed();else blocker.reset()}).finally(()=>{handling.current=false})},[blocker])
}
export function WorkspaceLink({onApproved,onClick,to,preserveDraft=false,...props}:LinkProps&{onApproved?:()=>void;preserveDraft?:boolean}){
 const navigate=useNavigate(),resolved=useResolvedPath(to,{relative:props.relative}),location=useLocation()
 const path=resolved.pathname+resolved.search+resolved.hash
 return <Link {...props} to={to} onClick={e=>{
  onClick?.(e)
  if(e.defaultPrevented||e.button!==0||e.metaKey||e.altKey||e.ctrlKey||e.shiftKey||(props.target&&props.target!=='_self')||props.reloadDocument)return
  if(path===location.pathname+location.search+location.hash&&props.state===undefined){e.preventDefault();onApproved?.();return}
  if(!needsGuard(path,preserveDraft)){onApproved?.();return}
  e.preventDefault()
  void guardNavigation(path,preserveDraft).then(ok=>{if(!ok)return;onApproved?.();navigate(to,{replace:props.replace,state:props.state,relative:props.relative,preventScrollReset:props.preventScrollReset})})
 }}/>
}

// Nested workbench steps get priority over their parent route.
const backSteps=new Map<symbol,{priority:number;run:()=>boolean}>()
export function useWorkspaceBack(handler:()=>boolean,priority=0){
 const latest=useRef(handler);latest.current=handler
 const key=useRef(Symbol('workspace-back'))
 useLayoutEffect(()=>{const id=key.current;backSteps.set(id,{priority,run:()=>latest.current()});return()=>{backSteps.delete(id)}},[priority])
}
export function handleWorkspaceBack(){return [...backSteps.values()].sort((a,b)=>b.priority-a.priority).some(step=>step.run())}
