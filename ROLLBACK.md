# Backup, recovery and rollback

## Backups made during the October 2026 stabilisation
- `backups/talentbridge-20261023-154042.db` and `backups/uploads-20261023-154042/` — the database and CV files **exactly as they were before any change**.
- `backups/before-repair-20261023-160013/` — taken by `scripts/repair_identity.py` immediately before it moved the misfiled CVs.

To go back to either point: stop the app, then replace `data/talentbridge.db` with the backed-up `.db` file and `data/uploads/` with the backed-up uploads folder. (The new code will re-apply its database upgrade on start; to run the *old* code too, restore the old project folder as well.)

## Backing up your data (do this before upgrades and regularly)
Stop the app (Control+C), then copy the whole `data` folder somewhere safe, e.g. `cp -R data ~/Documents/talentbridge-backup-$(date +%F)`. The database and the CV files must be backed up together.

## Restoring
Stop the app, rename the current `data` folder (keep it until you are sure), copy the backup back as `data`, start the app.

## Repairing CVs filed under the wrong person
`python3 scripts/repair_identity.py` shows what it would change; `--apply` takes a backup first and then moves each misfiled CV (and applications made with it) to its owner's record. Anything it cannot decide is listed as UNRESOLVED and left alone.

## Database upgrades
Applied automatically on start (`backend/app/schema.py`). Migration 3 only **adds** columns and a `match_history` table; nothing is deleted. Recalculated scores keep the previous value in `match_history`.

## Demo data vs real data
Keep them in separate folders: `DATA_DIR=./demo-data python3 run.py --load-demo-candidates` for demos, and `DEMO_SEED=0` with its own `DATA_DIR` for anything involving real people. The demo logins are public.
