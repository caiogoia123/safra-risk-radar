-- Cleans the CONAB grain series into one row per state x crop x season x harvest.
--
-- Three source quirks are handled here:
--   1. crop_year has two shapes: 'YYYY/YY' (summer) and 'YYYY' (winter).
--   2. the published yield is rounded to one decimal in t/ha, which would eat
--      most of the signal in a residual analysis - so it is recomputed.
--   3. 61% of rows are states that do not plant the crop, carrying zero area.

with source as (

    select * from {{ source('raw', 'conab_grain_series') }}

),

renamed as (

    select
        crop_year                                       as crop_year_label,

        -- Summer crops are labelled by the year they were planted; the harvest
        -- lands in the following calendar year. Winter crops carry a single year.
        case
            when length(crop_year) = 4 then cast(crop_year as int)
            else cast(substr(crop_year, 1, 4) as int) + 1
        end                                             as harvest_year,

        case
            when length(crop_year) = 4 then 'winter'
            else 'summer'
        end                                             as crop_cycle,

        season_label,
        state_code,
        crop_name,
        crop_id,

        planted_area_kha * 1000                         as planted_area_ha,
        production_kt * 1000                            as production_t,

        -- Recomputed, not taken from the source column.
        round(production_kt / nullif(planted_area_kha, 0) * 1000, 2) as yield_kg_ha,
        yield_source_t_ha

    from source

)

select * from renamed
where planted_area_ha > 0
