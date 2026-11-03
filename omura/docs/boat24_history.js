/* Shared browser/Node implementation of the Python paper-performance rules. */
(function(root) {
  'use strict';
  function eligible(r, final=false) {
    const created=Date.parse(r.created_at), cutoff=Date.parse(r.cutoff);
    let valid=Number.isFinite(created)&&Number.isFinite(cutoff)&&created<cutoff&&r.evaluation_eligible!==false;
    if (valid) valid=new Date(created+9*3600000).toISOString().slice(0,10)===new Date(cutoff+9*3600000).toISOString().slice(0,10);
    if(final){const t=Date.parse(r.final_snapshot?.created_at);valid=valid&&Number.isFinite(t)&&created<=t&&t<cutoff;}
    return valid;
  }
  const combo=x=>typeof x==='string'&&/^[1-6]-[1-6]-[1-6]$/.test(x)&&new Set(x.split('-')).size===3;
  function paper(r,n,final=false){
    const result=r.result,picks=(final?r.final_snapshot:r)?.selection?.[String(n)];
    if(!result||!combo(result.combo)||!Number.isFinite(result.payout_100yen)||result.payout_100yen<=0||!Array.isArray(picks)||picks.length!==n||new Set(picks).size!==n||!picks.every(combo))return null;
    const hit=picks.includes(result.combo);return {hit,stake:n*100,return:hit?result.payout_100yen:0};
  }
  function summarize(records,final=false){
    const approved=records.filter(r=>eligible(r,final));const out={saved:records.length,eligible:approved.length,excluded:records.length-approved.length,pending:approved.filter(r=>!r.result).length};
    for(const n of [12,18]){const bets=approved.map(r=>paper(r,n,final)).filter(Boolean);const hits=bets.filter(b=>b.hit).length,stake=bets.reduce((a,b)=>a+b.stake,0),returned=bets.reduce((a,b)=>a+b.return,0);out[n]={races:bets.length,hits,stake,return:returned,profit:returned-stake,hit_rate:bets.length?hits/bets.length:null,roi:stake?returned/stake:null};}return out;
  }
  root.Boat24History={eligible,paper,summarize};
  if(typeof module!=='undefined')module.exports=root.Boat24History;
})(globalThis);
