# Integrity Guardian — Documentation

| File | Contents |
|------|---------|
| [00_overview.md](00_overview.md) | What the system is, its role in AIEIC, technology stack, file map |
| [01_architecture.md](01_architecture.md) | Component diagram, per-message request flow, session lifecycle, storage layout, security |
| [02_api_reference.md](02_api_reference.md) | Every endpoint — method, path, request/response schemas, error codes |
| [03_data_models.md](03_data_models.md) | All enums, Pydantic models, and Cosmos DB document schemas with field descriptions |
| [04_classification_engine.md](04_classification_engine.md) | The LLM classifier — five categories, concept tags, decision rules, fail-safe behaviour |
| [05_reporting.md](05_reporting.md) | SESSION and POST_LAB reports — all fields, indicators, final_status logic |
| [06_analytics.md](06_analytics.md) | The faculty dashboard analytics endpoint — all response fields, student status logic |
| [07_configuration.md](07_configuration.md) | Environment variables, policy thresholds, Azure deployment, rate limiting |
| [08_local_development.md](08_local_development.md) | Setup, running the server, demo script, tests, common errors |
| [09_storage_layer.md](09_storage_layer.md) | CosmosIntegrityClient vs MemoryIntegrityClient, the interface contract, document design |
