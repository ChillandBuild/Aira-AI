-- Deals, Meta Ads, Auto-Messages, Anril Brain and Services used to ride on
-- other pages' permissions. They now have their own keys; grant each new key to
-- every role that could already reach that page, so nobody loses access.
--   deals.*         <- leads.view / leads.manage
--   meta_ads.*      <- inbound_leads.view / inbound_leads.manage
--   auto_messages.* <- settings.view / settings.manage / leads.manage (shop counter)
--   brain.view      <- knowledge.view / knowledge.manage
--   services.view   <- settings.* / catalog.*;  services.manage <- settings.manage
update public.tenant_roles r
set permissions = (
  select array(
    select distinct p from unnest(
      r.permissions
      || case when r.permissions && array['leads.view','leads.manage'] then array['deals.view'] else '{}'::text[] end
      || case when r.permissions && array['leads.manage'] then array['deals.manage'] else '{}'::text[] end
      || case when r.permissions && array['inbound_leads.view','inbound_leads.manage'] then array['meta_ads.view'] else '{}'::text[] end
      || case when r.permissions && array['inbound_leads.manage'] then array['meta_ads.manage'] else '{}'::text[] end
      || case when r.permissions && array['settings.view','settings.manage','leads.manage'] then array['auto_messages.view'] else '{}'::text[] end
      || case when r.permissions && array['settings.manage','leads.manage'] then array['auto_messages.manage'] else '{}'::text[] end
      || case when r.permissions && array['knowledge.view','knowledge.manage'] then array['brain.view'] else '{}'::text[] end
      || case when r.permissions && array['settings.view','settings.manage','catalog.view','catalog.manage'] then array['services.view'] else '{}'::text[] end
      || case when r.permissions && array['settings.manage'] then array['services.manage'] else '{}'::text[] end
    ) as p
    order by p
  )
);
