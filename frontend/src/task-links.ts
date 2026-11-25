export function taskLink(task:{kind:string;id:string;session_id:string|null;document_id?:string;document_kind?:string}){
 if(task.kind==='chat')return '/chat?session='+encodeURIComponent(task.session_id??'')
 if(task.kind==='document_ai'&&task.document_id)return (task.document_kind==='paper'?'/papers':task.document_kind==='handout'?'/handouts':'/intake')+'?doc='+encodeURIComponent(task.document_id)+'&ai=1'
 return '/intelligence?job='+encodeURIComponent(task.id)
}
