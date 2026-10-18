"""Read-only connection check; never prints secrets or uploads report data."""
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from roadproof.cloud import SupabaseDatabase
from roadproof.settings import backend_settings


def main():
    try:
        settings = backend_settings()
        if settings.backend != "supabase":
            print("Supabase is not selected. ROADPROOF_BACKEND is still sqlite.")
            return 1
        database = SupabaseDatabase(settings)
        database.client.table("rp_reports").select("id").limit(1).execute()
        database.client.table("rp_history").select("id").limit(1).execute()
        bucket = database.client.storage.get_bucket(settings.bucket)
        if bucket.public:
            print("Connection works, but the evidence bucket is public. Keep the app disabled until it is private.")
            return 1
        print("Supabase tables are reachable and the evidence bucket is private.")
        print("No report data was uploaded or changed. A real submission is still needed to verify the complete workflow.")
        return 0
    except Exception:
        print("Supabase check failed. Confirm project provisioning, the server-only URL/key, and supabase/schema.sql. No credentials were printed.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
