-- One row per tracked account. PUUID is the stable key; Riot IDs can change,
-- so the name columns reflect the most recent extraction.
with summoners as (

    select * from {{ ref('stg_summoners') }}

),

mastery as (

    select
        puuid,
        count(*)                as champions_with_mastery,
        sum(mastery_points)     as total_mastery_points,
        max(last_played_at)     as last_mastery_play_at
    from {{ ref('stg_champion_mastery') }}
    group by 1

),

activity as (

    select
        puuid,
        count(*)            as matches_extracted,
        min(game_start_at)  as first_match_at,
        max(game_start_at)  as last_match_at
    from {{ ref('int_participant_metrics') }}
    group by 1

)

select
    s.puuid,
    s.riot_id,
    s.riot_id_game_name,
    s.riot_id_tagline,
    s.platform,
    s.summoner_level,
    s.profile_icon_id,
    coalesce(a.matches_extracted, 0)        as matches_extracted,
    a.first_match_at,
    a.last_match_at,
    coalesce(m.champions_with_mastery, 0)   as champions_with_mastery,
    coalesce(m.total_mastery_points, 0)     as total_mastery_points,
    s._extracted_at
from summoners s
left join mastery m on s.puuid = m.puuid
left join activity a on s.puuid = a.puuid
