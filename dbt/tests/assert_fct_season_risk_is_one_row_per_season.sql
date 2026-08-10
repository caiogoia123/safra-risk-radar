-- The declared grain of the fact table. A duplicate here would silently double
-- a state's weight in every correlation and in the model's training set.
--
-- Written by hand rather than pulled from dbt_utils: adding a package would put
-- a `dbt deps` step in both workflows for one test.

select
    crop_name,
    state_code,
    harvest_year,
    count(*) as rows_for_this_season

from {{ ref('fct_season_risk') }}
group by crop_name, state_code, harvest_year
having count(*) > 1
