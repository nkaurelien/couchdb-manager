#!/usr/bin/env python3
"""
CouchDB Manager - Streamlit Application
Manage CouchDB backups, restores, and synchronization
"""

import streamlit as st
import subprocess
import json
import os
import requests
from datetime import datetime
from pathlib import Path
import shutil
from urllib.parse import urlparse
import time
from typing import List, Dict, Optional, Tuple
import pandas as pd

# Configuration - Base directory is the application directory
BASE_DIR = Path(__file__).parent.resolve()
BACKUP_DIR = BASE_DIR / "backups"
BACKUP_SCRIPT = BASE_DIR / "manage" / "backup_restore_couchdb.sh"


# Page config
st.set_page_config(
    page_title="CouchDB Manager",
    page_icon="🗄️",
    layout="wide",
    initial_sidebar_state="expanded"
)

def parse_couchdb_url(url: str) -> Dict[str, str]:
    """Parse CouchDB URL to extract components"""
    parsed = urlparse(url)
    return {
        'host': parsed.hostname,
        'port': str(parsed.port) if parsed.port else '5984',
        'username': parsed.username or '',
        'password': parsed.password or '',
        'protocol': parsed.scheme
    }

def test_connection(url: str) -> Tuple[bool, str]:
    """Test CouchDB connection"""
    try:
        response = requests.get(f"{url.rstrip('/')}/_up", timeout=5)
        if response.status_code == 200:
            return True, "✅ Connection successful"
        else:
            return False, f"❌ Connection failed: HTTP {response.status_code}"
    except requests.exceptions.RequestException as e:
        return False, f"❌ Connection failed: {str(e)}"

def get_databases(url: str) -> List[str]:
    """Get list of databases from CouchDB"""
    try:
        response = requests.get(f"{url.rstrip('/')}/_all_dbs", timeout=10)
        if response.status_code == 200:
            # Filter out system databases
            dbs = [db for db in response.json() if not db.startswith('_')]
            return dbs
        return []
    except:
        return []

def get_database_info(url: str, db_name: str) -> Dict:
    """Get database information"""
    try:
        response = requests.get(f"{url.rstrip('/')}/{db_name}", timeout=5)
        if response.status_code == 200:
            return response.json()
        return {}
    except:
        return {}

def run_backup_python(source_url: str, db_name: str, output_dir: str) -> Tuple[bool, str]:
    """Python-based backup using requests instead of curl"""
    try:
        print(f"🔄 [BACKUP] Starting Python backup for database: {db_name}")
        
        # Create output directory with timestamp
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        backup_subdir = Path(output_dir) / f"backup_{timestamp}"
        backup_subdir.mkdir(parents=True, exist_ok=True)
        print(f"📁 [BACKUP] Created output directory: {backup_subdir}")
        
        # Build the CouchDB URL for _all_docs with attachments
        base_url = source_url.rstrip('/')
        all_docs_url = f"{base_url}/{db_name}/_all_docs?include_docs=true&attachments=true"
        
        print(f"🌐 [BACKUP] Fetching all documents from: {all_docs_url}")
        
        # Fetch all documents
        response = requests.get(all_docs_url, timeout=300)
        print(f"📊 [BACKUP] HTTP Response: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ [BACKUP] Failed to fetch documents: HTTP {response.status_code}")
            return False, f"Failed to fetch documents: HTTP {response.status_code} - {response.text}"
        
        # Apply the SAME transformations as bash script does with sed
        data = response.json()
        print(f"📋 [BACKUP] Parsing response data...")
        
        if 'rows' not in data:
            print(f"❌ [BACKUP] Invalid response format: missing 'rows' key")
            return False, f"Invalid response format: {data}"
        
        # Extract docs from rows (like bash script sed transformations)
        docs = []
        design_docs = []
        regular_docs = []
        
        for row in data['rows']:
            if 'doc' in row:
                doc = row['doc']
                docs.append(doc)
                if doc.get('_id', '').startswith('_design/'):
                    design_docs.append(doc)
                else:
                    regular_docs.append(doc)
        
        print(f"📄 [BACKUP] Found {len(docs)} total documents:")
        print(f"   - 🎨 Design documents: {len(design_docs)}")
        print(f"   - 📝 Regular documents: {len(regular_docs)}")
        
        # Create the EXACT format that bash script produces
        backup_data = {
            "new_edits": False,
            "docs": docs
        }
        
        # Write to JSON file in compact format (like bash script)
        backup_file = backup_subdir / f"{db_name}.json"
        print(f"💾 [BACKUP] Writing to file: {backup_file}")
        
        with open(backup_file, 'w', encoding='utf-8') as f:
            # Write in compact format with proper line breaks like bash script
            f.write('{"new_edits":false,"docs":[\n')
            for i, doc in enumerate(docs):
                if i > 0:
                    f.write(',\n')
                json.dump(doc, f, separators=(',', ':'), ensure_ascii=False)
            f.write('\n]}')
        
        file_size = backup_file.stat().st_size
        doc_count = len(docs)
        
        print(f"✅ [BACKUP] Python backup completed successfully:")
        print(f"   - 📁 File: {backup_file}")
        print(f"   - 📊 Documents: {doc_count}")
        print(f"   - 💾 Size: {file_size} bytes")
        
        return True, f"Python backup completed: {backup_file} ({doc_count} docs, {file_size} bytes)"
        
    except requests.exceptions.RequestException as e:
        return False, f"HTTP request failed: {str(e)}"
    except json.JSONDecodeError as e:
        return False, f"JSON parsing failed: {str(e)}"
    except Exception as e:
        return False, f"Python backup error: {str(e)}"

