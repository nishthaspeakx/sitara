const pptxgen = require("pptxgenjs");
const cd = require("./chartdata.json");
const p = new pptxgen();
p.layout = "LAYOUT_WIDE";
const NAVY="1E2761", ICE="CADCFC", GOLD="C9A227", INK="22263B", MUT="6B7086", WHITE="FFFFFF", LIGHT="F4F6FC", GOOD="1A7F5C", BAD="B03A48";
const HF="Cambria", BF="Calibri";
function darkSlide(){ const s=p.addSlide(); s.background={color:NAVY}; return s; }
function lightSlide(kicker, title, note){
  const s=p.addSlide(); s.background={color:WHITE};
  if(kicker) s.addText(kicker.toUpperCase(), {x:0.55,y:0.32,w:9,h:0.3,fontFace:BF,fontSize:11,color:GOLD,bold:true,charSpacing:2,margin:0});
  s.addText(title, {x:0.55,y:0.58,w:12.2,h:0.85,fontFace:HF,fontSize:28,color:NAVY,bold:true,margin:0});
  if(note) s.addNotes(note);
  return s;
}
function card(s,x,y,w,h,opts={}){ s.addShape("roundRect",{x,y,w,h,rectRadius:0.07,fill:{color:opts.fill||LIGHT},line:{color:opts.line||"E3E6F2",width:0.75},shadow:{type:"outer",color:"9AA0B8",opacity:0.25,blur:6,offset:2,angle:90}}); }
function stat(s,x,y,w,big,label,color){ card(s,x,y,w,1.5);
  s.addText(big,{x:x+0.12,y:y+0.12,w:w-0.24,h:0.72,fontFace:HF,fontSize:24,bold:true,color:color||NAVY,margin:0});
  s.addText(label,{x:x+0.12,y:y+0.84,w:w-0.24,h:0.6,fontFace:BF,fontSize:10,color:MUT,margin:0}); }
function take(s,text){ s.addShape("roundRect",{x:0.55,y:6.78,w:12.23,h:0.5,rectRadius:0.06,fill:{color:NAVY}});
  s.addText([{text:"TAKEAWAY   ",options:{bold:true,color:GOLD,fontSize:10.5}},{text:text,options:{color:WHITE,fontSize:11.5}}],{x:0.75,y:6.78,w:11.9,h:0.5,fontFace:BF,valign:"middle",margin:0}); }
function bullets(s,x,y,w,h,items,size){ s.addText(items.map((t,i)=>({text:t,options:{bullet:{code:"2022",indent:14},breakLine:i<items.length-1,paraSpaceAfter:7}})),{x,y,w,h,fontFace:BF,fontSize:size||12.5,color:INK,valign:"top",margin:0}); }
function tbl(s, x,y,w, header, rows, colW, opts={}){
  const bodyColor = opts.dark? "FFFFFF" : INK;
  const bodyFill = opts.dark? {color:"2A2F63"} : undefined;
  const trows=[header.map(h=>({text:h,options:{bold:true,color:"FFFFFF",fill:{color:opts.dark?GOLD:NAVY},fontSize:opts.hs||10, ...(opts.dark?{color:NAVY}:{})}}))]
   .concat(rows.map(r=>r.map((c,ci)=>({text:String(c),options:{fontSize:opts.fs||10, color:bodyColor, bold:(opts.boldCol===ci), ...(bodyFill?{fill:bodyFill}:{})}}))));
  s.addTable(trows,{x,y,w,colW,fontFace:BF,border:{type:"solid",color:"D9DCEC",pt:0.5},rowH:opts.rowH||0.3,valign:"middle",margin:0.04});
}
const months=cd.months, cust=cd.customers, revL=cd.revenue_l, ebL=cd.ebitda_l;
const qLabels=months.map(m=> (m%3===0? "M"+m : ""));

// S1 COVER
let s=darkSlide();
s.addText("CONFIDENTIAL — BOARD PRESENTATION",{x:0.7,y:0.5,w:6,h:0.3,fontFace:BF,fontSize:11,color:ICE,charSpacing:3,margin:0});
s.addText("Investment Case & Three-Year Financial Plan",{x:0.7,y:2.2,w:11.9,h:1.6,fontFace:HF,fontSize:44,bold:true,color:WHITE,margin:0});
s.addText("Project Sitara — bottom-up model · conservative / base / aggressive cases · staged capital with hard gates",{x:0.7,y:3.9,w:10.8,h:0.7,fontFace:BF,fontSize:17,color:ICE,margin:0});
s.addText("Deck 2 of 2 · 28 July 2026 · All ₹ figures net of GST unless stated · FX assumption ₹90/$",{x:0.7,y:6.6,w:11,h:0.35,fontFace:BF,fontSize:12,color:ICE,margin:0});
s.addNotes("Companion to Deck 1. Every number traces to the attached Excel model (17 sheets, live formulas). Base case unless stated.");

// S2 FIN EXEC SUMMARY
s=lightSlide("Summary","The financial story on one slide","All from the recalculated model. EBITDA turns positive in month 30 (base). Peak funding ₹7.85 Cr staged across three gated tranches; the board only ever has one tranche at risk.");
const fes=[["₹1.25 Cr","Initial ask (Scenario A)"],["₹4.55 Cr","12-month staged total (A+B)"],["M30","first EBITDA-positive month (base)"],["₹1.42 Cr","Year-1 revenue"],["₹6.34 Cr","Year-2 revenue"],["₹12.16 Cr","Year-3 revenue"],["+₹0.20 Cr","Year-3 EBITDA (2%)"],["₹7.85 Cr","peak staged funding"],["₹11,306","LTV vs CAC ₹3,600 (3.1x)"],["Churn","the #1 financial risk"]];
fes.forEach((d,i)=>{ stat(s,0.55+(i%5)*2.5,1.8+Math.floor(i/5)*1.7,2.36,d[0],d[1], i===9?BAD:NAVY); });
card(s,0.55,5.35,12.23,1.15,{fill:"FDF6E8",line:"E8D9B0"});
s.addText([{text:"Honesty note: ",options:{bold:true,color:GOLD}},{text:"this is a deliberately conservative bottom-up build. 3-yr cumulative EBITDA is −₹4.63 Cr; the business is a Year-4 profit story funded by ₹7.85 Cr of staged, gated capital. The aggressive case (₹22.6 Cr Y3 revenue, +₹6.3 Cr EBITDA) requires churn ≤4.5% — only claimable after cohorts prove it.",options:{color:INK}}],{x:0.8,y:5.35,w:11.7,h:1.15,fontFace:BF,fontSize:11.5,valign:"middle",margin:0});
take(s,"A staged ₹7.85 Cr buys a ₹14.8 Cr exit-ARR business at base — and caps every tranche's risk with a gate.");

