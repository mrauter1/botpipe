# revised_request.md
Complete the remaining route-schema enforcement work from the standalone handoff migration.

The implemented route-helper/GLOBAL/`outcome.route_fields` migration is largely in place, but two material gaps remain:

1. Route payload and route-fields JSON-schema mappings must stay runtime-enforced in all supported environments.
   The current compiler drops to metadata-only when raw JSON Schema route contracts are used without the optional `jsonschema` package, which lets invalid scripted/rendered provider outcomes pass. Fix this so custom route `payload_schema` and `route_fields_schema` mappings are always validated at runtime, or compilation fails clearly instead of silently weakening validation.

2. Structured-output-capable provider backends must receive the generated provider response schema.
   The engine already builds canonical route-discriminated `response_schema` objects, but current runtime transports do not pass them through to the backend and rely only on prompt text. Wire the generated schema into supported transports/backends, and keep an explicit documented fallback path for unsupported backends. The fallback may relax provider-side generation only; it must not weaken post-parse route legality, payload validation, or route-fields validation.

Required follow-up coverage:

- Add regression tests proving raw JSON-schema route contracts are enforced for both scripted/fake providers and rendered providers.
- Add transport/backend coverage proving the canonical route-discriminated schema, or its recorded simplified fallback, is actually handed to structured-output-capable providers.
- Keep existing compatibility behavior for `ControlRoutes(question=...)` lowering and legacy top-level `question` / `reason` parsing unless it conflicts with the fixes above.
