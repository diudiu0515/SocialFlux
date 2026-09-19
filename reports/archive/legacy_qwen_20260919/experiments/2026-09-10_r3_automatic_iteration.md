# R3 automatic stabilization log — 2026-09-10

## Invariants

- Every environment turn uses two independent LLM calls: structured appraisal first, then deterministic state/dynamics calibration and numeric update, then response generation.
- Rejected and partial trajectories remain under each versioned `build/r3_debug_v*/.../rejected/` directory.
- A machine PASS is provisional until offline audit and full-dialogue review pass.
- The formal exact-20 contract is unchanged. A separate `natural_max_20` ablation is diagnostic only; it does not force a new event, remove rejected samples, or count as formal acceptance.

## Current stabilization sequence

| Version | Scenario/model | Attempts | Online pass | Full-trajectory finding | Primary attribution | Disposition |
|---|---|---:|---:|---|---|---|
| v22 | IA003 / Qwen3-32B both calls | 1 | 0/1 | t16–t18 repeat “不再借/到此为止” | agent policy + environment response; narrow scenario long tail | rejected |
| v23 | IA003 / Qwen3-32B both | 1 | 0/1 | t7–t9 reuse “下周见面” across amount, difficulty, communication | agent policy + focus validator | rejected |
| v24 | IA003 / Qwen3-32B both | 1 | 0/1 | t13–t15 renew meeting/document commitments | both policies + commitment ledger | rejected |
| v25 | IA003 / Qwen3-32B both | 1 | 0/1 | t9–t11 repeat consensus/plan closure | both policies | rejected |
| v26 | IA003 / Qwen3-32B both | 1 | 0/1 | t10–t12 rephrase no-new-borrowing boundary | agent policy + semantic validator gap | rejected |
| v27 | IA003 / Qwen3-32B both | 1 | 1/1 | machine PASS, but t13–t20 repeat economic boundary/consensus | validator false negative | rejected by model semantic review; preserved |
| v28 | IA003 / Qwen3-32B both | 1 | 0/1 | response renews the same future transfer | environment response | rejected |
| v29 | IA003 / Qwen3-32B both | 1 | 1/1 | machine PASS, but repayment follow-up loops, borrower role reversal, and future-cycle ending remain | validator false negative + response role | rejected by model semantic review; preserved |
| v30 | IA003 / Qwen3-32B both | 1 | 0/1 | t7 response returns from trust to a pending repayment plan; all retries renew it | environment response | rejected |
| v31 | IA003 / Qwen32 appraisal + GLM response | 1 | 0/1 | English/customer-service prose, long lists, invented process, repayment churn | response backbone | rejected; GLM excluded |
| v32 | IA019 / Qwen3-32B both | 1 | 0/1 | valid governance/equity switches rejected because non-debt goal progress stayed at zero | ledger + validator false positive | fixed in v33 |
| v33 | IA019 / Qwen3-32B both | 1 | 1/1 | online PASS but t14–t20 nest “我需要你说明”; t3/t7 report future work complete; t8/t15 appraisal swap speaker; t20 remains open | agent policy + response + ledger + appraisal + validator false negative | offline rejected under v34; preserved |
| v34 | IA019 / Qwen3-32B both | 1 | 0/1 | stopped at t3; repetitive shells correctly rejected, but substantive responsibility/compensation moves were also rejected; t2 response takes over agent demand | validator false positives + response ownership | fixed in v35 |
| v35 | IA019 / Qwen3-32B both | 1 | 0/1 | stopped at t5; agent evaded sentence-initial “I need” check, then environment was blocked from answering the proposal that saturated its thread | agent policy + validator ordering | fixed in v36 |
| v36 | IA019 / Qwen3-32B both | 1 | 1/1 | online/offline structural PASS, but model semantic review found unsupported time jumps, legal/assistant invention, self-defeating withdrawal, document tail, reopen-after-exit, and ledger undercount | both policies + ledger + validator false negative | rejected by model semantic review under v37; preserved |
| v37 | IA019 / Qwen3-32B both | 1 | 0/1 | stopped at t3; all responses fabricated agreement rules, decision steps, minutes, filings, or final ratios; generic artifact reason gave poor retry direction | environment response + validator diagnostic gap | fixed in v38 |
| v38 | IA019 / Qwen3-32B both | 1 | 0/1 | reached 19 turns; environment invented agreement authorship/content, valuation, growth threshold, and protection rights; ledger left answered proposal threads and a performed speech commitment open; all 12 final candidates asked another question or opened future work | environment response + ledger + final-generation compliance; one format-validator false positive | rejected; fixed in v39 |
| v39 | IA019 / Qwen3-32B both | 1 | 0/1 | stopped at t7; environment still asserted “files show” and “agreement contains restrictions”; agent deferred twice to tomorrow; latest environment proposal could not receive a plain answer once governance was saturated | environment grounding + agent policy + validator false positive/order | rejected; fixed in v40 |
| v40 | IA019 / Qwen3-32B both | 1 | 0/1 | reached t9; plain proposal acceptance worked at t5, but environment invented legal-document/financing-agreement facts and a secretary; repeated promises were marked performed; board meeting became another future-progress device | environment response + commitment ledger + agent policy | rejected; fixed in v41 |
| v41 | IA019 / Qwen3-32B both | 1 | infrastructure failure | service disconnected after t7; partial showed commitment ownership fixed and no invented secretary, but still asserted ongoing record work and ungrounded charter/board procedure; both speakers repeatedly used legal-letter “我方/你方” diction | local model service + environment response + naturalness | partial rejected; service restored; fixed in v42 |
| v42 | IA019 / Qwen3-32B both | 1 | 0/1 | reached t15; invented dilution cause/option-pool facts; overloaded single turns with ratios, maturities, veto/KPI and convertible debt; repeated an impersonal send promise; evaded a draft request; ledger falsely marked conditional acceptance/internal review as performed | environment response + agent policy + commitment ledger + validator false negatives | rejected; fixed in v43/v44 |
| v43 | IA019 / Qwen3-32B both | 0 | not run | preflight found compound acceptance+request could still be hidden by the appraisal's primary social-act label | deterministic obligation tracking | superseded by v44 before rollout |
| v44 | IA019 / Qwen3-32B both | 1 | 0/1 | stopped before t6: first five responses asserted unsupported financing rounds/votes/agreement/governance procedure; all t6 policy drafts accepted the newest offer and then moved to untouched economic compensation but were rejected as added conditions | environment response + validator false positive | rejected; fixed in v45 |
| v45 | IA019 / Qwen3-32B both | 1 | 0/1 | stopped after t6: responses asserted unsupported financing-process facts, reported a pending file promise as already sent, and repeatedly bounced compensation stance back; the required current compensation answer was blocked by focus saturation | environment response + agent policy + commitment validator + goal-progress/validator ordering | rejected; fixed in v46 |
| v46 | IA019 / Qwen3-32B both | 1 | 0/1 | reached t12; online stopped on a valid acceptance plus explicitly invited future-cooperation follow-up. Model semantic review found unsupported board/governance arrangements throughout t1–t10 and a false pending commitment from immediate “I can confirm” speech | environment response + commitment ledger + validator false positive + offline validator false negative | rejected; fixed in v47 |
| v47 | IA019 / Qwen3-32B both | 1 | 0/1 | reached t13; machine audit falsely passed a partial with unsupported authorization/board/shareholder-agreement facts, invented current document preparation, four-right bundles, a conditional future confirmation marked performed, and saturated-governance question ping-pong; t14 retries then exhausted | environment response + commitment ledger + online/offline validator false negatives; agent policy long-tail repetition | rejected; fixed in v48 |
| v48 | IA019 / Qwen3-32B both | 1 | 0/1 | stopped after t8; t1–t3 asserted a fixed financing structure and board-controlled rights, while t5 explicitly requested promised early-agreement details and t6 evaded into governance. The old machine audit passed the partial; t9 candidates exposed a downstream proposal/saturation conflict caused by that missed obligation | environment response + policy evasion + environment-request ledger + offline validator false negative | rejected; fixed in v49 |
| v49 | IA019 / Qwen3-32B both | 1 | 0/1 | stopped after 6 turns; exact A-round, invented legal archive/contact, and a pending summary treated as delivered | both policies + environment grounding + commitment tracking | rejected |
| v50 | IA019 / Qwen3-32B both | 1 | 0/1 | stopped after 4 turns; invented board/member/record facts and a focus false positive | environment response + validator false positive | rejected |
| v51 | IA019 / Qwen3-32B both | 1 | 0/1 | stopped after 10 turns; fabricated document chain and governance micro-loop | both policies + environment grounding | rejected |
| v52 | IA019 / Qwen3-32B both | 1 | 0/1 | stopped after 2 turns; invented investment-committee/compliance retrieval chain and misleading retry diagnostic | environment response + validator diagnostic | rejected |
| v53 | IA019 / Qwen3-32B both | 1 | 0/1 | stopped after 10 turns; unsupported authority/oral-agreement/trigger claims and repeated “next-week plan” | both policies + grounding + long-tail loop | rejected; frozen baseline |
| v54 | not run | 0 | not run | code changes were prepared before the diagnostic branch but no rollout was generated | superseded by rule × horizon ablation | no evidence claim |

