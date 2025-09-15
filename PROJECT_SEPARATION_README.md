# Cedar Project Separation Architecture

## Overview
Cedar now uses complete project isolation:
- **Database**: One SQLite file per project at `~/CedarPyData/projects/{project_id}/database.db`
- **Files**: Stored in `~/CedarPyData/projects/{project_id}/files/branch_{branch_name}/`
- **Central Registry**: Main database (`~/CedarPyData/cedarpy.db`) only tracks projects list

## Benefits
1. **Complete isolation**: Projects cannot see each other's data
2. **Easy backup/restore**: Copy entire project folder
3. **Simple deletion**: Remove project folder to delete all data
4. **No need for branch-aware SQL**: Each project has its own database

## Architecture Changes

### Before (Shared)
```
~/CedarPyData/
├── cedarpy.db (all projects, branches, files, user tables)
└── user_uploads/
    ├── project_1/
    │   └── branch_Main/
    └── project_2/
        └── branch_Main/
```

### After (Isolated)
```
~/CedarPyData/
├── cedarpy.db (only project registry)
└── projects/
    ├── 1/
    │   ├── database.db (project-specific data)
    │   └── files/
    │       ├── branch_Main/
    │       └── branch_Feature/
    └── 2/
        ├── database.db
        └── files/
            └── branch_Main/
```

## Migration Guide

### Automatic Migration
When you first access a project after updating, the system will:
1. Create the project folder structure
2. Initialize a new project-specific database
3. Migrate existing files to the new location
4. Copy relevant data from the shared database

### Manual Migration (if needed)
```bash
# Backup existing data
cp -r ~/CedarPyData ~/CedarPyData.backup

# Files will be auto-migrated on first access
# User tables need to be exported/imported manually if needed
```

## SQL Console Changes
- No more cross-project data: each project has its own DB
- Strict explicit-only branch policy for branch-aware tables:
  - The server does not rewrite SQL. For tables that include project_id and branch_id, mutating statements must explicitly reference both (see BRANCH_SQL_POLICY.md).
- Branch merging only affects app-managed tables (files, threads, datasets)

## Environment Variables
- `CEDARPY_DATA_DIR`: Base directory (default: `~/CedarPyData`)
- `CEDARPY_DATABASE_URL`: Now only for central registry
- `CEDARPY_UPLOAD_DIR`: Deprecated (files now in project folders)

## Troubleshooting

### Error: "Project database not found"
The project folder might not exist. Visit the project page to auto-create it.

### Files not showing up
Check if files exist in old location (`user_uploads/`) and haven't been migrated yet.

### SQL queries return empty
This is expected - each project starts with a fresh database. Your old data is in the shared database backup.

## How It Works

### When you create a project:
1. Entry added to central registry (`cedarpy.db`)
2. Project folder created at `~/CedarPyData/projects/{id}/`
3. Project-specific database initialized
4. Main branch created in project database

### When you run SQL:
1. System connects to `~/CedarPyData/projects/{project_id}/database.db`
2. All queries run in complete isolation
3. No cross-project data leakage possible

### When you upload files:
1. Files stored in `~/CedarPyData/projects/{project_id}/files/branch_{name}/`
2. Metadata stored in project-specific database
3. Path structure prevents accidental mixing

## See Also
- Comment in code: `# See PROJECT_SEPARATION_README.md for architecture details`