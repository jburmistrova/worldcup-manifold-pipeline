-- Singular test: returns any rows that violate the assertion. 0 rows = pass.
select *
from {{ ref('stg_manifold_market_answers') }}
where prob < 0 or prob > 1
   or prob_resolution < 0 or prob_resolution > 1