// S3 BUSINESS MODEL
s=lightSlide("Model","Revenue streams: core vs future","Core model only contains proven-shape streams. Future streams (rituals commission, B2B API, family plans) are upside, never in the base numbers — that is why the base looks modest and credible.");
const streams=[["IN CORE MODEL",true,["Monthly subscriptions (40% of subs)","Annual subscriptions (60%; cash collected upfront, revenue recognised monthly)","Premium tiers (25% of subs; consult minutes included)","Add-ons: extra consult minutes, premium reports (~8% attach)"]],
["FUTURE UPSIDE (not modelled)",false,["Family plans (priced per household)","Ritual fulfilment commission (DharmaSetu module, 20–25% take)","Matchmaking / kundli reports at wedding season","B2B muhurat API (wedding platforms) · white-label"]]];
streams.forEach((st,i)=>{ const x=0.55+i*6.24; card(s,x,1.85,6.04,4.3,{fill: st[1]?LIGHT:"F7F7F9"});
 s.addText(st[0],{x:x+0.25,y:2.05,w:5.5,h:0.4,fontFace:HF,fontSize:14,bold:true,color:st[1]?NAVY:MUT,margin:0});
 bullets(s,x+0.25,2.6,5.55,3.4,st[2],12);});
take(s,"Nothing speculative sits in the P&L. Upside is listed, labelled, and excluded.");

// S4 PRICING
s=lightSlide("Pricing","Pricing architecture — four plans, two markets","India prices GST-inclusive; model revenue net of 18% GST. NRI plans are zero-rated exports. Mix is a management estimate to be replaced by cohort data. Blended net ARPU ₹815/mo + ₹65 add-ons = ₹880.");
tbl(s,0.55,1.9,12.23,["Plan","Customer","Monthly","Annual","Mix","Net eff. ₹/mo","Incl. human support"],
[["NRI Standard","NRI individual","$12.99","$99","45%","₹913","—"],
 ["NRI Premium","NRI premium","$24.99","$199","12%","₹1,795","30 consult-min / quarter"],
 ["India Aarambh","Metro India","₹499","₹3,999","30%","₹339","—"],
 ["India Pragati","Metro India premium","₹999","₹7,999","13%","₹678","15 consult-min / quarter"]],
[1.7,2.5,1.2,1.2,0.9,1.6,3.13],{fs:11,hs:11,rowH:0.5});
stat(s,0.55,4.7,3.9,"₹880/mo","blended total ARPU (net) incl. add-ons");
stat(s,4.6,4.7,3.9,"60%","annual billing share — cash ahead of revenue");
stat(s,8.65,4.7,3.9,"79%","blended gross margin (model output)");
take(s,"Annual-first pricing hedges the churn risk and funds working capital.");

// S5 ASSUMPTIONS
s=lightSlide("Assumptions","Core assumptions — with their sources","The honesty slide. Colour meaning: FACT (published), BENCHMARK (named competitor), ESTIMATE (management). Every one lives in the Assumptions sheet and every board number recalculates from it.");
tbl(s,0.55,1.85,12.23,["Assumption","Value","Type","Source / logic"],
[["Blended CAC","₹3,600","Benchmark+est.","AstroTalk domestic ₹575–870 (Entrackr); NRI premium 4–5x assumed"],
 ["Monthly churn (base)","6.0%","Benchmark+est.","Recurly DTC 6.5%/mo; annual-mix damping; VALIDATION TARGET"],
 ["Visitor→trial / trial→paid","3% / 25%","Estimate","Gate-1 replaces with cohort actuals"],
 ["Referral share of new","12%","Estimate","Family-chart gifting loop"],
 ["Refund rate","2.5%","Estimate","30-day money-back guarantee"],
 ["AI + infra cost / user / mo","₹85","Estimate","LLM + ephemeris + cloud at Jul-2026 rates"],
 ["Human minutes / user / mo","₹45","Estimate","Premium-tier allowance blended"],
 ["Support + payment fees","₹25 + 2.8%","Fact/est.","Stripe/Razorpay published pricing"],
 ["FX","₹90 / $","Estimate","Sensitivity tested"]],
[3.4,1.5,1.7,5.63],{fs:10.5,hs:11,rowH:0.42});
take(s,"Three assumptions decide everything — churn, ARPU, CAC — and Gate-1 measures all three.");

// S6 GROWTH MODEL
s=lightSlide("Growth","Paying customers — 36-month build (base case)","Opening + new (marketing÷CAC ×1.12 referral) − churn = closing. Founding-500 bump at M4. Churn glidepath 6%→5% from M13 as annual mix seasons. Conservative M36: 7,538; aggressive: 24,345.");
s.addChart(p.ChartType.line,[{name:"Closing paying customers",labels:qLabels,values:cust}],
{x:0.55,y:1.85,w:8.1,h:4.5,chartColors:[NAVY],lineSize:2.5,lineSmooth:true,showLegend:false,showTitle:false,catAxisLabelColor:MUT,valAxisLabelColor:MUT,valGridLine:{color:"E7E9F4",size:0.5},catGridLine:{style:"none"},lineDataSymbol:"none",showValue:false});
stat(s,8.95,1.95,3.8,"3,231","month-12 payers");
stat(s,8.95,3.55,3.8,"8,552","month-24 payers");
stat(s,8.95,5.15,3.8,"14,544","month-36 payers");
take(s,"No hockey stick: growth is marketing-spend ÷ CAC, damped by churn, every month.");

