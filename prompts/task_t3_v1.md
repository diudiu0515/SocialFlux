# SocialFlux T3 Counterfactual State Transition Prediction v1

Purpose: predict consequences of 2–4 plausible free-form candidate actions branching from one real observable checkpoint.

Main T3 input includes target character, complete observable history, current observation, candidate actions, and horizon. It never includes current latent state; oracle state is allowed only in a separately identified ablation.

For every candidate and selected state, predict schema-defined semantic direction probabilities for immediate effect and delayed effect. Default delayed horizon is five interaction turns, maximum ten. All branches start from the same checkpoint and use the same free-form continuation-model protocol and horizon.

Do not use private state, appraisal, actual future branch observations/video, hidden intention, trigger logic, or author metadata. Internally verify candidate count, common checkpoint, common protocol, common horizon, and observable evidence IDs. Return JSON only according to schemas/task_t3_output.schema.json.

T3 instance:
{{payload_json}}
