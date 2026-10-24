import React from 'react';
import {createRoot} from 'react-dom/client';
import Demo from './app/annotation/demo';
import './app/annotation/annotation.css';

const win=window as any, original=window.fetch.bind(window), key='socialflux-annotation-recovery';
const backend=new URL(win.SOCIALFLUX_BACKEND_URL);
window.fetch=async(input,init={})=>{
 const url=new URL(typeof input==='string'?input:input instanceof URL?input.href:input.url,location.href);
 if(url.origin!==location.origin||!url.pathname.startsWith('/api/annotation/'))return original(input,init);
 const headers=new Headers(init.headers),code=localStorage.getItem(key);
 if(code)headers.set('X-Annotation-Recovery',code);
 const response=await win.socialfluxLabRequest(url.pathname,{...init,headers:Object.fromEntries(headers)});
 if(response.ok&&['start','recover'].includes(url.pathname.split('/').at(-1)!)){
  const posted=JSON.parse(String(init.body));localStorage.setItem(key,posted.recoveryCode);
 }
 if(response.ok&&url.pathname.endsWith('/logout'))localStorage.removeItem(key);
 return response;
};
// JSON downloads must carry the same authentication as saves; anchor navigation
// cannot attach the header used by the cross-origin Pages frontend.
document.addEventListener('click',async(event)=>{
 const link=(event.target as Element).closest('a');if(!link)return;
 const href=link.getAttribute('href');
 if(href==='/api/annotation/export'){
  event.preventDefault();
  try{const response=await fetch(href);if(!response.ok)throw new Error('下载失败，请重新登录后重试。');const blob=URL.createObjectURL(await response.blob()),a=document.createElement('a');a.href=blob;a.download='socialflux-annotation.json';a.click();setTimeout(()=>URL.revokeObjectURL(blob),1000);}catch(error:any){alert(error.message);}
 }else if(href==='/lab'||href==='/annotation'){
  event.preventDefault();location.href=new URL(href==='/lab'?'../lab/':'./',location.href).href;
 }
});
// Videos are fetched with authentication and played from a local Blob URL, so
// media tokens and passwords never appear in public URLs or request logs.
const mediaCache=new Map<string,Promise<string>>();
const observer=new MutationObserver(()=>{
 for(const video of document.querySelectorAll('video')){
  const src=video.getAttribute('src');if(!src||!src.startsWith('/media/')||video.dataset.loading===src)continue;
  video.dataset.loading=src;video.removeAttribute('src');
  if(!mediaCache.has(src))mediaCache.set(src,win.socialfluxLabRequest(src).then(async(r:Response)=>{if(!r.ok)throw Error('视频加载失败');return URL.createObjectURL(await r.blob());}));
  mediaCache.get(src)!.then(blob=>{if(video.isConnected)video.src=blob;}).catch(()=>{video.dispatchEvent(new Event('error'));});
 }
});
observer.observe(document.body,{subtree:true,childList:true,attributes:true,attributeFilter:['src']});
createRoot(document.getElementById('root')!).render(<div className="annotation-app"><Demo/></div>);
