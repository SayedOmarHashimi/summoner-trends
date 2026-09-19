-- Rolling averages and expanding percentiles of a player's own metrics across
-- their match history. This is the trend-line source: it describes movement
-- over time and makes no judgement about the player.
{{ config(materialized='table') }}

{% set window_size = var('rolling_window_matches') %}
{% set trend_metrics = [
    'kda_ratio_perfect_adjusted',
    'cs_per_minute',
    'gold_per_minute',
    'damage_per_minute',
    'vision_score_per_minute',
    'damage_share',
    'gold_share',
    'kill_participation',
    'damage_per_gold'
] %}

with sequenced as (

    select * from {{ ref('int_player_match_sequence') }}

),

rolling as (

    select
        participant_key,
        match_id,
        puuid,
        champion_id,
        champion_name,
        team_position,
        queue_id,
        patch,
        game_start_at,
        match_sequence_number,
        player_match_count,
        is_win,

        {% for metric in trend_metrics %}
        {{ metric }},
        avg({{ metric }}) over (
            partition by puuid
            order by match_sequence_number
            rows between {{ window_size - 1 }} preceding and current row
        ) as {{ metric }}_rolling_avg,
        avg({{ metric }}) over (
            partition by puuid
            order by match_sequence_number
            rows between unbounded preceding and current row
        ) as {{ metric }}_career_avg,
        percent_rank() over (
            partition by puuid
            order by {{ metric }}
        ) as {{ metric }}_career_percentile,
        {% endfor %}

        -- Rolling win rate is a descriptive frequency, not a rating.
        avg(case when is_win then 1.0 else 0.0 end) over (
            partition by puuid
            order by match_sequence_number
            rows between {{ window_size - 1 }} preceding and current row
        ) as win_rate_rolling,

        count(*) over (
            partition by puuid
            order by match_sequence_number
            rows between {{ window_size - 1 }} preceding and current row
        ) as matches_in_window

    from sequenced

)

select
    *,
    {{ window_size }}                               as rolling_window_matches,
    matches_in_window = {{ window_size }}           as is_full_window
from rolling
