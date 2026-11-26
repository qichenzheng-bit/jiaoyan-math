import './WorkspaceConfirm.css'

/** Styled modal, with native focus trapping and Escape handling, not window.confirm. */
export function confirmAction(message:string,title='确认操作',accept='确认'):Promise<boolean>{
 if(document.querySelector('.workspace-confirm[open]'))return Promise.resolve(false)
 return new Promise(resolve=>{
  const modal=document.createElement('dialog')
  modal.className='workspace-confirm'
  modal.setAttribute('aria-label',title)
  modal.setAttribute('aria-modal','true')
  const heading=document.createElement('h2');heading.textContent=title
  const body=document.createElement('p');body.textContent=message
  const actions=document.createElement('div');actions.className='workspace-confirm-actions'
  const cancel=document.createElement('button');cancel.type='button';cancel.textContent='取消'
  const ok=document.createElement('button');ok.type='button';ok.className='workspace-confirm-primary';ok.textContent=accept
  actions.append(cancel,ok);modal.append(heading,body,actions);document.body.append(modal)
  let accepted=false
  cancel.onclick=()=>modal.close()
  ok.onclick=()=>{accepted=true;modal.close()}
  modal.addEventListener('close',()=>{modal.remove();resolve(accepted)},{once:true})
  modal.addEventListener('click',e=>{if(e.target!==modal)return;const r=modal.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)modal.close()})
  try{modal.showModal();cancel.focus()}catch{modal.remove();resolve(false)}
 })
}
