with source as (

    select * from {{ source('riot_raw', 'raw_summoners') }}

),

renamed as (

    select
        puuid,
        game_name                                       as riot_id_game_name,
        tag_line                                        as riot_id_tagline,
        game_name || '#' || tag_line                    as riot_id,
        platform,
        cast(summoner_level as integer)                 as summoner_level,
        profile_icon_id,
        to_timestamp(cast(revision_date as bigint) / 1000) as profile_revised_at,
        _extracted_at
    from source

)

select * from renamed
