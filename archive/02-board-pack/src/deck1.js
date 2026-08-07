const pptxgen = require("pptxgenjs");
const p = new pptxgen();
p.layout = "LAYOUT_WIDE"; // 13.33 x 7.5
const NAVY="1E2761", ICE="CADCFC", GOLD="C9A227", INK="22263B", MUT="6B7086", WHITE="FFFFFF", LIGHT="F4F6FC", GOOD="1A7F5C", BAD="B03A48";
const HF="Cambria", BF="Calibri";
const W=13.33, H=7.5;

function darkSlide(){ const s=p.addSlide(); s.background={color:NAVY}; return s; }
function lightSlide(kicker, title, note){
  const s=p.addSlide(); s.background={color:WHITE};
  if(kicker) s.addText(kicker.toUpperCase(), {x:0.55,y:0.32,w:9,h:0.3,fontFace:BF,fontSize:11,color:GOLD,bold:true,charSpacing:2,margin:0});
  s.addText(title, {x:0.55,y:0.58,w:12.2,h:0.85,fontFace:HF,fontSize:30,color:NAVY,bold:true,margin:0});
  if(note) s.addNotes(note);
  return s;
}
function card(s,x,y,w,h,opts={}){
  s.addShape("roundRect",{x,y,w,h,rectRadius:0.07,fill:{color:opts.fill||LIGHT},line:{color:opts.line||"E3E6F2",width:0.75},shadow:{type:"outer",color:"9AA0B8",opacity:0.25,blur:6,offset:2,angle:90}});
}
function stat(s,x,y,w,big,label,color){
  card(s,x,y,w,1.5);
  s.addText(big,{x:x+0.12,y:y+0.12,w:w-0.24,h:0.75,fontFace:HF,fontSize:27,bold:true,color:color||NAVY,margin:0});
  s.addText(label,{x:x+0.12,y:y+0.86,w:w-0.24,h:0.58,fontFace:BF,fontSize:10.5,color:MUT,margin:0});
}
function take(s,text){
  s.addShape("roundRect",{x:0.55,y:6.75,w:12.23,h:0.52,rectRadius:0.06,fill:{color:NAVY}});
  s.addText([{text:"TAKEAWAY   ",options:{bold:true,color:GOLD,fontSize:10.5}},{text:text,options:{color:WHITE,fontSize:12}}],{x:0.75,y:6.75,w:11.9,h:0.52,fontFace:BF,valign:"middle",margin:0});
}
function bullets(s,x,y,w,h,items,size){
  s.addText(items.map((t,i)=>({text:t,options:{bullet:{code:"2022",indent:14},breakLine:i<items.length-1,paraSpaceAfter:8}})),{x,y,w,h,fontFace:BF,fontSize:size||13,color:INK,valign:"top",margin:0});
}

// ---------- S1 COVER ----------
let s=darkSlide();
s.addText("CONFIDENTIAL — BOARD PRESENTATION",{x:0.7,y:0.5,w:6,h:0.3,fontFace:BF,fontSize:11,color:ICE,charSpacing:3,margin:0});
s.addText("The Reassurance Economy",{x:0.7,y:2.1,w:11.9,h:1.1,fontFace:HF,fontSize:48,bold:true,color:WHITE,margin:0});
s.addText("Building India's first trust-first AI life-guidance subscription — from 14 researched categories to one decisive recommendation.",{x:0.7,y:3.3,w:10.5,h:0.9,fontFace:BF,fontSize:18,color:ICE,margin:0});
s.addText("PROJECT SITARA",{x:0.7,y:4.6,w:6,h:0.4,fontFace:BF,fontSize:15,bold:true,color:GOLD,charSpacing:3,margin:0});
s.addText("Deck 1 of 2 — Business Idea & Board Conviction  ·  28 July 2026",{x:0.7,y:6.6,w:9,h:0.35,fontFace:BF,fontSize:12,color:ICE,margin:0});
s.addNotes("Two research phases, 21 parallel workstreams, ~670 sources examined. Today's ask is a validation decision, not a scale decision. Companion documents: Deck 2 (financials), Excel model, research report Edition 2.");

// ---------- S2 DECISION ----------
s=lightSlide("The ask","The decision we need to make","We frame the ask upfront so the board evaluates everything that follows against a specific, capped decision. We are NOT asking for scale capital today. Stop-loss defined on the final slide.");
const dec=[["What we are considering","Entry into high-value AI subscriptions for affluent Indians & NRIs — a two-phase research programme has narrowed 14 categories and 20 scored ideas to one winner."],
["What we ask today","Approve Scenario A: ₹1.25 crore to validate demand and build v1 of Project Sitara, with a defined Gate at month 6 and a hard stop-loss."],
["What we are NOT asking","Launch or scale capital (₹3.3 Cr Gate-2 and ₹3.3 Cr Gate-3 tranches) — those require cohort evidence and return to this board."]];
dec.forEach((d,i)=>{ card(s,0.55+i*4.16,1.8,3.95,3.3); 
 s.addText(d[0],{x:0.75+i*4.16,y:2.0,w:3.55,h:0.6,fontFace:HF,fontSize:15,bold:true,color:NAVY,margin:0});
 s.addText(d[1],{x:0.75+i*4.16,y:2.7,w:3.55,h:2.2,fontFace:BF,fontSize:12.5,color:INK,margin:0});});
s.addText("Maximum downside of today's approval: ₹1.25 crore.",{x:0.55,y:5.5,w:12,h:0.5,fontFace:HF,fontSize:16,bold:true,color:GOLD,margin:0});
take(s,"A capped, gated bet — sized to buy certainty, not to bet the company.");

// ---------- S3 EXEC SUMMARY ----------
s=lightSlide("Executive summary","Proven spending. An unclaimed premium niche. One winner.","All figures from the attached bottom-up model, base case. AstroTalk figures are audited/press-verified facts (Entrackr). Break-even = first EBITDA-positive month.");
stat(s,0.55,1.7,2.98,"₹1,182 Cr","AstroTalk FY25 revenue — 80% from repeat customers (FACT)");
stat(s,3.63,1.7,2.98,"10x","NRI vs India ARPU, Sri Mandir devotional (FACT)");
stat(s,6.71,1.7,2.98,"4.6 vs 4.3","AI astrologers out-rate humans, at ~90% margins (FACT)");
stat(s,9.79,1.7,2.98,"8.1 / 10","Sitara — top score across all 20 ideas, both phases");
const es=[["Top three","Sitara 8.1 · Sahay 8.0 · KalaOS 7.6 — winner: Sitara, the trust-first AI Vedic life-planning companion"],
["Initial investment","₹1.25 Cr (validate + build v1); staged plan ₹7.85 Cr peak across 36 months"],
["Financial path (base)","Revenue ₹1.42 Cr → ₹6.34 Cr → ₹12.16 Cr; EBITDA-positive month 30; exit ARR ≈ ₹14.8 Cr"],
["Immediate next step","8-week concierge validation — 50 paying users, month-2 renewal ≥60% is the gate"]];
es.forEach((d,i)=>{ const x=0.55+(i%2)*6.24, y=3.55+Math.floor(i/2)*1.45; card(s,x,y,6.04,1.3);
 s.addText(d[0],{x:x+0.2,y:y+0.12,w:2.3,h:1.05,fontFace:BF,fontSize:12,bold:true,color:NAVY,margin:0});
 s.addText(d[1],{x:x+2.5,y:y+0.12,w:3.4,h:1.05,fontFace:BF,fontSize:11,color:INK,margin:0});});
