-- Each match's metrics expressed relative to that player's OWN prior history:
-- a z-score and a percentile rank against the matches that came before it.
--
-- This is descriptive statistics, not evaluation. A z-score says "this game was
-- 1.4 standard deviations above your usual CS/min" — it is not a score, grade,
-- or rating, and nothing here ranks one player against another.
--
-- Grain: one row per participant per metric.
{{ config(materialized='table') }}

{% set delta_metrics = [
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

unpivoted as (

    {% for metric in delta_metrics %}
    select
        participant_key,
        puuid,
        match_id,
        champion_id,
        champion_name,
        team_position,
        queue_id,
        patch,
        game_start_at,
        match_sequence_number,
        is_win,
        '{{ metric }}'          as metric_name,
        cast({{ metric }} as double) as metric_value
    from sequenced
    {% if not loop.last %}union all{% endif %}
    {% endfor %}

),

baseline as (

    -- Prior matches only: the baseline never includes the match being compared,
    -- so a match cannot inflate the baseline it is measured against.
    select
        *,
        avg(metric_value) over (
            partition by puuid, metric_name
            order by match_sequence_number
            rows between unbounded preceding and 1 preceding
        ) as baseline_mean,
        stddev_samp(metric_value) over (
            partition by puuid, metric_name
            order by match_sequence_number
            rows between unbounded preceding and 1 preceding
        ) as baseline_stddev,
        count(metric_value) over (
            partition by puuid, metric_name
            order by match_sequence_number
            rows between unbounded preceding and 1 preceding
        ) as baseline_match_count
    from unpivoted

),

percentiles as (

    select
        current_match.participant_key,
        current_match.metric_name,
        {{ safe_divide(
            'count(prior.metric_value) filter (where prior.metric_value <= current_match.metric_value)',
            'nullif(count(prior.metric_value), 0)'
        ) }} as baseline_percentile_rank
    from baseline current_match
    left join baseline prior
        on current_match.puuid = prior.puuid
       and current_match.metric_name = prior.metric_name
       and prior.match_sequence_number < current_match.match_sequence_number
    group by 1, 2

)

select
    b.participant_key,
    b.puuid,
    b.match_id,
    b.champion_id,
    b.champion_name,
    b.team_position,
    b.queue_id,
    b.patch,
    b.game_start_at,
    b.match_sequence_number,
    b.is_win,

    b.metric_name,
    b.metric_value,
    b.baseline_mean,
    b.baseline_stddev,
    b.baseline_match_count,

    b.metric_value - b.baseline_mean                    as delta_from_baseline,
    {{ safe_divide('b.metric_value - b.baseline_mean', 'nullif(b.baseline_mean, 0)') }}
                                                        as pct_change_from_baseline,
    {{ safe_divide('b.metric_value - b.baseline_mean', 'nullif(b.baseline_stddev, 0)') }}
                                                        as z_score,
    p.baseline_percentile_rank,

    -- Below the minimum history threshold a baseline is too thin to describe
    -- anything, so callers should ignore the delta columns.
    b.baseline_match_count >= {{ var('min_baseline_matches') }} as has_sufficient_baseline

from baseline b
left join percentiles p
    on b.participant_key = p.participant_key
   and b.metric_name = p.metric_name
