import type { ReactNode } from 'react'
const paths:Record<string,ReactNode>={
 back:<path d="M20 12H4m6-6-6 6 6 6"/>,
 film:<><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M7 3v18m10-18v18M3 8h4m-4 8h4M17 8h4m-4 8h4"/><path d="m10 9 5 3-5 3Z"/></>,
 refresh:<><path d="M20 11a8 8 0 0 0-14-5L3 9m0-5v5h5M4 13a8 8 0 0 0 14 5l3-3m0 5v-5h-5"/></>,
 'send-up':<path d="M12 19V5m-6 6 6-6 6 6" strokeWidth="2.2"/>,
 down:<path d="M12 5v14m-6-6 6 6 6-6" strokeWidth="2"/>,
 stop:<rect x="6" y="6" width="12" height="12" rx="1.6" fill="currentColor" stroke="none"/>,
 'chevron-down':<path d="m6 9 6 6 6-6"/>,
 copy:<><rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/></>,
 check:<path d="m5 12 4 4L19 6"/>,
 more:<><circle cx="5" cy="12" r="1.8" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.8" fill="currentColor" stroke="none"/><circle cx="19" cy="12" r="1.8" fill="currentColor" stroke="none"/></>,
 sidebar:<><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16m7-4-3-4 3-4"/></>,
 chat:<><path d="M20 11a8 8 0 0 1-8 8H4l2-4a8 8 0 1 1 14-4Z"/></>,
 graph:<><circle cx="6" cy="6" r="3"/><circle cx="18" cy="7" r="3"/><circle cx="12" cy="18" r="3"/><path d="m9 6 6 1M7 9l4 6m6-5-4 5"/></>,
 book:<><path d="M12 6C9 3 5 3 3 4v15c4-1 7 0 9 2 2-2 5-3 9-2V4c-2-1-6-1-9 2Zm0 0v15"/></>,
 slides:<><path d="M3 3h18v13H3zm9 13v5m-5 0 5-5 5 5"/></>,
 chart:<><path d="M4 3v17h17M8 15l4-5 4 2 5-7"/></>,
 calendar:<><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 10h18m-13 5 3 3 5-5"/></>,
 search:<><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/></>,
 plus:<><path d="M12 5v14M5 12h14"/></>,
 home:<><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></>,
 intake:<><path d="M12 3v12m-5-5 5 5 5-5M4 16v4h16v-4"/></>,
 resources:<><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M8 4v16m4-11h5m-5 4h5"/></>,
 research:<><path d="m14 5 5 5M4 20l5-1L21 7l-4-4L5 15l-1 5Z"/></>,
 media:<><rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8" cy="8" r="1.5"/><path d="m3 17 6-6 4 4 3-3 5 5"/></>,
 works:<><rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 9h6m-6 4h6m-6 4h4M8 4V2m8 2V2"/></>,
 publishing:<><path d="m3 11 18-8-8 18-3-7-7-3Zm7 3 11-11"/></>,
 files:<><path d="M3 7V5a2 2 0 0 1 2-2h5l3 3h6a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/></>,
 formulas:<><path d="M20 4H5l8 8-8 8h15M3 4h2m-2 16h2"/></>,
 settings:<><circle cx="12" cy="12" r="3"/><path d="m10 3-1 3-3 1-3 3v4l3 3 3 1 1 3h4l1-3 3-1 3-3v-4l-3-3-3-1-1-3Z"/></>,
 menu:<><path d="M4 6h16M4 12h16M4 18h16"/></>,
 close:<><path d="m6 6 12 12M18 6 6 18"/></>,
 arrow:<><path d="M4 12h15m-6-6 6 6-6 6"/></>,
 chevron:<><path d="m9 6 6 6-6 6"/></>,
 brain:<><path d="M12 4v16M12 5a4 4 0 0 0-7 3 4 4 0 0 0-2 7 4 4 0 0 0 4 5 3 3 0 0 0 5-2m0-13a4 4 0 0 1 7 3 4 4 0 0 1 2 7 4 4 0 0 1-4 5 3 3 0 0 1-5-2M5 8c1 0 3 1 3 3M19 8c-1 0-3 1-3 3M7 20v-4m10 4v-4"/></>,
 spark:<><path d="m12 2 2.7 7.3L22 12l-7.3 2.7L12 22l-2.7-7.3L2 12l7.3-2.7L12 2Z"/></>,
 logout:<><path d="M10 4H4v16h6m-1-8h12m-5-5 5 5-5 5"/></>,
 shield:<><path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z"/><path d="m8 12 3 3 5-6"/></>,
 upload:<><path d="M12 16V4m-5 5 5-5 5 5M4 16v4h16v-4"/></>,
 clock:<><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
 eye:<><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></>,
}
export function Icon({name,size=20}:{name:string;size?:number}){
 return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]??paths.home}</svg>
}
const lightLogo = new URL('../assets/logo.svg', import.meta.url).href
const darkLogo = new URL('../assets/logo-dark.svg', import.meta.url).href
export function BrandMark({onDark=false}:{onDark?:boolean}){
 return <span className={'brand-logo'+(onDark?' on-dark':'')}><img className="logo-light" src={lightLogo} alt="微光数学"/><img className="logo-dark" src={darkLogo} alt="微光数学"/></span>
}