Across v22–v53 there are 31 generation attempts: 4 online passes, 26 quality-generation rejections, and 1 infrastructure failure. The raw online pass rate is 4/31 (12.9%); excluding the non-evaluable infrastructure failure it is 4/30 (13.3%). All four online passes (v27, v29, v33, v36) fail later model semantic/full-trajectory review, so the verified high-quality pass count remains 0. No human acceptance review has occurred. v53 is frozen; subsequent work moved to the separate rule-profile × horizon diagnostic rather than adding more regular expressions.

## Earlier preserved attempts (v10–v21)

These attempts predate the current targeted sequence. Their progress files remain available. Observed online results: v11 and v13 accepted one attempt each; v10, v12, v14–v21 exhausted retries or had provider errors. Those older accepts have not been promoted as R3 evidence because they have not passed the current offline rules and full-dialogue review.

## v34 → v35 changes

- Added per-speaker repeated “我需要……” and nested clarification detection; prompt retries must synthesize an answer into a choice, bounded proposal, disagreement, or closure.
- Split authored Chinese enumeration facets (`、`) and added authorization/equity/governance semantic evidence.
- A stalled focus may escape only through a truly untouched thread (`discussion_rounds == 0`), not another micro-question inside a previously discussed thread.
- Future-timed commitments retain the latest request as observable object context and cannot become “已完成/已发送/已更新” without elapsed-time/event evidence.
- Structured appraisal rejects intent text that assigns the evaluated participant's action to the environment character.
- Turn 20 requires a present decision, explicit unresolved disagreement, or natural stop from both speakers.
- v35 narrows artifact churn to concrete artifacts, distinguishes questions/acceptance from action takeover, detects “要求暂停” ownership copying, and compares commitment moves semantically rather than treating a broad domain focus as one promise.

