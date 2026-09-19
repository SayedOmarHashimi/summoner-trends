-- Static champion reference data from Data Dragon, loaded as a seed.
with source as (

    select * from {{ ref('champion_static') }}

),

renamed as (

    select
        cast(champion_id as integer)    as champion_id,
        champion_key,
        champion_name,
        champion_title,
        primary_role,
        secondary_role,
        resource_type
    from source

)

select * from renamed
