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
  return <><h1>数学公式预览</h1><p className="muted">公共 LaTeX 渲染组件测试，原始公式保留在输入框中。</p>
    <div className="button-row">{examples.map(e => <button key={e.name} onClick={()=>setLatex(e.latex)}>{e.name}</button>)}</div>
    <label className="field">LaTeX 源码<textarea rows={5} value={latex} maxLength={12000} onChange={e=>setLatex(e.target.value)} spellCheck={false}/></label>
    <label><input type="checkbox" checked={display} onChange={e=>setDisplay(e.target.checked)}/> 独立公式（取消后为行内公式）</label>
    <section className="notice"><MathFormula latex={latex} display={display}/></section>
    <button onClick={async()=>{try{await navigator.clipboard.writeText(latex)}catch{window.alert('复制失败，请手动选择源码复制。')}}}>复制 LaTeX</button>
  </>
}
