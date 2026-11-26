import {createContext,useContext,useCallback,useLayoutEffect,useRef,type Ref} from 'react'
import {inlineImagePattern,inlineImage,imageToken} from './inlineImages'
export const InlineImageUpload=createContext<((file:File,complete:(id:string)=>void,failed:()=>void)=>void)|null>(null)
import katex from 'katex'

const formula=/(?<!\\)\$\$[\s\S]+?(?<!\\)\$\$|(?<![\\$])\$(?!\$)[^\n]+?(?<!\\)\$(?!\$)|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)/g
const tokens=new RegExp(formula.source+'|'+inlineImagePattern.source,'g')
function read(node:Node):string{
 if(node.nodeType===Node.TEXT_NODE)return node.textContent??''
 if(!(node instanceof HTMLElement))return ''
 if(node.dataset.mathSource!==undefined)return node.dataset.mathSource
 if(node.dataset.imageSource!==undefined)return node.dataset.imageSource
 if(node.tagName==='BR')return '\n'
 let value=''
 for(const child of Array.from(node.childNodes)){
  if(child instanceof HTMLElement&&['DIV','P'].includes(child.tagName)&&value&&!value.endsWith('\n'))value+='\n'
  value+=read(child)
 }
 return value
}
function drawMath(el:HTMLElement,raw:string){
 el.dataset.mathSource=raw;el.classList.remove('inline-math-invalid');el.replaceChildren()
 const display=raw.startsWith('$$')||raw.startsWith('\\[')
 const latex=raw.slice(raw.startsWith('$$')||raw.startsWith('\\')?2:1,raw.startsWith('$$')||raw.startsWith('\\')?-2:-1)
 try{if(latex.length>12000)throw Error('too long');katex.render(latex.replace(/\\lim(?=\s*_)/g,'\\lim\\limits'),el,{displayMode:display,throwOnError:true,trust:false,maxExpand:1000,maxSize:20})}catch{el.textContent=raw;el.classList.add('inline-math-invalid')}
 el.classList.toggle('inline-math-display',display)
}
function makeToken(raw:string){
 const span=document.createElement('span');span.className='inline-math-token';span.contentEditable='false';span.setAttribute('role','button');span.tabIndex=0;span.title='点击编辑 LaTeX';drawMath(span,raw);return span
}

