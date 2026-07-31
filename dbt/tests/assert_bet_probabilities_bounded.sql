-- Singular test: returns any rows that violate the assertion. 0 rows = pass.
-- prob_before/prob_after are probabilities and must be within [0, 1].
select *
from {{ ref('stg_manifold_bets') }}
where prob_before < 0 or prob_before > 1
   or prob_after < 0 or prob_after > 1
