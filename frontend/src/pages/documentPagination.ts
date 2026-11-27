import type {Layout} from './documentLayout'
import {dimensions,sectionName} from './documentLayout'

export type PaginationResult={pages:number;error:string}
const el=(tag:string,cls:string,text?:string)=>{const n=document.createElement(tag);n.className=cls;if(text!==undefined)n.textContent=text;return n}
function copy(n:Element){const c=n.cloneNode(true) as HTMLElement;c.querySelectorAll('.print-controls').forEach(x=>x.remove());return c}
function overflow(n:HTMLElement){return n.scrollHeight>n.clientHeight+2||n.scrollWidth>n.clientWidth+2}
function fitOptions(part:HTMLElement){
 for(const grid of part.querySelectorAll<HTMLElement>('.layout-options')){
  const mode=grid.dataset.optionLayout??'auto'
  const cols=mode==='auto'?[4,2,1]:[Number(mode)]
  for(const n of cols){grid.style.gridTemplateColumns='repeat('+n+',minmax(0,1fr))';if(Array.from(grid.querySelectorAll<HTMLElement>('.layout-option')).every(o=>o.scrollWidth<=o.clientWidth+2))break}
 }
}
export function pageVariables(l:Layout,w:number,h:number){
 return {'--layout-width':w+'mm','--layout-height':h+'mm','--layout-top':l.top+'mm','--layout-bottom':l.bottom+'mm','--layout-left':l.left+'mm','--layout-right':l.right+'mm','--layout-columns':l.columns,'--layout-gap':l.gap+'mm','--layout-size':l.size+'pt','--layout-line':l.lineHeight,'--layout-paragraph':l.paragraphGap+'pt','--layout-font':l.font==='sans'?'"Noto Sans CJK SC","Microsoft YaHei",sans-serif':'"Noto Serif CJK SC",SimSun,serif'}
}
function field(text:string,title:string,subject:string,page:number,total:number,chapter:string){
 return text.replace(/\{\{(文档名称|科目|当前页码|总页数|当前章名)\}\}/g,(_,key:string)=>({'文档名称':title,'科目':subject,'当前页码':String(page),'总页数':String(total),'当前章名':chapter}[key]??''))
}
// Build pages from the existing MathText DOM. No re-parsing or HTML injection.
// Measure actual rendered heights at the selected column width, after fonts and images load.
export async function paginateDocument(source:HTMLElement,target:HTMLElement,layout:Layout,title:string,subject:string,cancelled=()=>false):Promise<PaginationResult>{
 target.replaceChildren()
 const article=source.querySelector('.print-document'),body=article?.querySelector('.layout-body')
 if(!article||!body)return {pages:0,error:'文档内容尚未加载'}
 const sheets:{sheet:HTMLElement;columns:HTMLElement[];header:HTMLElement;footer:HTMLElement;chapter:string}[]=[]
 const contents=Array.from(body.children),headings:{id:string;title:string;level:number;page:number}[]=[]
 let current=0,col=0,chapter='',error='',chapterNumber=0,equationNumber=0,sectionKey=''
 const addPage=(withTitle=false,toc=false)=>{
  const key=toc?'':sectionKey
  const geometry={...layout,...(key?layout.sectionPages[key]:{})}
  const [w,h]=dimensions(geometry)
  const sheet=el('article','print-document layout-sheet')
  for(const [name,value] of Object.entries(pageVariables(geometry,w,h)))sheet.style.setProperty(name,String(value))
  if(key)sheet.style.setProperty('page',sectionName(layout,key))
  const header=el('div','layout-page-header',layout.header?'占位':'')
  const footer=el('div','layout-page-footer',layout.footer?'占位':'')
  if(!layout.header)header.hidden=true
  if(!layout.footer)footer.hidden=true
  sheet.append(header)
  if(withTitle){for(const n of Array.from(article.children).filter(n=>n.matches('h1,.print-subtitle')))sheet.append(copy(n))}
  const cols=el('div','layout-sheet-columns')
  const columns=Array.from({length:toc?1:geometry.columns},()=>el('div','layout-sheet-column'))
  columns.forEach(n=>cols.append(n));sheet.append(cols,footer);target.append(sheet)
  sheets.push({sheet,columns,header,footer,chapter});return sheets.length-1
 }
 current=addPage(true)
 const active=()=>sheets[current].columns[col]
 const next=()=>{if(col+1<sheets[current].columns.length)col++;else{current=addPage();col=0}}
 const newPage=()=>{if(sheets[current].columns.some(n=>n.childElementCount)){current=addPage();col=0}}
 function appendPart(part:HTMLElement,uid:string,attempt=0):boolean{
  let dest=active();dest.append(part);fitOptions(part)
  if(!overflow(dest))return true
  part.remove()
  if(dest.childElementCount){next();return appendPart(part,uid,attempt+1)}
  // The first page also has a title. Try a full column before splitting.
  if(current===0&&attempt===0){next();return appendPart(part,uid,attempt+1)}
  if(attempt>100||sheets.length>10000)return false
  // Split only at explicit semantic element boundaries; equations and images are atomic.
  if(part.matches('figure,.formula-block,.formula-inline,.katex,.katex-display,img,pre')||part.childElementCount<2||Array.from(part.childNodes).some(n=>n.nodeType===Node.TEXT_NODE&&n.textContent?.trim()))return false
  const children=Array.from(part.children)
  for(let i=0;i<children.length;i++){
   const wrapper=part.cloneNode(false) as HTMLElement
   if(i>0)wrapper.removeAttribute('id')
   wrapper.append(copy(children[i]))
   if(!appendPart(wrapper,uid,attempt+1))return false
  }
  return true
 }
 for(let i=0;i<contents.length;i++){
  if(i>0&&i%30===0)await new Promise<void>(resolve=>window.setTimeout(resolve,0))
  if(cancelled())return {pages:0,error:''}
  const item=contents[i]
  if(item.classList.contains('print-break')){newPage();continue}
  const uid=(item as HTMLElement).dataset.layoutUid??String(i+1)
  const level=Number((item as HTMLElement).dataset.layoutLevel??0)
  const pageBreak=(item as HTMLElement).dataset.layoutBreak
  if(pageBreak==='before'||pageBreak==='alone')newPage()
  if(level===1){
   chapterNumber++;if(layout.equationNumbering==='chapter')equationNumber=0
   const newChapter=item.textContent?.trim()??''
   const key=Object.prototype.hasOwnProperty.call(layout.sectionPages,uid)?uid:''
   const changed=key!==sectionKey
   if(changed){
    sectionKey=key;chapter=newChapter
    if(sheets[current].columns.every(n=>!n.childElementCount)){
     const withTitle=current===0
     sheets.pop()?.sheet.remove();current=addPage(withTitle);col=0
    }else{current=addPage();col=0}
   }else if(layout.chapterNewPage&&sheets[current].columns.some(n=>n.childElementCount)){chapter=newChapter;newPage()}
   chapter=newChapter
  }
  const node=copy(item)
  if(node.id)node.removeAttribute('id')
  node.dataset.layoutUid=uid
  node.id='layout-block-'+uid
  if(layout.equationNumbering!=='off')for(const formula of node.querySelectorAll<HTMLElement>('.formula-block')){
   if(formula.querySelector('.tag,.katex-error,.formula-error'))continue
   equationNumber++
   const label=layout.equationNumbering==='chapter'&&chapterNumber?chapterNumber+'.'+equationNumber:String(equationNumber)
   formula.classList.add('layout-numbered-equation');formula.append(el('span','layout-equation-number','('+label+')'))
  }
  if(!appendPart(node,uid)){error='内容 '+(i+1)+' 超过单栏页面且无法安全拆分，请在内容中插入换行或调整页面参数。';break}
  if(level){const first=target.querySelector('#'+CSS.escape('layout-block-'+uid))?.closest('.layout-sheet');headings.push({id:'layout-block-'+uid,title:item.querySelector('h2,h3,h4,h5,h6')?.textContent?.trim()||item.textContent?.trim()||'',level,page:Math.max(0,sheets.findIndex(p=>p.sheet===first))+1})}
  if(level===1)sheets[current].chapter=chapter
  if((pageBreak==='after'||pageBreak==='alone')&&i<contents.length-1)newPage()
 }
 // Drop only a truly empty trailing sheet, never a page holding the title.
 while(sheets.length>1&&!sheets[sheets.length-1].columns.some(n=>n.childElementCount)){sheets.pop()?.sheet.remove()}
 if(layout.toc&&headings.length&&!error){
  const before=sheets.slice();const tocSheets:typeof sheets=[]
  let idx=addPage(false,true);tocSheets.push(sheets[idx]);let dest=sheets[idx].columns[0]
  dest.append(el('h1','layout-toc-title','目　录'))
  for(const heading of headings.filter(x=>x.level<=layout.tocDepth)){
   const row=el('div','layout-toc-row');row.style.paddingLeft=(heading.level-1)*5+'mm'
   const link=el('a','layout-toc-link',heading.title) as HTMLAnchorElement;link.href='#'+heading.id
   const dots=el('span','layout-toc-dots');const number=el('span','layout-toc-number',String(heading.page));number.dataset.page=String(heading.page)
   row.append(link,dots,number);dest.append(row)
   if(overflow(dest)){row.remove();idx=addPage(false,true);tocSheets.push(sheets[idx]);dest=sheets[idx].columns[0];dest.append(row);if(overflow(dest)){error='目录单行超过页面，请调整纸张和字号。';break}}
  }
  const count=tocSheets.length
  tocSheets.forEach(p=>{p.sheet.querySelectorAll<HTMLElement>('.layout-toc-number').forEach(n=>{n.textContent=String(Number(n.dataset.page)+count)});target.insertBefore(p.sheet,before[0].sheet);p.chapter='目录'})
  sheets.splice(0,sheets.length,...tocSheets,...before)
 }
 if(layout.knowledgeIndex&&!error){
  const index=new Map<string,{label:HTMLElement;locations:{page:number;id:string}[]}>()
  for(const item of target.querySelectorAll<HTMLElement>('.layout-sheet [data-layout-knowledge]')){
   const name=item.dataset.layoutKnowledge??'',label=item.querySelector<HTMLElement>('.layout-index-label'),sheet=item.closest('.layout-sheet')
   if(!name||!label||!sheet||!item.id)continue
   const page=sheets.findIndex(p=>p.sheet===sheet)+1
   if(page<1)continue
   let row=index.get(name)
   if(!row){row={label,locations:[]};index.set(name,row)}
   if(!row.locations.some(x=>x.page===page))row.locations.push({page,id:item.id})
  }
  if(index.size){
   let idx=addPage(false,true),dest=sheets[idx].columns[0]
   sheets[idx].chapter='知识点索引'
   dest.append(el('h1','layout-toc-title','知识点索引'))
   for(const [,entry] of Array.from(index.entries()).sort((a,b)=>a[0].localeCompare(b[0],'zh-CN'))){
    const row=el('div','layout-toc-row'),name=copy(entry.label)
    name.hidden=false;name.className='layout-toc-link'
    const nums=el('span','layout-index-pages')
    entry.locations.forEach((loc,i)=>{if(i)nums.append(document.createTextNode('、'));const link=el('a','layout-index-page',String(loc.page)) as HTMLAnchorElement;link.href='#'+loc.id;link.dataset.page=String(loc.page);nums.append(link)})
    row.append(name,el('span','layout-toc-dots'),nums);dest.append(row)
    if(overflow(dest)){row.remove();idx=addPage(false,true);dest=sheets[idx].columns[0];sheets[idx].chapter='知识点索引';dest.append(row);if(overflow(dest)){error='知识点索引条目超过页面宽度或高度，请调整排版。';break}}
   }
  }
 }
 const total=sheets.length
 sheets.forEach((p,i)=>{
  p.sheet.dataset.page=String(i+1)
  if(layout.mirrorMargins&&i%2===1)p.sheet.classList.add('layout-mirror')
  p.header.textContent=field(layout.header,title,subject,i+1,total,p.chapter)
  p.footer.textContent=field(layout.footer,title,subject,i+1,total,p.chapter)
  if(p.columns.some(overflow)&&!error)error='第 '+(i+1)+' 页内容超出可用区域，请调整排版。'
 })
 if(!error&&target.querySelector('[data-layout-reference-error]'))error='存在失效的内容引用，请返回修改。'
 if(!error&&Array.from(target.querySelectorAll<HTMLElement>('.layout-option')).some(n=>n.scrollWidth>n.clientWidth+2))error='存在超过选项栏宽度的内容，请调整选项排列。'
 if(!error&&target.querySelector('.formula-error,.katex-error'))error='存在无法渲染的数学公式。'
 if(!error&&Array.from(target.querySelectorAll<HTMLElement>('.katex-display,.formula-block,.math-text-block')).some(n=>n.clientWidth>0&&n.scrollWidth>n.clientWidth+2))error='存在超出正文宽度的数学公式，请调整版式。'
 return {pages:total,error}
}
