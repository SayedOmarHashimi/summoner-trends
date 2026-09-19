{#
    Riot reports game_version as e.g. "14.18.615.9137". The patch people refer
    to is the first two components: "14.18".
#}
{% macro patch_from_game_version(column_name) -%}
    case
        when ({{ column_name }}) is null then null
        else split_part(({{ column_name }}), '.', 1) || '.' || split_part(({{ column_name }}), '.', 2)
    end
{%- endmacro %}
