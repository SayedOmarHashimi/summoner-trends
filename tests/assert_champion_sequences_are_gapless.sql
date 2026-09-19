-- Each champion's sequence must run 1..n with no gaps, or a rolling window
-- silently spans a different number of games than it claims.
with bounds as (

    select
        puuid,
        champion_id,
        count(*)                                as rows_present,
        max(champion_match_sequence_number)     as highest,
        min(champion_match_sequence_number)     as lowest
    from {{ ref('fct_player_champion_trends') }}
    group by 1, 2

)

select *
from bounds
where lowest <> 1
   or highest <> rows_present
