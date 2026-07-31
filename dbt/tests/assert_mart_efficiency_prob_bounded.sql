-- Singular test: returns any rows that violate the assertion. 0 rows = pass.
select *
from {{ ref('mart_market_efficiency') }}
where predicted_prob < 0 or predicted_prob > 1
   or prob_bucket < 0 or prob_bucket > 0.9
