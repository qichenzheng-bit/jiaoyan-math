// Declarative print layout shared by source exports and authored documents.
export type Layout={
 paper:'A4'|'A3'|'A5'|'B5'|'A6'|'custom';width:number;height:number;landscape:boolean;
 top:number;bottom:number;left:number;right:number;columns:1|2|3;gap:number;
 font:'serif'|'sans';size:number;lineHeight:number;paragraphGap:number;
 keepQuestions:boolean;originalNumbers:boolean;answerSpace:number;header:string;footer:string;
}
export const defaults:Layout={paper:'A4',width:210,height:297,landscape:false,top:20,bottom:20,left:20,right:20,columns:1,gap:8,font:'serif',size:10.5,lineHeight:1.5,paragraphGap:6,keepQuestions:true,originalNumbers:false,answerSpace:0,header:'',footer:''}
export type LayoutTemplate={id:string;name:string;kind:'paper'|'handout'|'textbook'|'all';layout:Layout}
export const builtins:LayoutTemplate[]=[
 {id:'paper',name:'标准试卷',kind:'paper',layout:{...defaults}},
 {id:'paper-double',name:'双栏试卷',kind:'paper',layout:{...defaults,columns:2}},
 {id:'handout',name:'简约讲义',kind:'handout',layout:{...defaults}},
 {id:'textbook',name:'传统教材',kind:'textbook',layout:{...defaults,paper:'B5',left:23,right:18,header:'{{文档名称}}'}},
 {id:'general',name:'通用黑白文档',kind:'all',layout:{...defaults}}
]
const sizes={A4:[210,297],A3:[297,420],A5:[148,210],B5:[176,250],A6:[105,148]}
export function dimensions(l:Layout):[number,number]{
 const d=l.paper==='custom'?[l.width,l.height]:sizes[l.paper]
 return l.landscape?[Math.max(...d),Math.min(...d)]:[Math.min(...d),Math.max(...d)]
}
export function layoutError(l:Layout):string{
 const [w,h]=dimensions(l)
 if(w-l.left-l.right-(l.columns-1)*l.gap<l.columns*20||h-l.top-l.bottom<25)return '纸张可用空间不足，请调整页边距或分栏。'
 return ''
}
export function sanitizeLayout(value:unknown):Layout{
 const v=value&&typeof value==='object'?value as Record<string,unknown>:{}
 const num=(key:keyof Layout,min:number,max:number)=>typeof v[key]==='number'&&Number.isFinite(v[key])?Math.max(min,Math.min(max,v[key] as number)):defaults[key] as number
 const bool=(key:keyof Layout)=>typeof v[key]==='boolean'?v[key] as boolean:defaults[key] as boolean
 const str=(key:keyof Layout)=>typeof v[key]==='string'?(v[key] as string).slice(0,200):''
 const paper=['A4','A3','A5','B5','A6','custom'].includes(String(v.paper))?v.paper as Layout['paper']:'A4'
 const columns=[1,2,3].includes(Number(v.columns))?Number(v.columns) as Layout['columns']:1
 return {paper,width:num('width',50,1000),height:num('height',50,1000),landscape:bool('landscape'),top:num('top',0,100),bottom:num('bottom',0,100),left:num('left',0,100),right:num('right',0,100),columns,gap:num('gap',3,30),font:v.font==='sans'?'sans':'serif',size:num('size',6,36),lineHeight:num('lineHeight',1,3),paragraphGap:num('paragraphGap',0,50),keepQuestions:bool('keepQuestions'),originalNumbers:bool('originalNumbers'),answerSpace:num('answerSpace',0,180),header:str('header'),footer:str('footer')}
}
export function readLocal<T>(key:string,fallback:T):T{
 try{const raw=localStorage.getItem(key);return raw?JSON.parse(raw) as T:fallback}catch{return fallback}
}
export function writeLocal(key:string,value:unknown):boolean{
 try{localStorage.setItem(key,JSON.stringify(value));return true}catch{return false}
}
export function readTemplates():LayoutTemplate[]{
 const list=readLocal<unknown>('wg-layout-templates-v1',[])
 if(!Array.isArray(list))return []
 return list.filter(t=>t&&typeof t.id==='string'&&typeof t.name==='string'&&['paper','handout','textbook','all'].includes(t.kind)).slice(0,100).map(t=>({id:t.id,name:t.name.slice(0,80),kind:t.kind,layout:sanitizeLayout(t.layout)}))
}
