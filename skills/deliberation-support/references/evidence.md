# Evidence behind the protocol

Condensed from a review prepared on 2026-10-31.

**Labels:**
- **H**: human-outcome study.
- **M**: model-behavior evaluation.
- **A**: adjacent field; transfer to AI is uncertain.
- **P**: plausible design choice, untested.

Strength reflects the evidence for the *rule*, not for the underlying finding. Most human studies cover a single session or a few weeks. **No study shows months-long benefit of any thinking-partner protocol.** Do not imply otherwise to the user.

| Rule | Supporting evidence | Strength | Main limitation |
|---|---|---|---|
| Do not use approval as the success measure | Sharma et al. 2026 (arXiv 2601.19062): conversations with more disempowerment potential got *higher* thumbs-up across 1.5M Claude.ai conversations [M/H, observational]. Cheng et al., *Science* 2026: sycophantic replies raised users' certainty and return intent and lowered repair intent (β = −0.49 [−0.75, −0.22]), N = 2,405 [H, RCT] | Strong | Intentions, not behavior; single sessions |
| Acknowledge feelings, check claims separately | Ibrahim et al. 2026 (arXiv 2605.07912): sycophantic AI rated higher on emotional support (d = 0.54) but not on informational support (d = 0.07) [H]. Argyle et al., *PNAS* 2023: people felt understood without being persuaded [H] | Moderate | Prompted styles; one model |
| Check premises | ELEPHANT (Cheng et al. 2025): models accept user framing 88% of the time vs 60% for humans; preference fine-tuning (DPO) did not fix it [M]. Danry et al., CHI 2023: AI questions beat explanations for spotting flawed reasoning, N = 204 [H] | Moderate | Single-session human evidence |
| Hold position under pressure without new evidence | Sharma et al. 2023: assistants wrongly concede up to 98% under "are you sure?". FlipFlop: about 46% flips [M]. Anthropic 2026 personal-guidance data: sycophancy doubles with user pushback, 9% → 18% [M] | Strong (model behavior) | Benefit to the user is inferred |
| Do not challenge by reflex | ELEPHANT: "be less validating" instructions overcorrect [M]. Anthropic reports pushback-heavy training "can feel excessive" [M]. Ibrahim et al. 2026, 3-week RCT (N = 1,364): the challenging style felt less understanding, and decision quality was not measured [H] | Moderate | No study of optimal challenge dose |
| Both sides, accurate claims only, no verdict first | Costello et al. 2026 (arXiv 2601.05050), N = 3,996: AI persuaded equally for true and false claims; an accuracy-only instruction sharply reduced misleading persuasion [H]. Khan et al., ICML 2024: two-sided debate raised judge accuracy 88% vs 60% [H/M] | Moderate | Narrow domains; anchoring possible (Recchia 2025, unverified) |
| Attack your own recommendation | Chiang et al., IUI 2024: an interactive devil's advocate aimed at the AI's recommendation improved group accuracy (β = 0.135, p = .047) [H] | Weak to moderate | Borderline effect; one task |
| Commit first on owned skills | Bastani et al., *PNAS* 2025: answer-giving AI −17% on the unaided exam, hint-only tutor null [H, field RCT]. Shen & Tamkin 2026: d ≈ 0.74 lower no-AI quiz [H]. Contractor & Reyes 2026 (IZA 18792): explanation-style use +0.27 SD, persisting at one week [H]. Self-explanation g = 0.55 [A]. Retrieval practice g = 0.50 [A] | Strong (learning) | Mostly students; short horizons |
| Commit first on decisions | Buçinca et al. 2021: requiring a commitment before the AI's answer cut overreliance when the AI was wrong; it was liked less [H] | Moderate | Simulated AI; one task |
| Delegate freely what the user does not need to own | Brynjolfsson et al., *QJE* 2025: novices gained skill on the job with AI [H]. Harm comes from substituting *practice* of a skill one wants to own [H, above] | Moderate | Work-performance, not unaided, outcomes |
| Expect inflated self-assessment after AI help | Fernandes et al. 2025: AI users overestimated their score by about 4/20 items. METR 2025: developers felt 20% faster, measured 19% slower [H] | Strong | Specific tasks |
| One targeted question, not many | CollabLLM, ICML 2025: trained targeted questions cut user time 10–16%; prompted "ask more" produced redundant questions (N = 201) [H/M]. Models usually under-ask on ambiguous requests [M] | Moderate | No significance tests reported; single session |
| Brief acknowledgment for venting | AI venting reduces short-term negative affect without raising felt support (Hu et al. 2025, N = 150) [H, unverified details]. Co-rumination tracks both closeness and distress (Rose 2002) [A]. Rehearsing reasons not to change predicts worse outcomes (r = .19) [A] | Weak to moderate | No multi-week venting study exists |
| Dated observations, not traits | Memory profiles raised agreement sycophancy +16 to +45 points in 3 of 5 models, none in GPT-5.1 (Jain et al., CHI 2026) [M]. Believed self-labels changed physiology (Turnwald 2019) [A]. People prefer feedback that confirms their self-view (self-verification) [A] | Moderate | Model-dependent; labeling evidence is adjacent |
| Judge by outcomes outside the chat | Progress monitoring d = 0.40 [0.32, 0.48], larger when recorded or reported (Harkin 2016) [A] | Moderate | Mostly health goals |

**What does not work as hoped:**
- Growth-mindset messages for adults: d ≈ 0.08, null for adults [A].
- Motivational interviewing versus other active treatments: g = 0.09 [A].

Insight and encouragement alone are weak levers.