def run_backup_bash(source_url: str, db_name: str, output_dir: str) -> Tuple[bool, str]:
    """Run backup for a specific database using bash script"""
    print(f"🔄 [BACKUP-BASH] Starting bash backup for database: {db_name}")
    
    parsed = parse_couchdb_url(source_url)
    print(f"🌐 [BACKUP-BASH] Parsed URL - Host: {parsed['host']}, Port: {parsed['port']}")
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    print(f"📁 [BACKUP-BASH] Created output directory: {output_dir}")
    
    # Check if backup script exists
    if not BACKUP_SCRIPT.exists():
        print(f"❌ [BACKUP-BASH] Backup script not found at {BACKUP_SCRIPT}")
        return False, f"Backup script not found at {BACKUP_SCRIPT}"
    
    print(f"✅ [BACKUP-BASH] Found backup script: {BACKUP_SCRIPT}")
    
    # Make sure script is executable
    try:
        os.chmod(str(BACKUP_SCRIPT), 0o755)
        print(f"✅ [BACKUP-BASH] Made script executable")
    except Exception as e:
        print(f"❌ [BACKUP-BASH] Could not make script executable: {str(e)}")
        return False, f"Could not make script executable: {str(e)}"
    
    # Escape spaces in paths with backslashes
    escaped_script = str(BACKUP_SCRIPT).replace(' ', '\\ ')
    escaped_output_dir = output_dir.replace(' ', '\\ ')
    
    # Build command string with escaped spaces
    cmd_str = (
        f'bash {escaped_script} '
        f'-b '
        f'-H {parsed["host"]} '
        f'-P {parsed["port"]} '
        f'-u {parsed["username"]} '
        f'-p {parsed["password"]} '
        f'-d {db_name} '
        f'-o {escaped_output_dir}'
    )
    
    print(f"🚀 [BACKUP-BASH] Executing command:")
    print(f"   {cmd_str}")
    
    try:
        # Use shell=True with proper quoting to handle spaces
        # Provide "N\nN\n" as input to answer "No" to any prompts
        print(f"⏳ [BACKUP-BASH] Running bash script...")
        result = subprocess.run(
            cmd_str,
            shell=True,
            capture_output=True,
            text=True,
            input="N\nN\n",  # Answer "No" to any prompts
            timeout=300,  # 5 minutes timeout
            cwd=str(BASE_DIR)  # Set working directory to couchdb folder
        )
        
        print(f"📊 [BACKUP-BASH] Script completed with exit code: {result.returncode}")
        
        if result.stdout:
            print(f"📝 [BACKUP-BASH] Script output:")
            for line in result.stdout.split('\n'):
                if line.strip():
                    print(f"   {line}")
        
        if result.stderr:
            print(f"⚠️ [BACKUP-BASH] Script errors:")
            for line in result.stderr.split('\n'):
                if line.strip():
                    print(f"   {line}")
        
        # Combine stdout and stderr for full output
        full_output = f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
        
        if result.returncode == 0:
            print(f"✅ [BACKUP-BASH] Script executed successfully, checking for backup file...")
            # Check if backup file was created
            backup_files = list(Path(output_dir).glob(f"**/{db_name}.json"))
            if backup_files:
                file_size = backup_files[0].stat().st_size
                print(f"✅ [BACKUP-BASH] Backup file created: {backup_files[0]} ({file_size} bytes)")
                return True, f"Backup completed: {backup_files[0]} ({file_size} bytes)"
            else:
                print(f"❌ [BACKUP-BASH] Backup script ran but no file created")
                return False, f"Backup script ran but no file created.\n{full_output}"
        else:
            print(f"❌ [BACKUP-BASH] Script failed with exit code {result.returncode}")
            return False, f"Backup failed (exit code {result.returncode}):\n{full_output}"
    except subprocess.TimeoutExpired as e:
        return False, f"Backup timeout (5 minutes):\n{e.stdout if e.stdout else ''}\n{e.stderr if e.stderr else ''}"
    except Exception as e:
        return False, f"Backup error: {str(e)}"

def run_backup(source_url: str, db_name: str, output_dir: str) -> Tuple[bool, str]:
    """Run backup for a specific database - try Python method first, fallback to bash script"""
    # Try Python-based backup first (no curl/path issues)
    success, msg = run_backup_python(source_url, db_name, output_dir)
    if success:
        return success, msg
    
    # Fallback to bash script if Python backup fails
    print("Python backup failed, trying bash script...")
    return run_backup_bash(source_url, db_name, output_dir)

