import type {ReactNode} from 'react'
export function AiHomeHeading({mode}:{mode:'chat'|'work'}){
 return <div className="chat-home-recent ai-home-welcome" aria-label={mode==='chat'?'最近事项':'最近录入'}><div className="chat-home-heading"><h1>{mode==='chat'?'今天想研究什么？':'今天需要完成什么工作？'}</h1></div></div>
}
export function AiHomeShortcuts({children}:{children:ReactNode}){
 return <div className="chat-home-links ai-home-shortcuts" aria-label="快捷功能">{children}</div>
}
