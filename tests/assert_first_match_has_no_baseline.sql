-- A player's first extracted match has nothing to compare against, so every
-- delta column must be null rather than zero.
select
    participant_key,
    metric_name,
    baseline_mean,
    z_score,
    delta_from_baseline
from {{ ref('fct_player_match_deltas') }}
where match_sequence_number = 1
  and (
      baseline_mean is not null
      or z_score is not null
      or delta_from_baseline is not null
  )