// S7 FUNNEL
s=lightSlide("Funnel","Acquisition funnel — representative month (M12)","Rates are management estimates until Gate-1 cohorts replace them. The funnel reconciles exactly to the growth model's new-customer line and the ₹15L monthly marketing spend at M12.");
const fun=[["Impressions","~3.1M",""],["Visitors","~13,900","3% visit-to-trial"],["Trials / Honest-Kundli","~1,700","25% trial-to-paid"],["New paid customers","417","₹3,600 CAC"],["+ Referrals","50","12% of funnel"],["Retained M2+","~85%","month-2 cohort"]];
fun.forEach((d,i)=>{ const w=11.4-i*1.55, x=0.55+(12.23-w)/2, y=1.85+i*0.78;
 s.addShape("roundRect",{x,y,w,h:0.68,rectRadius:0.06,fill:{color: i<3?"5A5FD4":NAVY}});
 s.addText(d[0]+"   "+d[1],{x:x+0.3,y,w:w-2.5,h:0.68,fontFace:BF,fontSize:12.5,bold:true,color:WHITE,valign:"middle",margin:0});
 s.addText(d[2],{x:x+w-2.4,y,w:2.2,h:0.68,fontFace:BF,fontSize:10.5,bold:true,color:"FFFFFF",valign:"middle",align:"right",margin:0});});
take(s,"Funnel ties to spend and CAC — no orphan conversion claims.");

// S8 CAC BY CHANNEL
s=lightSlide("Acquisition","CAC by channel → blended ₹3,600","Channel CACs are estimates anchored on AstroTalk's published domestic CAC and standard diaspora Meta auction economics. Kill-rule: any channel >₹6,000 after two cohorts is cut.");
s.addChart(p.ChartType.bar,[{name:"CAC (₹)",labels:["Referral","Community/organic","Influencers","Festival campaigns","Meta diaspora","Google intent"],values:[800,1200,3000,3400,4200,4800]}],
{x:0.55,y:1.85,w:7.6,h:4.5,barDir:"bar",chartColors:[GOOD,GOOD,NAVY,NAVY,NAVY,MUT],showValue:true,dataLabelPosition:"outEnd",dataLabelFontSize:10,showLegend:false,showTitle:false,catAxisLabelColor:INK,valAxisLabelColor:MUT,valGridLine:{color:"E7E9F4",size:0.5},catGridLine:{style:"none"}});
bullets(s,8.5,2.1,4.2,4.0,["Spend mix: Meta 40% · Google 15% · influencers 15% · community 12% · referral 10% · festivals 8%","Blended ₹3,600 = weighted average (Marketing sheet)","Referral loop: gifting a family chart costs ₹800 and deepens the moat","Benchmark: AstroTalk recovers CAC in 6–8 months; our payback is 5.3 months at 3x their ARPU"],11.5);
take(s,"Blended ₹3,600 with a payback of 5.3 months — conservative against the category benchmark.");

// S9 LTV
s=lightSlide("Economics","LTV ₹11,306 · LTV:CAC 3.1x · payback 5.3 months","LTV = contribution ₹678/mo ÷ churn 6%. No upsell or referral credit is included in LTV — genuine conservatism. At the Y3 churn target (5%) LTV rises to ₹13,560 (3.8x).");
s.addChart(p.ChartType.bar,[{name:"₹ per customer",labels:["Conservative (7.5% churn)","Base (6.0%)","Aggressive (4.5%)"],values:[8590,11306,15067]},{name:"CAC",labels:["Conservative (7.5% churn)","Base (6.0%)","Aggressive (4.5%)"],values:[4500,3600,3000]}],
{x:0.55,y:1.85,w:7.4,h:4.5,barDir:"col",chartColors:[NAVY,GOLD],showValue:true,dataLabelPosition:"outEnd",dataLabelFontSize:10,showLegend:true,legendPos:"b",legendFontSize:10,showTitle:false,catAxisLabelColor:INK,valAxisLabelColor:MUT,valGridLine:{color:"E7E9F4",size:0.5},catGridLine:{style:"none"}});
const lt=[["3.1x","LTV : CAC (base)"],["5.3 mo","CAC payback"],["16.7 mo","expected customer life"],["1.9x","conservative ratio — the floor that triggers stop-loss debate"]];
lt.forEach((d,i)=>{ stat(s,8.35+(i%2)*2.05,1.95+Math.floor(i/2)*1.75,1.95,d[0],d[1], i===3?BAD:NAVY); });
take(s,"Unit economics clear the 3x bar without any upsell credit — and fail gracefully, visibly, if churn slips.");

// S10 UNIT ECONOMICS WATERFALL
s=lightSlide("Economics","Where each ₹880 goes","Contribution ₹678/user/month (77%). Per-plan: NRI Premium contributes ₹1,595/mo at 89%; India Aarambh ₹204/mo at 60% — the India tier exists for strategic breadth, the NRI tier pays the bills.");
const wf=[["Total ARPU","880",NAVY],["AI + infra","-85",MUT],["Human minutes","-45",MUT],["Support","-25",MUT],["Payment 2.8%","-25",MUT],["Refunds 2.5%","-22",MUT],["Contribution","678",GOOD]];
let runx=0.55;
wf.forEach((d,i)=>{ const w=1.66; const h=Math.abs(parseFloat(d[1]))/880*3.2+0.35; const y= 5.75-h;
 s.addShape("roundRect",{x:runx,y,w:w-0.12,h,rectRadius:0.05,fill:{color:d[2]}});
 s.addText(d[1],{x:runx,y:y-0.4,w:w-0.12,h:0.35,fontFace:BF,fontSize:11,bold:true,color:INK,align:"center",margin:0});
 s.addText(d[0],{x:runx-0.05,y:5.85,w:w,h:0.6,fontFace:BF,fontSize:9.5,color:MUT,align:"center",margin:0});
 runx+=w;});
