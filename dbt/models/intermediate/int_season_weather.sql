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

-- Dry spells: runs of consecutive dry days, found once over the whole daily
-- series per cell, then matched against each season's critical window.
--
-- Counting dry days (below) and measuring the longest run are different things
-- agronomically: 20 dry days scattered over four months is an ordinary season,
-- 20 dry days back to back during grain filling is a crop failure. That run --
-- a veranico -- is what this captures.

dry_days as (

    select
        grid_latitude,
        grid_longitude,
        day_index,
        weather_year * 12 + weather_month as month_abs
    from {{ ref('stg_weather_daily') }}
    where is_dry_day = 1

),

dry_islands as (

    -- Gaps and islands: over consecutive days, day_index climbs in step with
    -- row_number, so their difference is constant within a run and changes
    -- whenever a wet day interrupts it. That constant identifies the spell.
    select
        grid_latitude,
        grid_longitude,
        day_index,
        month_abs,
        -- Partitioned by the coordinates cast to text: BigQuery refuses to
        -- partition by FLOAT64 at all, and DuckDB allows it, so the raw floats
        -- only work on dev. The grid is 0.5 degrees, far coarser than any
        -- rounding difference, so the cast groups exactly the same cells.
        day_index - row_number() over (
            partition by
                cast(grid_latitude as {{ dbt.type_string() }}),
                cast(grid_longitude as {{ dbt.type_string() }})
            order by day_index
        ) as spell_id
    from dry_days

),

spells_in_window as (

    -- Only the days that fall inside the critical window count. Measuring the
    -- whole spell instead -- every day of a drought that merely touches the
    -- window -- was tried and rejected: in Bahia the window closes in April,
    -- right as the five-month dry season starts, so the metric picked up the
    -- dry season rather than a veranico (29 mean days against 12 in Parana,
    -- 180 in the worst cell). Same class of region-biased error as the fan-out.
    select
        sw.crop_name,
        sw.state_code,
        sw.harvest_year,
        di.grid_latitude,
        di.grid_longitude,
        di.spell_id,
        count(*) as spell_days
    from dry_islands di
    join cell_weights cw
      on cw.grid_latitude = di.grid_latitude
     and cw.grid_longitude = di.grid_longitude
    join season_windows sw
      on sw.state_code = cw.state_code
     and di.month_abs between sw.window_start_month and sw.window_end_month
    group by
        sw.crop_name, sw.state_code, sw.harvest_year,
        di.grid_latitude, di.grid_longitude, di.spell_id

),

cell_spells as (

    select
        crop_name,
        state_code,
        harvest_year,
        grid_latitude,
        grid_longitude,
        max(spell_days) as max_dry_spell_days
    from spells_in_window
    group by crop_name, state_code, harvest_year, grid_latitude, grid_longitude

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

),

by_cell_enriched as (

    -- A cell with no dry spell at all inside the window has no row in
    -- cell_spells; that is a zero-length spell, not a missing measurement.
    select
        b.*,
        coalesce(cs.max_dry_spell_days, 0) as max_dry_spell_days
    from by_cell b
    left join cell_spells cs
      on cs.crop_name      = b.crop_name
     and cs.state_code     = b.state_code
     and cs.harvest_year   = b.harvest_year
     and cs.grid_latitude  = b.grid_latitude
     and cs.grid_longitude = b.grid_longitude

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
    max(temp_max_c)                                                       as temp_max_c,

    -- Longest run of consecutive dry days inside the critical window: the
    -- veranico. Weighted across cells for the belt as a whole, plus the worst
    -- single cell -- a drought concentrated in the core of the belt moves the
    -- state number even when the weighted mean looks calm.
    --
    -- Descriptive, NOT a model feature. It correlates 0.73 with plain dry-day
    -- count on soybean, and its partial correlation with the yield residual
    -- once dry days are controlled for is +0.05 -- it vanishes. Kept because
    -- "31 days without rain during grain filling" is the readable version of
    -- the same fact, and the dashboard needs to say it that way.
    sum(max_dry_spell_days * production_weight) / sum(production_weight)
                                                                          as max_dry_spell_days,
    max(max_dry_spell_days)                                               as max_dry_spell_worst_cell

from by_cell_enriched
group by crop_name, conab_crop_name, conab_season_label, state_code, harvest_year
