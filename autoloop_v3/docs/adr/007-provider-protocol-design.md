# ADR 007: Provider Protocol Design

Status: Final

Authoritative record: [ARCHITECTURE_DECISIONS.md](../../ARCHITECTURE_DECISIONS.md)
Topic: `10. Provider And Store Protocols`

Final decision:
- Providers and stores expose small typed protocols.
- Filesystem and fake implementations prove the protocols stay generic and replaceable.
- Workflow policy does not leak into provider or store interfaces.
- Generic session persistence may retain targeted wire-format compatibility such as legacy `thread_id`.

Rejected shape:
- no monolithic runtime service object
- no Autoloop-specific methods in generic protocols
- no provider/store surface that encodes workflow semantics
