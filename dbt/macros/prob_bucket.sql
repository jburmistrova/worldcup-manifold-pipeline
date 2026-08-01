{#
    Decile bucket for a probability expression: 0.0-0.1, 0.1-0.2, ... 0.9-1.0,
    matching how Manifold's own published platform-wide calibration is
    bucketed (see docs/results.md). Extracted here because both
    mart_market_efficiency and mart_trade_calibration need the exact same
    bucketing rule applied to two different underlying expressions
    (predicted_prob vs. (prob_before + prob_after) / 2) -- duplicating the
    formula risked the two marts quietly drifting to different bucket
    definitions if one got tweaked and not the other.
#}
{% macro prob_bucket(prob_expression) %}
    least(floor(({{ prob_expression }}) * 10) / 10, 0.9)
{% endmacro %}
