-- Adds photo ranking to catalog_media so clients can control which photos
-- send first when a reply's image count is capped by max_images_per_reply.
alter table catalog_media add column if not exists sort_order integer not null default 0;

with ranked as (
  select id, row_number() over (partition by catalog_item_id order by created_at asc) - 1 as rn
  from catalog_media
)
update catalog_media cm
set sort_order = ranked.rn
from ranked
where cm.id = ranked.id;

create index if not exists idx_catalog_media_item_sort on catalog_media (catalog_item_id, sort_order);
