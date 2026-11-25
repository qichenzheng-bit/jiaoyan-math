export type Module={path:string;name:string;desc:string;icon:string;group:string;ready:boolean}
export const groups=[
 {id:'overview',label:'工作空间'},
 {id:'resources',label:'教学资源'},
 {id:'research',label:'教研创作'},
 {id:'production',label:'内容制作'},
 {id:'publishing',label:'自媒体运营'},
 {id:'tools',label:'系统工具'},
]
export const modules:Module[]=[
 {path:'/',name:'首页',desc:'数学答疑与教研工作入口',icon:'home',group:'overview',ready:true},
 {path:'/library',name:'教学资源',desc:'题库、知识库、资料与素材',icon:'resources',group:'resources',ready:true},
 {path:'/create',name:'内容创作',desc:'视频、讲义、试卷及教学内容',icon:'research',group:'production',ready:true},
 {path:'/products',name:'商品售卖',desc:'课程与资料商品、订单及收入（待接入）',icon:'works',group:'production',ready:true},
 {path:'/operations',name:'内容发布',desc:'平台发布、封面设计及运营数据',icon:'chart',group:'publishing',ready:true},
 {path:'/videos',name:'视频制作',desc:'生成、渲染、微调和归档',icon:'media',group:'production',ready:true},
 {path:'/knowledge-library',name:'知识库',desc:'知识单元、公式与方法',icon:'book',group:'resources',ready:true},
 {path:'/chat',name:'AI 助手',desc:'数学答疑、资料检索和智能录入',icon:'chat',group:'overview',ready:true},
 {path:'/tasks',name:'任务中心',desc:'后台任务进度和执行记录',icon:'clock',group:'overview',ready:true},
 {path:'/intake',name:'录入工作台',desc:'在同一资料文档内录入题目与知识单元',icon:'intake',group:'resources',ready:true},
 {path:'/intelligence',name:'AI 智能录入',desc:'原文提取与草稿审核',icon:'spark',group:'resources',ready:true},
 {path:'/resources',name:'题库管理',desc:'题目、知识单元、查重与检索',icon:'resources',group:'resources',ready:true},
 {path:'/graph',name:'知识图谱',desc:'知识点树、关联与图谱',icon:'graph',group:'resources',ready:true},
 {path:'/sources',name:'来源资料',desc:'教材、试卷与讲义来源',icon:'files',group:'resources',ready:true},
 {path:'/assets',name:'素材库',desc:'图片、模板与公式素材',icon:'media',group:'resources',ready:true},
 {path:'/research',name:'Word 工作台',desc:'文档编辑、大纲和分页',icon:'research',group:'research',ready:true},
 {path:'/handouts',name:'讲义管理',desc:'教研讲义与知识编排',icon:'book',group:'research',ready:true},
 {path:'/papers',name:'试卷管理',desc:'组卷、排版与导出',icon:'works',group:'research',ready:true},
 {path:'/drawing',name:'数学绘图',desc:'数学图形创作',icon:'graph',group:'production',ready:true},
 {path:'/media',name:'图文制作',desc:'教学图文草稿（编辑器待完善）',icon:'media',group:'production',ready:false},
 {path:'/slides',name:'课件制作',desc:'课件草稿（编辑器待完善）',icon:'slides',group:'production',ready:false},
 {path:'/works',name:'教学作品',desc:'作品归档与版本管理',icon:'works',group:'production',ready:true},
 {path:'/covers',name:'封面设计',desc:'品牌封面与平台比例',icon:'media',group:'publishing',ready:true},
 {path:'/publishing',name:'发布管理',desc:'平台文案与发布台账',icon:'publishing',group:'publishing',ready:true},
 {path:'/analytics',name:'运营数据',desc:'平台数据与运营统计',icon:'chart',group:'publishing',ready:true},
 {path:'/checkin',name:'签到助手',desc:'签到、额度与积分记录',icon:'calendar',group:'tools',ready:true},
 {path:'/qoder',name:'AI 账号与模型',desc:'Qoder CN 授权及模型验证',icon:'spark',group:'tools',ready:true},
 {path:'/files',name:'文件管理',desc:'上传、预览、下载及归档',icon:'files',group:'tools',ready:true},
 {path:'/formulas',name:'公式预览',desc:'LaTeX 公式实时显示',icon:'formulas',group:'tools',ready:true},
 {path:'/settings',name:'系统设置',desc:'账号、外观、存储及操作记录',icon:'settings',group:'tools',ready:true},
]

export const mainSections=[
 {path:'/',name:'首页',icon:'home',children:[]},
 {path:'/chat',name:'AI 助手',icon:'spark',children:['/chat','/intelligence','/intake','/intake-single']},
 {path:'/library',name:'教学资源',icon:'resources',children:['/resources','/knowledge-library','/graph','/sources','/assets','/files']},
 {path:'/create',name:'内容创作',icon:'research',children:['/videos','/handouts','/papers','/research','/drawing','/media','/slides','/formulas','/works']},
 {path:'/products',name:'商品售卖',icon:'works',children:[]},
 {path:'/operations',name:'内容发布',icon:'publishing',children:['/covers','/publishing','/analytics']},
]
export const utilitySection={path:'/settings',name:'系统设置',icon:'settings',children:['/settings','/qoder','/checkin']}
export function sectionFor(path:string){return [...mainSections,utilitySection].find(s=>s.path===path||s.children.includes(path))}

export type WorkspaceEntry={path:string;name:string;icon:string}
export type WorkspaceGroup={id:string;name:string;icon:string;sections:{id:string;name:string;entries:WorkspaceEntry[]}[]}
function entry(path:string,name?:string):WorkspaceEntry{
 const m=modules.find(m=>m.path===path)
 if(!m)throw new Error('Unknown navigation route: '+path)
 return {path,name:name??m.name,icon:m.icon}
}
// Global sidebar is organized by work purpose, not implementation module.
export const workspaceGroups:WorkspaceGroup[]=[
 {id:'teaching',name:'教学教研',icon:'book',sections:[
  {id:'intake',name:'资料录入',entries:[{path:'/work',name:'AI 录入',icon:'spark'},{path:'/intake?mode=document',name:'整套资料录入',icon:'files'}]},
  {id:'resources',name:'教学资源',entries:[entry('/library','资源总览'),entry('/resources'),entry('/knowledge-library'),entry('/graph'),entry('/sources'),entry('/assets')]},
  {id:'creation',name:'教学制作',entries:[entry('/create','制作总览'),entry('/videos'),entry('/handouts'),entry('/papers'),entry('/research'),entry('/drawing'),entry('/formulas'),entry('/media'),entry('/slides'),entry('/works')]},
 ]},
 {id:'publishing',name:'内容发布',icon:'publishing',sections:[
  {id:'release',name:'发布运营',entries:[entry('/operations','发布总览'),entry('/covers'),entry('/publishing'),entry('/analytics')]},
 ]},
 {id:'sales',name:'商品售卖',icon:'works',sections:[
  {id:'store',name:'商品与交易',entries:[entry('/products','商品售卖总览')]},
 ]},
]
