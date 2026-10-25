"use strict";
(() => {
 const select=document.getElementById("outcome-filter"), search=document.getElementById("run-search"), rows=[...document.querySelectorAll("#run-table tbody tr")];
 function filter(){let n=0;const term=search.value.trim().toLowerCase();for(const row of rows){const visible=(select.value==="all"||select.value===row.dataset.result)&&row.textContent.toLowerCase().includes(term);row.hidden=!visible;if(visible)n++;}document.getElementById("visible-runs").textContent=`显示${n} / ${rows.length}轮`;document.getElementById("no-runs").hidden=n!==0;}
 function reset(){select.value="all";search.value="";filter();}
 function reveal(){if(/^#run-\d+$/.test(location.hash)){reset();document.getElementById(location.hash.slice(1))?.scrollIntoView({block:"center"});}}
 select.addEventListener("change",filter);search.addEventListener("input",filter);document.getElementById("reset-runs").addEventListener("click",reset);addEventListener("hashchange",reveal);filter();reveal();
})();

// Difficulty filters affect reviewed cards only, not execution/campaign counts.
(() => {
 const choice=document.getElementById("difficulty-filter"), cards=[...document.querySelectorAll("[data-difficulty]")];
 function apply(){let count=0;for(const card of cards){card.hidden=choice.value!=="all"&&choice.value!==card.dataset.difficulty;if(!card.hidden)count++;}document.getElementById("difficulty-count").textContent=`显示${count} / ${cards.length}条`;}
 choice.addEventListener("change",apply);document.getElementById("reset-difficulty").addEventListener("click",()=>{choice.value="all";apply();});apply();
})();