take(s,"Decision-ready: evidence, winner, price of certainty and path are all on the table.");

// ---------- S4 WHY NOW ----------
s=lightSlide("Why now","Four shifts converged in the last 24 months","AI credibility: AstroSage 2025 data. Subscriptions: Ormax OTT paid base. Wealth: MEA, World Bank, Goldman Sachs. Category heat: AstroTalk IPO reporting. The window is visible to everyone after the IPO — moving first matters.");
const wn=[["AI crossed the credibility line","AI astrologers rated 4.6 vs 4.3 for humans at ~90% gross margins (AstroSage, 2025). Voice AI in Indian languages matured this year."],
["Subscription comfort is here","India: ~119–148M paid OTT subscriptions. NRIs already live in the $10–25/month consumer band (Calm, Pattern, Joy)."],
["The diaspora wallet is at a peak","35.4M diaspora · $129.4B remittances (2024, record) · Indian-Americans = highest-earning US ethnic group (~$150K median)."],
["Category heat is arriving","AstroTalk IPO-bound (~₹12,500 Cr valuation talk). International revenue grew 4.2x — with no premium product serving it."]];
wn.forEach((d,i)=>{ const x=0.55+(i%2)*6.24, y=1.8+Math.floor(i/2)*2.3; card(s,x,y,6.04,2.1);
 s.addText(d[0],{x:x+0.22,y:y+0.16,w:5.6,h:0.5,fontFace:HF,fontSize:15,bold:true,color:NAVY,margin:0});
 s.addText(d[1],{x:x+0.22,y:y+0.72,w:5.6,h:1.3,fontFace:BF,fontSize:12,color:INK,margin:0});});
take(s,"Every input the winner needs — payer, product tech, and proof of category — matured simultaneously.");

// ---------- S5 TARGET CUSTOMER ----------
s=lightSlide("Who pays","Hard-currency income, Indian-heart spending","Segment WTP bands are documented spend (pricing pages, filings) not aspirations. Full 12-segment ranking is in the research report Part 1.");
const segs=[["NRI women 27–45","US/UK/Canada/Gulf · $120–400K HH","Timing & reassurance for life decisions","$13–25 / mo"],
["NRI children of ageing parents","32–55 · dollar income, parents in India","Parent safety, guilt relief","$49–299 / mo"],
["Affluent metro Indian women","25–45 · ₹15L+ HH income","Reassurance + self-growth","₹300–2,000 / mo"],
["Devout diaspora families","35–60 · US/UK/Gulf","Rituals never lapse","~$81 / yr proven"]];
segs.forEach((d,i)=>{ const y=1.85+i*1.22; card(s,0.55,y,12.23,1.08);
 s.addText(d[0],{x:0.75,y:y+0.1,w:3.1,h:0.9,fontFace:HF,fontSize:14,bold:true,color:NAVY,valign:"middle",margin:0});
 s.addText(d[1],{x:3.9,y:y+0.1,w:3.6,h:0.9,fontFace:BF,fontSize:11.5,color:MUT,valign:"middle",margin:0});
 s.addText(d[2],{x:7.55,y:y+0.1,w:3.1,h:0.9,fontFace:BF,fontSize:11.5,color:INK,valign:"middle",margin:0});
 s.addText(d[3],{x:10.7,y:y+0.1,w:1.9,h:0.9,fontFace:HF,fontSize:14,bold:true,color:GOLD,valign:"middle",margin:0});});
take(s,"The payer is the diaspora wallet; India's affluent are the second market, priced separately.");

// ---------- S6 EXISTING SPEND ----------
s=lightSlide("Existing spend","We reorganise existing spending — we don't invent it","Every band is a documented price from provider pages or filings (report Parts 1 & 8). Chart shows monthly-equivalent midpoints, ₹ thousands.");
s.addChart(p.ChartType.bar,[{name:"Monthly-equivalent spend (₹ '000)",labels:["Eldercare (NRI)","Exec coaching","Therapy (2/mo)","Tutoring (NRI)","Astrology (repeat)","Nutrition plans","Premium apps"],values:[14,40,5,11,2.5,6.5,0.55]}],
{x:0.55,y:1.8,w:7.6,h:4.6,barDir:"bar",chartColors:[NAVY],showValue:true,dataLabelPosition:"outEnd",dataLabelColor:MUT,dataLabelFontSize:10,valAxisHidden:false,catAxisLabelColor:INK,valAxisLabelColor:MUT,valGridLine:{color:"E7E9F4",size:0.5},catGridLine:{style:"none"},showLegend:false,showTitle:false});
bullets(s,8.5,2.0,4.2,4.2,["Astrologers: ₹500–1,500 per session — repeated (80% repeat revenue at the leader)","Weddings: ₹39.5 lakh average budget (WedMeGood 2025)","Pujas: $10–100+ per ritual for NRIs","Parenting coaches: $40–200 per session","Our ask — ₹499–999/mo (India), $13–25/mo (NRI) — sits below one existing transaction per month"],12);
take(s,"The subscription re-routes money already flowing to worse, episodic alternatives.");

// ---------- S7 CUSTOMER PROBLEM ----------
s=lightSlide("The problem","In their own words","Verbatims from Trustpilot, App Store reviews, Blind and the SproutsNews investigation — collected in the research report. The underlying need is anxiety regulation and decision confidence, which is why repeat rates are extreme.");
const quotes=[["“I paid ₹500 for a reading and got generic advice I could find online.”","AstroTalk user, SproutsNews investigation"],
["“They told me my bad luck could only be removed by a ₹15,000 puja.”","Fear-based upselling — documented pattern"],
["“Every astrologer tells me something different — none of them remembers me.”","Category synthesis — no continuity anywhere"],
["“This is the tax of living abroad.”","NRI on Blind — eldercare guilt"],
["“No proof the puja was performed.”","#1 App Store complaint, devotional category"],
["“My daughter understands Hindi but answers in English.”","Diaspora parent, Blind"]];
quotes.forEach((q,i)=>{ const x=0.55+(i%3)*4.16, y=1.85+Math.floor(i/3)*2.3; card(s,x,y,3.96,2.1,{fill:LIGHT});
 s.addText(q[0],{x:x+0.2,y:y+0.15,w:3.56,h:1.35,fontFace:HF,fontSize:12.5,italic:true,color:INK,margin:0});
 s.addText(q[1],{x:x+0.2,y:y+1.55,w:3.56,h:0.45,fontFace:BF,fontSize:9.5,color:MUT,margin:0});});
take(s,"Recurring anxiety, met today by transactional, memory-less, sometimes predatory solutions.");

