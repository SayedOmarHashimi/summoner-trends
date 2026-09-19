with source as (

    select * from {{ source('riot_raw', 'raw_champion_mastery') }}

),

renamed as (

    select
        {{ dbt_utils.generate_surrogate_key(['puuid', 'champion_id']) }} as mastery_key,
        puuid,
        cast(champion_id as integer)    as champion_id,
        cast(champion_level as integer) as mastery_level,
        cast(champion_points as integer) as mastery_points,
        cast(tokens_earned as integer)  as tokens_earned,
        to_timestamp(cast(last_play_time as bigint) / 1000) as last_played_at,
        _extracted_at
    from source

)

select * from renamed
