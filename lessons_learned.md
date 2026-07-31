# Lessons Learned

Generalizable takeaways from this project — distinct from `docs/decisions/` (which records *what* was decided and why, for this project specifically). This is about transferable methodology worth carrying into other work, including interview conversations about how I debug, not just what I built.

## Test your explanation, don't just believe the plausible one (2026-07-31)

**What happened:** found that Manifold's search results seemed to be missing a whole category of markets (sports-linked ones). The obvious, plausible explanation was already sitting right there — we'd *just* fixed a real pagination-instability bug (ADR-0006, duplicate markets from unstable relevance ranking). It would have been easy to assume "same bug, different symptom" and move on.

**What actually happened instead:** tested that exact hypothesis directly — ran 5 independent full pagination sweeps and checked whether the missing markets showed up in some sweeps but not others (which is what instability would look like). They didn't. Every sweep returned the identical result, zero variance. The obvious explanation was wrong.

That "failed" test wasn't wasted effort — ruling out the plausible-but-wrong explanation was what forced isolating the real variable (page size, `limit`), which was the actual cause (ADR-0007). If I'd shipped a fix based on the first explanation (more retries, more sweeps), it wouldn't have changed anything, and the real bug — silently missing 37% of the dataset — would still be there, undetected, because the fix would have "worked" by coincidence of not breaking anything, while not actually fixing the real problem.

**The generalizable lesson:** when a bug looks like one you've already seen, that's exactly when to be most suspicious of pattern-matching instead of testing. A quick, direct test that isolates one variable at a time (here: hold everything constant, vary only `limit`) is cheap compared to shipping a fix that doesn't address the real cause. "I ran a test and it disproved my first theory" is a *good* debugging story, not a failed one — it's evidence of a real investigation, not a guess that happened to work.
