-- One row per ban. The loader unpacks `info.teams[].bans[]` into its own raw
-- table so `raw_match_teams` keeps its one-row-per-team grain.
with source as (

    select * from {{ source('riot_raw', 'raw_match_bans') }}

),

bans as (

    select
        match_id,
        cast(team_id as integer)        as team_id,
        cast(champion_id as integer)    as champion_id,
        cast(pick_turn as integer)      as pick_turn,
        _extracted_at
    from source
    -- Riot uses -1 when a team declines or loses its ban.
    where champion_id is not null
      and cast(champion_id as integer) > 0

)

select * from bans
