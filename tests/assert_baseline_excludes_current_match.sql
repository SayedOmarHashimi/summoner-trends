-- The baseline a match is compared against must be built from PRIOR matches
-- only. If baseline_match_count ever equals the match's own sequence number,
-- the current match leaked into its own baseline.
select
    participant_key,
    metric_name,
    match_sequence_number,
    baseline_match_count
from {{ ref('fct_player_match_deltas') }}
where baseline_match_count <> match_sequence_number - 1
