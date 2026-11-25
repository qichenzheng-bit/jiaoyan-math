import { useState } from 'react'
import { MathFormula } from '../components/MathFormula'

const examples = [
  { name: '极限', latex: String.raw`\lim_{x\to0}\frac{\sin x}{x}=1` },
  { name: '矩阵', latex: String.raw`\begin{pmatrix}1&2\\3&4\end{pmatrix}` },
  { name: '方程组', latex: String.raw`\begin{cases}x+y=3,\\x-y=1.\end{cases}` },
  { name: '推导对齐', latex: String.raw`\begin{aligned}f(x)&=(x+1)^2\\&=x^2+2x+1.\end{aligned}` },
  { name: '积分', latex: String.raw`\int_0^1 x^2\,dx=\frac13` },
]
export default function FormulaLab() {
  const [latex, setLatex] = useState(examples[0].latex)
  const [display, setDisplay] = useState(true)
  return <><div className="page-heading"><div className="eyebrow">基础工具 / LATEX</div><h1>数学公式工作台</h1><p className="muted">输入 LaTeX，实时预览规范的数学公式。</p></div><div className="formula-grid"><section className="panel"><div className="panel-heading"><h2>公式编辑</h2></div>
    <div className="button-row">{examples.map(e => <button key={e.name} onClick={()=>setLatex(e.latex)}>{e.name}</button>)}</div>
    <label className="field">LaTeX 源码<textarea rows={5} value={latex} maxLength={12000} onChange={e=>setLatex(e.target.value)} spellCheck={false}/></label>
    <label><input type="checkbox" checked={display} onChange={e=>setDisplay(e.target.checked)}/> 独立公式（取消后为行内公式）</label>
    
    <div className="button-row"><button className="primary" onClick={async()=>{try{await navigator.clipboard.writeText(latex)}catch{window.alert('复制失败，请手动选择源码复制。')}}}>复制 LaTeX</button></div></section><section className="panel"><div className="panel-heading"><div><h2>实时预览</h2><p>{display?"独立公式":"行内公式"}</p></div></div><div className="formula-preview"><MathFormula latex={latex} display={display}/></div></section></div>
  </>
}