// ---------- S8 WHY SOLUTIONS FAIL ----------
s=lightSlide("The gap","Why existing solutions fail","The four failures define our product requirements: continuity, trust, ethics, and proactive cadence. Trustpilot 3.3/5 for the category leader; Nebula's $9.99/week dark-funnel complaints documented.");
const fails=[["Episodic by design","Per-minute meters reward stalling; every consult starts from zero. No player maintains a life-context memory."],
["Trust deficit","Fake-review allegations, fear-upsells to ₹15,000 remedies, 3.3/5 Trustpilot at the leader. Western apps run dark-pattern auto-renew funnels."],
["No premium NRI product","International revenue grew 4.2x at the leader with zero dedicated product. Diaspora pays 10x in the adjacent devotional category."],
["Free tools can't be trusted","ChatGPT reads a chart once: no verified computation, no memory, no humans, no accountability — and users know it."]];
fails.forEach((d,i)=>{ const x=0.55+(i%2)*6.24, y=1.85+Math.floor(i/2)*2.25; card(s,x,y,6.04,2.05);
 s.addText(d[0],{x:x+0.22,y:y+0.15,w:5.6,h:0.5,fontFace:HF,fontSize:15,bold:true,color:BAD,margin:0});
 s.addText(d[1],{x:x+0.22,y:y+0.7,w:5.6,h:1.25,fontFace:BF,fontSize:12,color:INK,margin:0});});
take(s,"The gap is trust + continuity — not information. That is buildable and defensible.");

// ---------- S9 AI ECONOMICS ----------
s=lightSlide("Why AI","AI turns a per-minute human business into a ~79% gross-margin subscription","Cost per interaction: human astrologers ₹20–139/min vs AI < ₹1. AstroSage proves quality AND margin. Humans move up the value chain to high-stakes moments; deterministic astronomy is computed, never generated — that kills the hallucination risk where it matters most.");
s.addChart(p.ChartType.bar,[{name:"Cost per guidance interaction (₹)",labels:["Human astrologer (per 10-min)","Sitara AI (per session)"],values:[750,8]}],
{x:0.55,y:1.9,w:5.6,h:3.1,barDir:"bar",chartColors:[MUT,NAVY],showValue:true,dataLabelPosition:"outEnd",dataLabelFontSize:11,showLegend:false,showTitle:false,catAxisLabelColor:INK,valAxisLabelColor:MUT,valGridLine:{color:"E7E9F4",size:0.5},catGridLine:{style:"none"}});
bullets(s,6.6,1.95,6.1,3.3,["Personalisation at scale: every brief computed from the user's actual chart + life log","24×7 across time zones — the NRI killer feature","Voice + Hinglish/Hindi; proactive transit & festival alerts","What AI cannot do alone: high-stakes trust moments (verified human escalation), ethics enforcement, deterministic Vedic computation (licensed ephemeris engine)"],12.5);
card(s,0.55,5.35,12.23,1.1,{fill:"EAF3EE",line:"CBE3D6"});
s.addText([{text:"Proof, not promise:  ",options:{bold:true,color:GOOD}},{text:"AstroSage's AI astrologers answer 250M+ questions, rated 4.6 vs 4.3 for its humans, at ~90% margins (Business Standard/ANI, 2025).",options:{color:INK}}],{x:0.8,y:5.35,w:11.7,h:1.1,fontFace:BF,fontSize:12.5,valign:"middle",margin:0});
take(s,"The economics flipped: humans become the premium layer, not the cost base.");

// ---------- S10 OPPORTUNITY UNIVERSE ----------
s=lightSlide("The universe","14 categories · 20 scored ideas · one map","Bubble position = theme; every idea scored on the same weighted model. Greyed = rejected on evidence (novelty collapse, frequency math, regulation, one-time shape). Full scorecards in report Parts 3 & 9.");
const themes=[["Spirituality & culture","Sitara 8.1 · DharmaSetu 7.4",NAVY,WHITE],["Family & care","Sahay 8.0 · Palna 6.6 · Bolo 6.9",NAVY,WHITE],
["Memory & celebrations","Smriti 7.1 · Dhara 5.3 · Photoshoots 4.4 · Celebrations 4.6 · Kitty 3.7","8B8FD9",WHITE],
["Wellness & companionship","Saathi 6.4 · Mann-ki-Baat 4.9","8B8FD9",WHITE],
["Pro & business content","KalaOS 7.6 · VyaparLens 6.4 · Brand Studio 5.8","8B8FD9",WHITE],
["Lifestyle & home","IndiaDesk 6.3 · YatraOS 5.6 · Shikhar 5.4 · GharShanti 4.2","C3C5D6",INK]];
themes.forEach((t,i)=>{ const x=0.55+(i%3)*4.16, y=1.9+Math.floor(i/3)*2.35; 
 s.addShape("roundRect",{x,y,w:3.96,h:2.15,rectRadius:0.09,fill:{color:t[2]}});
 s.addText(t[0],{x:x+0.2,y:y+0.15,w:3.56,h:0.5,fontFace:HF,fontSize:14.5,bold:true,color:t[3],margin:0});
 s.addText(t[1],{x:x+0.2,y:y+0.75,w:3.56,h:1.25,fontFace:BF,fontSize:11.5,color:t[3],margin:0});});
take(s,"Breadth was examined; rigour did the choosing. Darker = where the winners live.");

// ---------- S11 EVALUATION ----------
s=lightSlide("Method","How we evaluated: one weighted model, four kill-rules","Weights favour what makes subscriptions durable: WTP and retention 1.5x, AI advantage / market / subscription-fit 1.25x. Kill-rules ejected 10 ideas regardless of charm. This is why the board can trust the ranking.");
s.addChart(p.ChartType.doughnut,[{name:"Weights",labels:["Willingness to pay (1.5x)","Retention (1.5x)","AI advantage (1.25x)","Market size (1.25x)","Subscription fit (1.25x)","Urgency/Acq/Scale/Defens (1.0x)","Ops/Trust/Founder (0.75x)"],values:[1.5,1.5,1.25,1.25,1.25,4,2.25]}],
{x:0.4,y:1.9,w:5.6,h:4.4,chartColors:[NAVY,"3B3F8F","5A5FD4","8B8FD9","ADB1E6","C9CCEE","E0E2F5"],showLegend:true,legendPos:"r",legendFontSize:10,showValue:false,showTitle:false,holeSize:60});
bullets(s,6.5,2.0,6.2,4.2,["Kill-rule 1 — Replaceable by free ChatGPT: information-only ideas die (Woebot shut down citing exactly this)","Kill-rule 2 — One-time purchase shape: Vastu, photoshoots, weddings-B2C (Lensa: −98% from peak month)","Kill-rule 3 — Payer ≠ user without a channel: standalone companionship (Papa's payer collapse)","Kill-rule 4 — Regulatory minefield: kitty/tambola platforms (2025 Online Gaming Act killed the closest analogue)"],12.5);
take(s,"Same yardstick for every idea — no pet ideas survived it.");