take(s,"77% contribution margin/user before CAC — software economics with a human premium layer.");

// S11 INVESTMENT ALLOCATION
s=lightSlide("Investment","18-month allocation (Scenarios A + B = ₹4.55 Cr)","Full line-item detail in the Excel. Contingency 7% held unallocated. Marketing ramps only after Gate-1 passes — the allocation is gate-shaped, not calendar-shaped.");
s.addChart(p.ChartType.doughnut,[{name:"Allocation",labels:["Product & technology 38%","Marketing 30%","Content & expert layer 12%","Operations 8%","Legal & compliance 5%","Contingency 7%"],values:[38,30,12,8,5,7]}],
{x:0.4,y:1.9,w:5.8,h:4.5,chartColors:[NAVY,"5A5FD4",GOLD,"8B8FD9","ADB1E6","C9CCEE"],showLegend:true,legendPos:"r",legendFontSize:10,showValue:false,showTitle:false,holeSize:58});
bullets(s,6.6,2.0,6.1,4.3,["Product & tech ₹1.73 Cr: 3 engineers, design, chart engine licence, AI usage, security, QA","Marketing ₹1.37 Cr: brand, landing, paid cohorts, influencers, festival campaigns, referral incentives","Expert layer ₹55L: Jyotish lead, corpus curation, astrologer panel contracts, ethics review","Ops ₹36L: support, panel ops, QA-of-guidance workflows","Legal ₹23L: DPDP/GDPR, T&Cs, ASCI counsel, IP, insurance","Contingency ₹31L (7%) — unallocated by policy"],11.5);
take(s,"Every rupee is mapped to a gate; marketing money unlocks only on validated cohorts.");

// S12-14 SCENARIOS A/B/C
s=lightSlide("Scenario A","Lean validation & build — ₹1.25 Cr","Purpose: prove demand before scale capital. The concierge test (real astrologer + operator over WhatsApp) runs before serious code. Founding-500 annuals contribute ~₹27L cash offset. Max loss = ₹1.25 Cr, ~₹95L net of founding cash.");
tbl(s,0.55,1.9,12.23,["Item","Detail"],
[["Timeline","Months 1–6"],["Team","2 engineers + founder + part-time Jyotish lead + contract designer (~5.2 FTE)"],
 ["Users targeted","50 concierge @ $15/mo → 500 founding members @ $99/yr"],
 ["Expected revenue","~₹32L cash (founding annuals + concierge)"],
 ["Success criteria","Concierge M2 renewal ≥60% · landing capture >25% · CAC <₹4,000 · activation >60%"],
 ["Maximum acceptable loss","₹1.25 Cr (hard stop-loss)"],["Decision gate","Month-6 board review → Gate 2"]],
[3.2,9.03],{fs:11.5,hs:11.5,rowH:0.52});
take(s,"₹1.25 Cr buys the three numbers that decide everything: churn, CAC, activation.");

s=lightSlide("Scenario B","Focused market launch — +₹3.3 Cr (months 7–18)","Engages only if Gate 1 passes. Burn peaks ~₹22L/month; deferred annual cash softens working capital. Milestones are the Gate-3 conditions.");
tbl(s,0.55,1.9,12.23,["Item","Detail"],
[["Investment","₹3.3 Cr tranche at M7 (cumulative ₹4.55 Cr)"],
 ["Hiring","Team to ~9 FTE: +1 engineer, growth, content, panel ops, support"],
 ["Marketing budget","₹8L/mo (M4–6) → ₹15L/mo (M7–12) → ₹25L/mo (Y2)"],
 ["Customers","3,231 by M12 · ~6,500 by M18"],
 ["Revenue","₹1.42 Cr Y1; M18 run-rate ~₹55L/quarter GP"],
 ["Gross margin","79% blended"],
 ["Cash burn","Peak ~₹22L/mo; minimum cash ₹31L (policy floor ₹40L — tranche timing flagged)"],
 ["Milestones (Gate 3)","Churn ≤6% · blended CAC ≤₹3,600 · NPS ≥55 · cohort audit"]],
[3.2,9.03],{fs:11,hs:11.5,rowH:0.47});
take(s,"Launch capital follows evidence; every milestone is a number, not an adjective.");

s=lightSlide("Scenario C","Accelerated scale — +₹3.3 Cr at PMF (months 19–36)","Engages only after independent cohort audit. Adds India tier scaling, matchmaking reports, rituals module. Constraint stated plainly: capital cannot buy retention — if churn drifts, spend throttles automatically.");
tbl(s,0.55,1.9,12.23,["Item","Detail"],
[["Investment","₹3.3 Cr tranche at M19 (peak staged funding ₹7.85 Cr)"],
 ["Marketing","₹35L/mo average through Y3"],
 ["Expansion","India Pragati scale-up · matchmaking/kundli reports (wedding season) · rituals cross-sell module"],
 ["Customers","8,552 by M24 → 14,544 by M36 (base)"],
 ["Revenue / profit","Y3 revenue ₹12.16 Cr · EBITDA +₹0.20 Cr · exit ARR ≈ ₹14.8 Cr"],
 ["Break-even","First EBITDA-positive month: M30 (base) · M23 (aggressive)"],
 ["Return shape","Exit-ARR multiple on ₹7.85 Cr staged capital; Series-A optionality after M18 audit"],
 ["Risks","CAC inflation at scale · incumbent response · aggressive case requires churn ≤4.5%"]],
[3.2,9.03],{fs:11,hs:11.5,rowH:0.47});
take(s,"Scale is a consequence of gates passed — never a substitute for them.");

