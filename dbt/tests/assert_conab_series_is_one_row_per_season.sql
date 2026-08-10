-- CONAB publishes one figure per state x crop x season label x harvest year.
-- Season label has to be part of the key: a state can plant the same crop in
-- more than one season of the same harvest year, which is exactly what
-- separates safrinha corn from first-crop corn.

select
    crop_name,
    season_label,
    state_code,
    harvest_year,
    count(*) as rows_for_this_season

from {{ ref('stg_conab_grain') }}
group by crop_name, season_label, state_code, harvest_year
having count(*) > 1