## v38 → v39 changes

- Institutional facts are grounded only by declarative observable evidence; a question or hypothetical proposal no longer licenses the response to invent an agreement signer, decision basis, valuation, numeric threshold, protection right, or procedural status.
- Offline audit now reconstructs grounding sequentially, so the first unsupported factual assertion remains visible instead of laundering later repeats into evidence.
- Proposal/question threads are cleared by a direct counterparty response; `具备/包含/包括/取决于/影响` are recognized as direct dispositions.
- A promised conversational act is marked `performed_in_dialogue` only when the same owner later performs it with a shared semantic domain and observable content overlap. This does not convert off-screen work into completion.
- Natural rhetorical colons such as “我提议就此明确：” are no longer misread as a speaker label. Turn-20 retry guidance explicitly removes questions and future cycles while retaining the existing closure standard.
- The appraisal → deterministic calibration/update → response sequence remains two separate LLM calls.

## v39 → v40 changes

- “文件显示” and “协议中存在限制” are now covered by institutional grounding; questions and proposals remain non-evidence, while explicit hypothetical demands are not mislabeled as factual assertions.
- A second same-speaker “tomorrow/document/meeting, then discuss” move is rejected; this targets visible deferral reuse without pretending that time has passed.
- A plain present acceptance/refusal may answer the newest counterparty proposal even when that topic has saturated. Adding a percentage, condition, question, document step, or substitute process is still rejected and now receives the correct diagnostic.

## v40 → v41 changes

- Added exact grounding for claims about legal-document authority and financing-agreement content; generic document talk cannot license a more specific later institutional assertion.
- First-person commitments now recognize intervening time adverbs (`我今天会…`). A self-added deadline is not a substantive refinement unless the newest observable turn supplied it.
- Only promised conversational acts can become `performed_in_dialogue`; promises to organize/send/provide/coordinate/transfer off-screen work remain pending and cannot be completed by a later question or re-promise.
- A newly introduced secretary/assistant/lawyer/office/committee coordination action is rejected on first occurrence unless that actor is already observable. Offline audit now includes the same check.
- Reusing tomorrow/document/board-meeting review as future progress is rejected on the second same-speaker occurrence.
- Offline commitment consistency reconstructs the deterministic post-appraisal ledger before auditing the environment response, matching the online evidence boundary.

