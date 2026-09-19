-- Joins participants to their match and team context and derives the per-match
-- rate metrics. Everything here is descriptive: counts, rates, and shares.
with participants as (

    select * from {{ ref('stg_match_participants') }}

),

matches as (

    select * from {{ ref('stg_matches') }}

),

team_totals as (

    select * from {{ ref('int_match_team_totals') }}

),

joined as (

    select
        p.participant_key,
        p.match_id,
        p.puuid,
        p.participant_id,
        p.team_id,
        p.champion_id,
        p.champion_name,
        p.champion_level,
        coalesce(nullif(p.team_position, ''), p.individual_position) as team_position,

        m.queue_id,
        m.patch,
        m.platform,
        m.game_start_at,
        m.game_duration_seconds,
        m.game_duration_minutes,

        p.kills,
        p.deaths,
        p.assists,
        p.damage_to_champions,
        p.damage_taken,
        p.damage_to_objectives,
        p.gold_earned,
        p.gold_spent,
        p.creep_score,
        p.vision_score,
        p.wards_placed,
        p.wards_killed,
        p.control_wards_bought,
        p.is_win,
        p.ended_in_early_surrender,

        t.team_kills,
        t.team_damage_to_champions,
        t.team_gold_earned,
        t.team_vision_score,

        p._extracted_at
    from participants p
    inner join matches m
        on p.match_id = m.match_id
    inner join team_totals t
        on p.match_id = t.match_id
       and p.team_id = t.team_id

),

derived as (

    select
        *,

        -- KDA ratio. Riot's own convention treats a deathless game as
        -- "perfect", so deaths of 0 falls back to 1 rather than null.
        {{ safe_divide('kills + assists', 'nullif(deaths, 0)') }} as kda_ratio,
        cast(kills + assists as numeric)
            / greatest(deaths, 1)                                as kda_ratio_perfect_adjusted,

        -- Per-minute rates. Very short games (remakes) are excluded downstream.
        {{ per_minute('creep_score', 'game_duration_minutes') }}          as cs_per_minute,
        {{ per_minute('gold_earned', 'game_duration_minutes') }}          as gold_per_minute,
        {{ per_minute('damage_to_champions', 'game_duration_minutes') }}  as damage_per_minute,
        {{ per_minute('vision_score', 'game_duration_minutes') }}         as vision_score_per_minute,

        -- Share metrics, expressed as fractions of the player's own team.
        {{ safe_divide('damage_to_champions', 'team_damage_to_champions') }} as damage_share,
        {{ safe_divide('gold_earned', 'team_gold_earned') }}                 as gold_share,
        {{ safe_divide('vision_score', 'team_vision_score') }}               as vision_share,
        {{ safe_divide('kills + assists', 'team_kills') }}                   as kill_participation,

        -- Gold efficiency: damage to champions produced per gold earned.
        {{ safe_divide('damage_to_champions', 'gold_earned') }}              as damage_per_gold,
        {{ safe_divide('gold_spent', 'gold_earned') }}                       as gold_spent_share

    from joined

)

select * from derived
