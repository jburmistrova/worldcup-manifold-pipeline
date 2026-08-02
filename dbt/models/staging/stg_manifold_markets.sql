select
    id as market_id,
    question,
    slug,
    url,
    outcomeType as outcome_type,
    resolution,
    isResolved as is_resolved,
    probability as prob,
    volume,
    totalLiquidity as liquidity_total,
    epoch_ms(createdTime) as created_at,
    epoch_ms(closeTime) as closed_at,
    epoch_ms(resolutionTime) as resolved_at,
    -- present on 108 of 621 markets (sports-integrated markets only), a real
    -- precise kickoff time straight from Manifold, already ISO 8601, unlike
    -- the epoch-ms fields above. try_cast rather than cast: defensive
    -- against any future malformed value, returns NULL instead of erroring.
    try_cast(sportsStartTimestamp as timestamp) as sports_start_at
from {{ source('manifold_raw', 'markets') }}
