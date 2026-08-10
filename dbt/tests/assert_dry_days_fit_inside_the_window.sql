-- A window cannot contain more dry days than it contains days. Cheap, and it
-- catches the class of bug where the dry-day count and the window length stop
-- being measured over the same set of rows - which is how a weighting or join
-- change would first show itself.

select
    crop_name,
    state_code,
    harvest_year,
    days_in_window,
    dry_days

from {{ ref('fct_season_risk') }}
where dry_days > days_in_window
   or dry_days < 0