def run_restore_python(target_url: str, db_name: str, backup_file: str, clean: bool = False) -> Tuple[bool, str]:
    """Restore a database from backup using Python (avoids path space issues)"""
    try:
        import requests
        import json
        
        print(f"🔄 [RESTORE] Starting Python restore for database: {db_name}")
        print(f"📁 [RESTORE] Backup file: {backup_file}")
        print(f"🗑️ [RESTORE] Clean restore: {clean}")
        
        # Parse target URL
        parsed = parse_couchdb_url(target_url)
        base_url = f"http://{parsed['host']}:{parsed['port']}"
        auth = (parsed['username'], parsed['password'])
        print(f"🌐 [RESTORE] Target URL: {base_url}")
        
        # Check if backup file exists
        backup_path = Path(backup_file)
        if not backup_path.exists():
            print(f"❌ [RESTORE] Backup file not found: {backup_file}")
            return False, f"Backup file not found: {backup_file}"
        
        # Read backup data as raw text (don't parse JSON yet)
        try:
            print(f"📖 [RESTORE] Reading backup file...")
            with open(backup_path, 'r', encoding='utf-8') as f:
                raw_backup_data = f.read()
            file_size = len(raw_backup_data)
            print(f"📊 [RESTORE] File size: {file_size} bytes")
        except Exception as e:
            print(f"❌ [RESTORE] Error reading backup file: {e}")
            return False, f"Error reading backup file: {e}"
        
        # Parse JSON to validate format
        try:
            print(f"🔍 [RESTORE] Parsing JSON data...")
            backup_data = json.loads(raw_backup_data)
        except json.JSONDecodeError as e:
            print(f"❌ [RESTORE] Invalid JSON in backup file: {e}")
            return False, f"Invalid JSON in backup file: {e}"
        
        # Validate and fix backup format if needed
        if isinstance(backup_data, dict) and 'docs' in backup_data:
            docs = backup_data.get('docs', [])
            print(f"✅ [RESTORE] Found standard backup format with 'docs' key")
        elif isinstance(backup_data, dict) and 'rows' in backup_data:
            # Handle old format from _all_docs endpoint
            print(f"🔄 [RESTORE] Converting old format (rows) to new format (docs)")
            docs = []
            for row in backup_data['rows']:
                if 'doc' in row:
                    docs.append(row['doc'])
            # Create proper bulk_docs format
            raw_backup_data = json.dumps({"new_edits": False, "docs": docs})
            print(f"✅ [RESTORE] Converted {len(docs)} documents to new format")
        else:
            print(f"❌ [RESTORE] Invalid backup format: missing 'docs' or 'rows' key")
            return False, "Invalid backup format: missing 'docs' or 'rows' key"
        
        if not docs:
            print(f"❌ [RESTORE] No documents found in backup")
            return False, "No documents found in backup"
        
        print(f"📄 [RESTORE] Found {len(docs)} documents to restore")
        
        # Check if database exists
        db_url = f"{base_url}/{db_name}"
        print(f"🔍 [RESTORE] Checking if database exists: {db_name}")
        response = requests.head(db_url, auth=auth, timeout=10)
        db_exists = response.status_code == 200
        print(f"📊 [RESTORE] Database exists: {db_exists} (HTTP {response.status_code})")
        
        if clean and db_exists:
            print(f"🗑️ [RESTORE] Clean restore requested - deleting existing database")
            # Delete existing database
            response = requests.delete(db_url, auth=auth, timeout=10)
            if response.status_code not in [200, 202, 404]:  # 200=deleted, 202=accepted, 404=not found
                print(f"❌ [RESTORE] Failed to delete existing database: HTTP {response.status_code}")
                return False, f"Failed to delete existing database: {response.text}"
            print(f"✅ [RESTORE] Database deleted successfully (HTTP {response.status_code})")
        
        # Create database if it doesn't exist
        if not db_exists or clean:
            print(f"🏗️ [RESTORE] Creating database: {db_name}")
            response = requests.put(db_url, auth=auth, timeout=10)
            if response.status_code not in [201, 202, 412]:  # 201=created, 202=accepted, 412=already exists
                print(f"❌ [RESTORE] Failed to create database: HTTP {response.status_code}")
                return False, f"Failed to create database: {response.text}"
            print(f"✅ [RESTORE] Database created successfully (HTTP {response.status_code})")
        
        # Separate design documents from regular documents (like bash script does)
        regular_docs = []
        design_docs = []
        
        print(f"📋 [RESTORE] Analyzing document types...")
        for doc in docs:
            if doc.get('_id', '').startswith('_design/'):
                design_docs.append(doc)
            else:
                regular_docs.append(doc)
        
        print(f"📊 [RESTORE] Document breakdown:")
        print(f"   - 🎨 Design documents: {len(design_docs)}")
        print(f"   - 📝 Regular documents: {len(regular_docs)}")
        
        total_restored = 0
        messages = []
        
        # First, restore design documents individually (like bash script)
        if design_docs:
            print(f"🎨 [RESTORE] Restoring {len(design_docs)} design documents individually...")
            messages.append(f"Restoring {len(design_docs)} design documents...")
            
            for i, design_doc in enumerate(design_docs, 1):
                doc_id = design_doc.get('_id', '')
                print(f"   📄 [RESTORE] [{i}/{len(design_docs)}] Restoring design doc: {doc_id}")
                
                # Remove _rev for design docs to avoid conflicts
                clean_doc = {k: v for k, v in design_doc.items() if k != '_rev'}
                
                doc_url = f"{db_url}/{doc_id}"
                response = requests.put(
                    doc_url,
                    auth=auth,
                    json=clean_doc,
                    timeout=30
                )
                
                if response.status_code in [200, 201, 202]:  # Accept HTTP 202 for design docs
                    print(f"   ✅ [RESTORE] Design doc restored successfully (HTTP {response.status_code})")
                    total_restored += 1
                else:
                    print(f"   🔄 [RESTORE] Design doc exists, attempting update...")
                    # Try to update if it exists
                    get_response = requests.get(doc_url, auth=auth, timeout=10)
                    if get_response.status_code == 200:
                        existing_doc = get_response.json()
                        clean_doc['_rev'] = existing_doc['_rev']
                        update_response = requests.put(doc_url, auth=auth, json=clean_doc, timeout=30)
                        if update_response.status_code in [200, 201, 202]:  # Accept HTTP 202 for updates
                            print(f"   ✅ [RESTORE] Design doc updated successfully (HTTP {update_response.status_code})")
                            total_restored += 1
                        else:
                            print(f"   ❌ [RESTORE] Failed to update design doc: HTTP {update_response.status_code}")
                    else:
                        print(f"   ❌ [RESTORE] Failed to restore design doc: HTTP {response.status_code}")
        
        # Then, restore regular documents using bulk API
        if regular_docs:
            print(f"📝 [RESTORE] Restoring {len(regular_docs)} regular documents using bulk API...")
            
            # Clean documents by handling different attachment types
            cleaned_docs = []
            for doc in regular_docs:
                clean_doc = doc.copy()
                # Handle attachments - keep those with data, remove stubs
                if '_attachments' in clean_doc:
                    attachments = clean_doc['_attachments']
                    has_stubs = False
                    has_data = False
                    
                    # Check what type of attachments we have
                    for att_name, att_data in attachments.items():
                        if att_data.get('stub') == True:
                            has_stubs = True
                            print(f"📎 [RESTORE] Found attachment stub '{att_name}' in {clean_doc.get('_id', 'unknown')}")
                        elif 'data' in att_data:
                            has_data = True
                            print(f"📎 [RESTORE] Found attachment with data '{att_name}' in {clean_doc.get('_id', 'unknown')}")
                    
                    # Remove entire _attachments if we have stubs (they cause errors)
                    if has_stubs and not has_data:
                        print(f"📎 [RESTORE] Removing all attachment stubs from {clean_doc.get('_id', 'unknown')}")
                        del clean_doc['_attachments']
                    # Keep attachments with actual data - they should work fine
                    
                cleaned_docs.append(clean_doc)
            
            bulk_data = {"new_edits": False, "docs": cleaned_docs}
            bulk_raw_data = json.dumps(bulk_data)
            
            bulk_url = f"{db_url}/_bulk_docs"
            print(f"🌐 [RESTORE] Sending bulk request to: {bulk_url}")
            print(f"📊 [RESTORE] Payload size: {len(bulk_raw_data)} bytes")
            
            response = requests.post(
                bulk_url,
                auth=auth,
                data=bulk_raw_data,  # Send raw JSON data like the bash script
                headers={'Content-Type': 'application/json'},
                timeout=300  # 5 minutes for bulk operation
            )
            
            print(f"📊 [RESTORE] Bulk API response: HTTP {response.status_code}")
            
            if response.status_code in [200, 201, 202]:  # Accept HTTP 202 for bulk operations
                try:
                    result_data = response.json()
                    print(f"📋 [RESTORE] Processing bulk API results...")
                    print(f"📊 [RESTORE] Raw response: {result_data}")
                    
                    # Handle empty response (some CouchDB versions return [] for successful bulk operations)
                    if isinstance(result_data, list) and len(result_data) == 0:
                        print(f"📋 [RESTORE] Empty response detected - assuming all documents succeeded")
                        successful = len(cleaned_docs)  # Assume all succeeded
                        errors = []
                    else:
                        # Check results for each document
                        successful = 0
                        errors = []
                        
                        for result in result_data:
                            if result.get('error'):
                                error_msg = f"{result.get('id', 'unknown')}: {result.get('error')} ({result.get('reason', 'no reason')})"
                                errors.append(error_msg)
                            elif result.get('ok'):
                                successful += 1
                    
                    total_restored += successful
                    print(f"✅ [RESTORE] Bulk operation completed: {successful}/{len(cleaned_docs)} documents successful")
                    messages.append(f"Bulk restored {successful}/{len(cleaned_docs)} regular documents")
                    
                    if errors:
                        print(f"⚠️ [RESTORE] {len(errors)} documents had errors")
                        if len(errors) <= 10:
                            messages.append(f"Errors: {'; '.join(errors)}")
                            for error in errors[:5]:  # Log first 5 errors to console
                                print(f"   ❌ [RESTORE] {error}")
                        else:
                            messages.append(f"First 5 errors: {'; '.join(errors[:5])}... and {len(errors)-5} more")
                            for error in errors[:5]:  # Log first 5 errors to console
                                print(f"   ❌ [RESTORE] {error}")
                                
                except json.JSONDecodeError:
                    print(f"⚠️ [RESTORE] Could not parse bulk response as JSON, assuming success")
                    total_restored += len(cleaned_docs)
                    messages.append(f"Bulk restored {len(cleaned_docs)} regular documents (response not parsable)")
            else:
                print(f"❌ [RESTORE] Bulk restore failed: HTTP {response.status_code}")
                print(f"📋 [RESTORE] Response content: {response.text}")
                
                # HTTP 412 is often related to precondition failures - try to provide helpful info
                if response.status_code == 412:
                    try:
                        error_data = response.json()
                        print(f"📊 [RESTORE] Error details: {error_data}")
                        
                        # Common issue: document conflicts or missing _rev
                        if any(keyword in str(error_data).lower() for keyword in ['conflict', 'revision', 'rev']):
                            print(f"💡 [RESTORE] This might be a document revision conflict. Trying alternative approach...")
                            # Could implement a retry with individual document creation here
                            
                    except:
                        pass  # Continue with regular error handling
                
                return False, f"Bulk restore failed (HTTP {response.status_code}): {response.text}"
        
        # Verify the restore by checking document count
        print(f"🔍 [RESTORE] Verifying restore by checking database info...")
        try:
            verify_response = requests.get(db_url, auth=auth, timeout=10)
            if verify_response.status_code == 200:
                db_info = verify_response.json()
                actual_count = db_info.get('doc_count', 0)
                deleted_count = db_info.get('doc_del_count', 0)
                
                print(f"📊 [RESTORE] Database verification:")
                print(f"   - 📄 Total documents: {actual_count}")
                print(f"   - 🗑️ Deleted documents: {deleted_count}")
                
                messages.append(f"Database now contains {actual_count} documents")
                
                if actual_count == 0 and total_restored > 0:
                    print(f"⚠️ [RESTORE] WARNING: Documents restored but database shows 0 count - possible conflicts")
                    messages.append("⚠️ WARNING: Documents may not be visible due to conflicts")
                elif actual_count != total_restored:
                    print(f"⚠️ [RESTORE] NOTE: Restored {total_restored} but database shows {actual_count} documents")
            else:
                print(f"⚠️ [RESTORE] Could not verify database info: HTTP {verify_response.status_code}")
        except Exception as e:
            print(f"⚠️ [RESTORE] Verification error (non-critical): {e}")
            
        print(f"✅ [RESTORE] Restore operation completed!")
        print(f"📊 [RESTORE] Summary: {total_restored} documents restored to '{db_name}'")
        
        result_msg = f"Successfully restored {total_restored} documents to '{db_name}'. " + " | ".join(messages)
        return True, result_msg
            
    except requests.RequestException as e:
        print(f"❌ [RESTORE] Network error during restore: {str(e)}")
        return False, f"Network error during restore: {str(e)}"
    except Exception as e:
        print(f"❌ [RESTORE] Restore error: {str(e)}")
        return False, f"Restore error: {str(e)}"


