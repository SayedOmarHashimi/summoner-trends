-- Rolling trends computed per champion, rather than across a player's whole
-- history.
--
-- This exists because you cannot get a per-champion view by filtering
-- fct_player_rolling_trends: the rolling average there is computed across all
-- of a player's matches in order, so a row for a given champion carries a
-- window that includes whatever else was played in between. Filtering would
-- show a champion's matches beside an average that is not that champion's.
--
-- Here the window partitions by champion, so every average describes only games
-- on that champion. Descriptive only — no rating, ranking, or grade.
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
        champion_match_sequence_number,
        player_champion_match_count,
        is_win,

        {% for metric in trend_metrics %}
        {{ metric }},
        avg({{ metric }}) over (
            partition by puuid, champion_id
            order by champion_match_sequence_number
            rows between {{ window_size - 1 }} preceding and current row
        ) as {{ metric }}_rolling_avg,
        avg({{ metric }}) over (
            partition by puuid, champion_id
            order by champion_match_sequence_number
            rows between unbounded preceding and current row
        ) as {{ metric }}_champion_avg,
        percent_rank() over (
            partition by puuid, champion_id
            order by {{ metric }}
        ) as {{ metric }}_champion_percentile,
        {% endfor %}

        avg(case when is_win then 1.0 else 0.0 end) over (
            partition by puuid, champion_id
            order by champion_match_sequence_number
            rows between {{ window_size - 1 }} preceding and current row
        ) as win_rate_rolling,

        count(*) over (
            partition by puuid, champion_id
            order by champion_match_sequence_number
            rows between {{ window_size - 1 }} preceding and current row
        ) as matches_in_window

    from sequenced

)

select
    *,
    {{ window_size }}                       as rolling_window_matches,
    matches_in_window = {{ window_size }}   as is_full_window
from rolling
