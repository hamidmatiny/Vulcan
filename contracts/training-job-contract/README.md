# Vulcan training-job contract

Backend-agnostic **TrainingJobSpec** / **TrainingJobResult** (ADR-010). Every backend under `training/*` accepts a schema-valid spec and emits a schema-valid result.

```bash
pip install -e "contracts/training-job-contract[dev]"
pytest -q --cov=vulcan_training_contract --cov-fail-under=65
```
