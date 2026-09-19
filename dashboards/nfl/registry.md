# Registry review — 2026

*Framework status: **PROPOSED**. Everything below is proposed until ratified.*

> Week 1 review. No hypothesis added -- the catalogue was sharpened, not grown. H1 gained a conversion floor and an honest conjunction flag, H5 gained a second axis at no extra min_n cost, G3a proposed in rules.yaml. All four hypotheses still hold zero rows, which is the only reason these edits are legitimate: a definition may be revised freely before it has a record. Once the first row lands, the gate applies and the triggers freeze until min_n.


## Open hypotheses


### H1 — Route-participation lag

`SHADOW` · opens week 3 · gate 0/40 · conjunction, edge claimed on **opportunity**


**Mechanism.** Receiving prop lines are anchored to recent RESULT stats (yards, catches) and to name recognition. Route participation is the stable input and it moves BEFORE results do -- a player promoted into a full-time route role keeps a line priced off two weeks of low production in a smaller role. The market's error is anchoring on output while the input has already re-based. This is the cleanest available instance of G4.


**Fires when — all of:**

- route participation >= 78% in the most recent game
- route participation rose >= 12 percentage points vs the player's prior 3-game average
- the receptions line has NOT moved up more than 0.5 vs the prior week
- targets per route run >= 0.18 over the same window, and NOT trending down while route share rises (added 2026-09-19 -- a route-share read with no conversion floor is half a hypothesis)


**Conditions required (G3a):**

- *opportunity* — route participation holds at the observed level
- *conversion* — targets arrive at his established targets-per-route-run


**Expression.** player_receptions OVER


**Why flagged this way.** Revised 2026-09-19 under G3a. This was logged as conjunction:false, which was wrong -- receptions needs both the routes AND the targets, and the two are separately priced and separately variable. The read claims edge on opportunity only; conversion is assumed, not predicted, and is graded as an assumption that held or failed. Receptions is still chosen over receiving yards deliberately: yards adds a THIRD condition (efficiency -- aDOT, YAC, catch depth). Fewer conditions, not one.


**Dies if.** Mean margin vs fair <= 0 over 40 rows, or mean CLV <= 0 over 25 rows. Also dies if TPRR turns out to fall as route share rises (i.e. the promotion is dilution, not opportunity) -- that would mean the mechanism is backwards, not merely weak.


*Expected fire rate 3-6 rows/week from Week 3 => ~50-90 rows/season. Reachable. This is the hypothesis most likely to produce a real verdict.*


### H2 — Second-order target absorption

`SHADOW` · opens week 3 · gate 0/25


**Mechanism.** When a high-target player is ruled out, the market moves the obvious replacement at that position and stops. Vacated targets do not redistribute by depth chart -- they redistribute by alignment and route tree. The slot receiver and the TE frequently absorb more of a vacated outside WR's targets than the WR3 who "replaces" him does. The market prices the headline substitution and underprices the distribution.


**Fires when — all of:**

- a teammate with >= 20% target share (last 3 games) is ruled OUT or is CONFIRMED inactive
- the candidate ran >= 55% of routes WITH that teammate active
- the candidate's alignment overlaps the absent player's (slot/TE absorbing an outside WR, or the inverse), verified on route data -- not assumed from the depth chart


**Expression.** player_receptions OVER (primary), player_reception_yds OVER (secondary, logged in parallel per H5)


**Dies if.** Mean margin vs fair <= 0 over 25 rows. Dies faster if the mechanism check fails independent of the bet: if measured absorbed target share does not exceed the candidate's baseline in a majority of fires, the read is wrong even where the props happen to cash. Track that in mechanism.csv.


*Expected 1-2 rows/week => ~25-35 rows/season. Borderline. Likely to end the season with a directional read and no verdict. Accept that up front.*


### H3 — Friday-news latency (CLV-primary)

`SHADOW` · opens week 1 · gate 0/20


**Mechanism.** Prop markets for non-marquee players are thin, posted late, and repriced slowly after Friday practice reports and Saturday designations. Sides and totals absorb injury news within minutes; a WR3's receptions line can sit stale into Sunday morning. The error is not in the market's estimate -- it is in the market's SPEED, on the least-attended boards. This is the one hypothesis that needs no current-season usage history, so it is the only one that can open now.


**Fires when — all of:**

- a role-relevant designation lands Fri/Sat (starter ruled OUT, or a candidate upgraded to full participation off an injury)
- the affected player's prop is posted and has not moved >= 0.5 line or >= 10 cents within 4 hours of the news
- the player's projected role is legible from prior usage or, in Weeks 1-2 only, from preseason/camp role -- tagged PROJECTED


**Expression.** whichever prop the news most directly implicates, OVER or UNDER as the news dictates. Record the news timestamp in notes.


**Dies if.** Mean CLV <= 0 over 20 rows. This hypothesis is graded on CLV FIRST and W/L a distant second: if the line does not move toward the stake price by close, there was no latency to exploit and the read was imagined. A positive W/L with flat CLV here is GAMBLED, not CONFIRMED.


*1-3 rows/week => ~30-50 rows/season. CLV stabilizes faster than margin, so 20 rows is a real (if early) read on this one specifically.*


