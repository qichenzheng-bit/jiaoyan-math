import {useEffect,useState} from 'react'

// Matches the existing CSS drawer boundary. Desktop collapse preference is separate.
export const PHONE_LAYOUT_QUERY='(max-width: 760px)'
export function usePhoneLayout(){
 const [phone,setPhone]=useState(()=>window.matchMedia(PHONE_LAYOUT_QUERY).matches)
 useEffect(()=>{
  const media=window.matchMedia(PHONE_LAYOUT_QUERY)
  const sync=()=>setPhone(media.matches)
  sync();media.addEventListener('change',sync)
  return()=>media.removeEventListener('change',sync)
 },[])
 return phone
}
