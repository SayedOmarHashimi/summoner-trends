-- One row per player per match: the grain every downstream trend model builds
-- on. Metrics are descriptive counts, rates, and team shares — no rating,
-- ranking, or grade is derived here or anywhere downstream.
{{ config(materialized='table') }}

with metrics as (

    select * from {{ ref('int_participant_metrics') }}

),

players as (

    select puuid, riot_id from {{ ref('dim_players') }}

)

select
    m.participant_key,
    m.match_id,
    m.puuid,
    p.riot_id,
    m.team_id,
    m.team_position,
    m.champion_id,
    m.champion_name,
    m.champion_level,

    m.queue_id,
    m.patch,
    m.game_start_at,
    cast(m.game_start_at as date)   as game_date,
    m.game_duration_seconds,
    m.game_duration_minutes,

    -- Raw counts
    m.kills,
    m.deaths,
    m.assists,
    m.creep_score,
    m.gold_earned,
    m.gold_spent,
    m.damage_to_champions,
    m.damage_taken,
    m.damage_to_objectives,
    m.vision_score,
    m.wards_placed,
    m.wards_killed,
    m.control_wards_bought,

    -- Derived rates
    m.kda_ratio,
    m.kda_ratio_perfect_adjusted,
    m.cs_per_minute,
    m.gold_per_minute,
    m.damage_per_minute,
    m.vision_score_per_minute,

    -- Team shares
    m.damage_share,
    m.gold_share,
    m.vision_share,
    m.kill_participation,

    -- Gold efficiency
    m.damage_per_gold,
    m.gold_spent_share,

    -- Outcome
    m.is_win,
    case when m.is_win then 'win' else 'loss' end as match_result,
    m.ended_in_early_surrender,

    m._extracted_at
from metrics m
left join players p on m.puuid = p.puuid
where m.queue_id in ({{ var('included_queue_ids') | join(', ') }})