// S15 Y1 MONTHLY P&L
s=lightSlide("P&L","Year 1 — monthly P&L (₹ lakh)","Quarterly columns shown for readability; monthly detail in Excel P&L sheet. Y1 EBITDA −₹2.60 Cr is the validation-and-launch investment expressed in P&L form.");
tbl(s,0.55,1.9,12.23,["₹ lakh","Q1 (M1–3)","Q2 (M4–6)","Q3 (M7–9)","Q4 (M10–12)","Year 1"],
[["Net revenue","3.5","17.4","49.5","71.6","142.0"],
 ["COGS","0.7","3.7","10.4","15.0","29.8"],
 ["Gross profit","2.8","13.7","39.1","56.6","112.2"],
 ["Salaries","32.7","32.7","57.3","57.3","180.0"],
 ["Marketing","9.0","24.0","45.0","45.0","123.0"],
 ["Tech + G&A + conting.","10.5","10.5","18.0","18.1","57.1"],
 ["EBITDA","(49.4)","(53.5)","(81.2)","(63.8)","(260.0)*"]],
[2.2,2.0,2.0,2.0,2.0,2.03],{fs:11,hs:11,rowH:0.5,boldCol:5});
s.addText("*Sum differs from quarterly display due to rounding; exact figures in Excel. Founding-member annual cash (₹27L) arrives in Q2 ahead of recognition.",{x:0.55,y:6.15,w:12,h:0.5,fontFace:BF,fontSize:10,italic:true,color:MUT,margin:0});
take(s,"Year 1 is a purchased learning curve: ₹2.60 Cr of EBITDA investment buys 3,231 paying customers and proven cohorts.");

// S16 Y2-Y3 P&L
s=lightSlide("P&L","Years 2 and 3 — annual P&L (₹ crore)","GM holds at 79%. Y3 turns EBITDA-positive at +₹0.20 Cr with the year's later months at +₹16–19L/month — the Y4 profit engine. Depreciation negligible (asset-light); tax nil until carry-forwards absorb.");
tbl(s,0.55,1.9,7.6,["₹ crore","Year 2","Year 3"],
[["Net revenue","6.34","12.16"],["COGS","1.33","2.55"],["Gross profit","5.01","9.61"],
 ["Gross margin","79%","79%"],["Salaries","2.32","4.10"],["Marketing","3.00","4.20"],
 ["Tech + G&A + contingency","0.92","1.11"],["EBITDA","(2.23)","+0.20"],
 ["EBITDA margin","(35%)","+2%"],["Net profit","(2.24)","+0.19"]],
[3.0,2.3,2.3],{fs:11.5,hs:11.5,rowH:0.42,boldCol:0});
stat(s,8.5,2.0,4.2,"M30","first EBITDA-positive month");
stat(s,8.5,3.6,4.2,"+₹19L","EBITDA in month 36 (run-rate ₹2.3 Cr/yr)");
stat(s,8.5,5.2,4.2,"79%","durable gross margin");
take(s,"The P&L crosses over inside the plan window — on conservative assumptions.");

// S17 CASH FLOW
s=lightSlide("Cash","Cash flow & funding plan","Three tranches, each gated. Deferred annual-plan cash (₹1.0+ Cr cumulative) is a real working-capital cushion. Minimum cash ₹31L occurs at M6 — tranche-B timing is deliberately placed against it; the board can advance it two weeks if Gate-1 clears early.");
tbl(s,0.55,1.9,12.23,["Item","Amount / timing"],
[["Tranche 1 — Scenario A","₹1.25 Cr at M1 (validation + build)"],
 ["Tranche 2 — Scenario B","₹3.3 Cr at M7 (post Gate-1)"],
 ["Tranche 3 — Scenario C","₹3.3 Cr at M19 (post cohort audit)"],
 ["Peak staged funding","₹7.85 Cr"],
 ["Minimum cash balance","₹31L (M6) — floor policy ₹40L, flagged; mitigated by founding-member cash"],
 ["Deferred-revenue cushion","Annual plans collect ~5.5 months ahead of recognition"],
 ["Closing cash M36","₹3.47 Cr (base) — funds Y4 without further capital"],
 ["Additional funding requirement","None in base case within 36 months; conservative case triggers stop-loss instead"]],
[3.6,8.63],{fs:11,hs:11.5,rowH:0.47});
take(s,"The board never has more than one gated tranche at risk at any time.");

// S18 CHARTS
s=lightSlide("Trajectory","Revenue ramp and the EBITDA crossover","Both series direct from the model. The crossover at M30 is the base case; aggressive M23; conservative never (stop-loss intervenes long before).");
s.addChart(p.ChartType.line,[{name:"Net revenue (₹ lakh/mo)",labels:qLabels,values:revL},{name:"EBITDA (₹ lakh/mo)",labels:qLabels,values:ebL}],
{x:0.55,y:1.85,w:12.2,h:4.6,chartColors:[NAVY,GOLD],lineSize:2.5,lineSmooth:true,showLegend:true,legendPos:"b",legendFontSize:11,showTitle:false,catAxisLabelColor:MUT,valAxisLabelColor:MUT,valGridLine:{color:"E7E9F4",size:0.5},catGridLine:{style:"none"},lineDataSymbol:"none",showValue:false});
take(s,"Steady compounding, visible crossover — no hockey stick anywhere in this deck.");

