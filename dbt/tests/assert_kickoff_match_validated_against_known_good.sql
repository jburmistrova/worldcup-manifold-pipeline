-- Singular test: returns any rows that violate the assertion. 0 rows = pass.
-- For every market where Manifold's own sports_start_at already exists, the
-- matcher's openfootball-derived kickoff time must agree exactly. This is
-- the validation gate ADR-0008 requires before trusting the same matching
-- logic on the 102 Mega-Market answers, which have no independent ground
-- truth to check against. If this ever fails, the right response is to
-- narrow the match patterns further, not relax this test.
select *
from {{ ref('int_market_kickoff_times') }}
where answer_id is null
  and manifold_kickoff_at is not null
  and manifold_kickoff_at != openfootball_kickoff_at
