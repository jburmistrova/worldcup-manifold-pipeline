# ADR-0010: Polymarket verified as an eligible future data source, not yet integrated

**Status:** Accepted
**Date:** 2026-08-02

## Context

Considered whether comparing Manifold (play-money) to Polymarket (real-money) could answer a genuinely different question than anything built so far: are people more "fast and loose" with fake money than real money, visible as worse calibration or more volatile pricing on the play-money side. Before writing any code against it, checked Polymarket's actual terms the same way ADR-0001 checked Kalshi's and ADR-0008 checked openfootball's, not assuming "public API" or "other people already do this on GitHub" meant it was actually permitted.

**Search-engine snippets and a third-party mirror weren't good enough.** Polymarket's real Terms of Use page (`polymarket.com/tos`) is a client-rendered app that couldn't be fetched directly; search results surfaced a paraphrase suggesting a blanket "personal, non-commercial use" restriction with no API carve-out, different from what the primary document actually says. Read the real PDF directly (user-provided) before concluding anything, the same standard as reading Kalshi's actual Developer Agreement rather than trusting a summary of it.

**Checked whether "publish analysis only, not raw rows" would sidestep any restriction, since that's a real, common way projects try to de-risk this.** It doesn't, on its own: Polymarket's Terms define "Data" broadly enough to cover it regardless.

**Found real, cautionary counter-evidence before concluding anything, not just supporting evidence.** A public GitHub project (`jon-becker/prediction-market-analysis`) republishes 7.68M markets and 72.1M raw Kalshi and Polymarket trades, with no visible acknowledgment, license note, or documented permission from either platform. That's not validation that the practice is fine, someone doing something openly without visible authorization could just as easily mean it's unenforced, not that it's permitted. Kalshi's own terms (ADR-0001) already prohibit exactly what that project does with Kalshi's data specifically, so its existence argues for reading Polymarket's actual terms directly, not for skipping that step.

## Decision

**Polymarket is eligible as a future data source, based on reading the actual Terms of Use PDF directly**, not a summary. The operative clause, quoted directly:

> "Access or use any data, content, or information contained on our Site... directly or through an API, or any other means... whether in raw, derived, aggregated, or anonymized form (the "Data") if you are (i) a non-retail, professional entity that engages in capital markets activities (e.g., brokerage, market making, proprietary trading...), including but not limited to broker-dealers... hedge funds... financial technology companies, banks... (each, a "Capital Market Client"), or (ii) a market data distributor... unless otherwise agreed to in writing by us"

This restricts *who* can access the Data (raw, derived, or aggregated, all three explicitly named), not *what form* published output takes. The restriction targets professional financial entities and market data distributors specifically; a personal, non-commercial research project is neither. A separate clause bars selling or redistributing the Data *to* a Capital Market Client or market data distributor, commercial resale to institutional clients, not publishing your own analysis publicly. The API itself is treated as a normal, contemplated access method elsewhere in the document ("connecting via an API" is listed alongside using the site directly), and the anti-scraping clause ("data mining tools, robots, crawlers... to scrape") most plausibly targets unauthorized tools bypassing the documented API, not the API as provided, though that specific reading wasn't confirmed by an explicit carve-out in the text.

## Consequences

**Gained:** confirmation that Polymarket's terms don't block this project's actual use case (personal, non-commercial, public), a materially different answer than Kalshi's, reached the same way, by reading the primary document rather than inferring from what other public repos happen to do.

**Not resolved, flagged rather than guessed at:** a separate "Restricted Jurisdiction" section (naming the UK, several EU countries, and others) limits access to "Technology Features" for people in those jurisdictions, with an exception for "Content Features" (described as "news and information about global current events"). Whether pulling market/trade data via the API counts as one or the other isn't clear from the text itself, and depends on the accessing jurisdiction, unlike the Capital-Market-Client question, this wasn't fully resolved by this reading.

**Deliberately not attempted here:** no ingestion, matching, or comparison logic has been built against Polymarket. This ADR only clears the data-source-eligibility question ADR-0001 established as a precondition, the same order of operations, source cleared before any code gets written against it, not after.
