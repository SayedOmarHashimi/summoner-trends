{#
    Converts a per-game count into a per-minute rate. Games shorter than one
    minute return null rather than an implausible rate.
#}
{% macro per_minute(column_name, duration_minutes='game_duration_minutes') -%}
    case
        when ({{ duration_minutes }}) is null or ({{ duration_minutes }}) < 1 then null
        else cast(({{ column_name }}) as double) / ({{ duration_minutes }})
    end
{%- endmacro %}
