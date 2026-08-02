-- Singular test: returns any rows that violate the assertion. 0 rows = pass.
-- prob is only present for BINARY markets. MULTIPLE_CHOICE markets carry it
-- per-answer instead (see stg_manifold_market_answers), so prob is legitimately
-- NULL for those, and NULL fails neither side of this comparison (correct).
select *
from {{ ref('stg_manifold_markets') }}
where prob < 0 or prob > 1
