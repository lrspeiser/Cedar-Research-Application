# cedar_langextract.py
#
# Integration helpers for LangExtract in CedarPy.
# - Schema creation (doc_chunks, doc_chunks_fts, triggers)
# - File-to-text conversion (lightweight, optional PDF/DOCX support if installed)
# - Chunking with langextract.chunking.ChunkIterator
# - Retrieval of top chunks via FTS5 BM25
#
# This module has no side effects on import. Call ensure_langextract_schema(engine)
# before using chunking/retrieval in a per-project database.

from __future__ import annotations

import os
import json
from typing import Optional, Iterable, Tuple

from sqlalchemy.engine import Engine

# LangExtract chunking (no network calls)
try:
  from langextract import chunking
except Exception as e:  # pragma: no cover
  chunking = None  # type: ignore


# -------------------------
# Schema (per-project SQLite)
# -------------------------

def ensure_langextract_schema(engine: Engine) -> None:
  """Create tables and FTS index for per-file chunk storage.

  Tables:
    - doc_chunks(id TEXT PK, file_id INT, char_start INT, char_end INT, text TEXT, created_at DATETIME)
    - doc_chunks_fts (FTS5 on text) with chunk_id, file_id shadow columns
  Triggers mirror INSERT/DELETE/UPDATE between doc_chunks and doc_chunks_fts.
  """
  try:
    with engine.begin() as conn:
      # Base chunks table
      conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS doc_chunks (
          id TEXT PRIMARY KEY,
          file_id INTEGER NOT NULL,
          char_start INTEGER NOT NULL,
          char_end INTEGER NOT NULL,
          text TEXT NOT NULL,
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(file_id, char_start, char_end)
        )
        """
      )
      # FTS5 table
      conn.exec_driver_sql(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS doc_chunks_fts USING fts5(
          chunk_id UNINDEXED,
          file_id UNINDEXED,
          text,
          tokenize = 'porter'
        )
        """
      )
      # Triggers (SQLite doesn't support IF NOT EXISTS for triggers; guard via sqlite_master check)
      def _trigger_exists(name: str) -> bool:
        res = conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='trigger' AND name=?", (name,))
        return res.fetchone() is not None

      if not _trigger_exists("doc_chunks_ai"):
        conn.exec_driver_sql(
          """
          CREATE TRIGGER doc_chunks_ai AFTER INSERT ON doc_chunks BEGIN
            INSERT INTO doc_chunks_fts(rowid, chunk_id, file_id, text)
            VALUES (new.rowid, new.id, new.file_id, new.text);
          END;
          """
        )
      if not _trigger_exists("doc_chunks_ad"):
        conn.exec_driver_sql(
          """
          CREATE TRIGGER doc_chunks_ad AFTER DELETE ON doc_chunks BEGIN
            INSERT INTO doc_chunks_fts(doc_chunks_fts, rowid, chunk_id, file_id, text)
            VALUES ('delete', old.rowid, old.id, old.file_id, old.text);
          END;
          """
        )
      if not _trigger_exists("doc_chunks_au"):
        conn.exec_driver_sql(
          """
          CREATE TRIGGER doc_chunks_au AFTER UPDATE ON doc_chunks BEGIN
            INSERT INTO doc_chunks_fts(doc_chunks_fts, rowid, chunk_id, file_id, text)
            VALUES ('delete', old.rowid, old.id, old.file_id, old.text);
            INSERT INTO doc_chunks_fts(rowid, chunk_id, file_id, text)
            VALUES (new.rowid, new.id, new.file_id, new.text);
          END;
          """
        )
  except Exception:
    # Best-effort; avoid crashing upload flows
    pass


# -------------------------
# File -> text conversion
# -------------------------

