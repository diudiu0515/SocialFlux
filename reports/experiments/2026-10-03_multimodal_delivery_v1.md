# Multimodal delivery v1

Date: 2026-10-03

## Scope

The delivery plan covers all 200 active state-v3 scenarios without changing
latent state, rollout responses, or Gate thresholds:

- GPT50: 50 scenarios.
- Claude150: 150 scenarios.

Each scenario has one deterministic fictional identity shared by both video
lanes:

1. Response-neutral online cues selected by real four-dimensional state
   crossings. These clips contain synchronized nonverbal audio but no speech or
   mouthing, because the future public response is unknown at generation time.
2. Response-conditioned talking heads for recorded accepted trajectories. Each
   clip speaks one exact public environment response with reviewed phoneme-level
   lip synchronization.

The final render target is 720p, 16:9, with audio, no watermark, and no visible
text. Human review remains mandatory and pending; no generated asset is marked
runtime-ready before technical validation, review, hosting, and URL finalization.

## Designed coverage

| Batch | Scenarios | Online cue designs | Talking-head slots | Accepted trajectories | Source nodes bound |
| --- | ---: | ---: | ---: | ---: | ---: |
| GPT50 | 50 | 326 | 200 | 31 | 124 |
| Claude150 | 150 | 966 | 600 | 97 | 388 |
| Total | 200 | 1,292 | 800 | 128 | 512 |

The remaining 288 talking-head slots belong to 72 scenarios without an accepted
trajectory. They remain `pending_accepted_trajectory`; no rejected rollout or
invented public line is used to fill them.

## Corrected delivery defects

- The old talking-head prompt did not carry the deterministic scenario
  appearance, wardrobe, background, or camera into the request.
- The old request wrote `continuity_reference`, while the Seedance queue reads
  `reference_video_file`; the visual identity reference was therefore ignored.
- The v3 delivery request now writes the provider-consumed reference field,
  includes the same scenario identity in the full prompt, requires exact spoken
  content and lip synchronization, and preserves the original public-only
  leakage constraints.
- The online finalizer now writes beside the explicitly selected manifest rather
  than into the legacy queue and can enforce a minimum delivery height.

## Existing asset reuse

Fifty old online assets have an exact semantic request match: 47 GPT and 3
Claude. All have one audio stream, but all are 864x496. They are retained only as
identity references and low-cost previews. None meets the 720p delivery line, so
the final-resolution reuse count is zero.

The four legacy generated GPT talking-head clips do not meet the v3 identity
continuity contract and are not counted as final assets.

## External generation boundary

All 512 source nodes in accepted trajectories contain Chinese public responses.
The user explicitly authorized sending only each accepted rollout's public
`environment_response` and `observable_expression` to the configured GPT route
for English video rendering. Private state, deltas, scores, thresholds, Gate
answers, and benchmark answers are not included in that payload. A regression
check confirms each cached source has exactly those two public keys.

GPT adaptation is complete: 124/124 nodes passed the unchanged English-line and
observable-micro-action validators. Claude adaptation is resumable and active;
successful results are atomically cached. Transport timeouts receive at most
three bounded retries. The output cap was raised from 500 to 800 tokens only to
avoid truncated JSON; the prompt and validation rules were not weakened.

The manifest distinguishes logical adaptation count from physical provider-call
count. Historical failover calls created before accounting was corrected are
reported as unavailable rather than incorrectly reported as zero.

## Talking-head pilot

The first GPT v3 pilot is `GPT50_002`, turn `t1`. Its exact adapted English line
is bound into both the prompt and audio contract, with the scenario's generated
identity anchor used as the reference video.

- Structural result: pass.
- Duration: 13.088 seconds.
- Video: H.264, 1280x720, 24 fps.
- Audio: one AAC stereo stream at 32 kHz.
- Human identity, exact-speech, lip-sync, expression, factual-consistency, and
  private-state-leakage review: pending.

The talking-head finalizer now requires an audio stream and the manifest's 720p
minimum in addition to the existing duration and video checks.

## Review packet cardinality

