-- Team-level totals used as denominators for share metrics (damage share,
-- kill participation, gold share). Computed from participants rather than the
-- teams array so every denominator matches the numerator's source exactly.
with participants as (

    select * from {{ ref('stg_match_participants') }}

),

team_totals as (

    select
        match_id,
        team_id,
        sum(kills)                as team_kills,
        sum(deaths)               as team_deaths,
        sum(assists)              as team_assists,
        sum(damage_to_champions)  as team_damage_to_champions,
        sum(damage_taken)         as team_damage_taken,
        sum(gold_earned)          as team_gold_earned,
        sum(creep_score)          as team_creep_score,
        sum(vision_score)         as team_vision_score,
        count(*)                  as team_participant_count
    from participants
    group by 1, 2

)

select * from team_totals