// ---------- S12 FULL RANKING ----------
s=lightSlide("The ranking","Twenty ideas, honestly scored","Read bottom-up in the meeting: the rejections build credibility before the winner appears. Scores are weighted composites; full 24-32 point scorecards exist for each.");
const ranks=[["1. Sitara — AI Vedic life-planning",8.1,NAVY],["2. Sahay — NRI parent-care",8.0,NAVY],["3. KalaOS — wedding studio OS (NEW)",7.6,"3B3F8F"],
["4. DharmaSetu — devotional concierge",7.4,"5A5FD4"],["5. Smriti — family memory (NEW)",7.1,"5A5FD4"],["6. Bolo — Hindi for diaspora kids",6.9,"8B8FD9"],
["7. Palna — desi parenting",6.6,"8B8FD9"],["8. Saathi — cultural wellness",6.4,"8B8FD9"],["9. VyaparLens — product photos (NEW)",6.4,"8B8FD9"],
["10. IndiaDesk — NRI admin",6.3,"8B8FD9"]];
ranks.forEach((r,i)=>{ const y=1.75+i*0.47;
 s.addText(r[0],{x:0.55,y,w:4.6,h:0.42,fontFace:BF,fontSize:11.5,color:INK,valign:"middle",margin:0});
 s.addShape("roundRect",{x:5.3,y:y+0.06,w:r[1]/10*6.2,h:0.3,rectRadius:0.04,fill:{color:r[2]}});
 s.addText(String(r[1]),{x:5.35+r[1]/10*6.2,y,w:0.8,h:0.42,fontFace:BF,fontSize:11,bold:true,color:NAVY,valign:"middle",margin:0});});
s.addText("Below the cut (rejected on evidence): Brand Studio 5.8 · YatraOS 5.6 · Shikhar 5.4 · Dhara 5.3 · Companion 4.9 · Celebration concierge 4.6 · AI photoshoots 4.4 · Event studio 4.3 · Vastu 4.2 · Kitty platform 3.7",
 {x:0.55,y:6.35,w:12.2,h:0.4,fontFace:BF,fontSize:10.5,color:MUT,margin:0});
take(s,"Two research phases, one scoring model — the top three are clear and close.");

// ---------- S13 REJECTED TIER ----------
s=lightSlide("Discipline","What we will NOT build — and the evidence that spared us","Each rejection preserved capital. These stats are the strongest slides in diligence — they show the process kills attractive-sounding ideas.");
const rej=[["Consumer AI photoshoots","Lensa: ₹276 Cr revenue in one month, then −98%. Free Gemini served India's whole demand for ~₹85L total."],
["Celebrations, birthdays, kitty","1–3 events/family/yr fails subscription math. Evite ≈ $26M after 25 years. Gaming Act 2025 killed the kitty analogue."],
["Vastu / interior","Zero consumer Vastu subscriptions exist anywhere — revealed market wisdom. Per-property pricing only."],
["Standalone companionship","The lonely person never pays (Khyaal ₹999/yr). Payer channels are fragile (Papa lost ~36 payers in one cycle). Safety minefield."],
["Travel concierge","Every scaled AI planner is free/affiliate. 'A $500 travel agent for free' is the consumer's mental model."],
["Personal-brand studio","Quarterly cadence at best; PhotoAI's own founder logs 'MRR down, churn up.'"]];
rej.forEach((d,i)=>{ const x=0.55+(i%3)*4.16, y=1.85+Math.floor(i/3)*2.3; card(s,x,y,3.96,2.1,{fill:"F7F1F1",line:"E7D5D5"});
 s.addText(d[0],{x:x+0.2,y:y+0.13,w:3.56,h:0.5,fontFace:HF,fontSize:13.5,bold:true,color:BAD,margin:0});
 s.addText(d[1],{x:x+0.2,y:y+0.66,w:3.56,h:1.35,fontFace:BF,fontSize:10.5,color:INK,margin:0});});
take(s,"Saying no with evidence is the cheapest capital protection we have.");

// ---------- S14 CONTENDERS 10-7 ----------
s=lightSlide("Contenders","Ranks #10–7: real businesses, not board-scale winners","One minute each in the meeting. Each is viable for the right founder; none combines our required scale + subscription physics + ops profile.");
const c47=[["#10 IndiaDesk 6.3","NRI India-affairs concierge","₹29–249/mo eq.","Asset-anchored retention is superb; ops sprawl across tax/property/legal is the trap."],
["#9 VyaparLens 6.4","AI product photography for Indian SMBs","Per-outcome","Dresma proves ₹90 Cr-scale demand — as a services business. Sellers openly prefer 'no subscription.'"],
["#8 Saathi 6.4","Culturally-fluent emotional wellness","$120–350/mo","Real WTP at BetterHelp prices; human-hours cap margin at 35–45%; cross-border licensing complexity."],
["#7 Palna 6.6","Desi parenting companion","$12–15/mo","Joy validated the model ($14M Series A); thinnest moat — parents love free ChatGPT for exactly this."]];
c47.forEach((d,i)=>{ const x=0.55+(i%2)*6.24, y=1.85+Math.floor(i/2)*2.3; card(s,x,y,6.04,2.1);
 s.addText([{text:d[0]+"  ",options:{bold:true,color:NAVY,fontSize:14}},{text:"— "+d[1],options:{color:MUT,fontSize:11.5}}],{x:x+0.22,y:y+0.13,w:5.6,h:0.55,fontFace:BF,margin:0});
 s.addText("Price: "+d[2],{x:x+0.22,y:y+0.68,w:5.6,h:0.35,fontFace:BF,fontSize:11,bold:true,color:GOLD,margin:0});
 s.addText(d[3],{x:x+0.22,y:y+1.05,w:5.6,h:1.0,fontFace:BF,fontSize:11,color:INK,margin:0});});
take(s,"All four could exist; none is the best first use of this board's capital.");

// ---------- S15 CONTENDERS 6-5 ----------
s=lightSlide("Contenders","Ranks #6–5: strong niches, capped by retention physics","Bolo: the child is not the buyer — kids' novelty decay is the category graveyard. Smriti: the FamilyAlbum 30M proof is real, but every memory subscription ages out at years 3-5 as documentation collapses.");
const c56=[["#6 Bolo 6.9","Voice-first Hindi & heritage AI for diaspora kids 4–12","$20–49/mo","Proven tutoring WTP ($80–130/mo committed families); unclaimed conversation-practice gap; voice AI advantage is real.","Kids' churn: heritage motivation belongs to the parent. No breakout incumbent in 10 years — a warning as much as an invitation."],
["#5 Smriti 7.1 (NEW)","NRI family memory: AI-curated feed + printed albums to grandparents in India","$9–17/mo","FamilyAlbum: 30M users on the grandparent hook. Chatbooks: a decade of print subscriptions. Privacy fear is a tailwind.","Aging-out churn (0–5 window) caps LTV; Google Photos free gravity; FamilyAlbum could localise."]];
c56.forEach((d,i)=>{ const y=1.85+i*2.45; card(s,0.55,y,12.23,2.25);
 s.addText(d[0]+" — "+d[1],{x:0.78,y:y+0.13,w:8.6,h:0.5,fontFace:HF,fontSize:14.5,bold:true,color:NAVY,margin:0});
 s.addText("Price: "+d[2],{x:9.9,y:y+0.13,w:2.6,h:0.5,fontFace:BF,fontSize:12,bold:true,color:GOLD,margin:0});
 s.addText([{text:"For: ",options:{bold:true,color:GOOD}},{text:d[3],options:{color:INK}}],{x:0.78,y:y+0.72,w:11.6,h:0.7,fontFace:BF,fontSize:11.5,margin:0});
 s.addText([{text:"Against: ",options:{bold:true,color:BAD}},{text:d[4],options:{color:INK}}],{x:0.78,y:y+1.45,w:11.6,h:0.7,fontFace:BF,fontSize:11.5,margin:0});});
