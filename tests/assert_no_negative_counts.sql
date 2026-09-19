-- Kills, deaths, assists, gold, and CS are counts. A negative value means the
-- extraction or a cast went wrong, not that something unusual happened in game.
select
    participant_key,
    match_id,
    puuid,
    kills,
    deaths,
    assists,
    gold_earned,
    creep_score,
    vision_score
from {{ ref('fct_participant_performance') }}
where kills < 0
   or deaths < 0
   or assists < 0
   or gold_earned < 0
   or creep_score < 0
   or vision_score < 0
