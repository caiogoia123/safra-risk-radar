-- One row per crop x state x season: critical-window weather, how far it sits
-- from that state's normal, and the yield that came out of it.
--
-- Yield is also expressed as a residual against the state's linear trend. Raw
-- yield rises over time through genetics and practice; a model trained on the
-- level mostly rediscovers that trend and reports a flattering error with no
-- predictive value. The residual is the part technology does not explain.
--
-- Caveat, on purpose: the trend here is fitted over the whole series, so it is
-- in-sample and fine for exploring, NOT for scoring a forecast. The predictive
-- model refits the trend on training years only.

with weather as (

    select * from {{ ref('int_season_weather') }}

),

normals as (

    select
        crop_name,
        state_code,
        avg(precipitation_mm)       as normal_precipitation_mm,
        stddev(precipitation_mm)    as sd_precipitation_mm,
        avg(temp_mean_c)            as normal_temp_mean_c,
        stddev(temp_mean_c)         as sd_temp_mean_c,
        avg(dry_days)               as normal_dry_days,
        stddev(dry_days)            as sd_dry_days
    from weather
    where harvest_year between {{ var('normal_start_year') }} and {{ var('normal_end_year') }}
    group by crop_name, state_code

),

yields as (

    select
        crop_name,
        season_label,
        state_code,
        harvest_year,
        yield_kg_ha,
        planted_area_ha,
        production_t
    from {{ ref('stg_conab_grain') }}

),

trend as (

    select
        w.crop_name,
        w.state_code,
        regr_slope(y.yield_kg_ha, y.harvest_year)     as yield_slope,
        regr_intercept(y.yield_kg_ha, y.harvest_year) as yield_intercept
    from weather w
    join yields y
      on y.crop_name    = w.conab_crop_name
     and y.season_label = w.conab_season_label
     and y.state_code   = w.state_code
     and y.harvest_year = w.harvest_year
    group by w.crop_name, w.state_code

)

select
    w.crop_name,
    w.state_code,
    w.harvest_year,
    w.grid_cells,
    w.days_in_window,

    -- Critical-window weather
    w.precipitation_mm,
    w.temp_mean_c,
    w.temp_max_c,
    w.dry_days,
    w.growing_degree_days,

    -- Distance from normal, absolute and standardised
    n.normal_precipitation_mm,
    w.precipitation_mm - n.normal_precipitation_mm              as precipitation_anomaly_mm,
    (w.precipitation_mm - n.normal_precipitation_mm)
        / nullif(n.sd_precipitation_mm, 0)                      as precipitation_anomaly_z,

    n.normal_temp_mean_c,
    w.temp_mean_c - n.normal_temp_mean_c                        as temp_anomaly_c,
    (w.temp_mean_c - n.normal_temp_mean_c)
        / nullif(n.sd_temp_mean_c, 0)                           as temp_anomaly_z,

    n.normal_dry_days,
    w.dry_days - n.normal_dry_days                              as dry_days_anomaly,
    (w.dry_days - n.normal_dry_days)
        / nullif(n.sd_dry_days, 0)                              as dry_days_anomaly_z,

    -- Outcome
    y.yield_kg_ha,
    y.planted_area_ha,
    y.production_t,
    t.yield_intercept + t.yield_slope * w.harvest_year          as yield_trend_kg_ha,
    y.yield_kg_ha
        - (t.yield_intercept + t.yield_slope * w.harvest_year)  as yield_residual_kg_ha,
    (y.yield_kg_ha - (t.yield_intercept + t.yield_slope * w.harvest_year))
        / nullif(t.yield_intercept + t.yield_slope * w.harvest_year, 0)
                                                                as yield_residual_pct

from weather w
join normals n
  on n.crop_name = w.crop_name
 and n.state_code = w.state_code
left join yields y
  on y.crop_name    = w.conab_crop_name
 and y.season_label = w.conab_season_label
 and y.state_code   = w.state_code
 and y.harvest_year = w.harvest_year
left join trend t
  on t.crop_name = w.crop_name
 and t.state_code = w.state_code
