import type {ReactNode} from 'react'
export function AiHomeHeading({mode}:{mode:'chat'|'work'}){
 return <div className="chat-home-recent ai-home-welcome" aria-label={mode==='chat'?'最近事项':'最近录入'}><div className="chat-home-heading"><svg className="ai-home-spark" viewBox="0 0 50 50" aria-hidden="true"><path d="M25 2C27 18 32 22 48 25C32 28 27 32 25 48C23 32 18 28 2 25C18 22 23 18 25 2Z" fill="currentColor"/></svg><h1>{mode==='chat'?'今天想研究什么？':'今天需要完成什么工作？'}</h1></div></div>
}
export function AiHomeShortcuts({children}:{children:ReactNode}){
 return <div className="chat-home-links ai-home-shortcuts" aria-label="快捷功能">{children}</div>
}
