# Database Migration Instructions

This document provides step-by-step instructions for migrating from the file-based Twitter bot to the database-backed version.

## Prerequisites

1. **Backup existing data** (if any):
   ```bash
   cp -r drafts/ drafts_backup/
   cp -r logs/ logs_backup/
   ```

2. **Install database dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

## Migration Steps

### 1. Initialize Database

Run the database setup script to create tables and migrate existing data:

```bash
python setup_db.py
```

This will:
- Create all database tables
- Set up initial user accounts
- Import existing data from files:
  - `logs/last_tweet_id.txt` → system_state table
  - `logs/api_usage.json` → api_usage table
  - Draft files (noted for manual migration)

### 2. Run Database Migrations

Initialize the Alembic migration state:

```bash
alembic stamp head
```

For future schema changes, run:

```bash
alembic upgrade head
```

### 3. Switch to Database Mode

The bot will automatically use database services by default. To explicitly control this, set environment variables:

```env
USE_DATABASE_SERVICES=true
USE_DATABASE_CACHE=true
```

### 4. Test Database Integration

Test the database-backed bot:

```bash
# Test database connectivity
python main_database.py test

# Check database status
python main_database.py status

# Run bot once to test functionality
python main_database.py once
```

## Using the Database-Backed Bot

### Main Commands

```bash
# Run bot once (recommended for testing)
python main_database.py once

# Run bot continuously (production mode)
python main_database.py

# Show database status and statistics
python main_database.py status

# View pending drafts (now from database)
python main_database.py drafts

# Test all connections
python main_database.py test

# Initialize/reset database
python main_database.py setup

# Run database migrations
python main_database.py migrate
```

### Maintenance Commands

```bash
# Create database backup
python scripts/database_maintenance.py backup

# Clean up old data
python scripts/database_maintenance.py cleanup

# Optimize database performance
python scripts/database_maintenance.py vacuum

# Generate comprehensive usage report
python scripts/database_maintenance.py report

# Full maintenance (backup + cleanup + vacuum)
python scripts/database_maintenance.py full
```

## Configuration Options

### Database Settings

For **development** (default):
- Uses SQLite database: `data/twitter_bot.db`
- No additional configuration needed

For **production** (PostgreSQL):
```env
# Option 1: Full connection string
DATABASE_URL=postgresql://user:password@localhost:5432/twitter_bot

# Option 2: Individual components
DB_HOST=localhost
DB_PORT=5432
DB_NAME=twitter_bot
DB_USER=postgres
DB_PASSWORD=your_password
```

### Service Selection

```env
# Enable/disable database services
USE_DATABASE_SERVICES=true    # Use database-backed services
USE_DATABASE_CACHE=true      # Use database-backed translation cache

# Disable for file-based fallback
USE_DATABASE_SERVICES=false
USE_DATABASE_CACHE=false
```

### Debug Options

```env
# Enable SQL query logging
DB_ECHO=true

# Environment designation
ENV=development  # or production, staging
```

## Data Migration Details

### Automatically Migrated

✅ **Last Tweet ID** (`logs/last_tweet_id.txt`)
- Imported to `system_state` table
- Key: `last_tweet_id`

✅ **API Usage Data** (`logs/api_usage.json`)
- Imported to `api_usage` and `system_state` tables
- Preserves daily/monthly counters

✅ **System Configuration**
- Default user account created
- System initialization markers set

### Requires Manual Migration

⚠️ **Draft Files** (`drafts/pending/`)
- Location noted during setup
- Can be manually imported using draft manager
- Or will be recreated as new translations are processed

⚠️ **Custom Configurations**
- Review and update any custom settings
- API credentials still managed via `.env`

## Backward Compatibility

### Gradual Migration

The system supports gradual migration:

1. **Test phase**: Run with `USE_DATABASE_SERVICES=true` for testing
2. **Fallback**: Set `USE_DATABASE_SERVICES=false` to revert
3. **Full migration**: Remove file-based data after confidence

### Coexistence

Both systems can coexist:
- Database services for new data
- File-based services as fallback
- Service factory handles switching automatically

## Verification Steps

### 1. Database Health Check

```bash
python main_database.py test
```

Should show:
- ✅ Database connection successful
- ✅ All tables created
- ✅ Basic queries working

### 2. Data Verification

```bash
python main_database.py status
```

Should show:
- Database status: ✅ Healthy
- Proper API usage counters
- Zero drafts initially (unless migrated)

### 3. Functional Test

```bash
python main_database.py once
```

Should complete without errors (may need API credentials for full functionality).

## Troubleshooting

### Common Issues

**Database connection failed**:
- Check database credentials
- Ensure database server is running (PostgreSQL)
- Verify database exists and is accessible

**Migration failed**:
- Check file permissions
- Ensure `data/` directory is writable
- Review error logs for specific issues

**Service initialization failed**:
- Check environment variables
- Verify Python path includes project root
- Review import errors in logs

### Recovery Procedures

**Revert to file-based**:
```env
USE_DATABASE_SERVICES=false
USE_DATABASE_CACHE=false
```

**Reset database**:
```bash
rm data/twitter_bot.db  # For SQLite
python setup_db.py
```

**Restore from backup**:
```bash
python scripts/database_maintenance.py restore backup_file.db
```

## Performance Considerations

### SQLite (Development)
- Single file database
- Good for development and small deployments
- Automatic WAL mode for better concurrency

### PostgreSQL (Production)
- Full ACID compliance
- Better concurrent access
- Advanced analytics capabilities
- Requires separate database server

### Optimization Tips

1. **Regular maintenance**:
   ```bash
   python scripts/database_maintenance.py cleanup
   python scripts/database_maintenance.py vacuum
   ```

2. **Monitor database size**:
   ```bash
   python scripts/database_maintenance.py report
   ```

3. **Backup regularly**:
   ```bash
   python scripts/database_maintenance.py backup
   ```

## Support

If you encounter issues during migration:

1. **Check logs**: Look for error messages in bot output
2. **Verify setup**: Ensure all prerequisites are met
3. **Test incrementally**: Use `python main_database.py test` to isolate issues
4. **Fallback**: Use `USE_DATABASE_SERVICES=false` to revert temporarily
5. **Clean setup**: Remove database and re-run `setup_db.py` if needed

The database system is designed to be robust and maintain backward compatibility throughout the migration process.