take(s,"Both are fundable niches — but their churn physics rank them below the top four.");

// ---------- S16 CONTENDER 4 ----------
s=lightSlide("Contender","#4 DharmaSetu 7.4 — the clearest WTP signal in the corpus","The 10x ARPU fact is the single most striking datapoint of the research. But three blockers keep it out of the top three — and it survives as the winner's Phase-4 cross-sell module (rituals attached to guidance moments).");
stat(s,0.55,1.85,3.9,"10x","NRI vs domestic devotional ARPU (₹7,000 vs ₹600–800) — Sri Mandir, FACT");
stat(s,4.6,1.85,3.9,"55%","6-month retention at category leader");
stat(s,8.65,1.85,3.9,"₹1/day","The only subscription pilot in the category — never scaled");
bullets(s,0.55,3.7,12.2,2.6,["What it is: family ritual calendar (tithis, shraddh, festivals) + verified, video-documented pujas via vetted priests — membership $10–17/mo + per-event fulfilment","Why not top-three: subscription conversion doubly unproven; fulfilment ops (priest network, video proof, festival surges); fraud-scarred category taxes every entrant; Sri Mandir ($20M Series C, 20% revenue already NRI) can build it fastest","Where it lives in our plan: Phase-4 module inside the winner — rituals cross-sell attached to guidance moments (AstroTalk's own e-commerce arm runs ₹200 Cr ARR on this attach)"],12.5);
take(s,"Not a loser — a module. The winner absorbs its best economics without its fulfilment risk.");

// ---------- S17 TOP THREE ----------
s=lightSlide("Top three","Three fundable ideas — one best first bet","All three clear every bar. The decision is sequencing risk: Sitara is the fastest, cheapest certainty with the largest consumer upside. 3-yr revenue ranges from the idea-comparison model (Deck 2, Excel).");
const t3=[["Sitara 8.1","NRI + affluent Indian women","Reassurance & timing","₹499–999 / $13–25 mo","79%","3/10 (lightest)","₹11–17 Cr","Subscription conversion unproven"],
["Sahay 8.0","NRI children of ageing parents","Parent safety, guilt relief","$49–299 mo","65/40% by tier","6.5/10","₹16–22 Cr","Ops gravity + emergency liability"],
["KalaOS 7.6","Indian wedding studios (B2B)","Post-production bottleneck","₹2,000–10,000 mo","65–72%","7.5/10 light B2B","₹9–12 Cr","Race vs funded Indian incumbent"]];
const hdrs=["","Customer","Core need","Price","Gross margin","Ops complexity","3-yr revenue","Key risk"];
hdrs.forEach((h,i)=>{ s.addText(h,{x:0.55+ (i===0?0:2.1+(i-1)*1.53), y:1.8,w:i===0?2.0:1.5,h:0.5,fontFace:BF,fontSize:9.5,bold:true,color:MUT,margin:0}); });
t3.forEach((r,ri)=>{ const y=2.35+ri*1.5; card(s,0.55,y,12.23,1.35,{fill:ri===0?"EEF2E6":LIGHT});
 s.addText(r[0],{x:0.72,y:y+0.1,w:1.9,h:1.15,fontFace:HF,fontSize:14,bold:true,color:ri===0?GOOD:NAVY,valign:"middle",margin:0});
 r.slice(1).forEach((v,ci)=>{ s.addText(v,{x:2.65+ci*1.53,y:y+0.08,w:1.46,h:1.2,fontFace:BF,fontSize:9.3,color:INK,valign:"middle",margin:0});});});
take(s,"Sitara first; Sahay is the natural second product on the same family graph; KalaOS is the safest pivot.");

// ---------- S18 TOP IDEA 3 KALAOS ----------
s=lightSlide("Top idea #3","KalaOS — the best-proven economics, the smallest dream","Every layer of WTP proven by profitable companies. If consumer validation fails, this is the disciplined pivot: same AI-product skills, B2B buyer whose income depends on the tool.");
bullets(s,0.55,1.85,6.2,4.4,["What: India-priced AI OS for wedding studios — culling 10,000-image events, style-learned editing, album design, face-recognition guest delivery — ₹1,999–9,999/mo","Proof stack: Imagen AI $10M ARR profitable in 2.5 yrs · Aftershoot 188K photographers · HoneyBook $140M ARR · 24% of Indian wedding vendors already use AI (WedMeGood 2025)","Why not first: India software TAM ₹450–1,350 Cr est. (smaller ceiling), head-on race vs an Indian-founded global incumbent, and a B2B-tools brand is not the consumer platform this thesis targets","When to revisit: as the disciplined pivot if Gate-1 fails, or a Year-3 B2B2C adjacency (studios feeding family archives)"],12);
const ks=[["$10M ARR","Imagen — profitable at 2.5 yrs"],["188K","photographers on Aftershoot"],["₹75K–5L","Indian wedding photo spend per event"],["~M24","modelled break-even (earliest of top 3)"]];
ks.forEach((d,i)=>{ stat(s,7.1+(i%2)*3.05,1.95+Math.floor(i/2)*1.7,2.9,d[0],d[1]);});
take(s,"Keep it warm: the safest economics in the corpus, one decision away.");

// ---------- S19 TOP IDEA 2 SAHAY ----------
s=lightSlide("Top idea #2","Sahay — the bigger company, the harder company","Phase-2 research de-risked its central unknown: elders DO engage daily with proactive voice companions, for months. But ops weight and emergency liability fail our 'scale without heavy human dependence' condition. It is the natural second product — same buyer, same family graph.");
bullets(s,0.55,1.85,6.2,4.4,["What: voice-AI daily check-in calls (Hindi/regional) to parents in India + family dashboard + verified on-ground partners — $49–299/mo, paid by the NRI child","New evidence: ElliQ elders average 30–40 interactions/day sustained 7+ months; families already pay $15–40/mo for AI calls (inTouch, Meela); IamFine has charged $14.99/mo for a decade","Blockers: ops 6.5/10 at the tiers that deliver peace of mind; funded incumbents (Emoha ₹85 Cr, Samarth); one mishandled emergency is existential","Sequencing: launch as product #2 on the same NRI family graph — with Dhara life-story recording and Smriti albums as its emotional layer (endorsed Combination 6)"],12);
const ss2=[["30–40/day","ElliQ interactions, sustained 7+ months"],["$15–40/mo","proven family-paid AI-call band"],["₹11–17K/mo","incumbent human-only pricing (Samarth)"],["#1","most intense pain in the whole corpus"]];
ss2.forEach((d,i)=>{ stat(s,7.1+(i%2)*3.05,1.95+Math.floor(i/2)*1.7,2.9,d[0],d[1]);});
take(s,"Sahay is where this company goes next — after Sitara proves the engine.");

