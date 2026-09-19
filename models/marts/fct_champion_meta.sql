-- Aggregate champion meta by patch and queue: pick rate, ban rate, win rate.
-- Champion-level aggregates across the whole player pool — this is meta
-- description, not player evaluation.
{{ config(materialized='table') }}

with appearances as (

    select * from {{ ref('int_champion_match_appearances') }}

),

match_counts as (

    select
        patch,
        queue_id,
        count(distinct match_id) as matches_on_patch
    from appearances
    group by 1, 2

),

champion_agg as (

    select
        patch,
        queue_id,
        champion_id,
        count(distinct case when was_picked then match_id end) as matches_picked,
        count(distinct case when was_banned then match_id end) as matches_banned,
        count(case when was_picked and is_win then 1 end)      as wins,
        count(case when was_picked and not is_win then 1 end)  as losses
    from appearances
    group by 1, 2, 3

)

select
    {{ dbt_utils.generate_surrogate_key(['a.patch', 'a.queue_id', 'a.champion_id']) }} as champion_meta_key,
    a.patch,
    a.queue_id,
    {{ queue_name('a.queue_id') }}  as queue_name,
    a.champion_id,
    c.champion_name,
    c.primary_role,

    m.matches_on_patch,
    a.matches_picked,
    a.matches_banned,
    a.wins,
    a.losses,

    {{ safe_divide('a.matches_picked', 'nullif(m.matches_on_patch, 0)') }} as pick_rate,
    {{ safe_divide('a.matches_banned', 'nullif(m.matches_on_patch, 0)') }} as ban_rate,
    {{ safe_divide('a.matches_picked + a.matches_banned', 'nullif(m.matches_on_patch, 0)') }} as presence_rate,
    {{ safe_divide('a.wins', 'nullif(a.wins + a.losses, 0)') }} as win_rate

from champion_agg a
inner join match_counts m
    on a.patch = m.patch
   and a.queue_id = m.queue_id
left join {{ ref('dim_champions') }} c
    on a.champion_id = c.champion_id
