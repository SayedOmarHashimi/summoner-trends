with source as (

    select * from {{ source('riot_raw', 'raw_match_participants') }}

),

renamed as (

    select
        {{ dbt_utils.generate_surrogate_key(['match_id', 'puuid']) }} as participant_key,
        match_id,
        puuid,
        cast(participant_id as integer)         as participant_id,
        cast(team_id as integer)                as team_id,
        riot_id_game_name,
        riot_id_tagline,
        cast(champion_id as integer)            as champion_id,
        champion_name,
        cast(champ_level as integer)            as champion_level,
        team_position,
        individual_position,
        lane,
        role,

        cast(kills as integer)                  as kills,
        cast(deaths as integer)                 as deaths,
        cast(assists as integer)                as assists,

        cast(total_damage_dealt_to_champions as integer) as damage_to_champions,
        cast(total_damage_taken as integer)              as damage_taken,
        cast(damage_dealt_to_objectives as integer)      as damage_to_objectives,
        cast(total_heal as integer)                      as total_heal,

        cast(gold_earned as integer)            as gold_earned,
        cast(gold_spent as integer)             as gold_spent,

        cast(total_minions_killed as integer)
            + cast(neutral_minions_killed as integer)    as creep_score,
        cast(total_minions_killed as integer)   as minions_killed,
        cast(neutral_minions_killed as integer) as neutral_minions_killed,

        cast(vision_score as integer)           as vision_score,
        cast(wards_placed as integer)           as wards_placed,
        cast(wards_killed as integer)           as wards_killed,
        cast(vision_wards_bought_in_game as integer) as control_wards_bought,

        cast(turret_takedowns as integer)       as turret_takedowns,
        cast(dragon_kills as integer)           as dragon_kills,
        cast(baron_kills as integer)            as baron_kills,

        cast(time_played as integer)            as time_played_seconds,
        cast(win as boolean)                    as is_win,
        cast(game_ended_in_early_surrender as boolean) as ended_in_early_surrender,
        cast(game_ended_in_surrender as boolean)       as ended_in_surrender,

        _extracted_at
    from source

)

select * from renamed