The configured talking-head review target remains 40 videos. The previous
sampler selected at most one item per accepted scenario, which capped GPT at 31
and made the unchanged 40-video machine threshold unreachable. The corrected
sampler first covers every accepted scenario, then fills deterministically from
the remaining accepted nodes. GPT now has 40 review items; no threshold was
lowered and no successful sample was cherry-picked.

## Evidence paths

- GPT manifest: `data/gpt50/experiment/multimodal_delivery_v1/delivery/manifest.json`
- Claude manifest: `data/claude150_v1/multimodal_delivery_v1/delivery/manifest.json`
- Per-scenario packages: each batch's `multimodal_delivery_v1/delivery/packages/`
- Online generation queues: each batch's
  `multimodal_delivery_v1/online_multimodal/`
- Talking-head generation queues and isolated review evidence: each batch's
  `multimodal_delivery_v1/talking_head/`
- Delivery config: `configs/multimodal_delivery.json`
- Current talking-head prompt: `prompts/talking_head_generation_v4.md`; v3 delivery evidence remains archived unchanged.

## Verification

- 200 package files exist.
- All 1,292 online cue designs have at least one concrete state-derived
  activation rule.
- All 512 accepted source nodes have a non-empty public response.
- All package identity IDs are scenario-scoped.
- Four 720p anchors and ten dependent event-family clips were generated for
  bounded validation. All 14 passed the machine screen: 1280x720, 24 fps, H.264,
  one AAC stereo audio stream, and approximately 4.1 seconds.
- GPT50_001 and CF150_001 each retained the same realized person, wardrobe,
  background, and camera across all six generated event families. This was a
  machine-assisted visual spot check, not a human attestation.
- GPT anchor generation completed its first pass at 43/50. A bounded replacement
  pass recovered five of seven copyright-policy failures, producing 48/50 final
  scenario anchors. The two remaining provider failures stay in the denominator
  and are not replaced by selected successes.
- Claude anchor generation remains active. Provider policy failures remain
  recorded and successful assets are finalized incrementally.
- The browser review page supports both `/multimodal?batch=gpt` and
  `/multimodal?batch=claude`, with batch-isolated review drafts, state-derived
  trigger conditions, and separate per-asset checklists for nonverbal state
  videos versus talking-head speech. The GPT pilot is served by a range-enabled
  `/talking-video/gpt/...` URL and remains `pending` for human review.
- Focused multimodal queue, online-asset, evidence-isolation, terminal-failure,
  prompt-catalog, and multimodal web regression suite: 52 tests passed. The
  talking-head browser packet
  regression also verifies that private consistency fields are not exposed.
- Human review status: pending.

## Review UI and natural-voice v4 update

The review page now presents the two delivery lanes explicitly. Every online
nonverbal card permanently shows its state family, state variable, direction,
threshold expression, and the separate offline replay evidence. Reviewers can
filter the page to state-trigger or talking-head assets. Talking-head cards show
their trajectory, turn, importance score/reasons, exact line, and prompt version.

`talking_head_generation_v4` is the current request prompt. It preserves the
exact public English line while requiring connected phrasing, natural
coarticulation, semantic emphasis, and punctuation-sensitive micro-pauses. It
explicitly rejects synthetic monotone, announcer cadence, uniformly timed
pauses, and word-by-word recitation. Existing v3 delivery evidence is unchanged
and remains compatible.

GPT50_002 t1 was regenerated as an isolated v4 comparison pilot:

- Technical screen: pass.
- Duration: 13.073 seconds; 1280x720; H.264; 24 fps.
- Audio: one AAC stereo stream at 32 kHz.
- Live review source: `talking_head_generation_v4`.
- Human exact-speech, lip-sync, voice-naturalness, identity, expression, and
  factual-consistency review: pending; no model review is counted as human.

The Claude queue retry reused 386 validated public adaptations and retried only
the two strict-validation failures. Both retries passed without weakening the
validators. The resulting Claude v4 request queue contains 388 requests from 97
accepted trajectories; video API generation has not yet been scaled for that