// ---------- S20 WINNER ----------
s=darkSlide();
s.addText("THE WINNER",{x:0.7,y:0.7,w:6,h:0.4,fontFace:BF,fontSize:13,color:GOLD,charSpacing:3,bold:true,margin:0});
s.addText("Sitara",{x:0.7,y:1.15,w:8,h:1.0,fontFace:HF,fontSize:54,bold:true,color:WHITE,margin:0});
s.addText("A trust-first AI Vedic life-planning companion. It knows your chart, your family and your life story; gives a daily 60-second timing brief; explains its reasoning; and puts a verified human astrologer one tap away — with no fear-selling, ever.",
 {x:0.7,y:2.35,w:11.9,h:1.0,fontFace:BF,fontSize:16,color:ICE,margin:0});
const wstats=[["₹1,182 Cr","proven category revenue, 80% repeat (AstroTalk FY25)"],["4.6 vs 4.3","AI beats human astrologers at ~90% margins (AstroSage)"],["4.2x","international growth, no premium product serving it"],["3/10","operational complexity — lightest of any finalist"],["8.1/10","top weighted score across all 20 ideas"]];
wstats.forEach((d,i)=>{ const x=0.7+i*2.44;
 s.addShape("roundRect",{x,y:3.75,w:2.3,h:1.9,rectRadius:0.08,fill:{color:"2A2F63"}});
 s.addText(d[0],{x:x+0.12,y:3.9,w:2.06,h:0.6,fontFace:HF,fontSize:19,bold:true,color:GOLD,margin:0});
 s.addText(d[1],{x:x+0.12,y:4.5,w:2.06,h:1.05,fontFace:BF,fontSize:9.5,color:ICE,margin:0});});
s.addText("Pricing: $99–199/yr NRI  ·  ₹3,999–7,999/yr India   |   The one unproven leap — episodic spend → subscription — is exactly what the ₹1.25 Cr validation buys.",
 {x:0.7,y:6.1,w:12,h:0.7,fontFace:BF,fontSize:13,color:WHITE,margin:0});
s.addNotes("Winner on the weighted model, not on any single dimension. It sells recurring reassurance — the one consumer emotion with documented 80% repeat behaviour — not novelty (which the Lensa curve kills). Ops 3/10 means a small founding team can run it globally.");

// ---------- S21 PERSONA ----------
s=lightSlide("The customer","Priya, 34 — and Meera, 39","Personas synthesised from segment research. Priya's trigger moments: job offer, kundli matching, house muhurat, naming ceremony. Objection handling — 'is this real Jyotish?' — is why the Jyotish lead hire and ethics code are launch-critical.");
card(s,0.55,1.8,6.0,4.6);
s.addText("PRIYA — primary (NRI)",{x:0.8,y:2.0,w:5.5,h:0.4,fontFace:HF,fontSize:15,bold:true,color:NAVY,margin:0});
bullets(s,0.8,2.5,5.5,3.7,["34, product manager, New Jersey; H-1B→green card; married, one daughter; parents in Pune; HH income $210K","Pays without blinking: Calm, Peloton, Kumon, annual India tickets","Consulted astrologers at her wedding and house purchase; follows 2 Instagram astrologers; finds AstroTalk 'sketchy but I go back'","Trigger: startup job offer — 'is this the right time?'","Objection: 'Is this real Jyotish or an app gimmick?'","WTP: $199/yr in one tap — if she trusts it"],11);
card(s,6.8,1.8,6.0,4.6);
s.addText("MEERA — secondary (metro India)",{x:7.05,y:2.0,w:5.5,h:0.4,fontFace:HF,fontSize:15,bold:true,color:NAVY,margin:0});
bullets(s,7.05,2.5,5.5,3.7,["39, marketing head, Bengaluru; ₹28L HH income; two children","Already spends: therapist ₹2,000/session occasionally, family panditji at festivals, ₹500–1,000 astrology consults at decisions","Wants: honest guidance without the neighbourhood grapevine","Trigger: daughter's board-exam year + husband's job change","Objection: privacy — 'who sees my birth details?'","WTP: ₹999/mo tier (Pragati), annual preferred"],11);
take(s,"She already spends more than our ask — on worse alternatives.");

// ---------- S22 JOURNEY ----------
s=lightSlide("Experience","The journey: habit by day 7, trust by month 3, family lock-in by month 6","Each stage has an instrumented metric (activation, WAU, consult attach, renewal). The Year-Ahead artefact is deliberately timed to the renewal moment.");
const jz=[["Discover","IG astrologer collab → free Honest-Kundli teaser","Magic moment: one chart-specific insight in 60 seconds"],
["Onboard","10 min: birth details, goals, tone preference","First daily brief scheduled"],
["Week 1","Daily 60-second briefs + first decision session","Activation: chart + 3 briefs read"],
["Month 1–3","Monthly transit report · journal · family charts","WAU >45% target"],
["Quarter","Verified human consult (premium tiers)","Trust anchor + upsell"],
["Month 12","Year-Ahead report — beautiful, shareable","Renewal + referral moment"]];
jz.forEach((d,i)=>{ const x=0.55+(i%3)*4.16, y=1.95+Math.floor(i/3)*2.25; card(s,x,y,3.96,2.05);
 s.addShape("ellipse",{x:x+0.18,y:y+0.16,w:0.42,h:0.42,fill:{color:NAVY}});
 s.addText(String(i+1),{x:x+0.18,y:y+0.16,w:0.42,h:0.42,fontFace:BF,fontSize:14,bold:true,color:WHITE,align:"center",valign:"middle",margin:0});
 s.addText(d[0],{x:x+0.72,y:y+0.18,w:3.0,h:0.4,fontFace:HF,fontSize:14,bold:true,color:NAVY,margin:0});
 s.addText(d[1],{x:x+0.2,y:y+0.72,w:3.55,h:0.75,fontFace:BF,fontSize:11,color:INK,margin:0});
 s.addText(d[2],{x:x+0.2,y:y+1.5,w:3.55,h:0.45,fontFace:BF,fontSize:9.5,italic:true,color:MUT,margin:0});});
take(s,"Every stage has a number attached — the funnel is measurable end to end.");

