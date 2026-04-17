# ADR 007: Provider Protocol Design

Status: Final

Authoritative record: [ARCHITECTURE_DECISIONS.md](../../ARCHITECTURE_DECISIONS.md)
Topic: `10. Provider / Store Protocol Design`

Final decision:
- Providers, prompt registries, session stores, and checkpoint stores expose small typed contracts.
- The engine depends on those contracts, not on concrete adapter implementations.
- Filesystem and fake implementations prove replaceability and keep tests small.
- Workflow policy stays outside provider and store protocols.

Rejected shape:
- no Autoloop-specific helpers in provider/store interfaces
- no monolithic runtime service object
- no protocol surface that embeds workflow orchestration policy
