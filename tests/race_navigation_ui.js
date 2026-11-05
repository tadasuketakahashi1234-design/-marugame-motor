const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('omura/docs/boat24_full_ui.js','utf8');
const elements={},cards={},events={};let jumps=[],renders=0,observerCallback;
function el(id){if(id.startsWith('race-'))return cards[id]||null;return elements[id]||={value:id==='venue'?'19':'',innerHTML:'',textContent:'',disabled:false,querySelectorAll(){return []},addEventListener(t,fn){events[id+':'+t]=fn},dispatchEvent(){events['venue:change']?.()}};}
const row=(v,r)=>({race_code:'20261105'+String(v).padStart(2,'0')+String(r).padStart(2,'0'),venue:v,race:r,cutoff:'2026-11-05T20:00:00+09:00'});
function materialize(rows){for(const r of rows)cards['race-'+r.race_code]={scrollIntoView(){jumps.push(r.race_code)},focus(){}};}
const c={$:el,esc:x=>String(x),names:Array.from({length:25},(_,i)=>'場'+i),raceVisible:24,render(){renders++;materialize(c.rows)},Event:class{},renderReport(){},IntersectionObserver:class{constructor(fn){observerCallback=fn;}disconnect(){}observe(){}}};vm.createContext(c);
vm.runInContext(source.slice(source.indexOf('let quickRows='),source.indexOf('function render(){')),c);
vm.runInContext(source.slice(source.indexOf("$('fullQuickVenue')&&"),source.indexOf("$('fullDate').addEventListener")),c);
const rows=[row(19,2),row(19,1),row(19,3)];materialize(rows);c.renderQuickNav(rows,'2026-11-05|19');
assert.equal(el('fullQuickRace').value,rows[0].race_code,'Default follows next upcoming race, not numeric 1R');
c.jumpToRace(rows[1].race_code);assert(el('fullQuickPrev').disabled);assert(!el('fullQuickNext').disabled);
events['fullQuickNext:click']();assert.equal(jumps.at(-1),rows[0].race_code,'Next follows numeric race order');
events['fullQuickNext:click']();assert.equal(jumps.at(-1),rows[2].race_code);assert(el('fullQuickNext').disabled);
events['fullQuickPrev:click']();assert.equal(jumps.at(-1),rows[0].race_code);
c.renderQuickNav(rows.slice().reverse(),'2026-11-05|19');assert.equal(el('fullQuickRace').value,rows[0].race_code,'Auto-refresh preserves the selected race');
el('fullQuickRace').value=rows[2].race_code;events['fullQuickRace:change']();assert.equal(jumps.at(-1),rows[2].race_code);
c.renderQuickNav([],'2026-11-06|19');assert(el('fullQuickRace').disabled);assert(el('fullQuickPrev').disabled);assert(el('fullQuickNext').disabled);
el('venue').value='0';c.rows=Array.from({length:36},(_,i)=>row(1+Math.floor(i/12),i%12+1));c.renderQuickNav(c.rows,'2026-11-05|0');c.jumpToRace(c.rows[35].race_code);assert.equal(renders,1);assert.equal(jumps.at(-1),c.rows[35].race_code,'A race outside the first 24 must be reachable');
events['venue:change']=()=>c.renderQuickNav([row(15,1)],'2026-11-05|15');el('fullQuickVenue').value='15';materialize([row(15,1)]);events['fullQuickVenue:change']();assert.equal(el('venue').value,'15');assert.equal(jumps.at(-1),row(15,1).race_code);
c.observeReadingRace();c.jumpToRace(row(15,1).race_code);observerCallback([{isIntersecting:true,target:{id:'race-202611050101'},boundingClientRect:{top:0}}]);assert.equal(el('fullQuickRace').value,row(15,1).race_code,'A stale scroll callback must not undo an explicit race choice');
console.log('Race navigation PASS: direct selection, venue switch, numeric previous/next, boundaries, refresh retention, empty day and off-screen national races');