// ---------- S23 STORYBOARD ----------
s=lightSlide("Product","Six screens tell the whole story","Wireframes to be produced in design sprint (validation phase). The visible memory chips ('remembers: job search, Ananya's school') are the differentiation made tangible — no competitor can show that screen.");
const scr=[["Today","Personal morning brief + timing windows for the day"],["Companion","Chat with visible memory chips — it remembers your life"],["Decision room","Structured 'should I / when should I' → recommendation + the why"],["Family","Charts for spouse, children, parents + festival calendar"],["Consult","Verified astrologer, fixed price, your context pre-briefed"],["Year Ahead","The premium annual artefact — shareable, printable"]];
scr.forEach((d,i)=>{ const x=0.55+(i%3)*4.16, y=1.9+Math.floor(i/3)*2.3;
 s.addShape("roundRect",{x,y,w:3.96,h:2.1,rectRadius:0.09,fill:{color:NAVY}});
 s.addShape("roundRect",{x:x+0.25,y:y+0.2,w:1.05,h:1.7,rectRadius:0.06,fill:{color:"2A2F63"},line:{color:"4A4F8F",width:1}});
 s.addText(d[0],{x:x+1.45,y:y+0.25,w:2.4,h:0.5,fontFace:HF,fontSize:14.5,bold:true,color:GOLD,margin:0});
 s.addText(d[1],{x:x+1.45,y:y+0.8,w:2.4,h:1.2,fontFace:BF,fontSize:10.5,color:ICE,margin:0});});
take(s,"An operating system for life-timing — not a horoscope feed.");

// ---------- S24 PAY & STAY ----------
s=lightSlide("Value","Why users pay — and why they stay","Left: six value types at purchase. Right: the retention engine — each layer compounds. Ethics note: no manipulative retention; one-tap cancel is brand strategy in a dark-pattern category.");
card(s,0.55,1.8,6.0,4.6);
s.addText("WHY THEY PAY",{x:0.8,y:1.95,w:5,h:0.4,fontFace:HF,fontSize:14,bold:true,color:NAVY,margin:0});
bullets(s,0.8,2.45,5.5,3.8,["Functional: timing windows; one trusted answer, not five contradictory ones","Emotional: reassurance without judgment, 24×7","Convenience: 2 a.m. answers across time zones","Identity: a premium, modern way to honour tradition","Financial: less than one human consult per month","Family: shared festival calendar + family charts"],11.5);
card(s,6.8,1.8,6.0,4.6);
s.addText("WHY THEY STAY",{x:7.05,y:1.95,w:5,h:0.4,fontFace:HF,fontSize:14,bold:true,color:GOOD,margin:0});
bullets(s,7.05,2.45,5.5,3.8,["Life-context memory compounds — guidance gets sharper every month","The calendar auto-recurs: festivals, transits, dashas regenerate relevance","Quarterly human consult anchors trust","Family charts embed the household","Year-Ahead artefact resets the annual loop","Cancelling = losing the astrologer who finally remembers you"],11.5);
take(s,"Retention is engineered into the product loop — not hoped for.");

// ---------- S25 MOAT ----------
s=lightSlide("Defensibility","Why free ChatGPT cannot easily replace it","₹399 ChatGPT Go is precisely why we sell continuity + humans + ethics, not text generation. Each layer is independently hard; together they compound. Passes the NFX switching-cost test: leaving loses accumulated context and relationships.");
const moat=[["Deterministic Vedic engine","Licensed ephemeris computes charts, dashas, muhurta — astronomy is calculated, never generated"],
["Years-deep life log","Decisions, outcomes, patterns — the one asset a fresh prompt can never import"],
["Proactive cadence","Transit & festival alerts arrive unprompted — ChatGPT waits to be asked"],
["Verified human panel","Ethics-contracted astrologers with full context handoff — trust at high stakes"],
["Family graph","Multi-member charts, shared calendars — household infrastructure"],
["Brand covenant","'We will never scare you into spending' — structurally unavailable to incumbents whose revenue is fear"]];
moat.forEach((d,i)=>{ const x=0.55+(i%3)*4.16, y=1.9+Math.floor(i/3)*2.28; card(s,x,y,3.96,2.08);
 s.addText(d[0],{x:x+0.2,y:y+0.15,w:3.56,h:0.55,fontFace:HF,fontSize:13.5,bold:true,color:NAVY,margin:0});
 s.addText(d[1],{x:x+0.2,y:y+0.75,w:3.56,h:1.25,fontFace:BF,fontSize:10.8,color:INK,margin:0});});
take(s,"The moat is memory, trust and people — not the model.");

// ---------- S26 COMPETITIVE 2x2 ----------
s=lightSlide("Competition","The top-right quadrant is empty","Axes: trust/ethics (vertical) x continuity/personalisation (horizontal). AstroTalk is huge but bottom-left — and cannot move up-right without cannibalising fear-driven consult revenue (innovator's dilemma). Family astrologers are trusted but memory-less and unscalable.");
s.addShape("rect",{x:1.2,y:1.85,w:10.4,h:4.4,fill:{color:LIGHT},line:{color:"D9DCEC",width:1}});
s.addShape("line",{x:6.4,y:1.85,w:0,h:4.4,line:{color:"B9BDD4",width:1}});
s.addShape("line",{x:1.2,y:4.05,w:10.4,h:0,line:{color:"B9BDD4",width:1}});
s.addText("TRUST / ETHICS →",{x:0.45,y:3.3,w:2.4,h:0.4,fontFace:BF,fontSize:9,color:MUT,rotate:270,margin:0});
s.addText("CONTINUITY / PERSONALISATION →",{x:8.4,y:6.35,w:3.4,h:0.3,fontFace:BF,fontSize:9,color:MUT,margin:0});
const comp=[["AstroTalk (₹1,182 Cr)",2.0,5.0,MUT],["AstroSage AI (80M)",3.4,4.5,MUT],["Nebula / Co-Star",4.6,5.3,MUT],["Family astrologer",2.3,2.3,"8B8FD9"],["ChatGPT (free)",5.0,4.6,"8B8FD9"],["SITARA",9.3,2.35,GOLD]];
comp.forEach((c,i)=>{ const isS=c[0]==="SITARA";
 s.addShape("ellipse",{x:c[1],y:c[2],w:isS?0.55:0.4,h:isS?0.55:0.4,fill:{color:c[3]}});
 s.addText(c[0],{x:c[1]-0.7,y:c[2]+(isS?0.6:0.42),w:2.1,h:0.35,fontFace:BF,fontSize:isS?12:9.5,bold:isS,color:isS?NAVY:MUT,align:"center",margin:0});});
take(s,"Premium trust + compounding continuity: a defensible position no incumbent can chase without self-harm.");