def file_to_text(path: str, display_name: Optional[str], meta: Optional[dict]) -> str:
  """Convert a file on disk to a UTF-8 text string.

  Supported out-of-the-box: .txt/.md/.json/.ndjson/.csv/.tsv/.ipynb
  Optional (best-effort): .pdf via pypdf, .docx via python-docx
  Fallbacks: if file looks text-like, read as UTF-8; otherwise use sample_text from meta.
  """
  display_name = display_name or os.path.basename(path)
  ext = os.path.splitext(display_name)[1].lower().lstrip(".")

  # Simple text
  if ext in {"txt", "md", "html", "htm", "xml"}:
    try:
      with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()
    except Exception:
      pass

  # JSON and NDJSON
  if ext in {"json", "ipynb"}:
    try:
      with open(path, "r", encoding="utf-8", errors="replace") as f:
        data = json.load(f)
      return json.dumps(data, ensure_ascii=False, indent=2)
    except Exception:
      pass
  if ext in {"ndjson"}:
    try:
      out_lines = []
      with open(path, "r", encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f):
          out_lines.append(line.rstrip("\n"))
          if i > 100_000:  # safety bound
            break
      return "\n".join(out_lines)
    except Exception:
      pass

  # CSV/TSV
  if ext in {"csv", "tsv"}:
    try:
      with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()
    except Exception:
      pass

  # PDF (optional)
  if ext == "pdf":
    try:
      from pypdf import PdfReader  # type: ignore
      reader = PdfReader(path)
      return "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception:
      pass

  # DOCX (optional)
  if ext == "docx":
    try:
      import docx  # type: ignore
      d = docx.Document(path)
      return "\n".join(p.text for p in d.paragraphs)
    except Exception:
      pass

  # If it looks like text, read it
  try:
    with open(path, "rb") as f:
      raw = f.read(1 << 20)
      if b"\x00" not in raw:
        try:
          with open(path, "r", encoding="utf-8", errors="replace") as f2:
            return f2.read()
        except Exception:
          pass
  except Exception:
    pass

  # Final fallback: use interpreter's sample_text if available
  sample = (meta or {}).get("sample_text") if isinstance(meta, dict) else None
  return str(sample or "")


# -------------------------
# Chunking and storage
# -------------------------

def chunk_document_insert(engine: Engine, file_id: int, text: str, max_char_buffer: int = 1500) -> int:
  """Chunk text and insert rows into doc_chunks. Returns number of chunks stored.
  Requires ensure_langextract_schema(engine) to have been called.
  """
  if not text:
    return 0
  if chunking is None:  # pragma: no cover
    return 0

  count = 0
  try:
    iterator = chunking.ChunkIterator(text=text, max_char_buffer=max_char_buffer)
  except Exception:
    return 0

  try:
    with engine.begin() as conn:
      for i, tchunk in enumerate(iterator):
        try:
          c = tchunk.char_interval
          char_start = getattr(c, "start_pos", None)
          char_end = getattr(c, "end_pos", None)
          cid = f"{file_id}:{i:06d}"
          conn.exec_driver_sql(
            "INSERT OR IGNORE INTO doc_chunks (id, file_id, char_start, char_end, text) VALUES (?,?,?,?,?)",
            (cid, int(file_id), int(char_start or 0), int(char_end or 0), tchunk.chunk_text),
          )
          count += 1
        except Exception:
          # Skip bad chunk rows but keep going
          continue
  except Exception:
    return 0

  return count


# -------------------------
# Retrieval (FTS5 BM25)
# -------------------------

def retrieve_top_chunks(engine: Engine, query: str, file_id: Optional[int] = None, limit: int = 20) -> Iterable[Tuple[str, int, str, float]]:
  """Return (chunk_id, file_id, text, rank) for best chunks.
  If file_id provided, restrict to that file.
  """
  sql = (
    "SELECT c.id AS chunk_id, c.file_id, c.text, bm25(doc_chunks_fts) AS rank "
    "FROM doc_chunks_fts JOIN doc_chunks c ON c.rowid = doc_chunks_fts.rowid "
    "WHERE doc_chunks_fts MATCH ? "
  )
  params = [query]
  if file_id is not None:
    sql += "AND c.file_id = ? "
    params.append(int(file_id))
  sql += "ORDER BY rank LIMIT ?"
  params.append(int(limit))

  try:
    with engine.begin() as conn:
      rows = conn.exec_driver_sql(sql, tuple(params)).fetchall()
      return [(r[0], int(r[1]), r[2], float(r[3]) if r[3] is not None else 0.0) for r in rows]
  except Exception:
    return []
