# Image Analysis Database Schema

This document defines the structured data format for image analysis results and corresponding database tables.

## Database Tables

### 1. `image_metadata`
Core metadata and purpose assessment for analyzed images.

```sql
CREATE TABLE IF NOT EXISTS image_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL UNIQUE,
    image_type TEXT NOT NULL,  -- 'chart', 'diagram', 'photo', 'screenshot', 'mixed'
    chart_type TEXT,           -- 'line', 'scatter', 'bar', 'histogram', 'heatmap', 'pie', etc.
    title TEXT,
    width INTEGER,
    height INTEGER,
    color_palette TEXT,        -- JSON array of hex colors
    has_annotations BOOLEAN,
    has_legend BOOLEAN,
    has_gridlines BOOLEAN,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
);
```

### 2. `image_purpose`
Assessment of what the image is trying to communicate.

```sql
CREATE TABLE IF NOT EXISTS image_purpose (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    purpose_type TEXT NOT NULL,  -- 'data_visualization', 'comparison', 'trend_analysis', 'distribution', 
                                  -- 'relationship', 'composition', 'documentation', 'illustration', etc.
    primary_message TEXT NOT NULL,  -- Main takeaway/message
    audience TEXT,                  -- Intended audience (if discernible)
    context TEXT,                   -- Domain context (astronomy, finance, medical, etc.)
    confidence REAL DEFAULT 0.8,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
);
```

### 3. `image_conclusions`
Conclusions drawn from the image with supporting reasoning.

```sql
CREATE TABLE IF NOT EXISTS image_conclusions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    conclusion_text TEXT NOT NULL,       -- The conclusion statement
    evidence TEXT NOT NULL,              -- Observable evidence supporting this conclusion
    reasoning TEXT NOT NULL,             -- Logical reasoning connecting evidence to conclusion
    confidence REAL DEFAULT 0.7,         -- Confidence in this conclusion (0.0-1.0)
    conclusion_type TEXT,                -- 'trend', 'correlation', 'anomaly', 'pattern', 'relationship', etc.
    order_index INTEGER DEFAULT 0,       -- For maintaining order of multiple conclusions
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
);
```

### 4. `chart_axes`
Axis information for charts and plots.

```sql
CREATE TABLE IF NOT EXISTS chart_axes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    axis_name TEXT NOT NULL,       -- 'x', 'y', 'z', 'color', 'size', etc.
    label TEXT,
    units TEXT,
    scale_type TEXT,               -- 'linear', 'log', 'log10', 'symlog', 'date', etc.
    min_value REAL,
    max_value REAL,
    tick_values TEXT,              -- JSON array of tick values
    gridlines BOOLEAN,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
);
```

### 5. `chart_series`
Data series information for charts.

```sql
CREATE TABLE IF NOT EXISTS chart_series (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    series_name TEXT NOT NULL,
    legend_label TEXT,
    color TEXT,                    -- Hex color or name
    marker_style TEXT,
    line_style TEXT,
    series_type TEXT,              -- 'line', 'scatter', 'bar', 'area', 'error_bars', etc.
    order_index INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
);
```

### 6. `chart_data_points`
Individual data points extracted from charts.

```sql
CREATE TABLE IF NOT EXISTS chart_data_points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    series_id INTEGER,             -- Links to chart_series.id
    x_value REAL,
    y_value REAL,
    z_value REAL,                  -- For 3D plots
    error_x REAL,                  -- Error bars
    error_y REAL,
    label TEXT,                    -- Point label if present
    order_index INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
    FOREIGN KEY (series_id) REFERENCES chart_series(id) ON DELETE CASCADE
);
```

### 7. `image_text`
OCR text extraction results.

```sql
CREATE TABLE IF NOT EXISTS image_text (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    text_content TEXT NOT NULL,
    text_type TEXT,                -- 'title', 'subtitle', 'axis_label', 'legend', 'annotation', 
                                    -- 'caption', 'table', 'equation', 'body', etc.
    bbox_x0 INTEGER,               -- Bounding box coordinates (if available)
    bbox_y0 INTEGER,
    bbox_x1 INTEGER,
    bbox_y1 INTEGER,
    confidence REAL DEFAULT 0.9,
    order_index INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
);
```

---

## JSON Output Format

ImageAnalysisAgent should return results in this structured JSON format:

