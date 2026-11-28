export type Module={path:string;name:string;desc:string;icon:string;group:string;ready:boolean}
export const modules:Module[]=[
 {path:'/',name:'聊天',desc:'数学答疑与教研工作入口',icon:'home',group:'overview',ready:true},
 {path:'/videos',name:'视频制作',desc:'生成、渲染、微调和归档',icon:'media',group:'production',ready:true},
 {path:'/knowledge-library',name:'知识库',desc:'知识单元、公式与方法',icon:'book',group:'resources',ready:true},
 {path:'/chat',name:'AI 助手',desc:'数学答疑、资料检索和智能录入',icon:'chat',group:'overview',ready:true},
 {path:'/original-library',name:'原始资料库',desc:'管理上传的原件、处理进度与回收区',icon:'files',group:'resources',ready:true},
 {path:'/intake',name:'资料录入',desc:'统一手动录入、AI 工作及历史资料',icon:'intake',group:'resources',ready:true},
 {path:'/intelligence',name:'AI 智能录入',desc:'原文提取与草稿审核',icon:'spark',group:'resources',ready:true},
 {path:'/teaching-library',name:'教学资料库',desc:'自己组编的试卷、讲义和教材',icon:'files',group:'resources',ready:true},
 {path:'/resources',name:'题库',desc:'题目、查重与检索',icon:'resources',group:'resources',ready:true},
 {path:'/graph',name:'知识图谱',desc:'知识标签树、关联与图谱',icon:'graph',group:'resources',ready:true},
 {path:'/sources',name:'来源库',desc:'录入的试卷、讲义、教材等原始来源',icon:'files',group:'resources',ready:true},
 {path:'/handouts',name:'组讲义',desc:'从教学资源组编讲义并导出',icon:'book',group:'research',ready:true},
 {path:'/papers',name:'组卷',desc:'组卷、排版与导出',icon:'works',group:'research',ready:true},
 {path:'/textbooks',name:'组教材',desc:'从题库和知识库组编教材并导出',icon:'book',group:'research',ready:true},
 {path:'/works',name:'教学作品',desc:'作品归档与版本管理',icon:'works',group:'production',ready:true},
 {path:'/covers',name:'封面设计',desc:'品牌封面与平台比例',icon:'media',group:'publishing',ready:true},
 {path:'/checkin',name:'签到助手',desc:'签到、额度与积分记录',icon:'calendar',group:'tools',ready:true},
 {path:'/qoder',name:'AI 账号与模型',desc:'Qoder CN 授权及模型验证',icon:'spark',group:'tools',ready:true},
 {path:'/settings',name:'系统设置',desc:'账号、外观、存储及操作记录',icon:'settings',group:'tools',ready:true},
]

export type WorkspaceEntry={path:string;name:string;icon:string}
export type WorkspaceGroup={id:string;name:string;icon:string;sections:{id:string;name:string;entries:WorkspaceEntry[]}[]}
function entry(path:string,name?:string):WorkspaceEntry{
 const m=modules.find(m=>m.path===path)
 if(!m)throw new Error('Unknown navigation route: '+path)
 return {path,name:name??m.name,icon:m.icon}
}
// Global sidebar is organized by work purpose, not implementation module.
export const workspaceGroups:WorkspaceGroup[]=[
 {id:'intake',name:'资料录入',icon:'intake',sections:[
  {id:'intake',name:'录入方式',entries:[{path:'/intake',name:'录入首页',icon:'intake'},entry('/original-library')]},
 ]},
 {id:'teaching',name:'教学教研',icon:'book',sections:[
  {id:'resources',name:'基础资源',entries:[entry('/resources'),entry('/knowledge-library'),entry('/sources'),entry('/graph')]},
  {id:'compositions',name:'自编教学资料',entries:[entry('/teaching-library')]},
 ]},
 {id:'creation',name:'教学制作',icon:'media',sections:[
  {id:'creation',name:'制作与导出',entries:[entry('/videos'),entry('/papers'),entry('/handouts'),entry('/textbooks')]},
 ]},
 {id:'publishing',name:'作品与封面',icon:'works',sections:[{id:'release',name:'制作与管理',entries:[entry('/covers'),entry('/works','作品管理')]}]},
]

export function workspaceParent(path:string,search:string):string{
 const params=new URLSearchParams(search)
 if(path==='/selection')return '/project/creation'
 if(path.startsWith('/project/'))return '/'
 if(path==='/original-library')return '/intake'
 if(path==='/intake')return params.has('doc')||params.has('mode')||params.has('resource')?'/intake':'/'
 if(path.startsWith('/source-print/')||path.startsWith('/source-catalog/'))return '/sources'
 if(path.startsWith('/print/'))return '/teaching-library'
 if(path.startsWith('/resource-edit/'))return params.has('return_source')?'/source-print/'+encodeURIComponent(params.get('return_source')!):'/resources'
 if(path==='/intake-single')return '/intake'
 if(path==='/work'&&params.has('job')&&params.has('review'))return '/work?job='+encodeURIComponent(params.get('job')!)
 if(path==='/work'&&(params.has('job')||params.has('history')))return '/work'
 if(path==='/works')return params.has('work')?'/works':'/project/publishing'
 const group=workspaceGroups.find(g=>g.sections.some(s=>s.entries.some(e=>e.path===path)))
 return group?'/project/'+group.id:'/'
}

// Parent matching ignores search params only when identifying the business group.
export function activeWorkspaceGroup(path:string){
 if(path==='/selection')return workspaceGroups.find(g=>g.id==='creation')
 if(path.startsWith('/resource-edit/')||path.startsWith('/source-print/')||path.startsWith('/source-catalog/'))return workspaceGroups.find(g=>g.id==='teaching')
 if(path==='/intake-single')return workspaceGroups.find(g=>g.id==='intake')
 if(path.startsWith('/print/'))return workspaceGroups.find(g=>g.id==='creation')
 return workspaceGroups.find(g=>path==='/project/'+g.id||g.sections.some(s=>s.entries.some(e=>e.path.split('?')[0]===path)))
}
