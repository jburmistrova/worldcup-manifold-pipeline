# ADR-0008: Kickoff-time enrichment from openfootball, seeded and matched by strict pattern, not fuzzy text

**Status:** Accepted
**Date:** 2026-08-02

## Context

ADR-0007 found that Manifold's own `sportsStartTimestamp` field, a real, precise kickoff time, covers only a fraction of markets, closing off a full-dataset pre-kickoff calibration analysis (see `docs/results.md`'s "What would strengthen this"). Investigated whether an external football schedule could fill that gap.

**Data source check, same standard as ADR-0001.** `openfootball/worldcup.json` (GitHub) hosts the 2026 World Cup schedule with exact kickoff times (including UTC offset), team names, and final scores. License verified two ways, not just read off the README: GitHub's own license API reports `CC0-1.0` for the repository, and the actual `LICENSE.md` file confirms the full CC0 1.0 Universal public domain text, no restrictions on commercial use, redistribution, or publishing derived analysis. More permissive than Manifold's own terms.

**The real risk, raised directly before writing any matching code:** naively joining on team-name mentions in free text would produce false positives, not just missing data. A market like "Will Norway advance to the quarterfinals?" mentions a team name but isn't about any single game; attaching a kickoff time to it would be silently wrong, not just incomplete, and wrong-but-plausible-looking data is worse than an honest NULL.

**Investigated empirically before designing the join**, rather than assume the shape of the problem:

- All 108 markets carrying `sportsStartTimestamp` are `MULTIPLE_CHOICE` markets in one exact, structured format: `🇹🇳TUN vs 🇯🇵JPN [World Cup '26]` (flag emoji, 3-letter code, "vs," flag emoji, 3-letter code). Genuine single-match markets and the `sportsStartTimestamp` field are, in practice, nearly the same population, confirming the field is a real signal of market type, not sparse metadata on an otherwise-uniform set.
- **One more market is a genuine single-match question but doesn't share that format at all**: `"Argentina vs England: FIFA 2026 World Cup"`, full team names instead of codes, no flags, a different punctuation shape. Found only by checking coverage against the actual population (109 total match-shaped markets, not 108) rather than stopping once the first pattern's count looked plausible. Mattered because it's the actual gap this ADR exists to close, the 1 market genuinely missing `sportsStartTimestamp`, and because the fix is to add a second, equally strict pattern for this exact shape, not to loosen the first pattern until it happens to also catch this one. Confirmed the new pattern matches only this single market before adding it as its own branch.
- Every `MULTIPLE_CHOICE` market that doesn't fit that pattern is something structurally different, confirmed by reading the actual questions: prop bets, Ballon d'Or, other tournaments entirely (AFCON, Esports World Cup), and 5 "Mega-Market" round aggregators ("Round of 16," "Semi-Finals," etc.) whose top-level question isn't about one game at all.
- Those 5 Mega-Markets turn out to hold the real opportunity: 102 **answers** nested inside them, none carrying `sportsStartTimestamp` (the field isn't populated at answer level at all), but every one in a consistent, strict pattern: `"{Team A} beats {Team B} ⚽ {Month} {Day} ({time}) {Broadcaster}"`.
- No `BINARY` market carries `sportsStartTimestamp`, and none read as single-match questions ("Will Thomas Tuchel survive the 2026 World Cup?", "Will Iran officially withdraw..."). Confirmed by reading a sample directly rather than assuming from the type name alone.

That empirical pass turned "match against 621 markets" into a much smaller, bounded, safer target: 1 market and 102 answers, both already in a strict, predictable shape, not free text needing a fuzzy classifier.

## Decision

1. **Ingestion: dbt seed, not the raw-ingest + Spark pipeline.** The schedule is 104 rows, static, and will never change (the tournament is over). Running it through the machinery built for Manifold's large, paginated, retry-needing API would be the wrong tool for a completely different problem shape. Commit the schedule as `dbt/seeds/worldcup_schedule.csv`, load with `dbt seed`.
2. **New staging model** (`stg_worldcup_schedule`): pure rename + type conversion of the seed, same convention as every other staging model.
3. **New intermediate model** (`int_market_kickoff_times`): the actual matching logic lives here, not in staging (matching is business logic, not a rename) and not in a mart (it's reconstruction work, the same role `int_market_implied_probability` already plays). Matches only records whose text fits one of three strict patterns, kept as separate branches rather than one loosened pattern: the 108 code-format markets, the 1 full-name-format market, and the 102 Mega-Market answers. Anything that doesn't fit any of them, or matches ambiguously, gets no kickoff time rather than a guessed one.
4. **Validation before trusting the matcher on the unverified 102:** run it against the 108 markets that already carry `sportsStartTimestamp` first, and compare the matched openfootball kickoff time against Manifold's own value. Close agreement across nearly all 108 is the bar for trusting the same logic on the 102 answers, where there's no independent ground truth to check against.

## Consequences

**Gained:** kickoff-time coverage for 211 markets/answers that are actually single-match questions (109 markets, 102 answers), closing the specific gap ADR-0007 identified, without the false-positive risk a text-similarity or fuzzy-NLP match would carry.

**Deliberately not attempted:** no kickoff time gets attached to tournament-progression or outright markets (Golden Boot, "wins the tournament," "advances to the quarterfinals"). Not a limitation of the matcher, a correct reflection that those markets aren't about one game and shouldn't have one.

**Risk managed, and the result was better than the bar set for it:** the validation step required close agreement across nearly all 108 known-good markets before trusting the same logic on the 102 answers with no ground truth. The actual result: **exact agreement, 108 of 108, 0 seconds off**. That check is now a permanent dbt test (`assert_kickoff_match_validated_against_known_good.sql`), not a one-off, so it keeps validating on every future build rather than only at the moment this was built.

**Follow-up: `mart_pre_kickoff_calibration`, and a bug this ADR's work surfaced.** With validated kickoff times in place, the actual pre-kickoff calibration analysis ADR-0007 originally wanted is now built: `int_pre_kickoff_probability` finds each market/answer's implied probability from its last real trade strictly before kickoff, and `mart_pre_kickoff_calibration` compares that to the same outcome `mart_market_efficiency` uses at resolution time, for the 380 predictions where a validated kickoff time and a pre-kickoff trade both exist. Building it surfaced a real gap in `mart_market_efficiency` itself: most of the 109 clean-format World Cup markets are "single-select" `MULTIPLE_CHOICE` markets, where Manifold resolves the *market* to a winning `answer_id` and never sets a per-answer `resolution` field at all. The existing mart only checked the answer-level field, so it silently excluded these predictions, and 1,310 more like them platform-wide, since the mart was first built. Fixed by deriving the winner from the market's own `resolution` field when the answer-level one is absent. Full mechanism in `lessons_learned.md`, numbers in `docs/results.md`.
