# Supabase Migration Guide

This guide explains how to migrate from JSON files to Supabase PostgreSQL database.

## Prerequisites

1. Supabase project set up with PostgreSQL database
2. `.env` file configured with:
   - `SUPABASE_URL` - Your Supabase project URL
   - `SUPABASE_KEY` - Your Supabase anon key
   - `DATABASE_URL` - PostgreSQL connection string (from Supabase Dashboard → Settings → Database → Connection string)
     - Format: `postgresql://postgres:[PASSWORD]@[PROJECT_REF].supabase.co:5432/postgres`

## Migration Steps

### 1. Install Dependencies

```bash
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Run Database Migrations

This creates the database tables (sources, watched_videos, app_state):

```bash
alembic upgrade head
```

### 3. Migrate Existing Data

Run the migration script to copy data from JSON files to the database:

```bash
python scripts/migrate_to_supabase.py
```

This will:
- Migrate sources from `data/sources.json` to the `sources` table
- Migrate watched videos from `data/watched_videos.json` to the `watched_videos` table
- Create backup files (`*.json.backup`) of the original JSON files
- Verify the migration by counting records

### 4. Verify Migration

After migration, verify the data:

```bash
# Check migration script output for record counts
# Or connect to Supabase and query the tables directly
```

## How It Works

### SourceManager
- On initialization, tries to load sources from database first
- Falls back to `data/sources.json` if database is unavailable
- Loads `current_source_index` from `app_state` table on startup
- Saves `current_source_index` to database whenever it changes (next/previous source)

### YouTubeThread
- Loads watched video IDs from database on initialization
- Falls back to `data/watched_videos.json` if database is unavailable
- Saves watched video IDs to database when videos are marked as watched
- Uses batch operations for performance

### Fallback Behavior
- All database operations have try/except blocks
- If database is unavailable, the system automatically falls back to file-based storage
- No application crashes if database is temporarily unavailable

## Troubleshooting

### Database Connection Issues
- Verify `DATABASE_URL` is correct in `.env`
- Check network connectivity to Supabase
- Verify Supabase project is active

### Migration Errors
- Check that JSON files are valid
- Verify database tables exist (run `alembic upgrade head`)
- Check logs for specific error messages

### Performance Issues
- Database operations are async and batched where possible
- Watched videos are saved in batches, not individually
- Connection pooling is configured for optimal performance

## Rollback

If you need to rollback to JSON files:
1. Restore from backup files (`.json.backup`)
2. Comment out database loading code in `SourceManager` and `YouTubeThread`
3. Restart the application

Note: The system will automatically fall back to files if the database is unavailable, so rollback may not be necessary.

