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
    epoch_ms(resolutionTime) as resolved_at
from {{ source('manifold_raw', 'markets') }}
