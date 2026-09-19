-- Every participant's damage share is a fraction of their own team's damage,
-- so the five shares on a team must sum to 1 (within float tolerance).
-- Teams with zero total damage are skipped: the share is null by design.
with team_shares as (

    select
        match_id,
        team_id,
        sum(damage_share) as total_damage_share,
        count(*)          as participants
    from {{ ref('fct_participant_performance') }}
    where damage_share is not null
    group by 1, 2

)

select *
from team_shares
where participants = 5
  and abs(total_damage_share - 1.0) > 0.0001
