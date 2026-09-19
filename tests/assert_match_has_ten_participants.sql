-- A complete Summoner's Rift match has ten participants. Fewer means a match
-- was partially loaded and any team-share denominator computed from it is wrong.
select
    match_id,
    count(*) as participant_count
from {{ ref('stg_match_participants') }}
group by 1
having count(*) <> 10