```json
{
  "file_id": 6,
  "metadata": {
    "image_type": "chart",
    "chart_type": "line",
    "title": "Galaxy-galaxy lensing shape (LogTail tail)",
    "width": 768,
    "height": 896,
    "color_palette": ["#FF0000", "#1f77b4"],
    "has_annotations": true,
    "has_legend": true,
    "has_gridlines": false
  },
  "purpose": {
    "purpose_type": "trend_analysis",
    "primary_message": "Demonstrates the decline in galaxy-galaxy lensing signal (ΔΣ) as a function of radial distance from galaxy centers",
    "audience": "Astrophysics researchers studying dark matter halos",
    "context": "Observational cosmology - weak gravitational lensing analysis",
    "confidence": 0.9
  },
  "conclusions": [
    {
      "conclusion_text": "The lensing signal decreases with increasing radial distance, following an approximate power-law relationship",
      "evidence": "Data points show ΔΣ dropping from ~5×10^7 at 50 kpc to ~2×10^7 at 100 kpc on log-log axes",
      "reasoning": "The log-log plot shows a roughly linear trend with negative slope, indicating a power-law decay. This is consistent with extended dark matter halo profiles.",
      "confidence": 0.85,
      "conclusion_type": "trend",
      "order_index": 0
    },
    {
      "conclusion_text": "The slope annotation shows 'nan', indicating a potential computational issue or insufficient data for robust slope estimation",
      "evidence": "Annotation text explicitly states 'slope ≈ nan'",
      "reasoning": "NaN (Not a Number) typically indicates a failed calculation, possibly due to too few data points, invalid fitting domain, or numerical instability in the analysis pipeline.",
      "confidence": 0.95,
      "conclusion_type": "anomaly",
      "order_index": 1
    }
  ],
  "axes": [
    {
      "axis_name": "x",
      "label": "R (kpc)",
      "units": "kpc",
      "scale_type": "log10",
      "min_value": 10,
      "max_value": 100,
      "tick_values": [10, 100],
      "gridlines": false
    },
    {
      "axis_name": "y",
      "label": "ΔΣ (Msun/kpc²)",
      "units": "Msun/kpc²",
      "scale_type": "log10",
      "min_value": 1e7,
      "max_value": 1e8,
      "tick_values": [1e7, 1e8],
      "gridlines": false
    }
  ],
  "series": [
    {
      "series_name": "LogTail ΔΣ",
      "legend_label": "LogTail ΔΣ",
      "color": "#1f77b4",
      "marker_style": "circle",
      "line_style": "solid",
      "series_type": "line",
      "order_index": 0
    }
  ],
  "data_points": [
    {
      "series_name": "LogTail ΔΣ",
      "x_value": 50,
      "y_value": 5e7,
      "error_x": null,
      "error_y": null,
      "label": null,
      "order_index": 0
    },
    {
      "series_name": "LogTail ΔΣ",
      "x_value": 100,
      "y_value": 2e7,
      "error_x": null,
      "error_y": null,
      "label": null,
      "order_index": 1
    }
  ],
  "text_extractions": [
    {
      "text_content": "Galaxy-galaxy lensing shape (LogTail tail)",
      "text_type": "title",
      "bbox_x0": null,
      "bbox_y0": null,
      "bbox_x1": null,
      "bbox_y1": null,
      "confidence": 0.95,
      "order_index": 0
    },
    {
      "text_content": "50 kpc",
      "text_type": "annotation",
      "confidence": 0.9,
      "order_index": 1
    },
    {
      "text_content": "100 kpc",
      "text_type": "annotation",
      "confidence": 0.9,
      "order_index": 2
    },
    {
      "text_content": "slope ≈ nan",
      "text_type": "annotation",
      "confidence": 0.9,
      "order_index": 3
    }
  ]
}
```

---

## Usage Notes

1. **All fields referencing `file_id`** should use the uploaded file's ID as a foreign key
2. **JSON fields** (like `color_palette`, `tick_values`) should be stored as TEXT and parsed when retrieved
3. **Confidence scores** range from 0.0 (no confidence) to 1.0 (certain)
4. **NULL values** are allowed for optional fields like `bbox` coordinates, error bars, etc.
5. **order_index** maintains the sequence of multiple items (conclusions, data points, etc.)

## Agent Integration

When ImageAnalysisAgent is called:
1. It receives the task and file_id from Chief Agent
2. It analyzes the image using GPT Vision
3. It returns structured JSON matching this schema
4. Chief Agent then calls SQLAgent to create tables and insert data
5. SQLAgent uses the JSON to populate all appropriate tables

This separation ensures:
- ImageAnalysisAgent focuses on visual analysis
- SQLAgent handles all database operations
- Schema is documented and consistent
- No fallbacks or silent failures