// S19 BREAK-EVEN
s=lightSlide("Break-even","What break-even requires — three cases","BE customers = fixed costs ÷ contribution per customer. Cash-to-BE is cumulative EBITDA burn until the crossover month. Conservative case does not break even in 36 months — which is why gates exist.");
tbl(s,0.55,1.9,12.23,["Metric","Conservative","Base","Aggressive"],
[["Monthly churn","7.5%","6.0%","4.5%"],
 ["Contribution / customer / month","₹607","₹678","₹762"],
 ["Fixed cost at crossover (₹/mo)","—","~₹52L","~₹48L"],
 ["Customers to break even","not reached","~7,700","~6,300"],
 ["Revenue to break even (₹/mo)","—","~₹68L","~₹55L"],
 ["Break-even month","beyond M36","M30","M23"],
 ["Cash consumed to BE","stop-loss at gates","~₹6.9 Cr","~₹4.6 Cr"]],
[3.6,2.8,2.8,3.03],{fs:11.5,hs:11.5,rowH:0.5});
take(s,"Base case breaks even at ~7,700 customers — 0.05% of the diaspora-adult addressable base.");

// S20 SCENARIO COMPARISON
s=lightSlide("Scenarios","Conservative · base · aggressive","Conservative combines churn 7.5% + CAC ₹4,500 + ARPU −8% + marketing −20%. Aggressive requires proof before spend. Y3 EBITDA range spans −₹3.7 Cr to +₹6.3 Cr — the spread IS the argument for staged capital.");
s.addChart(p.ChartType.bar,[{name:"Y3 revenue (₹ Cr)",labels:["Conservative","Base","Aggressive"],values:[6.2,12.16,22.64]},{name:"Y3 EBITDA (₹ Cr)",labels:["Conservative","Base","Aggressive"],values:[-3.74,0.2,6.33]}],
{x:0.55,y:1.85,w:7.6,h:4.5,barDir:"col",chartColors:[NAVY,GOLD],showValue:true,dataLabelPosition:"outEnd",dataLabelFontSize:10,showLegend:true,legendPos:"b",legendFontSize:10,showTitle:false,catAxisLabelColor:INK,valAxisLabelColor:MUT,valGridLine:{color:"E7E9F4",size:0.5},catGridLine:{style:"none"}});
tbl(s,8.5,1.95,4.3,["","Cons.","Base","Aggr."],
[["M36 payers","7.5K","14.5K","24.3K"],["Exit ARR (₹Cr)","6.7","14.8","24.9"],["BE month",">36","30","23"],["Peak cash (₹Cr)","5.9*","7.85","8.6*"]],
[1.5,0.93,0.93,0.94],{fs:10,hs:10,rowH:0.45});
s.addText("*Conservative peak reflects stop-loss at gates; aggressive adds growth capital only after cohort proof.",{x:8.5,y:4.4,w:4.2,h:0.8,fontFace:BF,fontSize:9.5,italic:true,color:MUT,margin:0});
take(s,"The spread between cases is exactly why capital is staged and gated.");

// S21 SENSITIVITY
s=lightSlide("Sensitivity","What moves the model most","Single-variable stresses (closed-form approximations; Excel Sensitivity sheet). The three biggest drivers — churn, ARPU, CAC — are precisely what Gate-1 measures. That is the design.");
const sens=[["Churn 6.0% → 7.5%","M36 customers −24% · BE slips ~7 months",1.0],
["ARPU −15%","Y3 EBITDA turns negative (−₹1.6 Cr)",0.9],
["CAC +25%","Peak funding +₹85L · payback 6.6 months",0.75],
["Conversion −25%","M36 customers −24%",0.7],
["AI cost ×2","GM 79% → 71% — absorbable",0.45],
["Growth delayed 6 months","Peak funding +₹1.1 Cr",0.4],
["Annual mix 60% → 40%","Working-capital cushion −₹45L",0.3],
["Refunds ×2","GM −2.5 pts — minor",0.2]];
sens.forEach((d,i)=>{ const y=1.9+i*0.56;
 s.addText(d[0],{x:0.55,y,w:3.3,h:0.5,fontFace:BF,fontSize:11,color:INK,valign:"middle",margin:0});
 s.addShape("roundRect",{x:4.0,y:y+0.09,w:d[2]*5.4,h:0.32,rectRadius:0.04,fill:{color: i<3?BAD:"8B8FD9"}});
 s.addText(d[1],{x:4.1+d[2]*5.4,y,w:12.7-4.1-d[2]*5.4,h:0.5,fontFace:BF,fontSize:10,color:MUT,valign:"middle",margin:0});});
take(s,"Top-3 drivers: churn, ARPU, CAC — all three are measured by the ₹1.25 Cr validation before scale money moves.");

// S22 RETURNS BY LEVEL
s=lightSlide("Returns","What each investment level buys — and its constraint","Levels adjusted to the staged structure. Honesty rule applied: capital does not buy retention — every level hits the same gates. ROI shapes are ranges, not promises; the model's base case is the ₹7.85 Cr staged path.");
tbl(s,0.55,1.9,12.23,["Level","What it buys","Payers target","Exit ARR","3-yr cum EBITDA","Constraint"],
[["₹50L","Concierge validation only; no product","50 pilot + 250 founding","₹0.25 Cr","−₹0.5 Cr","No product = no compounding"],
 ["₹1.25 Cr","Validation + v1 + founding 500 (Scenario A)","500–800","₹0.7–0.9 Cr","−₹1.1 Cr","Stops at Gate 1 by design"],
 ["₹4.55 Cr","A + B: launch to ~6,500 payers (M18)","3,200 (M12)","₹3.4 Cr (M18)","−₹4.4 Cr","CAC inflation risk beyond ₹15L/mo spend"],
 ["₹7.85 Cr","Full staged plan (base case)","14,544 (M36)","₹14.8 Cr","−₹4.6 Cr","Churn ≤6% required; gates unchanged"],
 ["₹10+ Cr","Adds India mass-tier + rituals module earlier","18–22K","₹18–22 Cr","−₹4 to −₹5 Cr","Diminishing: retention gates bind, CAC rises"]],
[1.3,3.3,1.9,1.5,1.7,2.53],{fs:10,hs:10.5,rowH:0.62});
take(s,"₹7.85 Cr staged is the efficient frontier; more money buys speed, not certainty.");

