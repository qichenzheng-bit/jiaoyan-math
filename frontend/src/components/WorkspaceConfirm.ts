import './WorkspaceConfirm.css'

type Options={message:string;title:string;accept:string;prompt?:boolean;danger?:boolean}
function show({message,title,accept,prompt=false,danger=false}:Options):Promise<string|null>{
 if(document.querySelector('.workspace-confirm[open]'))return Promise.resolve(null)
 return new Promise(resolve=>{
  const modal=document.createElement('dialog')
  modal.className='workspace-confirm'+(danger?' workspace-confirm-danger':'')
  modal.setAttribute('aria-label',title);modal.setAttribute('aria-describedby','workspace-confirm-message')
  modal.setAttribute('aria-modal','true')
  const header=document.createElement('div');header.className='workspace-confirm-head';const heading=document.createElement('h2');heading.textContent=title;const close=document.createElement('button');close.type='button';close.className='workspace-confirm-close';close.textContent='×';close.setAttribute('aria-label','关闭确认框');header.append(heading,close)
  const body=document.createElement('p');body.id='workspace-confirm-message';body.textContent=message
  const actions=document.createElement('div');actions.className='workspace-confirm-actions'
  const cancel=document.createElement('button');cancel.type='button';cancel.textContent='取消'
  const ok=document.createElement('button');ok.type='button';ok.className='workspace-confirm-primary';ok.textContent=accept
  let input:HTMLTextAreaElement|undefined
  actions.append(cancel,ok);modal.append(header,body)
  if(prompt){input=document.createElement('textarea');input.className='workspace-confirm-input';input.setAttribute('aria-label','原因');input.placeholder='请输入原因';input.maxLength=200;input.rows=3;ok.disabled=true;input.oninput=()=>{ok.disabled=!input?.value.trim()};input.onkeydown=e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)&&!ok.disabled){e.preventDefault();ok.click()}};modal.append(input)}
  modal.append(actions);document.body.append(modal)
  let result:string|null=null
  const previous=document.activeElement
  let finished=false
  function finish(){if(finished)return;finished=true;if(modal.open)modal.close();modal.remove();if(previous instanceof HTMLElement&&previous.isConnected)previous.focus({preventScroll:true});resolve(result)}
  cancel.onclick=finish;close.onclick=finish
  ok.onclick=()=>{if(input&&!input.value.trim())return;result=input?input.value.trim():'';finish()}
  modal.addEventListener('cancel',e=>{e.preventDefault();finish()})
  modal.addEventListener('close',finish,{once:true})
  modal.addEventListener('click',e=>{if(e.target!==modal)return;const r=modal.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)finish()})
  try{modal.showModal();(input??cancel).focus()}catch{modal.remove();resolve(null)}
 })
}
export async function confirmAction(message:string,title='确认操作',accept='确认'):Promise<boolean>{return await show({message,title,accept,danger:/^(归档|删除|覆盖|放弃|排除|退出|离开)/.test(title)||/^(归档|删除|覆盖|放弃|排除|退出|离开)/.test(accept)||/^(归档|删除|覆盖|放弃|退出)/.test(message)})!==null}
export function promptAction(message:string,title='填写原因',accept='确认'):Promise<string|null>{return show({message,title,accept,prompt:true})}
