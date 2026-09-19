{#
    Division that returns null instead of erroring or returning infinity when
    the denominator is zero or null. Used everywhere a rate or share is derived.
#}
{% macro safe_divide(numerator, denominator) -%}
    case
        when ({{ denominator }}) is null or ({{ denominator }}) = 0 then null
        else cast(({{ numerator }}) as double) / ({{ denominator }})
    end
{%- endmacro %}
