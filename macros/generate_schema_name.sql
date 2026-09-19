{#
    Use the schema configured on the model as-is rather than prefixing it with
    the target schema. Keeps DuckDB schemas readable: staging, marts, seeds.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
