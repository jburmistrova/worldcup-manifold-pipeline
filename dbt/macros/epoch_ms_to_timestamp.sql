-- Cross-adapter epoch-milliseconds-to-timestamp conversion. Manifold's raw
-- timestamps (createdTime, closeTime, resolutionTime) are epoch
-- milliseconds. DuckDB has a direct epoch_ms() function for this; Postgres
-- doesn't, its to_timestamp() takes epoch *seconds* and returns a
-- timestamptz, not a naive timestamp. Cast to timestamp at the end so both
-- adapters agree on a plain (timezone-naive, UTC) value, matching what
-- Manifold's epoch-ms fields already represent.
{% macro epoch_ms_to_timestamp(field) %}
    {{ return(adapter.dispatch('epoch_ms_to_timestamp', 'worldcup_pipeline')(field)) }}
{% endmacro %}

{% macro default__epoch_ms_to_timestamp(field) %}
    epoch_ms({{ field }})
{% endmacro %}

{% macro postgres__epoch_ms_to_timestamp(field) %}
    cast(to_timestamp({{ field }} / 1000.0) as timestamp)
{% endmacro %}
