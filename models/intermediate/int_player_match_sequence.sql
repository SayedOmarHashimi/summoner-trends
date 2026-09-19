-- Orders each player's matches so window functions downstream have a stable,
-- gap-free sequence to work with. Remakes and very short games are dropped so
-- they do not distort rolling averages.
with performance as (

    select * from {{ ref('int_participant_metrics') }}

),

tracked_players as (

    -- Trends are only built for the accounts this project tracks. A match also
    -- contains nine other players, and they are not the subject of the analysis.
    select puuid from {{ ref('stg_summoners') }}

),

filtered as (

    select p.*
    from performance p
    inner join tracked_players t on p.puuid = t.puuid
    where p.game_duration_seconds >= 300
      and not p.ended_in_early_surrender

),

sequenced as (

    select
        *,
        row_number() over (
            partition by puuid
            order by game_start_at, match_id
        ) as match_sequence_number,
        count(*) over (partition by puuid) as player_match_count,

        -- A second sequence per champion. A champion's rolling average has to
        -- be built from that champion's games only — mixing in other champions
        -- would describe a window the player never actually played.
        row_number() over (
            partition by puuid, champion_id
            order by game_start_at, match_id
        ) as champion_match_sequence_number,
        count(*) over (
            partition by puuid, champion_id
        ) as player_champion_match_count
    from filtered

)

select * from sequenced
