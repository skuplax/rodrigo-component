#!/usr/bin/env python3
"""Migration script to migrate sources.json and watched_videos.json to Supabase database"""

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import List, Dict, Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from db.models import Source, WatchedVideo, AppState
from db.database import AsyncSessionLocal
from player.source_manager import SourceType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate_sources(data_dir: Path) -> int:
    """Migrate sources.json to database"""
    sources_file = data_dir / "sources.json"
    
    if not sources_file.exists():
        logger.warning(f"sources.json not found at {sources_file}, skipping sources migration")
        return 0
    
    try:
        with open(sources_file, 'r') as f:
            sources_data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read sources.json: {e}")
        return 0
    
    if not isinstance(sources_data, list):
        logger.error("sources.json must contain a list of sources")
        return 0
    
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        
        # Get existing sources by URI to avoid duplicates
        result = await session.execute(select(Source.uri))
        existing_uris = set(result.scalars().all())
        
        new_sources = []
        skipped = 0
        
        for item in sources_data:
            try:
                # Check if source already exists
                if item.get('uri') in existing_uris:
                    logger.debug(f"Source with URI {item.get('uri')} already exists, skipping")
                    skipped += 1
                    continue
                
                # Validate required fields
                if not all(key in item for key in ['type', 'name', 'uri']):
                    logger.warning(f"Invalid source entry (missing required fields): {item}")
                    continue
                
                # Validate source type
                try:
                    SourceType(item['type'])
                except ValueError:
                    logger.warning(f"Invalid source type '{item['type']}' in entry: {item}")
                    continue
                
                source = Source(
                    type=item['type'],
                    name=item['name'],
                    uri=item['uri'],
                    source_type=item.get('source_type', 'music')
                )
                new_sources.append(source)
                existing_uris.add(item['uri'])
                
            except Exception as e:
                logger.error(f"Error processing source entry {item}: {e}")
                continue
        
        if new_sources:
            session.add_all(new_sources)
            await session.commit()
            logger.info(f"Migrated {len(new_sources)} sources to database (skipped {skipped} duplicates)")
            return len(new_sources)
        else:
            logger.info(f"No new sources to migrate (skipped {skipped} duplicates)")
            return 0


async def migrate_watched_videos(data_dir: Path) -> int:
    """Migrate watched_videos.json to database"""
    watched_file = data_dir / "watched_videos.json"
    
    if not watched_file.exists():
        logger.warning(f"watched_videos.json not found at {watched_file}, skipping watched videos migration")
        return 0
    
    try:
        with open(watched_file, 'r') as f:
            watched_data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read watched_videos.json: {e}")
        return 0
    
    if not isinstance(watched_data, dict) or 'watched' not in watched_data:
        logger.error("watched_videos.json must contain a 'watched' array")
        return 0
    
    video_ids = watched_data.get('watched', [])
    if not isinstance(video_ids, list):
        logger.error("watched_videos.json 'watched' field must be an array")
        return 0
    
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        from sqlalchemy.dialects.postgresql import insert
        
        # Get existing video IDs
        result = await session.execute(select(WatchedVideo.video_id))
        existing_ids = set(result.scalars().all())
        
        # Find new video IDs to insert
        new_ids = [vid for vid in video_ids if vid and vid not in existing_ids]
        
        if new_ids:
            # Bulk insert
            stmt = insert(WatchedVideo).values([
                {'video_id': video_id} for video_id in new_ids
            ])
            stmt = stmt.on_conflict_do_nothing(index_elements=['video_id'])
            await session.execute(stmt)
            await session.commit()
            logger.info(f"Migrated {len(new_ids)} watched video IDs to database (skipped {len(video_ids) - len(new_ids)} duplicates)")
            return len(new_ids)
        else:
            logger.info(f"No new watched videos to migrate (all {len(video_ids)} already exist)")
            return 0


async def backup_json_files(data_dir: Path) -> bool:
    """Backup original JSON files with .backup extension"""
    sources_file = data_dir / "sources.json"
    watched_file = data_dir / "watched_videos.json"
    
    backed_up = False
    
    if sources_file.exists():
        backup_path = sources_file.with_suffix('.json.backup')
        if not backup_path.exists():
            import shutil
            shutil.copy2(sources_file, backup_path)
            logger.info(f"Backed up sources.json to {backup_path}")
            backed_up = True
        else:
            logger.debug(f"Backup already exists: {backup_path}")
    
    if watched_file.exists():
        backup_path = watched_file.with_suffix('.json.backup')
        if not backup_path.exists():
            import shutil
            shutil.copy2(watched_file, backup_path)
            logger.info(f"Backed up watched_videos.json to {backup_path}")
            backed_up = True
        else:
            logger.debug(f"Backup already exists: {backup_path}")
    
    return backed_up


async def verify_migration() -> Dict[str, int]:
    """Verify migration by counting records in database"""
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select, func
        
        sources_count = await session.scalar(select(func.count(Source.id)))
        watched_count = await session.scalar(select(func.count(WatchedVideo.id)))
        app_state_count = await session.scalar(select(func.count(AppState.key)))
        
        return {
            'sources': sources_count or 0,
            'watched_videos': watched_count or 0,
            'app_state': app_state_count or 0
        }


async def main():
    """Main migration function"""
    logger.info("Starting migration to Supabase...")
    
    # Get data directory
    project_root = Path(__file__).parent.parent
    data_dir = project_root / "data"
    
    if not data_dir.exists():
        logger.error(f"Data directory not found: {data_dir}")
        return 1
    
    try:
        # Migrate sources
        sources_count = await migrate_sources(data_dir)
        
        # Migrate watched videos
        watched_count = await migrate_watched_videos(data_dir)
        
        # Backup JSON files
        await backup_json_files(data_dir)
        
        # Verify migration
        counts = await verify_migration()
        logger.info(f"Migration complete! Database now contains:")
        logger.info(f"  - {counts['sources']} sources")
        logger.info(f"  - {counts['watched_videos']} watched videos")
        logger.info(f"  - {counts['app_state']} app state entries")
        
        return 0
        
    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

