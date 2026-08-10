-- The worst single cell cannot have a shorter dry spell than the weighted mean
-- across cells. If it ever does by a real margin, the weighting broke.
--
-- The tolerance is not slack for a weak invariant, it is for floating point.
-- When every cell in a state records the same spell length, the weighted mean
-- is sum(x * w) / sum(w) over identical x, which lands a few ulps away from x
-- itself: two rows sit 1.4e-14 below their own maximum. A strict comparison
-- fails on those, and any real weighting error would be orders of magnitude
-- larger than a day.

select
    crop_name,
    state_code,
    harvest_year,
    max_dry_spell_days,
    max_dry_spell_worst_cell,
    max_dry_spell_worst_cell - max_dry_spell_days as shortfall

from {{ ref('fct_season_risk') }}
where max_dry_spell_worst_cell - max_dry_spell_days < -0.001
