# SocialFlux T1/T3 Checkpoint Extraction v1

You extract construction checkpoints from one complete observable SocialFlux trajectory. This is task construction, not task answering and not environment simulation.

Use only the supplied public history. Never infer hidden intention, latent values, appraisal, trigger thresholds, future events, or author metadata.

T1:
- select one or two checkpoints that genuinely require longitudinal evidence;
- use only allowed_target_state_ids;
- cite one to four real evidence turn IDs, none later than the checkpoint.

T3:
- select one checkpoint with at least five actual later turns and multiple locally executable strategies;
- future_turns_available must exactly equal the number of supplied turns strictly after that checkpoint;
- return null only when no valid five-turn window exists;
- do not invent candidate utterances or extend/shorten the trajectory.

Return JSON only, with exactly this structure and no additional keys:

{{output_schema_json}}

Public construction input:

{{payload_json}}
