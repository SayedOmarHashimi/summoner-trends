-- One row per champion per match per team: picked or banned. Feeds the
-- champion meta aggregate.
with picks as (

    select
        p.match_id,
        m.patch,
        m.queue_id,
        p.champion_id,
        p.team_id,
        true            as was_picked,
        false           as was_banned,
        p.is_win        as is_win
    from {{ ref('stg_match_participants') }} p
    inner join {{ ref('stg_matches') }} m
        on p.match_id = m.match_id

),

bans as (

    select
        b.match_id,
        m.patch,
        m.queue_id,
        b.champion_id,
        b.team_id,
        false           as was_picked,
        true            as was_banned,
        cast(null as boolean) as is_win
    from {{ ref('stg_team_bans') }} b
    inner join {{ ref('stg_matches') }} m
        on b.match_id = m.match_id

)

select * from picks
union all
select * from bans
