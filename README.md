# CouchDB Manager

A comprehensive Streamlit-based GUI application for managing CouchDB databases with backup, restore, sync, and delete capabilities.

## Features

- **🔄 Synchronization**: Sync databases between source and target CouchDB instances
- **🧬 Native replication**: Copy databases with CouchDB's own `_replicate` (all revisions, attachments, design docs, `_security`), verified document by document; re-runs only copy the difference
- **💾 Backup**: Create local backups of CouchDB databases with full attachment support
- **♻️ Restore**: Restore databases from backup files (supports both old and new backup formats)
- **🗑️ Delete**: Safely delete databases with multiple confirmation steps
- **📊 Dashboard**: View and compare databases across multiple CouchDB instances
- **🔍 Real-time Monitoring**: Live status updates and progress tracking

## Installation

### Prerequisites

- Python 3.8 or higher
- CouchDB instance(s) accessible via HTTP/HTTPS
- Network access to CouchDB servers

### Setup

1. Clone or download this repository:
```bash
git clone https://github.com/yourusername/couchdb-manager.git
cd couchdb-manager
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure your CouchDB connections:
```bash
cp .env.example .env
```

4. Edit `.env` file with your CouchDB credentials:
```env
# Source CouchDB Configuration
SOURCE_COUCHDB_URL=http://localhost:5984
SOURCE_COUCHDB_USER=admin
SOURCE_COUCHDB_PASSWORD=password

# Target CouchDB Configuration  
TARGET_COUCHDB_URL=http://remote-server:5984
TARGET_COUCHDB_USER=admin
TARGET_COUCHDB_PASSWORD=password
```

### Docker image

Published on GitHub Container Registry by the `Release image` workflow (amd64 + arm64): `main` → `:main`,
tag `vX.Y.Z` → `:X.Y.Z`, `:X.Y`, `:latest`. Each image is scanned with Trivy (blocked on CRITICAL fixable
vulnerabilities), runs as a non-root user, and is signed with cosign (keyless) with SBOM and provenance.

```bash
docker run -d --name couchdb-manager -p 127.0.0.1:8501:8501 --env-file .env \
  -v "$PWD/backups:/app/backups" ghcr.io/nkaurelien/couchdb-manager:latest

cosign verify ghcr.io/nkaurelien/couchdb-manager:latest \
  --certificate-identity-regexp 'https://github.com/nkaurelien/couchdb-manager/.github/workflows/release.yml@.*' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

## Usage

### Starting the Application

```bash
streamlit run couchdb_manager.py
```

The application will open in your default web browser at `http://localhost:8501`

### Dashboard Tab

View all databases from both source and target CouchDB instances:
- Compare database counts and sizes
- See design documents and regular documents count
- Identify which databases exist in each instance

### Sync Tab

Synchronize databases between source and target:
1. Select databases to sync
2. Choose sync options:
   - Skip design documents
   - Handle conflicts automatically
3. Monitor real-time progress
4. View detailed logs

### Backup Tab

Create local backups of your databases:
1. Select source (Source or Target CouchDB)
2. Choose databases to backup
3. Backups are saved to `./backups/` directory
4. Full attachment data is included in backups

Backup format:
- JSON files with CouchDB bulk docs format
- Includes all documents and attachments
- Preserves revision history

### Restore Tab

Restore databases from backup files:
1. Select target (Source or Target CouchDB)
2. Choose backup directory
3. Select databases to restore
4. Supports both attachment formats:
   - Old format: Attachments with base64 data
   - New format: Attachment stubs (automatically handled)

### Delete Tab

Safely delete databases with multiple confirmations:
1. Select target (Source or Target)
2. Choose databases to delete
3. Type database name to confirm
4. Final confirmation required
5. Irreversible operation - use with caution!

### Native Replication Tab

Copy databases from the source to the target with CouchDB's native replication — the recommended way to
migrate or catch up a database:
1. Connect both source and target in the sidebar
2. Choose all databases or a selection (system databases such as `_users` are skipped)
3. Set **Source as seen by the target** when the target CouchDB reaches the source through another address
   (e.g. `http://172.17.0.1:5984` from a container to a CouchDB running on the host)
4. Start: for each database the target is created, `_security` is copied, `_replicate` runs, then every
   document is compared (winning revision and attachment digests)
5. **Verify only** compares without copying. A source that is still written to shows mismatches until the
   writers are stopped and a last catch-up run is done.

