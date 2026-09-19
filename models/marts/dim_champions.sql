with champions as (

    select * from {{ ref('stg_champions') }}

)

select
    champion_id,
    champion_key,
    champion_name,
    champion_title,
    primary_role,
    secondary_role,
    resource_type
from champions