def run_restore_bash(target_url: str, db_name: str, backup_path: str, clean: bool = False) -> Tuple[bool, str]:
    """Restore a database from backup using bash script"""
    print(f"🔄 [RESTORE-BASH] Starting bash restore for database: {db_name}")
    print(f"📁 [RESTORE-BASH] Backup path: {backup_path}")
    print(f"🗑️ [RESTORE-BASH] Clean restore: {clean}")
    
    parsed = parse_couchdb_url(target_url)
    print(f"🌐 [RESTORE-BASH] Parsed URL - Host: {parsed['host']}, Port: {parsed['port']}")
    
    # Check if backup exists
    if not Path(backup_path).exists():
        print(f"❌ [RESTORE-BASH] Backup file not found: {backup_path}")
        return False, f"Backup file not found: {backup_path}"
    
    print(f"✅ [RESTORE-BASH] Found backup file: {backup_path}")
    
    # Build command with proper path handling
    backup_dir = str(Path(backup_path).parent)
    cmd = [
        "bash", str(BACKUP_SCRIPT),
        "-r",  # restore mode
        "-H", parsed['host'],
        "-P", parsed['port'],
        "-u", parsed['username'],
        "-p", parsed['password'],
        "-d", db_name,
        "-i", backup_dir
    ]
    
    if clean:
        cmd.append("-c")  # clean/recreate database
        print(f"🗑️ [RESTORE-BASH] Clean mode enabled - will recreate database")
    
    print(f"🚀 [RESTORE-BASH] Executing bash restore command:")
    cmd_display = cmd.copy()
    cmd_display[9] = "****"  # Hide password in logs
    print(f"   {' '.join(cmd_display)}")
    
    try:
        print(f"⏳ [RESTORE-BASH] Running bash restore script...")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minutes timeout
            input="N\nN\n"  # Auto-answer interactive prompts
        )
        
        print(f"📊 [RESTORE-BASH] Script completed with exit code: {result.returncode}")
        
        if result.stdout:
            print(f"📝 [RESTORE-BASH] Script output:")
            for line in result.stdout.split('\n'):
                if line.strip():
                    print(f"   {line}")
        
        if result.stderr:
            print(f"⚠️ [RESTORE-BASH] Script errors:")
            for line in result.stderr.split('\n'):
                if line.strip():
                    print(f"   {line}")
        
        full_output = result.stdout + "\n" + result.stderr
        
        if result.returncode == 0:
            print(f"✅ [RESTORE-BASH] Database '{db_name}' restored successfully")
            return True, f"Database '{db_name}' restored successfully"
        else:
            print(f"❌ [RESTORE-BASH] Restore failed with exit code {result.returncode}")
            return False, f"Restore failed (exit code {result.returncode}):\n{full_output}"
            
    except subprocess.TimeoutExpired:
        print(f"⏰ [RESTORE-BASH] Restore script timed out after 10 minutes")
        return False, "Restore timeout (10 minutes)"
    except Exception as e:
        print(f"❌ [RESTORE-BASH] Restore error: {str(e)}")
        return False, f"Restore error: {str(e)}"


def run_restore(target_url: str, db_name: str, backup_path: str, clean: bool = False) -> Tuple[bool, str]:
    """Restore a database from backup - try Python method first, fallback to bash script"""
    # Try Python-based restore first (no path space issues)
    success, msg = run_restore_python(target_url, db_name, backup_path, clean)
    if success:
        return success, msg
    
    # Fallback to bash script if Python restore fails
    print("Python restore failed, trying bash script...")
    return run_restore_bash(target_url, db_name, backup_path, clean)


def delete_database(server_url: str, db_name: str) -> Tuple[bool, str]:
    """Delete a database from CouchDB server"""
    try:
        import requests
        
        print(f"🗑️ [DELETE] Starting deletion of database: {db_name}")
        
        # Parse server URL
        parsed = parse_couchdb_url(server_url)
        base_url = f"http://{parsed['host']}:{parsed['port']}"
        auth = (parsed['username'], parsed['password'])
        
        print(f"🌐 [DELETE] Target server: {base_url}")
        
        # Check if database exists
        db_url = f"{base_url}/{db_name}"
        print(f"🔍 [DELETE] Checking if database exists: {db_name}")
        
        response = requests.head(db_url, auth=auth, timeout=10)
        
        if response.status_code == 404:
            print(f"❌ [DELETE] Database '{db_name}' does not exist")
            return False, f"Database '{db_name}' does not exist"
        elif response.status_code != 200:
            print(f"❌ [DELETE] Error checking database: HTTP {response.status_code}")
            return False, f"Error checking database: HTTP {response.status_code} - {response.text}"
        
        print(f"✅ [DELETE] Database exists, proceeding with deletion")
        
        # Delete the database
        print(f"🗑️ [DELETE] Sending DELETE request...")
        delete_response = requests.delete(db_url, auth=auth, timeout=30)
        
        print(f"📊 [DELETE] Delete response: HTTP {delete_response.status_code}")
        
        if delete_response.status_code in [200, 202]:
            print(f"✅ [DELETE] Database '{db_name}' deleted successfully (HTTP {delete_response.status_code})")
            return True, f"Database '{db_name}' deleted successfully"
        else:
            print(f"❌ [DELETE] Failed to delete database: HTTP {delete_response.status_code}")
            return False, f"Failed to delete database: HTTP {delete_response.status_code} - {delete_response.text}"
            
    except requests.RequestException as e:
        print(f"❌ [DELETE] Network error: {str(e)}")
        return False, f"Network error: {str(e)}"
    except Exception as e:
        print(f"❌ [DELETE] Error: {str(e)}")
        return False, f"Error: {str(e)}"

