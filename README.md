# EmoTree

EmoTree is a stateful social-interaction benchmark pipeline with observable/private state separation, fixed semantic deltas, controlled-policy validation, model-provider adapters, and T1/T2/T3 offline task construction.

## Repository map

- prompts/: versioned prompts and SHA-256 manifest
- environment/: state, memory, appraisal, response, and termination components
- policies/ and providers/: policy interface and model-provider adapters
- rollout/ and offline/: trajectory logging and T1/T2/T3 instance extraction
- worlds/ and tasks/: interactive story worlds, schemas, and task definitions
- build/: reproducible benchmark and pipeline outputs
- demo/: standalone on-policy interactive demo

## Run the full pipeline

~~~bash
python -m scripts.run_pipeline   --scenarios configs/scenarios   --output build/pipeline_v1
~~~

The current checked-in output contains 10 scenarios and 120 candidate instances. Formal ground truth remains pending independent human annotation and adjudication.

## Run tests

~~~bash
python -m unittest discover -s tests -v
python -m unittest discover -s demo/tests -v
python -m unittest discover -s interactive_benchmark/tests -v
~~~

## Run the demo

~~~bash
python demo/server.py
~~~

The participant view exposes only observable information. Researcher and replay views require the runtime debug token.

## Prompt change policy

Every fixed model-facing prompt belongs in prompts/ as a versioned Markdown file. Runtime code must read prompts through prompts/loader.py. After changing a prompt, update prompts/manifest.json and run all tests.

## Secrets

No GitHub credential or provider key belongs in this repository. Use a GitHub fine-grained personal access token or a repository deploy key created in your own GitHub account, and store provider/demo secrets in local environment variables only. See .env.example for the local variable names.
