# Algorithm and ML audit

LockLens intentionally contains no ML model. Its core algorithms are deterministic and evidence-oriented:

- SQL guard: lexical single-statement parsing plus allow/deny checks. It is defense in depth, not a SQL sandbox.
- Schedule engine: concurrent worker threads, named barriers, cancellation, timeouts, and ordered event recording.
- Analyzer: correlates SQLSTATEs, repeated reads, final invariant probes, and serial replay results to produce scoped findings.
- Counterfactual comparison: applies one documented mechanical change, runs baseline/candidate, and compares persisted metrics and findings.

Serial permutations grow factorially with transaction count; configuration caps transaction count at four. The comparison engine makes only an indicative single-run conclusion and records that limitation.
