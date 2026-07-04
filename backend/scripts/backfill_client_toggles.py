import os
import sys
import argparse

# Add parent directory to sys.path so we can import from app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.supabase import get_supabase
from app.services.subscription_requests import sync_client_toggles
from app.services.assignment import get_telecalling_config


def main():
    parser = argparse.ArgumentParser(description="Backfill client toggles based on subscriptions.")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing them to the database.")
    args = parser.parse_args()

    db = get_supabase()

    # Get all unique tenant_ids with active subscription items
    items_res = db.table("tenant_subscription_items").select("tenant_id").execute()
    tenant_ids = sorted(list({row["tenant_id"] for row in (items_res.data or [])}))

    print(f"Found {len(tenant_ids)} tenants with subscription items.")

    for tenant_id in tenant_ids:
        # Get tenant name/details for logging
        tenant_res = db.table("tenants").select("name, enabled_features").eq("id", tenant_id).maybe_single().execute()
        tenant_name = (tenant_res.data or {}).get("name") if tenant_res else tenant_id
        old_features = set((tenant_res.data or {}).get("enabled_features") or [])

        # Get old calling provider
        old_cfg = get_telecalling_config(tenant_id)
        old_provider = old_cfg.get("calling_provider")

        print(f"\nProcessing tenant: {tenant_name} ({tenant_id})")

        if args.dry_run:
            # We want to see what sync_client_toggles would do.
            # Let's mock/simulate the sync logic:
            from app.services.entitlements import resolve_entitlements
            ent = resolve_entitlements(db, tenant_id)
            features_to_enable = set(ent.get("features") or [])

            # Compute BILLING_DERIVED_KEYS
            catalog_res = db.table("feature_catalog").select("feature_key, depends_on").execute()
            billing_derived = set()
            for row in (catalog_res.data or []):
                billing_derived.add(row["feature_key"])
                for dep in (row.get("depends_on") or []):
                    billing_derived.add(dep)

            new_features = (old_features - billing_derived) | features_to_enable

            # Determine calling provider
            items_res = db.table("tenant_subscription_items").select("feature_key").eq("tenant_id", tenant_id).execute()
            active_keys = {row["feature_key"] for row in (items_res.data or [])}

            sim_active = "telecalling_sim" in active_keys
            telecmi_active = "telecalling_telecmi" in active_keys

            new_provider = old_provider
            if sim_active and not telecmi_active:
                new_provider = "sim_basic"
            elif telecmi_active and not sim_active:
                new_provider = "telecmi"
            elif sim_active and telecmi_active:
                new_provider = "telecmi"

            print("  [DRY RUN] Features diff:")
            print(f"    Added:   {sorted(list(features_to_enable - old_features))}")
            print(f"    Removed: {sorted(list(old_features - new_features))}")
            print(f"    Result:  {sorted(list(new_features))}")
            print(f"  [DRY RUN] Calling Provider: {old_provider} -> {new_provider}")
        else:
            # Run for real
            sync_client_toggles(db, tenant_id)
            # Fetch new values
            new_tenant_res = db.table("tenants").select("enabled_features").eq("id", tenant_id).maybe_single().execute()
            new_features = set((new_tenant_res.data or {}).get("enabled_features") or [])
            new_cfg = get_telecalling_config(tenant_id)
            new_provider = new_cfg.get("calling_provider")

            print("  Features diff:")
            print(f"    Added:   {sorted(list(new_features - old_features))}")
            print(f"    Removed: {sorted(list(old_features - new_features))}")
            print(f"    Result:  {sorted(list(new_features))}")
            print(f"  Calling Provider: {old_provider} -> {new_provider}")


if __name__ == "__main__":
    main()