def list_backups() -> List[Dict]:
    """List all available backups"""
    backups = []
    
    if not BACKUP_DIR.exists():
        return backups
    
    for backup_dir in BACKUP_DIR.iterdir():
        if backup_dir.is_dir():
            # Find all JSON files in this backup
            json_files = list(backup_dir.glob("**/*.json"))
            
            if json_files:
                # Get backup info
                total_size = sum(f.stat().st_size for f in json_files)
                
                backups.append({
                    'name': backup_dir.name,
                    'path': str(backup_dir),
                    'databases': [f.stem for f in json_files],
                    'file_count': len(json_files),
                    'size_mb': round(total_size / (1024 * 1024), 2),
                    'created': datetime.fromtimestamp(backup_dir.stat().st_mtime)
                })
    
    return sorted(backups, key=lambda x: x['created'], reverse=True)

# Initialize session state
if 'source_url' not in st.session_state:
    st.session_state.source_url = ""
if 'target_url' not in st.session_state:
    st.session_state.target_url = ""

# Header
st.title("🗄️ CouchDB Manager")
st.markdown("Manage CouchDB backups, restores, and synchronization")

# Initialize cache in session state
if 'source_dbs_cache' not in st.session_state:
    st.session_state.source_dbs_cache = []
if 'target_dbs_cache' not in st.session_state:
    st.session_state.target_dbs_cache = []
if 'source_connected' not in st.session_state:
    st.session_state.source_connected = False
if 'target_connected' not in st.session_state:
    st.session_state.target_connected = False
if 'backups_cache' not in st.session_state:
    st.session_state.backups_cache = []

# Sidebar - Connection Settings
with st.sidebar:
    st.header("🔌 Connections")

    # Load from .env if exists
    # Try multiple locations for .env file
    env_locations = [
        BASE_DIR / ".env",
        BASE_DIR.parent / "backend" / ".env",
        Path("../.env"),
        Path(".env")
    ]
    
    env_file = None
    for location in env_locations:
        if location.exists():
            env_file = location
            break
    
    if env_file and st.button(f"📄 Load from {env_file.name}"):
        with open(env_file) as f:
            for line in f:
                if line.startswith("COUCHDB_URL="):
                    st.session_state.source_url = line.split("=", 1)[1].strip()
                elif line.startswith("REMOTE_COUCHDB_URL="):
                    st.session_state.target_url = line.split("=", 1)[1].strip()
        # Clear cache when loading new URLs
        st.session_state.source_dbs_cache = []
        st.session_state.target_dbs_cache = []
        st.session_state.source_connected = False
        st.session_state.target_connected = False

    st.divider()

    st.subheader("Source Database")
    col1, col2 = st.columns([3, 1])
    
    with col1:
        source_url = st.text_input(
            "Source CouchDB URL",
            value=st.session_state.source_url,
            placeholder="http://username:password@localhost:5984/",
            help="Format: http://username:password@host:port/"
        )
    
    with col2:
        st.write("")  # Space for alignment
        refresh_source = st.button("🔄", key="refresh_source", help="Refresh source databases")
    
    if source_url:
        st.session_state.source_url = source_url
        
        # Check if we need to refresh the connection/cache
        if refresh_source or not st.session_state.source_connected or not st.session_state.source_dbs_cache:
            connected, msg = test_connection(source_url)
            st.session_state.source_connected = connected
            
            if connected:
                with st.spinner("Loading databases..."):
                    st.session_state.source_dbs_cache = get_databases(source_url)
                st.success(f"✅ Found {len(st.session_state.source_dbs_cache)} databases")
            else:
                st.error(f"❌ {msg}")
                st.session_state.source_dbs_cache = []
        else:
            # Use cached data
            if st.session_state.source_connected:
                st.success(f"✅ Found {len(st.session_state.source_dbs_cache)} databases (cached)")
            else:
                st.error("❌ Not connected")
    
    st.divider()
    
    st.subheader("Target Database")
    col1, col2 = st.columns([3, 1])
    
    with col1:
        target_url = st.text_input(
            "Target CouchDB URL",
            value=st.session_state.target_url,
            placeholder="http://username:password@remote-server:5984/",
            help="Format: http://username:password@host:port/"
        )
    
    with col2:
        st.write("")  # Space for alignment
        refresh_target = st.button("🔄", key="refresh_target", help="Refresh target databases")
    
    if target_url:
        st.session_state.target_url = target_url
        
        # Check if we need to refresh the connection/cache
        if refresh_target or not st.session_state.target_connected or not st.session_state.target_dbs_cache:
            connected, msg = test_connection(target_url)
            st.session_state.target_connected = connected
            
            if connected:
                with st.spinner("Loading databases..."):
                    st.session_state.target_dbs_cache = get_databases(target_url)
                st.success(f"✅ Found {len(st.session_state.target_dbs_cache)} databases")
            else:
                st.error(f"❌ {msg}")
                st.session_state.target_dbs_cache = []
        else:
            # Use cached data
            if st.session_state.target_connected:
                st.success(f"✅ Found {len(st.session_state.target_dbs_cache)} databases (cached)")
            else:
                st.error("❌ Not connected")

    st.divider()

    # Show current paths for debugging
    with st.expander("🔧 Debug Info"):
        st.text(f"Base Dir: {BASE_DIR}")
        st.text(f"Backup Dir: {BACKUP_DIR}")
        st.text(f"Script: {BACKUP_SCRIPT}")
        st.text(f"Script exists: {BACKUP_SCRIPT.exists()}")
        st.text(f"Current Dir: {Path.cwd()}")

# Main content - Tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs(["🔍 Overview", "💾 Backup", "📥 Restore", "🔄 Sync", "🗑️ Delete"])

# Tab 1: Overview
with tab1:
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📊 Source Databases")
        if source_url and st.session_state.source_connected and st.session_state.source_dbs_cache:
            source_dbs = st.session_state.source_dbs_cache
            db_info = []
            for db in source_dbs:
                info = get_database_info(source_url, db)
                db_info.append({
                    'Database': db,
                    'Documents': info.get('doc_count', 0),
                    'Size (MB)': round(info.get('data_size', 0) / (1024 * 1024), 2) if 'data_size' in info else 0
                })
            
            df = pd.DataFrame(db_info)
            st.dataframe(df, width='stretch')
        else:
            st.info("No databases found or not connected")
    
    with col2:
        st.subheader("📊 Target Databases")
        if target_url and st.session_state.target_connected and st.session_state.target_dbs_cache:
            target_dbs = st.session_state.target_dbs_cache
            db_info = []
            for db in target_dbs:
                info = get_database_info(target_url, db)
                db_info.append({
                    'Database': db,
                    'Documents': info.get('doc_count', 0),
                    'Size (MB)': round(info.get('data_size', 0) / (1024 * 1024), 2) if 'data_size' in info else 0
                })
            
            df = pd.DataFrame(db_info)
            st.dataframe(df, width='stretch')
        else:
            st.info("No databases found or not connected")
    
    st.divider()
    
    # Available Backups with refresh button
    col1, col2 = st.columns([4, 1])
    with col1:
        st.subheader("📦 Available Backups")
    with col2:
        st.write("")  # Space for alignment
        refresh_backups = st.button("🔄", key="refresh_backups", help="Refresh backup list")
    
    # Load backups: refresh if button clicked, or load initially if cache is empty
    if refresh_backups or not st.session_state.backups_cache:
        with st.spinner("Loading backups..."):
            backups = list_backups()
            st.session_state.backups_cache = backups
    else:
        backups = st.session_state.backups_cache
    
    if backups:
        backup_df = pd.DataFrame(backups)
        backup_df['created'] = backup_df['created'].dt.strftime('%Y-%m-%d %H:%M:%S')
        st.dataframe(
            backup_df[['name', 'file_count', 'size_mb', 'created']],
            width='stretch'
        )
        if not refresh_backups and 'backups_cache' in st.session_state:
            st.caption("ℹ️ Showing cached backup list - click 🔄 to refresh")
    else:
        st.info("No backups found")

