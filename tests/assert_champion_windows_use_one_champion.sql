-- A champion's rolling window must be built from that champion's games only.
-- If the window ever spans more matches than the player has on that champion,
-- the partition is wrong and the average describes games never played on it.
select
    participant_key,
    puuid,
    champion_name,
    champion_match_sequence_number,
    matches_in_window,
    player_champion_match_count
from {{ ref('fct_player_champion_trends') }}
where matches_in_window > champion_match_sequence_number
   or matches_in_window > player_champion_match_count
