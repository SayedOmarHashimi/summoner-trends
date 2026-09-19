{#
    Human-readable label for the Riot queue ids this project keeps. Ids come
    from the official queue list published with Riot's static data.
#}
{% macro queue_name(column_name) -%}
    case cast(({{ column_name }}) as integer)
        when 400 then 'Normal Draft'
        when 420 then 'Ranked Solo/Duo'
        when 430 then 'Normal Blind'
        when 440 then 'Ranked Flex'
        when 450 then 'ARAM'
        when 700 then 'Clash'
        when 1700 then 'Arena'
        else 'Other'
    end
{%- endmacro %}
