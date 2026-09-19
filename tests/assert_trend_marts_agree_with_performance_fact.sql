-- The trend models and the performance fact must cover the same matches.
-- They are filtered in two different places, so a filter added to one and not
-- the other would silently leave the marts describing different histories.
with trend_rows as (

    select participant_key from {{ ref('fct_player_rolling_trends') }}
    union
    select participant_key from {{ ref('fct_player_champion_trends') }}

)

select t.participant_key
from trend_rows t
left join {{ ref('fct_participant_performance') }} p
    on t.participant_key = p.participant_key
where p.participant_key is null
