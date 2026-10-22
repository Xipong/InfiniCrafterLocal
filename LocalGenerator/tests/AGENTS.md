# Behavioral test contracts

Read the root `AGENTS.md` and `docs/development/TESTING_RU.md` first. These rules
apply to test changes, not to production behavior.

- Start with the observable promise: delivered wire/bytes, permitted mutation,
  failure/refusal, persisted state, or real consumer output. Mock external I/O at
  its boundary; do not replace the owner whose behavior the test claims to prove.
- Compare independent deliveries by identity, **including multiplicity**, payload
  and provenance. Use `Counter` for hashable records or sort complete records.
  A plain set/dict can hide duplicate delivery. Exercise another valid ordering
  when removing an accidental ordering assertion.
- Preserve order when it is the contract: dependency readiness before use,
  persistence before acknowledgement, retry/failover, cancellation/join before
  return, authored arrays with positional meaning, and literal wire identity.
- Synchronize concurrent tests on observable events or existing controlled-clock
  fixtures. A short sleep is not proof a worker reached a particular state;
  elapsed wall-clock thresholds measure host load as well as behavior. Timeouts
  remain bounded deadlock guards. Always release and join workers in teardown,
  including assertion failures; collect failures on the test thread.
- For timeout/rate policy, advance the existing fake clock and assert admission,
  attempts, cleanup and error type. Keep complementary real transport tests;
  do not replace all end-to-end deadline coverage with mocked time.
- Use `tmp_path` and restoring fixtures (`monkeypatch`, context managers). Do not
  read operator credentials or mutate a real home/config/cache. Run the existing
  shard runner for final Python acceptance; do not add broad retries, xfails or
  process isolation to hide unexplained failures.
- Exact C# text is not runtime coverage. Use registered native checks for native
  behavior. Keep real source-language/security policies and localization data
  checks; remove source snapshots only after mapping their meaningful invariant
  to an executable test. Report native checks as not run when prerequisites are
  absent, never as passed because a source scan passed.
- When relaxing an accidental constraint, show that missing/duplicate/wrong-owner
  delivery, overbroad repair permissions, or another relevant real defect still
  fails. No production changes, fixture golden rewrites, or assertion deletion
  merely to make a test green.
- Delete redundant tests when the retained executable case exercises the same
  setup and guarantees (or a strict superset). Record that mapping and check a
  relevant broken behavior still fails. Similar names, identical coarse-runner
  wrappers, or assertions on opposite sides of a state change are not duplicates.
- Never pre-normalize a test input to the desired result before calling the owner
  under test. Stub OS process/network boundaries, not the cleanup/delivery owner;
  fake process IDs must never reach real termination APIs on any platform.

Primary references consulted for this policy:
[pytest flaky tests](https://docs.pytest.org/en/stable/explanation/flaky.html),
[pytest monkeypatch](https://docs.pytest.org/en/stable/how-to/monkeypatch.html),
[Hermes test guidance](https://github.com/NousResearch/hermes-agent/blob/main/tests/AGENTS.md).
Hermes-specific retry/runner/platform conventions are not copied into IFC: IFC
already has its own offline bootstrap, targeted subprocess isolation and native
consumer runner.
