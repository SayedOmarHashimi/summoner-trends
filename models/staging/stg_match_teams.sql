with source as (

    select * from {{ source('riot_raw', 'raw_match_teams') }}

),

renamed as (

    select
        {{ dbt_utils.generate_surrogate_key(['match_id', 'team_id']) }} as team_key,
        match_id,
        cast(team_id as integer)            as team_id,
        cast(win as boolean)                as is_win,

        cast(baron_kills as integer)        as baron_kills,
        cast(dragon_kills as integer)       as dragon_kills,
        cast(herald_kills as integer)       as herald_kills,
        cast(tower_kills as integer)        as tower_kills,
        cast(inhibitor_kills as integer)    as inhibitor_kills,
        cast(champion_kills as integer)     as champion_kills,
        cast(first_blood as boolean)        as took_first_blood,
        cast(first_tower as boolean)        as took_first_tower,

        _extracted_at
    from source

)

select * from renamed