function makeImage(raw:string,emit:()=>void,isLocked:()=>boolean){
 const data=inlineImage(raw)
 if(!data)return document.createTextNode(raw)
 const token=document.createElement('span')
 token.className='inline-image-token';token.contentEditable='false';token.dataset.imageSource=raw
 const img=document.createElement('img');img.src=data.url;img.alt='已插入图片';img.loading='lazy'
 const controls=document.createElement('span');controls.className='inline-image-controls'
 const sizes=[25,50,75,100],buttons:HTMLButtonElement[]=[]
 const resize=(width:number)=>{token.style.width=width+'%';token.dataset.imageSource=imageToken(data.id,width);for(const b of buttons)b.setAttribute('aria-pressed',String(Number(b.dataset.width)===width))}
 for(const width of sizes){const button=document.createElement('button');button.type='button';button.textContent=width+'%';button.dataset.width=String(width);button.setAttribute('aria-label','图片宽度 '+width+'%');button.disabled=isLocked();button.addEventListener('click',e=>{e.stopPropagation();if(isLocked())return;resize(width);emit()});buttons.push(button);controls.append(button)}
 const view=document.createElement('a');view.href=data.url;view.target='_blank';view.rel='noopener noreferrer';view.textContent='查看原图';view.setAttribute('aria-label','查看图片原图');controls.append(view)
 const remove=document.createElement('button');remove.type='button';remove.textContent='移除';remove.setAttribute('aria-label','移除内嵌图片');remove.disabled=isLocked();remove.addEventListener('click',e=>{e.stopPropagation();if(isLocked())return;token.remove();emit()});controls.append(remove)
 token.append(img,controls);resize(data.width);return token
}
type TokenFactory=(raw:string)=>Node
// Only replace newly typed math in ordinary text nodes. Existing rendered
// tokens and neighboring text are deliberately kept in place.
function renderNewMath(root:HTMLElement,make:TokenFactory){
 const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT,{acceptNode(node){return node.parentElement?.closest('[data-math-source],[data-image-source]')?NodeFilter.FILTER_REJECT:NodeFilter.FILTER_ACCEPT}})
 const nodes:Text[]=[]
 while(walker.nextNode())nodes.push(walker.currentNode as Text)
 for(const node of nodes){
  const value=node.data,matches=[...value.matchAll(tokens)]
  if(!matches.length)continue
  const f=document.createDocumentFragment();let pos=0
  for(const m of matches){const start=m.index??0;if(start>pos)f.append(document.createTextNode(value.slice(pos,start)));f.append(make(m[0]));pos=start+m[0].length}
  if(pos<value.length)f.append(document.createTextNode(value.slice(pos)))
  node.replaceWith(f)
 }
}
function paint(root:HTMLElement,value:string,make:TokenFactory){
 const f=document.createDocumentFragment();let pos=0
 for(const m of value.matchAll(tokens)){
  const start=m.index??0
  if(start>pos)f.append(document.createTextNode(value.slice(pos,start)))
  f.append(make(m[0]));pos=start+m[0].length
 }
 if(pos<value.length)f.append(document.createTextNode(value.slice(pos)))
 root.replaceChildren(f)
}
export default function InlineMathEditor({label,value,onChange,locked,placeholder,rows=3,editorRef}:{label:string;value:string;onChange:(v:string)=>void;locked:boolean;placeholder?:string;rows?:number;editorRef?:Ref<HTMLDivElement>}){
 const root=useRef<HTMLDivElement>(null),latest=useRef(value),change=useRef(onChange),lock=useRef(locked)
 const upload=useContext(InlineImageUpload);lock.current=locked
 latest.current=value;change.current=onChange
 const emit=useCallback(()=>{const el=root.current;if(!el)return;const v=read(el);if(v!==latest.current){latest.current=v;change.current(v)}},[])
 const make=useCallback((raw:string)=>inlineImage(raw)?makeImage(raw,emit,()=>lock.current):makeToken(raw),[emit])
 const finish=useCallback(()=>{const el=root.current;if(!el)return;emit();renderNewMath(el,make)},[emit,make])
 useLayoutEffect(()=>{const outside=(event:PointerEvent)=>{const el=root.current;if(!el||!(event.target instanceof Node)||el.contains(event.target))return;if(el.contains(document.activeElement)){const active=document.activeElement;if(active instanceof HTMLElement&&active!==el)active.blur();finish()}};document.addEventListener('pointerdown',outside,true);return()=>document.removeEventListener('pointerdown',outside,true)},[finish])
 useLayoutEffect(()=>{const el=root.current;if(el&&!el.contains(document.activeElement)&&read(el)!==value)paint(el,value,make)},[value,make])
 useLayoutEffect(()=>{if(root.current)paint(root.current,latest.current,make)},[make])
 useLayoutEffect(()=>{root.current?.querySelectorAll<HTMLButtonElement>('.inline-image-controls button').forEach(b=>{b.disabled=locked})},[locked])
 function editToken(token:HTMLElement){
  if(locked||token.querySelector('input'))return
  const raw=token.dataset.mathSource??'',input=document.createElement('input')
  input.type='text';input.value=raw;input.className='inline-math-source';input.setAttribute('aria-label','编辑 LaTeX 公式')
  token.replaceChildren(input)
  input.addEventListener('input',e=>{e.stopPropagation();token.dataset.mathSource=input.value;emit()})
  input.addEventListener('keydown',e=>{e.stopPropagation();if(e.key==='Enter'){e.preventDefault();input.blur()}if(e.key==='Escape'){input.value=raw;token.dataset.mathSource=raw;emit();input.blur()}})
  input.addEventListener('blur',()=>{const edited=input.value;token.dataset.mathSource=edited;emit();const parts=[...edited.matchAll(formula)];if(parts.length===1&&parts[0][0]===edited){drawMath(token,edited)}else{token.replaceWith(document.createTextNode(edited))}},{once:true})
  input.focus();input.setSelectionRange(0,input.value.length)
 }
 function insertNode(node:Node){
  const sel=window.getSelection(),el=root.current;if(!el)return
  if(sel?.rangeCount&&el.contains(sel.anchorNode)){
   const range=sel.getRangeAt(0);range.deleteContents();range.insertNode(node);range.setStartAfter(node);range.collapse(true);sel.removeAllRanges();sel.addRange(range)
  }else el.append(node)
  emit()
 }
 function insert(text:string){insertNode(document.createTextNode(text))}
 function pasteImage(file:File){
  if(!upload||locked)return
  const placeholder=document.createElement('span');placeholder.contentEditable='false';placeholder.dataset.imageSource='';placeholder.className='inline-image-pending';placeholder.textContent='正在插入图片…'
  insertNode(placeholder)
  upload(file,id=>{if(!root.current?.contains(placeholder))return;const raw=imageToken(id);if(!inlineImage(raw)){placeholder.remove();return}placeholder.replaceWith(make(raw));emit()},()=>{placeholder.remove();emit()})
 }
 return <div className="manual-field"><span>{label}</span><div ref={el=>{root.current=el;if(typeof editorRef==='function')editorRef(el);else if(editorRef)editorRef.current=el}} role="textbox" aria-label={label} aria-multiline="true" aria-disabled={locked} contentEditable={!locked} suppressContentEditableWarning className="inline-math-editor" data-placeholder={placeholder??'输入文字，公式用 $...$ 包裹'} style={{minHeight:rows*25+'px'}} onInput={emit} onBlur={e=>{if(!e.currentTarget.contains(e.relatedTarget))finish()}} onPointerDown={e=>{const t=(e.target as HTMLElement).closest<HTMLElement>('[data-math-source]');if(t&&!locked&&!t.querySelector('input')){e.preventDefault();editToken(t)}}} onKeyDown={e=>{const t=(e.target as HTMLElement).closest<HTMLElement>('[data-math-source]');if(t&&e.key==='Enter'&&!t.querySelector('input')){e.preventDefault();editToken(t);return}if(e.key==='Enter'&&!e.nativeEvent.isComposing){e.preventDefault();insert('\n')}}} onPaste={e=>{e.preventDefault();if(locked)return;const image=Array.from(e.clipboardData.items).find(item=>item.kind==='file'&&item.type.startsWith('image/'))?.getAsFile()??Array.from(e.clipboardData.files).find(file=>file.type.startsWith('image/'));if(image&&upload){pasteImage(image);return}insert(e.clipboardData.getData('text/plain'))}}/></div>
}
