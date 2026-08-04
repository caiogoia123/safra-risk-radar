-- Producing municipalities carrying 80% of each state's grain output, with the
-- weather grid cell each one maps to. See ingestion/geo.py for the selection.

with source as (

    select * from {{ source('raw', 'producer_hubs') }}

)

select
    municipality_id,
    municipality_name,
    state_code,
    mean_production_t,
    rank_in_state,
    cumulative_share,
    latitude,
    longitude,
    grid_latitude,
    grid_longitude
from source
