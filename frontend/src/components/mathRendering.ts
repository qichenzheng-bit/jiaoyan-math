import katex from 'katex'

// All callers render a derived string; stored LaTeX is never rewritten.
const limitOperators=new Set(['lim','liminf','limsup'])
const literalCommands=new Set(['text','textrm','textsf','texttt','textnormal','textbf','textit','textup','textmd','mbox','url','operatorname'])
export function normalizeMath(source:string):string{
 const wrapper=source.trim().match(/^\\begin\{(align\*?|split|gather\*?|equation\*?)\}([\s\S]*)\\end\{\1\}$/)
 let latex=wrapper?(wrapper[1].startsWith('equation')?wrapper[2]:'\\begin{'+(wrapper[1].startsWith('gather')?'gathered':'aligned')+'}'+wrapper[2]+'\\end{'+(wrapper[1].startsWith('gather')?'gathered':'aligned')+'}'):source
 let result='',i=0
 while(i<latex.length){
  if(latex[i]==='%'){
   const end=latex.indexOf('\n',i);if(end===-1){result+=latex.slice(i);break}
   result+=latex.slice(i,end+1);i=end+1;continue
  }
  if(latex[i]!=='\\'){result+=latex[i++];continue}
  const token=latex.slice(i).match(/^\\([a-zA-Z]+|[\s\S])/)
  if(!token){result+=latex[i++];continue}
  const command=token[1];result+=token[0];i+=token[0].length
  if(command==='verb'){
   if(latex[i]==='*')result+=latex[i++]
   const delimiter=latex[i];if(delimiter){const end=latex.indexOf(delimiter,i+1);if(end>=0){result+=latex.slice(i,end+1);i=end+1}}
   continue
  }
  if(literalCommands.has(command)){
   const start=i;while(i<latex.length&&/\s/.test(latex[i]))i++
   if(latex[i]==='*')i++
   while(i<latex.length&&/\s/.test(latex[i]))i++
   if(latex[i]==='{'){
    let depth=0
    do{const ch=latex[i++];if(ch==='\\'&&i<latex.length){i++;continue}if(ch==='{')depth++;if(ch==='}')depth--}while(i<latex.length&&depth>0)
   }
   result+=latex.slice(start,i);continue
  }
  if(!limitOperators.has(command))continue
  const explicit=latex.slice(i).match(/^\s*\\(?:limits|nolimits|displaylimits)(?![A-Za-z])/)
  if(explicit)i+=explicit[0].length
  result+='\\limits'
 }
 return result
}
export function renderMathHtml(source:string,display:boolean):string{
 if(source.length>12000)throw Error('公式过长，请拆分。')
 return katex.renderToString(normalizeMath(source),{displayMode:display,throwOnError:true,trust:false,strict:'warn',maxExpand:1000,maxSize:20,output:'htmlAndMathml'})
}
export function mathError(source:string){return source.length>12000?'公式过长，请拆分。':'LaTeX 语法或命令有误，请检查原公式。'}
