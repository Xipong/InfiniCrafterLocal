"""Bounded runtime authoring package.

Import the defining module directly: capability_registry (facts), program_schema
(shape), validator (Author admission), compiler (wire), technical_lowering
(receipts), repair.scope (permissions), repair.filter (frozen-first patch),
repair.validation (patch admission), wire_validator (persisted wire),
wire_views (read-only presentation facts).
Package import deliberately performs no eager imports or API re-exports.
"""
