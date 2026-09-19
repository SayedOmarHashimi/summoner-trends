with source as (

    select * from {{ source('riot_raw', 'raw_matches') }}

),

renamed as (

    select
        match_id,
        data_version,
        platform_id                                         as platform,
        cast(queue_id as integer)                           as queue_id,
        game_mode,
        game_type,
        cast(map_id as integer)                             as map_id,

        -- Riot reports the patch as e.g. "14.18.615.9137"; the first two parts
        -- are the patch everyone actually refers to.
        game_version,
        {{ patch_from_game_version('game_version') }}       as patch,

        -- Timestamps arrive as epoch milliseconds.
        to_timestamp(cast(game_creation as bigint) / 1000)  as game_creation_at,
        to_timestamp(cast(game_start_timestamp as bigint) / 1000) as game_start_at,
        to_timestamp(cast(game_end_timestamp as bigint) / 1000)   as game_end_at,

        cast(game_duration as integer)                      as game_duration_seconds,
        cast(game_duration as numeric) / 60.0               as game_duration_minutes,

        _extracted_at
    from source

)

select * from renamed
