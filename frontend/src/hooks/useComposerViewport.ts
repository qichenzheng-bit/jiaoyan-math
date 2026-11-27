import {useEffect} from 'react'
export function useComposerViewport(enabled:boolean){
 useEffect(()=>{
  const viewport=window.visualViewport
  if(!enabled||!viewport)return
  const root=document.documentElement
  function sync(){
   const focused=document.activeElement instanceof HTMLElement&&Boolean(document.activeElement.closest('[data-chat-layout="v3"]'))&&document.activeElement.matches('textarea,input:not([type=file]):not([type=checkbox]):not([type=radio])')
   // Pin the workspace to the keyboard-reduced visual viewport, not pinch zoom.
   const keyboard=focused&&viewport!.scale===1&&window.innerHeight-viewport!.height>100
   if(keyboard){root.style.setProperty('--composer-visible-height',Math.floor(viewport!.height)+'px');root.dataset.composerKeyboard='true'}else{root.style.removeProperty('--composer-visible-height');delete root.dataset.composerKeyboard}
  }
  viewport.addEventListener('resize',sync);window.addEventListener('resize',sync);document.addEventListener('focusin',sync);document.addEventListener('focusout',sync);sync()
  return()=>{viewport.removeEventListener('resize',sync);window.removeEventListener('resize',sync);document.removeEventListener('focusin',sync);document.removeEventListener('focusout',sync);root.style.removeProperty('--composer-visible-height');delete root.dataset.composerKeyboard}
 },[enabled])
}
