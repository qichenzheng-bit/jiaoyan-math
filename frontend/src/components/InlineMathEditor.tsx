import {useCallback,useLayoutEffect,useRef,type Ref} from 'react'
import katex from 'katex'

const formula=/(?<!\\)\$\$[\s\S]+?(?<!\\)\$\$|(?<![\\$])\$(?!\$)[^\n]+?(?<!\\)\$(?!\$)|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)/g
function read(node:Node):string{
 if(node.nodeType===Node.TEXT_NODE)return node.textContent??''
 if(!(node instanceof HTMLElement))return ''
 if(node.dataset.mathSource!==undefined)return node.dataset.mathSource
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
function paint(root:HTMLElement,value:string){
 const f=document.createDocumentFragment();let pos=0
 for(const m of value.matchAll(formula)){
  const start=m.index??0
  if(start>pos)f.append(document.createTextNode(value.slice(pos,start)))
  const span=document.createElement('span');span.className='inline-math-token';span.contentEditable='false';span.setAttribute('role','button');span.tabIndex=0;span.title='点击编辑 LaTeX';drawMath(span,m[0]);f.append(span);pos=start+m[0].length
 }
 if(pos<value.length)f.append(document.createTextNode(value.slice(pos)))
 root.replaceChildren(f)
}
export default function InlineMathEditor({label,value,onChange,locked,placeholder,rows=3,editorRef}:{label:string;value:string;onChange:(v:string)=>void;locked:boolean;placeholder?:string;rows?:number;editorRef?:Ref<HTMLDivElement>}){
 const root=useRef<HTMLDivElement>(null),latest=useRef(value),change=useRef(onChange)
 latest.current=value;change.current=onChange
 const emit=useCallback(()=>{const el=root.current;if(!el)return;const v=read(el);if(v!==latest.current){latest.current=v;change.current(v)}},[])
 const finish=useCallback(()=>{const el=root.current;if(!el)return;emit();paint(el,read(el))},[emit])
 useLayoutEffect(()=>{const outside=(event:PointerEvent)=>{const el=root.current;if(!el||!(event.target instanceof Node)||el.contains(event.target))return;if(el.contains(document.activeElement)){const active=document.activeElement;if(active instanceof HTMLElement&&active!==el)active.blur();finish()}};document.addEventListener('pointerdown',outside,true);return()=>document.removeEventListener('pointerdown',outside,true)},[finish])
 useLayoutEffect(()=>{const el=root.current;if(el&&!el.contains(document.activeElement)&&read(el)!==value)paint(el,value)},[value])
 useLayoutEffect(()=>{if(root.current)paint(root.current,latest.current)},[])
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
 function insert(text:string){
  const sel=window.getSelection(),el=root.current;if(!el)return
  if(sel?.rangeCount&&el.contains(sel.anchorNode)){
   const range=sel.getRangeAt(0);range.deleteContents();const node=document.createTextNode(text);range.insertNode(node);range.setStartAfter(node);range.collapse(true);sel.removeAllRanges();sel.addRange(range)
  }else el.append(document.createTextNode(text))
  emit()
 }
 return <div className="manual-field"><span>{label}</span><div ref={el=>{root.current=el;if(typeof editorRef==='function')editorRef(el);else if(editorRef)editorRef.current=el}} role="textbox" aria-label={label} aria-multiline="true" aria-disabled={locked} contentEditable={!locked} suppressContentEditableWarning className="inline-math-editor" data-placeholder={placeholder??'输入文字，公式用 $...$ 包裹'} style={{minHeight:rows*25+'px'}} onInput={emit} onBlur={e=>{if(!e.currentTarget.contains(e.relatedTarget))finish()}} onPointerDown={e=>{const t=(e.target as HTMLElement).closest<HTMLElement>('[data-math-source]');if(t&&!locked&&!t.querySelector('input')){e.preventDefault();editToken(t)}}} onKeyDown={e=>{const t=(e.target as HTMLElement).closest<HTMLElement>('[data-math-source]');if(t&&e.key==='Enter'&&!t.querySelector('input')){e.preventDefault();editToken(t);return}if(e.key==='Enter'&&!e.nativeEvent.isComposing){e.preventDefault();insert('\n')}}} onPaste={e=>{e.preventDefault();insert(e.clipboardData.getData('text/plain'))}}/></div>
}
