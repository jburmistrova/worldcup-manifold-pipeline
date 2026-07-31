-- Singular test: returns any rows that violate the assertion. 0 rows = pass.
select *
from {{ ref('int_market_implied_probability') }}
where prob_vwap_running < 0 or prob_vwap_running > 1
