with matches as (

    select * from {{ ref('stg_matches') }}

),

teams as (

    select
        match_id,
        max(case when is_win then team_id end) as winning_team_id
    from {{ ref('stg_match_teams') }}
    group by 1

)

select
    m.match_id,
    m.platform,
    m.queue_id,
    {{ queue_name('m.queue_id') }}  as queue_name,
    m.game_mode,
    m.game_type,
    m.map_id,
    m.game_version,
    m.patch,
    m.game_creation_at,
    m.game_start_at,
    m.game_end_at,
    cast(m.game_start_at as date)   as game_date,
    m.game_duration_seconds,
    m.game_duration_minutes,
    m.game_duration_seconds < 300   as is_probable_remake,
    t.winning_team_id,
    m._extracted_at
from matches m
left join teams t on m.match_id = t.match_id
