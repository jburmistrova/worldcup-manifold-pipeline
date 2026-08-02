select
    contractId as market_id,
    id as answer_id,
    index as answer_index,
    text as answer_text,
    isOther as is_other,
    probability as prob,
    resolution,
    resolutionProbability as prob_resolution,
    volume,
    totalLiquidity as liquidity_total,
    {{ epoch_ms_to_timestamp('createdTime') }} as created_at,
    {{ epoch_ms_to_timestamp('resolutionTime') }} as resolved_at
from {{ source('manifold_raw', 'market_answers') }}
