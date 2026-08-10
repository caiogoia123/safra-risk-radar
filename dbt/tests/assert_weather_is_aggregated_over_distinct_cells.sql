-- Guards the most expensive mistake this project has made.
--
-- Producing hubs map many-to-one onto NASA POWER cells, and the ratio is wildly
-- uneven: 3.30 hubs per cell in Parana, 1.00 in Bahia. Aggregating weather after
-- joining hubs to the daily series triples Parana's rainfall and leaves Bahia's
-- correct - a silent error, biased by region, which is the worst kind. The first
-- validation of this pipeline reported 5,350 mm/year for Parana against a real
-- ~1,620.
--
-- `grid_cells` in the fact is a count of the rows that were aggregated. If it
-- ever exceeds the number of distinct cells in the state, a join started
-- fanning out again and every weather number in that row is inflated.

with cells_per_state as (

    select
        state_code,
        count(*) as distinct_cells
    from (
        select distinct state_code, grid_latitude, grid_longitude
        from {{ ref('stg_producer_hubs') }}
    ) as deduplicated
    group by state_code

)

select
    f.crop_name,
    f.state_code,
    f.harvest_year,
    f.grid_cells,
    c.distinct_cells

from {{ ref('fct_season_risk') }} f
join cells_per_state c
  on c.state_code = f.state_code
where f.grid_cells > c.distinct_cells