# Tab 2: Backup
with tab2:
    st.header("💾 Backup Databases")
    
    # Choose backup source
    backup_source = st.radio(
        "Backup From:",
        ["Source Database", "Target Database"],
        help="Choose which database to backup from"
    )
    
    backup_url = source_url if backup_source == "Source Database" else target_url
    backup_dbs_cache = st.session_state.source_dbs_cache if backup_source == "Source Database" else st.session_state.target_dbs_cache
    backup_connected = st.session_state.source_connected if backup_source == "Source Database" else st.session_state.target_connected
    
    if backup_url and backup_connected and backup_dbs_cache:
        backup_dbs = backup_dbs_cache
        
        if backup_dbs:
            col1, col2 = st.columns([2, 1])
            
            with col1:
                # Database selection
                backup_mode = st.radio(
                    "Backup Mode",
                    ["Selected Databases", "All Databases"]
                )
                
                if backup_mode == "Selected Databases":
                    selected_dbs = st.multiselect(
                        f"Select databases to backup from {backup_source.lower()}",
                        backup_dbs,
                        default=[]
                    )
                else:
                    selected_dbs = backup_dbs
                    st.info(f"Will backup all {len(backup_dbs)} databases from {backup_source.lower()}")
            
            with col2:
                # Backup name
                source_prefix = "source" if backup_source == "Source Database" else "target"
                default_name = f"{source_prefix}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                backup_name = st.text_input(
                    "Backup Name",
                    value=default_name
                )
            
            # Start backup
            if st.button("🚀 Start Backup", type="primary"):
                if selected_dbs and backup_name:
                    backup_dir = BACKUP_DIR / backup_name
                    
                    # Console logging
                    print(f"\n{'='*50}")
                    print(f"🚀 [UI] BACKUP OPERATION STARTED")
                    print(f"{'='*50}")
                    print(f"📅 Timestamp: {datetime.now().isoformat()}")
                    print(f"👤 User initiated backup via Streamlit UI")
                    print(f"📁 Backup directory: {backup_dir}")
                    print(f"📊 Selected databases: {selected_dbs}")
                    print(f"🌐 Source URL: {source_url}")
                    print(f"🛠️ Backup method: Python (with Bash fallback)")
                    
                    # Show debug info
                    with st.expander("Debug Information", expanded=False):
                        st.text(f"Backup directory: {backup_dir}")
                        st.text(f"Script path: {BACKUP_SCRIPT}")
                        st.text(f"Script exists: {BACKUP_SCRIPT.exists()}")
                        st.text(f"Source URL: {source_url}")
                    
                    progress = st.progress(0)
                    status = st.empty()
                    results_container = st.container()
                    
                    success_count = 0
                    failed_dbs = []
                    
                    for idx, db in enumerate(selected_dbs):
                        status.text(f"Backing up {db}... ({idx+1}/{len(selected_dbs)})")
                        
                        # Use the main backup directory - the script will create its own subdirectory
                        success, msg = run_backup(backup_url, db, str(backup_dir))
                        
                        if success:
                            success_count += 1
                            with results_container:
                                st.success(f"✅ {db}: {msg}")
                        else:
                            failed_dbs.append((db, msg))
                            with results_container:
                                with st.expander(f"❌ {db} - Click for details", expanded=False):
                                    st.code(msg)
                        
                        progress.progress((idx + 1) / len(selected_dbs))
                    
                    status.empty()
                    
                    # Show final summary
                    st.divider()
                    if success_count == len(selected_dbs):
                        st.success(f"✅ All {success_count} databases backed up successfully to {backup_name}")
                        # Refresh backups cache after successful backup
                        st.session_state.backups_cache = list_backups()
                    else:
                        st.warning(f"⚠️ Backed up {success_count}/{len(selected_dbs)} databases")
                        # Refresh backups cache even if partial success (new backups may have been created)
                        if success_count > 0:
                            st.session_state.backups_cache = list_backups()
                        
                        if failed_dbs:
                            st.error(f"Failed: {len(failed_dbs)} database(s)")
                else:
                    st.warning("Please select databases and provide a backup name")
        else:
            st.warning(f"No databases found in {backup_source.lower()}")
    else:
        st.warning(f"Please configure {backup_source.lower()} in the sidebar")

