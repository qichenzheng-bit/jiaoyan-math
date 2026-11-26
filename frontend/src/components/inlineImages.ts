// Only authenticated, stored image IDs are accepted. No arbitrary URL or HTML.
export const inlineImagePattern=/\[\[img:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}:(?:20|25|30|35|40|45|50|55|60|65|70|75|80|85|90|95|100)\]\]/g
export function inlineImage(raw:string){
 const m=raw.match(/^\[\[img:([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}):(\d{2,3})\]\]$/)
 if(!m||Number(m[2])<20||Number(m[2])>100||Number(m[2])%5)return null
 return {id:m[1],width:Number(m[2]),url:'/api/files/'+m[1]+'/preview'}
}
export function imageToken(id:string,width=50){return '[[img:'+id+':'+width+']]'}