// ---------- S27 RIGHT TO WIN ----------
s=lightSlide("Right to win","Our advantages — and the gap we will hire for","Only supported claims. The named gap (Jyotish authority) is an early-hire commitment, budgeted in Scenario A. Incumbents' ethics-blindness is structural, not accidental — their revenue depends on per-minute anxiety.");
const rtw=[["AI product capability","This research programme — multi-agent, evidence-first — is itself the working demo of how we build."],
["Cultural fluency","India + diaspora insight and Hinglish/Hindi product design — the exact surface incumbents ignore."],
["Structural freedom","No fear-revenue to protect. The ethics covenant costs incumbents crores to copy; it costs us nothing."],
["Named gap — hired, not faked","Respected Jyotish lead as early hire/co-founder: credibility-critical, budgeted, non-negotiable."]];
rtw.forEach((d,i)=>{ const x=0.55+(i%2)*6.24, y=1.85+Math.floor(i/2)*2.3; card(s,x,y,6.04,2.1,{fill: i===3?"FDF6E8":LIGHT, line: i===3?"E8D9B0":"E3E6F2"});
 s.addText(d[0],{x:x+0.22,y:y+0.16,w:5.6,h:0.5,fontFace:HF,fontSize:14.5,bold:true,color:i===3?GOLD:NAVY,margin:0});
 s.addText(d[1],{x:x+0.22,y:y+0.72,w:5.6,h:1.3,fontFace:BF,fontSize:12,color:INK,margin:0});});
take(s,"Our edge is product + trust posture; we buy the domain authority we lack.");

// ---------- S28 MVP + VALIDATION ----------
s=lightSlide("Plan","MVP in 12 weeks — every rupee buys a kill-or-scale answer","Concierge test runs BEFORE serious code: a real astrologer + operator over WhatsApp at $15/mo for 50 users. Month-2 renewal is the single most important number this company will ever measure.");
bullets(s,0.55,1.8,12.1,1.9,["Build: chart engine (licensed ephemeris) · daily brief (WhatsApp/web) · memory chat · Year-Ahead report · 5 contracted astrologers · billing","Not built in v1: voice, community, native apps, rituals, matchmaking"],12);
const gates=[["Gate 0 (wk 2)","Landing test: >25% email capture from cold traffic"],["Gate 1 (wk 10)","Concierge 50 users: M2 renewal ≥60% · M3 ≥45%"],["Gate 2 (M6)","Founding 500 at $99: CAC <₹4,000 · activation >60%"],["STOP-LOSS","Concierge M2 <40% or founding <250 by M6 → stop or pivot; exposure capped at ₹1.25 Cr"]];
gates.forEach((d,i)=>{ const y=4.3+i*0.55;
 s.addShape("roundRect",{x:0.55,y,w:12.23,h:0.5,rectRadius:0.06,fill:{color:i===3?"F7F1F1":LIGHT},line:{color:i===3?"E7D5D5":"E3E6F2",width:0.75}});
 s.addText(d[0],{x:0.75,y,w:2.2,h:0.5,fontFace:BF,fontSize:11.5,bold:true,color:i===3?BAD:NAVY,valign:"middle",margin:0});
 s.addText(d[1],{x:3.0,y,w:9.6,h:0.5,fontFace:BF,fontSize:11.5,color:INK,valign:"middle",margin:0});});
s.addText("Team: 2 engineers · founder · part-time Jyotish lead · contract designer   |   12-week build inside the ₹1.25 Cr envelope",{x:0.55,y:3.82,w:12.2,h:0.4,fontFace:BF,fontSize:11,color:MUT,margin:0});
take(s,"Gates and a hard stop-loss make this a purchase of information, not a leap of faith.");

// ---------- S29 GTM + ROADMAP ----------
s=lightSlide("Go-to-market","First 100 organic. First 1,000 paid. Then the flywheel.","AstroTalk's published CAC (₹575–870 domestic, recovered 6–8 months) proves the Meta channel; our NRI guardrail is ₹4,000 blended at 3x the ARPU. Roadmap phases map to funding gates.");
bullets(s,0.55,1.8,6.1,4.5,["First 100: r/ABCDesis + two diaspora micro-influencer astrologers + the free Honest-Kundli hook","First 1,000: Meta lookalikes on chart-teaser creative · festival campaigns (Navratri, wedding season) · referral = gift a family chart","Later: SEO transit calendars · YouTube honest-astrology · wedding-platform B2B2C partnerships","CAC guardrail ₹4,000 blended; kill any channel above ₹6,000 after 2 cohorts"],12);
const road=[["P1 Validate","M1–6"],["P2 Productise","M7–12 · voice, family charts"],["P3 Scale","M13–24 · matchmaking, India tier"],["P4 Expand","M25–36 · rituals module (DharmaSetu)"],["P5 Platform","Y3+ · muhurat API, family-graph ecosystem"]];
road.forEach((d,i)=>{ const y=1.95+i*0.92;
 s.addShape("roundRect",{x:7.0,y,w:5.75,h:0.8,rectRadius:0.07,fill:{color:i<2?NAVY:"5A5FD4"}});
 s.addText(d[0],{x:7.2,y,w:2.2,h:0.8,fontFace:HF,fontSize:12.5,bold:true,color:WHITE,valign:"middle",margin:0});
 s.addText(d[1],{x:9.45,y,w:3.2,h:0.8,fontFace:BF,fontSize:10.5,color:ICE,valign:"middle",margin:0});});
take(s,"Validate narrow; expand along the family graph the product itself creates.");

// ---------- S30 BOARD RECOMMENDATION ----------
s=darkSlide();
s.addText("BOARD RECOMMENDATION",{x:0.7,y:0.6,w:8,h:0.4,fontFace:BF,fontSize:13,color:GOLD,charSpacing:3,bold:true,margin:0});
s.addText("Approve ₹1.25 crore. Buy the answer to a ₹1,182-crore question.",{x:0.7,y:1.1,w:12,h:1.0,fontFace:HF,fontSize:30,bold:true,color:WHITE,margin:0});
const recs=[["APPROVE","Scenario A: ₹1.25 Cr — validate demand and build Sitara v1 (12-week MVP + concierge + founding 500)"],
["MILESTONE","Concierge M2 renewal ≥60% and 500 founding members by month 6"],
["NEXT REVIEW","Month-6 board meeting with full cohort data → Gate-2 decision on ₹3.3 Cr launch tranche"],
["IF VALIDATION FAILS","Stop-loss executes: exposure capped at ₹1.25 Cr; brand, astrologer panel and cohort learning reusable (pivot: hybrid credits or KalaOS)"],
["IF IT SUCCEEDS","Deck 2 economics engage: path to 14,500+ subscribers, ₹12.2 Cr Y3 revenue, EBITDA-positive month 30 (base case)"]];
recs.forEach((d,i)=>{ const y=2.35+i*0.88;
 s.addShape("roundRect",{x:0.7,y,w:11.95,h:0.76,rectRadius:0.07,fill:{color:"2A2F63"}});
 s.addText(d[0],{x:0.95,y,w:2.6,h:0.76,fontFace:BF,fontSize:11.5,bold:true,color:GOLD,valign:"middle",margin:0});
 s.addText(d[1],{x:3.7,y,w:8.8,h:0.76,fontFace:BF,fontSize:11.5,color:WHITE,valign:"middle",margin:0});});
s.addNotes("Close by returning to the framing: this is a capped purchase of certainty. The board is not approving a company today — it is approving the cheapest possible test of the best-evidenced opportunity from 14 categories of research.");

p.writeFile({fileName:"Sitara_Deck1_Board_Conviction.pptx"}).then(()=>console.log("deck1 done"));
