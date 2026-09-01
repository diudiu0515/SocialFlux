# EmoTree

EmoTree is a stateful social-interaction benchmark pipeline with observable/private state separation, fixed semantic deltas, controlled-policy validation, model-provider adapters, and T1/T2/T3 offline task construction.

## Repository map

- prompts/: versioned prompts and SHA-256 manifest
- configs/scenarios/: each scenario JSON plus a generated same-name Markdown explanation
- environment/: state, memory, appraisal, response, and termination components
- policies/ and providers/: policy interface and model-provider adapters
- rollout/ and offline/: trajectory logging and T1/T2/T3 instance extraction
- tasks/ and interactive_benchmark/: task schemas, conversion tools, and annotation utilities; legacy worlds are optional and currently removed
- build/: reproducible benchmark and pipeline outputs
- web/: read-only scenario and pipeline visualization website
- talkinghead_generation.md: state-triggered multimodal observation design

## Add or update a scenario

Every `configs/scenarios/scenario_NNN.json` must have a generated `scenario_NNN.md`. The Markdown explains story initialization, initial state/dynamics, action effects, observable expression, and video trigger thresholds.

~~~bash
python scripts/scenario_docs.py configs/scenarios/scenario_NNN.json
python scripts/scenario_docs.py --check
python -m scripts.run_pipeline --scenarios configs/scenarios --output build/pipeline_v1
~~~

The generator also rebuilds `configs/scenarios/manifest.json`. The pipeline refuses missing/stale Markdown or a manifest that does not match the scenario directory.

## Run the full pipeline

~~~bash
python -m scripts.run_pipeline   --scenarios configs/scenarios   --output build/pipeline_v1
~~~

The pipeline is configured for 10 scenarios and 120 candidate instances. Its full pipeline_v1 master trajectories are generated locally and ignored because they contain private environment fields; formal ground truth remains pending independent human annotation and adjudication.

The current scenarios also emit structured observable expression and spec-only Talking Head media events after state updates; trigger internals remain private.
Run the acceptance command to inspect trigger and trajectory evidence in build/pipeline_v1/acceptance_report.*. The automated gate covers all five criteria; the full-trajectory criterion also records whether formal human review is still pending.

## Run tests

~~~bash
python -m unittest discover -s tests -v
python -m unittest discover -s web/tests -v
python -m unittest discover -s interactive_benchmark/tests -v
~~~

## Run the scenario website

~~~bash
python web/server.py --host 127.0.0.1 --port 8000
~~~

The website is a read-only view of the current scenario configs and generated pipeline artifacts. It does not maintain a second environment or demo scenario.

## Task completion self-check

At the end of every project task, review self_check.md. Mark only fully evidenced items as [x]; retain every unfinished [ ] item and never delete existing TODO rows. Human-required items stay open until real reviewer records exist.

## Prompt change policy

Every fixed model-facing prompt belongs in prompts/ as a versioned Markdown file. New pipeline scenarios use `scenario_generation_v1`; paired prose is then generated deterministically from the saved JSON. Runtime code must read prompts through prompts/loader.py. After changing a prompt, update prompts/manifest.json and run all tests.

## Secrets

No GitHub credential or provider key belongs in this repository. Use a GitHub fine-grained personal access token or a repository deploy key created in your own GitHub account, and store provider secrets in local environment variables only. See .env.example for the local variable names.