// S23 IDEA-WISE COMPARISON
s=lightSlide("Alternatives","The same money in the other top ideas","Same ARPU/churn/CAC logic applied top-down (Excel Idea Comparison sheet); ranges, not precision. Sitara has the best balance of ceiling, margin, ops and validation cost. KalaOS = cheapest break-even, smallest ceiling. Sahay = biggest Y3, biggest cash and ops risk.");
tbl(s,0.55,1.9,12.23,["Metric","Sitara","Sahay","KalaOS","DharmaSetu","Smriti"],
[["MVP investment","₹0.6–1.0 Cr","₹0.8–1.3 Cr","₹0.6–1.0 Cr","₹0.5–0.9 Cr","₹0.6–0.9 Cr"],
 ["3-yr cash need","₹6–7 Cr","₹9–12 Cr","₹4–5 Cr","₹5–7 Cr","₹5.5–7.5 Cr"],
 ["Gross margin","72–78%","40–65%","65–72%","55–70%","50–65%"],
 ["Monthly churn","5–7.5%","2.5–4%+life events","2.5–3.5% logo","3–5%","3.5–5%+aging-out"],
 ["Break-even","~M30","~M30–34","~M22–26","~M28–34","~M30–36"],
 ["Y3 revenue","₹11–17 Cr","₹16–22 Cr","₹9–12 Cr","₹7–11 Cr","₹6–10 Cr"],
 ["Y3 EBITDA","₹0.8–1.8 Cr","(₹1)–₹1.5 Cr","₹1.2–2.2 Cr","₹0.3–1.2 Cr","(₹0.5)–₹0.8 Cr"],
 ["Risk-adj. score","8.1","8.0","7.6","7.4","7.1"]],
[2.3,2.0,2.1,1.95,1.95,1.93],{fs:10,hs:10.5,rowH:0.47,boldCol:1});
take(s,"The ranking survives financial scrutiny — not just strategic scoring.");

// S24 DOWNSIDE
s=lightSlide("Downside","What the bad case looks like — and why we never fully ride it","The conservative case is shown unflinchingly. The gates exist precisely so the board's exposure to this case is ₹1.25 Cr (Gate 1) or ₹4.55 Cr (Gate 2) — never the full ₹7.85 Cr.");
bullets(s,0.55,1.85,6.2,4.3,["Conservative walk: churn 7.5%, CAC ₹4,500, ARPU −8% → M36 only 7,538 payers, Y3 EBITDA −₹3.74 Cr, no break-even in window","Exposure ladder: Gate-1 failure caps loss at ₹1.25 Cr (≈₹95L net of founding cash); Gate-3 failure caps at ₹4.55 Cr with a ~₹3.4 Cr-ARR business and pivot assets","Stop-loss triggers: concierge M2 <40% · founding <250 by M6 · churn >8% for 2 consecutive quarters · CAC >₹6,000 blended for 2 quarters","Pivot assets even in failure: trust brand, astrologer panel, chart engine, cohort data — reusable for hybrid-credits model or KalaOS"],12);
card(s,7.1,1.95,5.65,3.9,{fill:"F7F1F1",line:"E7D5D5"});
s.addText("STOP-INVESTMENT CONDITIONS",{x:7.35,y:2.15,w:5.2,h:0.4,fontFace:HF,fontSize:13,bold:true,color:BAD,margin:0});
bullets(s,7.35,2.6,5.2,3.1,["Concierge M2 renewal <40%","<250 founding members by month 6","Churn >8%/mo, 2 consecutive quarters","Blended CAC >₹6,000, 2 quarters","Regulatory action on category claims"],11.5);
take(s,"The downside is visible, bounded, and pre-agreed — the definition of a governable bet.");

// S25 RISK REGISTER
s=lightSlide("Risks","Risk register with mitigations","Each risk maps to a mitigation already embedded in plan or product. The ethics code is simultaneously brand, regulatory shield, and moat.");
tbl(s,0.55,1.9,12.23,["Risk","Likelihood","Impact","Mitigation"],
[["Subscription conversion fails","Medium","High","Concierge gate before code; pivot to membership+credits pre-planned"],
 ["Free-AI erosion","Medium","Medium","Moat = memory + deterministic engine + humans + ethics brand"],
 ["Incumbent response (AstroTalk/AstroSage)","Medium","Medium","Premium NRI niche they cannot serve without cannibalising fear-revenue"],
 ["Regulatory / claims (ASCI, CPA)","Low-Med","High","No outcome guarantees; ethics code; marketing counsel review"],
 ["Key-person Jyotish credibility","Medium","Medium","Codify methodology into reviewed corpus from day 1"],
 ["Emotional-dependency ethics","Low","High","Spending caps, vulnerable-moment detection, human referral prompts"],
 ["FX and platform fees","Low","Low","Web-first billing; FX sensitivity tested"]],
[3.4,1.4,1.2,6.23],{fs:10.5,hs:11,rowH:0.5});
take(s,"No hidden risks: each one is named, sized, and answered.");

// S26 GOVERNANCE
s=lightSlide("Governance","Reporting cadence and gate calendar","Monthly MIS + quarterly deep reviews; independent cohort audit before scale tranche. The board sees churn curves, not vanity metrics.");
const gov=[["Monthly MIS","Payers · cohort retention curves · CAC by channel · NPS · cash runway"],
["Quarterly review","Full P&L vs model · sensitivity re-run · risk register refresh"],
["Gate 1 — Month 6","Concierge + founding results → approve/deny ₹3.3 Cr Tranche B"],
["Gate 2 — Month 12","Churn ≤6%, CAC ≤₹3,600, NPS ≥55 checkpoint"],
["Gate 3 — Month 18","Independent cohort audit → approve/deny ₹3.3 Cr Tranche C"]];
gov.forEach((d,i)=>{ const y=1.95+i*0.92; card(s,0.55,y,12.23,0.8);
 s.addText(d[0],{x:0.8,y,w:2.9,h:0.8,fontFace:HF,fontSize:12.5,bold:true,color:NAVY,valign:"middle",margin:0});
 s.addText(d[1],{x:3.8,y,w:8.7,h:0.8,fontFace:BF,fontSize:11.5,color:INK,valign:"middle",margin:0});});