# Tab 3: Restore
with tab3:
    st.header("📥 Restore Databases")
    
    # Choose restore target
    restore_target = st.radio(
        "Restore To:",
        ["Source Database", "Target Database"],
        help="Choose which database to restore to"
    )
    
    restore_url = source_url if restore_target == "Source Database" else target_url
    restore_connected = st.session_state.source_connected if restore_target == "Source Database" else st.session_state.target_connected
    
    if restore_url and restore_connected:
        # Use cached backups if available
        if 'backups_cache' in st.session_state:
            backups = st.session_state.backups_cache
        else:
            backups = list_backups()
            st.session_state.backups_cache = backups
        
        if backups:
            col1, col2 = st.columns([2, 1])
            
            with col1:
                # Select backup
                backup_names = [b['name'] for b in backups]
                selected_backup_name = st.selectbox(
                    "Select Backup",
                    backup_names
                )
                
                if selected_backup_name:
                    selected_backup = next(b for b in backups if b['name'] == selected_backup_name)
                    
                    st.info(f"📅 Created: {selected_backup['created']}")
                    st.info(f"📊 Databases: {', '.join(selected_backup['databases'])}")
                    
                    # Select databases to restore
                    restore_mode = st.radio(
                        "Restore Mode",
                        ["Selected Databases", "All Databases"]
                    )
                    
                    if restore_mode == "Selected Databases":
                        selected_dbs = st.multiselect(
                            "Select databases to restore",
                            selected_backup['databases'],
                            default=[]
                        )
                    else:
                        selected_dbs = selected_backup['databases']
                        st.info(f"Will restore all {len(selected_dbs)} databases")
            
            with col2:
                # Restore options
                clean_restore = st.checkbox(
                    "Clean Restore",
                    value=False,
                    help="Delete existing database before restore"
                )
                
                if clean_restore:
                    st.error("⚠️ Clean restore will DELETE ALL existing data!")
                    confirm_clean = st.checkbox(
                        "I understand and confirm deletion of existing data",
                        value=False,
                        key="confirm_clean_restore"
                    )
                else:
                    confirm_clean = True  # No confirmation needed for normal restore
            
            # Start restore
            if st.button("🚀 Start Restore", type="primary"):
                if selected_dbs and (not clean_restore or confirm_clean):
                    backup_path = Path(selected_backup['path'])
                    
                    # Console logging
                    print(f"\n{'='*50}")
                    print(f"🚀 [UI] RESTORE OPERATION STARTED")
                    print(f"{'='*50}")
                    print(f"📅 Timestamp: {datetime.now().isoformat()}")
                    print(f"👤 User initiated restore via Streamlit UI")
                    print(f"📁 Backup path: {backup_path}")
                    print(f"📊 Selected databases: {selected_dbs}")
                    print(f"🌐 Target URL: {target_url}")
                    print(f"🗑️ Clean restore: {clean_restore}")
                    
                    progress = st.progress(0)
                    status = st.empty()
                    
                    success_count = 0
                    failed_dbs = []
                    
                    for idx, db in enumerate(selected_dbs):
                        status.text(f"Restoring {db}... ({idx+1}/{len(selected_dbs)})")
                        
                        # Find backup file
                        db_files = list(backup_path.glob(f"**/{db}.json"))
                        if db_files:
                            success, msg = run_restore(restore_url, db, str(db_files[0]), clean_restore)
                            
                            if success:
                                success_count += 1
                            else:
                                failed_dbs.append((db, msg))
                        else:
                            failed_dbs.append((db, "Backup file not found"))
                        
                        progress.progress((idx + 1) / len(selected_dbs))
                    
                    status.empty()
                    progress.empty()
                    
                    # Show results
                    if success_count == len(selected_dbs):
                        st.success(f"✅ All {success_count} databases restored successfully")
                    else:
                        st.warning(f"⚠️ Restored {success_count}/{len(selected_dbs)} databases")
                        
                        if failed_dbs:
                            st.error("Failed databases:")
                            for db, error in failed_dbs:
                                st.error(f"  - {db}: {error}")
                elif clean_restore and not confirm_clean:
                    st.error("⚠️ You must confirm deletion of existing data to proceed with clean restore")
                else:
                    st.warning("Please select databases to restore")
        else:
            st.info("No backups available. Create a backup first.")
    else:
        st.warning(f"Please configure {restore_target.lower()} in the sidebar")

# Tab 4: Sync
with tab4:
    st.header("🔄 Synchronize Databases")
    
    if source_url and target_url:
        # Choose sync direction
        sync_direction = st.radio(
            "Sync Direction:",
            ["Source → Target", "Target → Source"],
            help="Choose the direction of synchronization"
        )
        
        if sync_direction == "Source → Target":
            sync_from_url = source_url
            sync_to_url = target_url
            sync_from_name = "Source"
            sync_to_name = "Target"
        else:
            sync_from_url = target_url
            sync_to_url = source_url
            sync_from_name = "Target"
            sync_to_name = "Source"
        
        sync_from_dbs = st.session_state.source_dbs_cache if sync_direction == "Source → Target" else st.session_state.target_dbs_cache
        sync_to_dbs = st.session_state.target_dbs_cache if sync_direction == "Source → Target" else st.session_state.source_dbs_cache
        sync_from_connected = st.session_state.source_connected if sync_direction == "Source → Target" else st.session_state.target_connected
        sync_to_connected = st.session_state.target_connected if sync_direction == "Source → Target" else st.session_state.source_connected
        
        if sync_from_connected and sync_to_connected and sync_from_dbs and sync_to_dbs:
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader(f"{sync_from_name} → {sync_to_name}")
                
                # Sync mode
                sync_mode = st.radio(
                    "Sync Mode",
                    ["Selected Databases", "All Databases", "New Databases Only"]
                )
                
                if sync_mode == "Selected Databases":
                    selected_dbs = st.multiselect(
                        f"Select databases to sync from {sync_from_name.lower()}",
                        sync_from_dbs,
                        default=[]
                    )
                elif sync_mode == "All Databases":
                    selected_dbs = sync_from_dbs
                    st.info(f"Will sync all {len(sync_from_dbs)} databases")
                else:  # New Databases Only
                    selected_dbs = [db for db in sync_from_dbs if db not in sync_to_dbs]
                    st.info(f"Will sync {len(selected_dbs)} new databases")
                    if selected_dbs:
                        st.write("New databases:", ", ".join(selected_dbs))
            
            with col2:
                st.subheader("Options")
                
                clean_sync = st.checkbox(
                    "Clean Sync",
                    value=False,
                    help="Delete target database before sync"
                )
                
                if clean_sync:
                    st.error(f"⚠️ Clean sync will DELETE ALL existing data in {sync_to_name.lower()}!")
                    confirm_clean_sync = st.checkbox(
                        f"I understand and confirm deletion of existing data in {sync_to_name.lower()}",
                        value=False,
                        key="confirm_clean_sync"
                    )
                else:
                    confirm_clean_sync = True  # No confirmation needed for normal sync
                
                # Show comparison
                st.divider()
                comparison = {
                    f'{sync_from_name} Only': [db for db in sync_from_dbs if db not in sync_to_dbs],
                    f'{sync_to_name} Only': [db for db in sync_to_dbs if db not in sync_from_dbs],
                    'Both': [db for db in sync_from_dbs if db in sync_to_dbs]
                }
                
                st.write(f"📊 {sync_from_name} only: {len(comparison[f'{sync_from_name} Only'])}")
                st.write(f"📊 {sync_to_name} only: {len(comparison[f'{sync_to_name} Only'])}")
                st.write(f"📊 In both: {len(comparison['Both'])}")
            
            # Start sync
            if st.button("🚀 Start Synchronization", type="primary"):
                if selected_dbs and (not clean_sync or confirm_clean_sync):
                    # Create temporary backup directory
                    temp_backup = BACKUP_DIR / f"temp_sync_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    
                    progress = st.progress(0)
                    status = st.empty()
                    
                    success_count = 0
                    failed_dbs = []
                    total_steps = len(selected_dbs) * 2  # backup + restore
                    current_step = 0
                    
                    for db in selected_dbs:
                        # Backup from source
                        status.text(f"Backing up {db} from {sync_from_name.lower()}...")
                        success, msg = run_backup(sync_from_url, db, str(temp_backup))
                        current_step += 1
                        progress.progress(current_step / total_steps)
                        
                        if success:
                            # Restore to target
                            status.text(f"Restoring {db} to {sync_to_name.lower()}...")
                            
                            # Find backup file
                            db_files = list(temp_backup.glob(f"**/{db}.json"))
                            if db_files:
                                success, msg = run_restore(sync_to_url, db, str(db_files[0]), clean_sync)
                                
                                if success:
                                    success_count += 1
                                else:
                                    failed_dbs.append((db, f"Restore failed: {msg}"))
                            else:
                                failed_dbs.append((db, "Backup file not found"))
                        else:
                            failed_dbs.append((db, f"Backup failed: {msg}"))
                        
                        current_step += 1
                        progress.progress(current_step / total_steps)
                    
                    status.empty()
                    progress.empty()
                    
                    # Clean up temp backup
                    if temp_backup.exists():
                        shutil.rmtree(temp_backup)
                    
                    # Show results
                    if success_count == len(selected_dbs):
                        st.success(f"✅ All {success_count} databases synchronized successfully")
                    else:
                        st.warning(f"⚠️ Synchronized {success_count}/{len(selected_dbs)} databases")
                        
                        if failed_dbs:
                            st.error("Failed databases:")
                            for db, error in failed_dbs:
                                st.error(f"  - {db}: {error}")
                elif clean_sync and not confirm_clean_sync:
                    st.error(f"⚠️ You must confirm deletion of existing data in {sync_to_name.lower()} to proceed with clean sync")
                else:
                    st.warning("Please select databases to synchronize")
        else:
            st.warning(f"Please ensure both {sync_from_name.lower()} and {sync_to_name.lower()} databases are connected")
    else:
        st.warning("Please configure both source and target databases in the sidebar")

