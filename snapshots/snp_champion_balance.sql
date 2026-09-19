{#
    Champion balance data changes patch to patch. This snapshot keeps the
    history so trends can be read against the balance state at the time a match
    was played, rather than against whatever is current.

    Source is the `champion_static` seed, refreshed from Data Dragon.
#}
{% snapshot snp_champion_balance %}

{{
    config(
        unique_key='champion_id',
        strategy='check',
        check_cols=[
            'primary_role',
            'secondary_role',
            'resource_type',
            'champion_name',
            'champion_title'
        ],
        invalidate_hard_deletes=True
    )
}}

select
    champion_id,
    champion_key,
    champion_name,
    champion_title,
    primary_role,
    secondary_role,
    resource_type,
    data_dragon_version
from {{ ref('champion_static') }}

{% endsnapshot %}
