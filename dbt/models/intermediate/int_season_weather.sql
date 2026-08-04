-- Weather over each crop's critical window, per state and season.
--
-- The fan-out trap: hubs map many-to-one onto grid cells (3.3 hubs per cell in
-- Parana, 1.0 in Bahia). Summing rainfall after joining hubs to weather would
-- triple Parana and leave Bahia untouched -- a silent, region-biased error.
-- `cell_weights` collapses hubs to one row per cell first, carrying the summed
-- production as the weight, so every later aggregate is over distinct cells.

with windows as (

    select * from {{ ref('int_crop_windows') }}

),

cell_weights as (

    select
        state_code,
        grid_latitude,
        grid_longitude,
        sum(mean_production_t) as production_weight
    from {{ ref('stg_producer_hubs') }}
    group by state_code, grid_latitude, grid_longitude

),

seasons as (

    select distinct harvest_year
    from {{ ref('stg_conab_grain') }}
    where harvest_year >= {{ var('first_harvest_year') }}

),

season_windows as (

    select
        w.crop_name,
        w.conab_crop_name,
        w.conab_season_label,
        w.state_code,
        s.harvest_year,
        -- Season index s of harvest year Y is absolute month Y * 12 + s.
        s.harvest_year * 12 + w.critical_start as window_start_month,
        s.harvest_year * 12 + w.critical_end   as window_end_month
    from windows w
    cross join seasons s

),

by_cell as (

    select
        sw.crop_name,
        sw.conab_crop_name,
        sw.conab_season_label,
        sw.state_code,
        sw.harvest_year,
        cw.grid_latitude,
        cw.grid_longitude,
        cw.production_weight,

        sum(wd.precipitation_mm)     as precipitation_mm,
        avg(wd.temp_mean_c)          as temp_mean_c,
        max(wd.temp_max_c)           as temp_max_c,
        sum(wd.growing_degree_days)  as growing_degree_days,
        sum(wd.is_dry_day)           as dry_days,
        count(*)                     as days_in_window

    from season_windows sw
    join cell_weights cw
      on cw.state_code = sw.state_code
    join {{ ref('stg_weather_daily') }} wd
      on wd.grid_latitude = cw.grid_latitude
     and wd.grid_longitude = cw.grid_longitude
     and (wd.weather_year * 12 + wd.weather_month)
         between sw.window_start_month and sw.window_end_month

    group by
        sw.crop_name, sw.conab_crop_name, sw.conab_season_label, sw.state_code,
        sw.harvest_year, cw.grid_latitude, cw.grid_longitude, cw.production_weight

)

select
    crop_name,
    conab_crop_name,
    conab_season_label,
    state_code,
    harvest_year,

    count(*)                as grid_cells,
    max(days_in_window)     as days_in_window,

    -- Production-weighted across cells: a cell in the heart of the belt should
    -- count for more than one on the fringe.
    sum(precipitation_mm    * production_weight) / sum(production_weight) as precipitation_mm,
    sum(temp_mean_c         * production_weight) / sum(production_weight) as temp_mean_c,
    sum(growing_degree_days * production_weight) / sum(production_weight) as growing_degree_days,
    sum(dry_days            * production_weight) / sum(production_weight) as dry_days,
    max(temp_max_c)                                                       as temp_max_c

from by_cell
group by crop_name, conab_crop_name, conab_season_label, state_code, harvest_year