## v41 → v42 changes

- Restored the crashed Qwen3-32B service on GPU 1 using the repository runbook; model and sampling configuration are unchanged.
- Environment assertions that files/records/materials are “currently being organized” are rejected as unsupported off-screen activity.
- Claims that governance changes must occur through a board/charter framework, or that legal documents necessarily contain an answer, require declarative observable grounding.
- Repeated `我方/你方` legal-letter diction is tracked as a discourse template; prompts require natural `我/你` ownership in interpersonal scenarios.

## v42 → v43/v44 changes

- Added grounding for asserted dilution initiator/cause/purpose and missing-confirmation claims; a question is not evidence of its answer.
- A turn may contain at most a bounded set of consequential numbers/rights; early turns cannot draft an entire compensation/governance package at once.
- Impersonal future wording such as “the proposal will be sent today” is checked against same-owner pending commitments, so dropping “I” no longer bypasses renewal detection.
- `performed_in_dialogue` examines only the commitment object, not request context, and excludes organizing/internal-evaluation work. Plain requests are no longer stored as active proposals.
- Environment responses must address the current request/question domain before changing topic; offline audit applies the same paired-turn check.
- v44 preserves appraisal's single primary `social_act` contract but deterministically detects secondary explicit requests in compound utterances. `请立即/请立刻发送…` creates an environment obligation even when appraisal labels the overall action `commitment`.

## v44 → v45/v46 changes

- Clause-level grounding splits on true sentence/contrast boundaries, so “cannot confirm A, but B is definitely true” cannot launder B; Chinese commas no longer hide “according to the agreement, ...” assertions.
- Accepting/refusing the latest proposal may be followed by one untouched authored goal facet; adding a condition, number, artifact, or same-topic substitute remains rejected.
- Financing-process assertions now cover direct investor negotiation, email/investment-agreement execution, absent board authorization/signature, and claims that no new file/fact supports a request.
- A pending off-screen promise such as providing/sending a file cannot become “already sent/completed” without an observable event, even when the original promise had no explicit future date.
- “权益如何补偿/补偿方式” now counts toward the authored economic-compensation thread rather than leaving it falsely untouched.
- A response that owes the current answer may remain on that focus despite the rolling focus cap; this bypass applies only to the current owned obligation. Immediate reciprocal “tell me what you want” stance bouncing is rejected online and offline.
- The appraisal → deterministic calibration/numeric update → response sequence remains two independent LLM calls.

## v46 → v47 changes

- Added grounding for claims that every financing had a board resolution, governance/information/decision rights derive from agreements or board resolutions, final decisions belong to the board, and a detailed governance workflow already exists.
- “建议书” no longer inherits the non-factual exemption for sentence-initial “I suggest”; suggestion/proposal/demand exemptions are limited to first-person speech acts.
- Immediate speech such as “I can confirm: ...” is not stored as a future commitment, while “I can provide the files” remains pending.
- An acceptance may follow up on a second facet only when the newest proposal explicitly invited it. The follow-up cannot introduce a new number, cadence, artifact, agreement, or named right; this strict result bypasses only proposal/focus false positives.
- Model semantic review overrode v46's offline PASS; under v47 the preserved v46 partial trajectory fails institutional grounding.

## v47 → v48 changes

- Extended grounding to authorization chains involving boards/investment term sheets, asserted bundles of retained founder rights, governance arrangements attributed to investor/board rules, supplemental-agreement procedure, named concert-party clauses, “usual” founder rights, investor board majorities, and document claims about rights.
- Current off-screen preparation now covers charters and copies; early bundles count consultation, approval, and information rights as consequential terms.
- Conditional or deferred “we can first confirm/explain” speech cannot perform a pending conversational commitment. This keeps the original promise pending so a later restatement is visible.
- A currently owed answer may cross a saturated focus only as an answer. Adding another question on that saturated focus is rejected online for both speakers and by the offline audit.
- v47 model semantic review again overrode its old offline PASS; v48 re-audit exposes four independent failures rather than hiding the partial.

## v48 → v49 changes