The data goes from CouchDB to CouchDB: it never transits through the Manager.

## Command-line Replication

The same logic is available without the UI (`manage/replicate.py`, Python standard library only). Run it
where both CouchDB are reachable; passwords are read from stdin (source, then target):

```bash
printf '%s\n%s\n' "$SRC_PASS" "$TGT_PASS" | python3 manage/replicate.py \
  --source http://127.0.0.1:5984 --source-user admin \
  --source-from-target http://172.17.0.1:5984 \
  --target http://127.0.0.1:15984 --target-user admin \
  [--db <name>]... [--verify-only] [--no-attachments-check]
```

Exit code 0 only when every database matches. Databases are processed one by one; for a large catch-up,
run several databases in parallel (`xargs -P 8 ... --db {}`).

## Advanced Features

### Attachment Handling

The manager intelligently handles CouchDB attachments:
- **Backup**: Includes full attachment data (`attachments=true`)
- **Restore**: Automatically detects and handles:
  - Attachment stubs (removes before bulk insert)
  - Full attachment data (preserves in restore)
  - Mixed formats (handles appropriately)

### Error Recovery

- Automatic retry on network failures
- Detailed error logging
- Graceful handling of HTTP status codes (200, 201, 202)
- Empty response handling for bulk operations

### Performance Optimization

- Batch processing for large databases
- Configurable batch sizes (default: 100 documents)
- Progress tracking with time estimates
- Efficient memory usage for large backups

## Troubleshooting

### Common Issues

1. **Empty databases after restore**
   - Check CouchDB logs for authentication issues
   - Verify backup file integrity
   - Ensure proper permissions on target database

2. **HTTP 412 Errors during restore**
   - Usually caused by attachment stubs
   - The manager automatically handles this

3. **Connection refused**
   - Verify CouchDB is running
   - Check firewall settings
   - Confirm URL and port in `.env`

4. **Authentication failures**
   - Verify username and password
   - Check CouchDB security settings
   - Ensure user has appropriate permissions

### Debug Mode

Enable detailed logging by setting in your environment:
```bash
export DEBUG=true
streamlit run couchdb_manager.py
```

## Backup Structure

Backups are organized as follows:
```
backups/
├── source_backup_YYYYMMDD_HHMMSS/
│   └── backup_YYYYMMDD-HHMMSS/
│       ├── database1.json
│       ├── database2.json
│       └── ...
└── target_backup_YYYYMMDD_HHMMSS/
    └── backup_YYYYMMDD-HHMMSS/
        └── ...
```

## Security Considerations

- Store `.env` file securely
- Never commit credentials to version control
- Use HTTPS for remote CouchDB connections
- Implement network-level security for CouchDB access
- Regular backup verification
- The Manager has **no authentication of its own** and can delete databases: never expose it directly. The
  provided `docker-compose.yml` publishes it on `127.0.0.1` only; put it behind an authenticating proxy
  (e.g. Cloudflare Access, basic auth) if it must be reachable remotely
- Connection URLs are masked in the UI but contain credentials: anyone using the Manager can use them

## Requirements

- Python 3.8+
- streamlit >= 1.40.0
- requests >= 2.31.0
- python-dotenv >= 1.0.0
- pandas >= 2.0.0

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## License

MIT License - See LICENSE file for details

## Support

For issues, questions, or contributions, please contact the maintainer or open an issue on GitHub.

## Changelog

### Version 1.1.0 (2026-10-15)
- Native replication tab and `manage/replicate.py` CLI (revisions, attachments, design docs, `_security`,
  per-document verification, incremental re-runs)
- Database sizes read from `sizes.active` (CouchDB 2.1+ no longer returns `data_size`)
- Connection URLs masked in the UI; Python backup / restore improvements
- `docker-compose.yml` publishes the UI on `127.0.0.1` only

### Version 1.0.0 (2024-09-03)
- Initial release with full backup/restore/sync/delete capabilities
- Intelligent attachment handling for different backup formats
- Comprehensive error handling and logging
- Streamlit-based modern UI
- Support for multiple CouchDB instances

## Acknowledgments

Built with:
- [Streamlit](https://streamlit.io/) - The fantastic Python app framework
- [CouchDB](https://couchdb.apache.org/) - The reliable NoSQL database
- [Python Requests](https://requests.readthedocs.io/) - HTTP library for Python