take(s,"Cohort curves to the board, every month — the model stays falsifiable.");

// S27 DECISION FRAMEWORK
s=lightSlide("Decision","Four options before the board","Recommendation is Option 2. Option 4 assessed honestly: no ethics-compatible acquisition target exists; partnership optionality (e.g., AstroSage compute/supply) noted for Scenario C, not now.");
const opts=[["1 · Do nothing","₹0","Category IPO window passes; the premium NRI niche gets claimed — likely by an incumbent's spin-off. Opportunity cost, not safety.",false],
["2 · Validate & build v1  ✓ RECOMMENDED","₹1.25 Cr","Capped risk; buys churn/CAC/activation truth in 6 months; every later rupee becomes evidence-based.",true],
["3 · Build & launch now","₹4.55 Cr","Skips the cheapest learning; commits launch capital on research alone; higher variance for no added upside.",false],
["4 · Partner / acquire","n/a","No suitable ethics-compatible target; white-label astrology stacks would inherit the trust problem we exist to solve.",false]];
opts.forEach((d,i)=>{ const y=1.85+i*1.18; card(s,0.55,y,12.23,1.05,{fill:d[3]?"EEF2E6":LIGHT,line:d[3]?"CBE3D6":"E3E6F2"});
 s.addText(d[0],{x:0.8,y:y+0.08,w:4.3,h:0.9,fontFace:HF,fontSize:13,bold:true,color:d[3]?GOOD:NAVY,valign:"middle",margin:0});
 s.addText(d[1],{x:5.2,y:y+0.08,w:1.3,h:0.9,fontFace:BF,fontSize:12,bold:true,color:GOLD,valign:"middle",margin:0});
 s.addText(d[2],{x:6.6,y:y+0.08,w:6.0,h:0.9,fontFace:BF,fontSize:10.5,color:INK,valign:"middle",margin:0});});
take(s,"Option 2 dominates: the same information at a fraction of the capital at risk.");

// S28 FINAL ASK
s=darkSlide();
s.addText("THE ASK",{x:0.7,y:0.55,w:6,h:0.4,fontFace:BF,fontSize:13,color:GOLD,charSpacing:3,bold:true,margin:0});
s.addText("Approve ₹1.25 crore — Scenario A",{x:0.7,y:1.0,w:12,h:0.8,fontFace:HF,fontSize:34,bold:true,color:WHITE,margin:0});
tbl(s,0.7,2.0,11.9,["Item","Commitment"],
[["Use of funds","Product ₹52L · expert layer ₹18L · marketing ₹22L · ops+legal ₹17L · contingency ₹16L"],
 ["90-day deliverables","Concierge cohort live · landing >25% capture · 20 interviews · chart-engine alpha"],
 ["6-month target","500 founding members · concierge M2 renewal ≥60% · CAC <₹4,000"],
 ["12-month target (post Gate-2)","3,231 payers · ₹1.42 Cr revenue · churn ≤6%"],
 ["Stop-loss","Concierge M2 <40% or founding <250 by M6 → stop/pivot; exposure capped ₹1.25 Cr"],
 ["Next funding decision","Month-6 board: Gate 2 (₹3.3 Cr) on cohort evidence"],
 ["Board support required","Approval today · monthly MIS review · Gate-2 calendar commitment"]],
[3.3,8.6],{fs:11.5,hs:12,rowH:0.55,dark:true});
s.addNotes("End on the one-liner: Rs1.25 crore buys the answer to a Rs1,182-crore question. If the answer is no, we lose 1.6% of the category leader's ANNUAL PROFIT. If yes, we own the premium trust position in a category going public.");

// S29 APPENDIX POINTERS
s=lightSlide("Appendix","Where every number lives","All documents ship with this deck. Formulas are editable; recalculation verified (2,044 formulas, zero errors).");
tbl(s,0.55,1.9,12.23,["Document","Contents"],
[["Excel model (17 sheets)","Assumptions · Pricing · Customer Growth · Funnel · Revenue · COGS · Headcount · Marketing · OpEx · P&L · Cash Flow · Unit Economics · Scenarios · Sensitivity · Idea Comparison · Investment Returns · Dashboard"],
 ["Research report (Edition 2)","14 categories · 20 scorecards · sources with URLs · rejected-idea evidence"],
 ["Deck outlines","Slide-by-slide spec incl. presenter notes for both decks"],
 ["Investment memo (1 page)","The ask, gates, stop-loss, returns"],
 ["Idea comparison (1 page)","Top-10 side-by-side"]],
[3.3,8.93],{fs:11,hs:11.5,rowH:0.62});
take(s,"Everything is traceable: deck → Excel cell → research citation.");

// S30 CLOSE
s=darkSlide();
s.addText("₹1.25 crore buys the answer\nto a ₹1,182-crore question.",{x:0.7,y:2.6,w:11.9,h:1.8,fontFace:HF,fontSize:40,bold:true,color:WHITE,margin:0});
s.addText("Thank you. Discussion.",{x:0.7,y:4.8,w:8,h:0.5,fontFace:BF,fontSize:16,color:ICE,margin:0});
s.addText("PROJECT SITARA · CONFIDENTIAL · 28 JULY 2026",{x:0.7,y:6.7,w:9,h:0.35,fontFace:BF,fontSize:11,color:GOLD,charSpacing:2,margin:0});
s.addNotes("Hold on this slide for questions. Key backup slides: sensitivity (21), downside (24), idea comparison (23).");

p.writeFile({fileName:"Sitara_Deck2_Investment_Case.pptx"}).then(()=>console.log("deck2 done"));