> ⚠ Requires paid Odds API historical endpoints or disciplined manual capture at two timestamps. Without a real close, this hypothesis cannot be graded at all -- do not open it on manual-only capture.


### H5 — Expression-form control (meta)

`SHADOW` · opens week 3 · gate 0/30


**Mechanism.** Not a market read. A test of G3 itself. The claim is that for one underlying read, the single-condition expression (receptions, attempts) produces better mean margin vs fair and better CLV than the multi-condition expression (yards), because the yards line silently charges for an efficiency condition the read never claimed. If true, every future hypothesis should default to counting stats. If false, the repo's structural preference for props is weaker than assumed and G3 needs amending.


**Fires when — all of:**

- any H1 or H2 row fires and both expressions are available on the board


**Axis `form`** — counting stat (receptions, attempts) vs yardage on the same read  
fewer conditions should produce better margin vs fair and CLV


**Axis `anchor`** — volume-anchored read (team pass attempts, implied total, funnel matchup) vs share-anchored read (target share, targets per route run) on the same game  
Team pass volume is heavily bet and tied to the game total, so it is priced efficiently. Individual share is priced off reputation and season-long averages and moves slower. If that holds, the edge lives in share, and a volume-anchored read is buying something the market already knows. Week 1 is one data point consistent with this and nothing more -- it is why the axis exists, not evidence for it.


**Expression.** parallel shadow rows on the identical read, identical timestamp, sharing a pair_id


**Dies if.** Per axis, independently. FORM: paired mean margin vs fair shows no advantage to the fewer-condition expression over 30 pairs, or the advantage reverses. ANCHOR: share-anchored reads show no advantage over volume-anchored ones across 30 pairs. Either axis can die alone.


*Rides free on H1/H2 -- costs no additional judgment and no dollars, and doubles the row count from reads already being made. This is the cheapest sample in the repo and directly attacks the sample-starvation problem.*


> ⚠ Pairs must share a pair_id in bets.csv notes for the comparison to be computable. Suggest adding a pair_id column.


## Candidates — written down, not opened


### H6 — Share-blind volume pricing

**Mechanism.** Receiving lines move with the team's implied total and with the opposing defence's pass-funnel reputation, but not with the player's own target share trend. If true, a player whose share is declining inside a rising team total is systematically overpriced -- the line inherits the team's good news and ignores his bad news.


**Why it stays closed.** Three reasons, any one sufficient. (1) It needs three or more weeks of current-season share data, so it could not fire before Week 5 anyway. (2) It overlaps H1 enough that the two would compete for the same rows, and with ~16 games a week the binding constraint is sample, not ideas -- a fifth hypothesis makes all five slower to resolve. (3) It was suggested by one Sunday. One Sunday is not evidence of a market behaviour, and a catalogue that grows every time a bet loses is fitting noise with extra steps.


**Revisit.** Week 6, and only if H1 has produced rows showing conversion failures are systematic rather than incidental.


## Rules


**G1 — Fair-line grading.** Never grade against an arbitrary bar. Grade against the closing line or a clearly-labeled derived fair line. Judge hypotheses on mean margin vs fair, not W/L count.
  
*Origin: A prior project's hypothesis showed a 3-0 record against a soft bar that collapsed to ~0 edge against a fair line.*

**G2 — CLV on every row.** Capture line and price at stake-time AND at close on every row, including shadow rows. CLV is the primary early signal; with NFL sample sizes it reveals edge long before W/L can.

**G3 — Expression decomposition.** Before staking, decompose the bet into the conditions it actually requires. Flag hidden conjunctions. Log conditions_required per row.
  
*Origin: A moneyline expression presented as single-condition was a conjunction; the elite arm performed exactly as predicted and the bet still lost because the hidden second leg failed.*

**G4 — Verify the underlying.** Reads must rest on usage inputs (snap share, route participation, target share, aDOT, air yards, PROE, pressure rate, red-zone usage), not result stats (yards per game). Results regress; usage holds.

**G5 — Prospective only.** A play counts only if identified, logged, and priced before kickoff. No retroactive "would have won" ever enters bets.csv.

**G6 — Retroactive mechanism capture.** For missed weeks, recover mechanism not markets. Box-score-settled observations go to mechanism.csv, tagged separately, and inform a hypothesis's truth but never the W/L ledger. Reconstructing a line is forbidden.


## Amendment log


### G3 · 2026-09-19 · **PROPOSED**

G3a — no player prop is a single condition. Every prop expression requires at least two: OPPORTUNITY (the player is on the field in the role assumed) and CONVERSION (the opportunity turns into the counted event at his established rate). Stop recording conjunction as a boolean. Record both conditions, and name which one the read claims edge on. A read that claims edge on opportunity must not be graded as though it claimed conversion — that is how a half-correct read gets filed as a clean miss.


*Origin: Week 1 2026. A receiving read was logged as "volume, single condition." Team volume arrived exactly as predicted -- 35 attempts, 254 yards -- and the player drew four targets, the second-fewest of his career. The opportunity condition held; the conversion condition collapsed. Logged as one condition, the ledger would have recorded a clean miss on a read that was half right, and the lesson would have been unavailable.*

