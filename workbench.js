"use strict";
(() => {
 const workspace=document.getElementById("workspace"),frame=document.getElementById("report-frame"),overview=document.getElementById("overview");
 const labels={overview:"总体概览",report:"完整评测报告",capabilities:"能力与难点",help:"教师帮助归因",history:"执行轨迹摘要",portability:"跨机迁移复核"};
 const base="reports/calendar/2026-10-25/",storageKey="agentlab.public-workbench.v1";
 let state={view:"overview",left:true,right:true,bottom:true};
 try{const saved=JSON.parse(localStorage.getItem(storageKey));if(saved&&labels[saved.view])state={...state,...saved};}catch(_){}
 function save(){try{localStorage.setItem(storageKey,JSON.stringify(state));}catch(_){}}
 function panels(){for(const side of ["left","right","bottom"]){workspace.classList.toggle("no-"+side,!state[side]);document.getElementById("toggle-"+side).setAttribute("aria-pressed",String(Boolean(state[side])));}save();}
 function select(){const requested=location.hash.slice(1);state.view=labels[requested]?requested:state.view;const home=state.view==="overview";overview.hidden=!home;frame.hidden=home;if(!home){const next=base+(state.view==="report"?"":"#"+state.view);if(frame.getAttribute("src")!==next)frame.setAttribute("src",next);}document.querySelectorAll("[data-view]").forEach(el=>{const active=el.dataset.view===state.view||(el.closest(".tabs")&&el.dataset.view==="report"&&!home);el.classList.toggle("active",active);if(active)el.setAttribute("aria-current","page");else el.removeAttribute("aria-current");});document.getElementById("breadcrumb").textContent="报告 / Calendar / "+labels[state.view];document.getElementById("status-view").textContent=labels[state.view];save();}
 for(const side of ["left","right","bottom"])document.getElementById("toggle-"+side).addEventListener("click",()=>{if(side!=="bottom"&&matchMedia("(max-width:760px)").matches){workspace.classList.toggle("mobile-"+side);return;}state[side]=!state[side];panels();});
 document.getElementById("bottom-close").addEventListener("click",()=>{state.bottom=false;panels();});
 addEventListener("hashchange",()=>{workspace.classList.remove("mobile-left","mobile-right");select();});
 document.addEventListener("keydown",event=>{if(event.key==="Escape")workspace.classList.remove("mobile-left","mobile-right");});
 frame.addEventListener("load",()=>{try{const doc=frame.contentDocument;const root=new URL(".",location.href);doc.querySelectorAll("a[href]").forEach(a=>{const url=new URL(a.getAttribute("href"),frame.contentWindow.location.href);if(url.origin===location.origin&&url.pathname===root.pathname){a.href=root.href+"#overview";a.target="_top";}else if(url.origin!==location.origin||url.pathname.endsWith(".json")){a.target="_blank";a.rel="noopener";}});}catch(_){} });
 panels();select();
})();