- Model policy now applies the same latest-obligation domain check as environment responses. A concrete “please list/provide/explain” request requires the same practical focus rather than any broad institutional topic.
- Environment statements with explicit request wording create a deterministic obligation even without a question mark; both speakers now use the same surface-request rule.
- Offline action auditing reconstructs the visible latest response directly, so old trajectories with a missing legacy ledger obligation are still rejected.
- Grounding now covers claims that a financing structure is final, that a participant may take part in named product/budget/hiring decisions, and that board authority governs financing, nomination, or final appointment.
- Generic “reasonable rights” progress recognizes substantive rights/equity wording, preventing a broad duplicate goal from staying falsely untouched while its concrete facets saturate.

## Verification

- v34 targeted tests: 98/98 passed after fixing one compound-thread match bug and refreshing prompt/scenario manifests.
- v34 full backend: 252/252 passed; web: 8/8 passed.
- v35 targeted tests: 102/102 passed.
- v35 full backend: 256/256 passed; web: 8/8 passed.
- v36 targeted tests: 103/103 passed; full backend: 257/257 passed; web: 8/8 passed.
- v37 targeted tests: 106/106 passed; full backend: 260/260 passed; web: 8/8 passed.
- v38 targeted tests: 108/108 passed; full backend: 262/262 passed; web: 8/8 passed.
- v39 targeted tests: 101/101 passed; full backend: 267/267 passed; web: 8/8 passed.
- v40 targeted tests: 104/104 passed; final full backend: 270/270 passed; web: 8/8 passed.
- v41 targeted tests: 109/109 passed; full backend: 275/275 passed; web: 8/8 passed.
- v42 targeted tests: 110/110 passed; full backend: 276/276 passed; web: 8/8 passed.
- v43 targeted tests: 114/114 passed; full backend: 280/280 passed; web: 8/8 passed.
- v44 targeted tests: 115/115 passed; final full backend: 281/281 passed; web: 8/8 passed.
- v45 targeted tests: 132/132 passed before the v46 additions.
- v46 targeted tests: 136/136 passed; full backend: 287/287 passed; web: 8/8 passed.
- v47 targeted tests: 136/136 passed; full backend: 290/290 passed; web: 8/8 passed.
- v48 targeted tests: 139/139 passed; full backend: 293/293 passed; web: 8/8 passed.
- v49 targeted tests: 142/142 passed; full backend: 296/296 passed; web: 8/8 passed.
- v48 offline re-audit under v49: rejected by action latest-obligation and institutional-grounding checks despite its v48 offline PASS.
- v47 offline re-audit under v48: rejected by institutional grounding, unsupported off-screen response, consequential-term boundedness, and saturated-follow-up checks.
- v46 offline re-audit under v47: rejected by `institutional_procedures_are_grounded` despite its v46 offline PASS.
- v45 offline re-audit under v46: rejected by institutional grounding, pending-commitment consistency, and reciprocal stance-bounce checks.
- v42 offline re-audit under v44: rejected by pending-commitment consistency, institutional grounding, consequential-term boundedness, and latest-obligation response checks.
- v41 partial offline re-audit under v42: rejected by action/response template loops, unsupported off-screen response claims, and ungrounded institutional procedures.
- v40 offline re-audit under v41: rejected by `institutional_procedures_are_grounded` and `coordination_actors_are_grounded`.
- v39 offline re-audit under v40: rejected by `institutional_procedures_are_grounded`.
- v38 offline re-audit under v39: rejected by `institutional_procedures_are_grounded`, catching the substantive hallucinations before considering the turn-20 surface failure.
- v33 offline re-audit under v34: rejected by `actions_no_template_loop`, `appraisals_preserve_action_owner`, and `fixed_horizon_closes_naturally`.
- v36 offline re-audit under v37: rejected for action/response artifact loops, third-party errand loops, off-screen process claims, inconsistent pending commitments, and ungrounded legal escalation.

## Residual risks before development expansion

- Exact-20 can still induce unnatural long tails in narrow scenarios; this is treated as a scenario-design/selection issue, not solved by hiding early natural resolution.
- Qwen3-32B may continue obeying the newest noun while retaining the same request/conditional speech act; v35 needs full-trajectory evidence.
- Commitment completion remains a reported observable claim, not independently verified real-world completion; future-timed completion is blocked unless observable time/event evidence exists.
- State saturation can still occur after repeated high-pressure appraisals; representative reruns must show that policy-level repetition controls prevent artificial numeric drift.

## Diagnostic branch after v53

The regex-accumulation route was stopped after v53. The preserved 2×2 rule-profile × horizon experiment, physical request accounting, model semantic review, and evidence-backed follow-up fixes are documented in `reports/experiments/2026-09-10_r3_rule_length_ablation.md`.
