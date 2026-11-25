import { useMemo } from 'react'
import katex from 'katex'
import 'katex/dist/katex.min.css'

export function MathFormula({ latex, display = true }: { latex: string; display?: boolean }) {
  const result = useMemo(() => {
    if (latex.length > 12000) return { error: '公式过长，请拆分。' }
    try {
      return { html: katex.renderToString(latex, { displayMode: display, throwOnError: true,
        trust: false, strict: 'warn', maxExpand: 1000, maxSize: 20, output: 'htmlAndMathml' }) }
    } catch {
      return { error: 'LaTeX 语法或命令有误，请检查原公式。' }
    }
  }, [latex, display])
  if (result.error) return <span className="formula-error" role="status">{result.error}</span>
  return <span className={display ? 'formula-block' : 'formula-inline'} dangerouslySetInnerHTML={{ __html: result.html ?? '' }} />
}
