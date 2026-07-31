-- Singular test: returns any rows that violate the assertion. 0 rows = pass.
select *
from {{ ref('mart_trade_calibration') }}
where prob_trade < 0 or prob_trade > 1
   or prob_bucket < 0 or prob_bucket > 0.9
