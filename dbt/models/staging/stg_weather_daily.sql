-- Daily weather per NASA POWER grid cell, from 1991 onward.
--
-- One row per cell x day. Cells are shared by neighbouring municipalities, so
-- this is deliberately not at municipality grain -- joining to hubs happens
-- downstream, where production weights are applied.

with source as (

    select * from {{ source('raw', 'nasa_power_daily') }}

),

typed as (

    select
        grid_latitude,
        grid_longitude,
        cast(date as date)                          as weather_date,

        extract(year from date)                     as weather_year,
        extract(month from date)                    as weather_month,
        extract(dayofyear from date)                as day_of_year,

        -- A gapless day counter, needed downstream to find runs of consecutive
        -- days. `weather_year * 366 + day_of_year` would look equivalent and is
        -- not: it leaves a hole at every new year, which would split a dry spell
        -- running Dec into Jan -- precisely the soybean critical window.
        -- datediff is the dbt cross-database macro, so this stays portable.
        {{ dbt.datediff("cast('1991-01-01' as date)", "date", "day") }} as day_index,

        temp_mean_c,
        temp_max_c,
        temp_min_c,
        precipitation_mm,
        radiation_mj_m2,

        -- Growing degree days, base 10 C, capped at 30 C. Base and cap follow
        -- the usual convention for soybean and corn: below 10 C the crop does
        -- not develop, above 30 C extra heat stops helping.
        greatest(
            least((temp_max_c + temp_min_c) / 2, 30.0) - 10.0,
            0.0
        )                                           as growing_degree_days,

        -- A dry day by the agronomic convention, not literally zero rain.
        case when precipitation_mm < 1.0 then 1 else 0 end as is_dry_day

    from source

)

select * from typed
