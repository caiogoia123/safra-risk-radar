-- Planting, harvest and critical windows per crop and state.
--
-- Months are expressed as a *season index* rather than a calendar month, so the
-- season can be reasoned about arithmetically despite straddling two years:
--
--     Sep(-1yr) = -3 ... Dec(-1yr) = 0, Jan = 1 ... Sep = 9
--
-- The useful property: for a season with harvest year Y, any season index s maps
-- to the absolute month `Y * 12 + s` in both branches, so date arithmetic needs
-- no date construction at all -- which also keeps the SQL portable, since DuckDB
-- spells it make_date() and BigQuery spells it DATE().

with calendar as (

    select * from {{ ref('crop_calendar') }}

),

indexed as (

    select
        crop_name,
        state_code,
        phase,
        case
            when year_offset = -1 then month_number - 12
            else month_number
        end as season_index
    from calendar

),

bounds as (

    select
        crop_name,
        state_code,
        min(case when phase = 'planting' then season_index end) as planting_start,
        max(case when phase = 'planting' then season_index end) as planting_end,
        min(case when phase = 'harvest'  then season_index end) as harvest_start,
        max(case when phase = 'harvest'  then season_index end) as harvest_end
    from indexed
    group by crop_name, state_code

)

select
    crop_name,

    -- CONAB's grain series names these differently from the calendar; carrying
    -- both keys here keeps the join downstream honest instead of hiding a
    -- string translation inside it.
    case crop_name
        when 'SOJA' then 'SOJA'
        when 'MILHO 2A SAFRA' then 'MILHO'
    end as conab_crop_name,
    case crop_name
        when 'SOJA' then 'UNICA'
        when 'MILHO 2A SAFRA' then '2ª SAFRA'
    end as conab_season_label,

    state_code,
    planting_start,
    planting_end,
    harvest_start,
    harvest_end,

    -- Critical window: grain filling, the drought-sensitive phase. CONAB
    -- publishes planting and harvest, not phenological stages, so this is
    -- derived -- deliberately as an explicit rule that is easy to revisit,
    -- rather than buried in an aggregate.
    --
    -- It runs from the end of planting (the last fields to go in) to one month
    -- before harvest ends (grain fills immediately before it is cut; the tail of
    -- the harvest window is field drying, when weather no longer sets yield).
    -- Soybean in Mato Grosso resolves to Dec-Mar, safrinha corn to Mar-Jul.
    planting_end            as critical_start,
    harvest_end - 1         as critical_end

from bounds
where crop_name in ('SOJA', 'MILHO 2A SAFRA')
