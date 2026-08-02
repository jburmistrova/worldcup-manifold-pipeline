-- Cross-adapter timestamp cast for sportsStartTimestamp (ADR-0008), which
-- is either a well-formed ISO8601 string or NULL/absent in this dataset,
-- never malformed garbage (confirmed empirically, see int_market_kickoff_times).
-- DuckDB's try_cast returns NULL on a bad value instead of raising; Postgres
-- has no built-in equivalent. dbt-core's own safe_cast macro hits the same
-- wall and falls back to a plain cast, with its own comment admitting
-- "most databases don't support this function yet." A plain cast is safe
-- here in practice, since there's nothing malformed to catch, but it's a
-- real, honest divergence from DuckDB if that ever stopped being true:
-- Postgres would raise on a genuinely malformed value where DuckDB would
-- silently null it.
{% macro try_cast_timestamp(field) %}
    {{ return(adapter.dispatch('try_cast_timestamp', 'worldcup_pipeline')(field)) }}
{% endmacro %}

{% macro default__try_cast_timestamp(field) %}
    try_cast({{ field }} as timestamp)
{% endmacro %}

{% macro postgres__try_cast_timestamp(field) %}
    cast(nullif({{ field }}, '') as timestamp)
{% endmacro %}