# Tab 5: Delete Databases
with tab5:
    st.header("🗑️ Delete Databases")
    st.warning("⚠️ **WARNING**: This will permanently delete databases and all their data!")
    
    # Choose server
    delete_server = st.radio(
        "Select Server:",
        ["Source", "Target"],
        help="Choose which server to delete databases from"
    )
    
    # Get the appropriate URL and databases
    if delete_server == "Source":
        server_url = source_url
        available_dbs = st.session_state.source_dbs_cache
        server_connected = st.session_state.source_connected
        server_name = "Source"
    else:
        server_url = target_url
        available_dbs = st.session_state.target_dbs_cache
        server_connected = st.session_state.target_connected
        server_name = "Target"
    
    if server_url and server_connected:
        st.info(f"📊 Connected to {server_name}: {len(available_dbs)} databases available")
        
        if available_dbs:
            # Database selection
            st.subheader("Select Databases to Delete")
            
            # Select all/none buttons
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ Select All", key="select_all_delete"):
                    st.session_state.select_all_delete_flag = True
            with col2:
                if st.button("❌ Select None", key="select_none_delete"):
                    st.session_state.select_none_delete_flag = True
            
            # Handle select all/none flags
            if hasattr(st.session_state, 'select_all_delete_flag') and st.session_state.select_all_delete_flag:
                for db in available_dbs:
                    if f"delete_{db}" not in st.session_state:
                        st.session_state[f"delete_{db}"] = True
                st.session_state.select_all_delete_flag = False
            
            if hasattr(st.session_state, 'select_none_delete_flag') and st.session_state.select_none_delete_flag:
                # Remove all delete checkboxes from session state to effectively uncheck them
                keys_to_remove = [key for key in st.session_state.keys() if key.startswith("delete_")]
                for key in keys_to_remove:
                    del st.session_state[key]
                st.session_state.select_none_delete_flag = False
            
            # Database checkboxes
            selected_dbs = []
            for db in available_dbs:
                if st.checkbox(
                    f"🗄️ {db}", 
                    key=f"delete_{db}",
                    help=f"Delete database '{db}' from {server_name.lower()} server"
                ):
                    selected_dbs.append(db)
            
            if selected_dbs:
                st.error(f"⚠️ **DANGER ZONE**: You are about to delete {len(selected_dbs)} database(s) from {server_name}:")
                for db in selected_dbs:
                    st.error(f"  • {db}")
                
                # Safety confirmation
                st.subheader("🔒 Safety Confirmation")
                
                confirm_text = st.text_input(
                    f"Type 'DELETE {len(selected_dbs)} DATABASES' to confirm:",
                    help="This is required to prevent accidental deletions"
                )
                
                expected_text = f"DELETE {len(selected_dbs)} DATABASES"
                confirmation_valid = confirm_text == expected_text
                
                if confirm_text and not confirmation_valid:
                    st.error(f"❌ Please type exactly: {expected_text}")
                
                # Final confirmation checkbox
                final_confirm = st.checkbox(
                    f"✅ I understand that deleting these databases is PERMANENT and IRREVERSIBLE",
                    help="Final confirmation before deletion"
                )
                
                # Delete button
                if confirmation_valid and final_confirm:
                    if st.button("🗑️ DELETE DATABASES", type="primary"):
                        
                        # Console logging
                        print(f"\n{'='*50}")
                        print(f"🗑️ [UI] DATABASE DELETION OPERATION STARTED")
                        print(f"{'='*50}")
                        print(f"📅 Timestamp: {datetime.now().isoformat()}")
                        print(f"👤 User initiated deletion via Streamlit UI")
                        print(f"🌐 Target server: {server_url}")
                        print(f"📊 Selected databases: {selected_dbs}")
                        print(f"⚠️ DANGER: Permanent deletion in progress!")
                        
                        progress = st.progress(0)
                        status = st.empty()
                        
                        success_count = 0
                        failed_dbs = []
                        
                        for idx, db in enumerate(selected_dbs):
                            status.text(f"Deleting {db}... ({idx+1}/{len(selected_dbs)})")
                            
                            success, msg = delete_database(server_url, db)
                            
                            if success:
                                success_count += 1
                                st.success(f"✅ Deleted: {db}")
                            else:
                                failed_dbs.append((db, msg))
                                st.error(f"❌ Failed to delete {db}: {msg}")
                            
                            progress.progress((idx + 1) / len(selected_dbs))
                        
                        status.empty()
                        progress.empty()
                        
                        print(f"📊 [DELETE] Operation completed: {success_count}/{len(selected_dbs)} databases deleted")
                        
                        # Results summary
                        if success_count == len(selected_dbs):
                            st.success(f"🎉 Successfully deleted all {success_count} databases!")
                            # Clear the checkboxes after successful deletion by removing them from session state
                            for db in selected_dbs:
                                if f"delete_{db}" in st.session_state:
                                    del st.session_state[f"delete_{db}"]
                        else:
                            st.warning(f"⚠️ Deleted {success_count}/{len(selected_dbs)} databases")
                            # Also clear checkboxes for successfully deleted databases
                            successful_dbs = [db for db in selected_dbs if db not in [failed_db[0] for failed_db in failed_dbs]]
                            for db in successful_dbs:
                                if f"delete_{db}" in st.session_state:
                                    del st.session_state[f"delete_{db}"]
                        
                        if failed_dbs:
                            st.error("Failed deletions:")
                            for db, error in failed_dbs:
                                st.error(f"  • {db}: {error}")
                        
                        # Refresh database cache to reflect deletions
                        if delete_server == "Source":
                            st.session_state.source_dbs_cache = get_databases(source_url)
                        else:
                            st.session_state.target_dbs_cache = get_databases(target_url)
                        
                        st.info("🔄 Database list has been refreshed")
                        st.rerun()  # Refresh the UI
                
                elif not confirmation_valid:
                    st.info("💡 Type the confirmation text above to enable deletion")
                elif not final_confirm:
                    st.info("💡 Check the final confirmation box to enable deletion")
            else:
                st.info("Select databases to delete from the list above")
        else:
            st.info("No databases found on the selected server")
    else:
        if not server_url:
            st.warning(f"Please configure the {server_name.lower()} database URL in the sidebar")
        else:
            st.error(f"Not connected to {server_name.lower()} database. Please check your connection.")


st.divider()
st.caption("CouchDB Manager v1.0 - Manage your CouchDB instances with ease")