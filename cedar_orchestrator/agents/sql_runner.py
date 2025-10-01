"""
SQLRunner Agent

Executes SQL statements against the active project database session. Intended to run
AFTER SQLAgent generates SQL. This agent does not call an LLM; it executes SQL directly.

Notes:
- Uses a 5-minute (300s) timeout per execution request, as requested.
- Echoes SQL and per-statement results to the UI for transparency (no fallbacks).
- On errors, returns a detailed failure report with the exact SQL that failed.

For DB configuration details, see README (DB setup) referenced in code comments.
"""

import asyncio
import time
import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from openai import AsyncOpenAI  # Kept for constructor signature consistency (not used)

from .agent_result import AgentResult

logger = logging.getLogger(__name__)


class SQLRunner:
    """Executes SQL synchronously against SQLAlchemy session with a 300s timeout."""

    TIMEOUT_SECONDS = 300  # 5 minutes general timeout per your requirement

    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        # llm_client is unused here; kept for a consistent agent constructor pattern
        self.llm_client = llm_client

    async def process(self, sql: str, db_session=None, project_id: Optional[int] = None, branch_id: Optional[int] = None) -> AgentResult:
        start = time.time()
        logger.info("[SQLRunner] Starting SQL execution")
        logger.info(f"[SQLRunner] Project context: project_id={project_id}, branch_id={branch_id}")

        if not db_session:
            return AgentResult(
                agent_name="SQLRunner",
                display_name="SQL Runner",
                result="**Runner Failure:** No database session available to execute SQL.",
                confidence=0.0,
                method="Execution",
                explanation="db_session was None",
                summary="SQLRunner failed: missing db_session"
            )

        # Normalize SQL (strip and allow multiple statements separated by ;) 
        sql_text = (sql or "").strip()
        if not sql_text:
            return AgentResult(
                agent_name="SQLRunner",
                display_name="SQL Runner",
                result="**No SQL to execute**",
                confidence=0.2,
                method="Execution",
                explanation="Empty SQL string",
                summary="No SQL provided"
            )

        async def _execute_all():
            outputs = []
            errors = []
            total_rowcount = 0
            try:
                # Use a connection for explicit execution
                conn = db_session.connection() if hasattr(db_session, 'connection') else db_session.bind.connect()
                try:
                    # Split on ';' for separate statements (rudimentary, but adequate for typical DDL/DML)
                    # Ignore empty segments after strip
                    statements = [s.strip() for s in sql_text.split(';') if s.strip()]
                    for idx, stmt in enumerate(statements, 1):
                        logger.info(f"[SQLRunner] Executing statement {idx}/{len(statements)}: {stmt[:200]}{'...' if len(stmt) > 200 else ''}")
                        try:
                            res = conn.execute(text(stmt))
                            # rowcount can be -1 depending on driver; handle gracefully
                            rc = getattr(res, 'rowcount', -1)
                            total_rowcount += rc if isinstance(rc, int) and rc >= 0 else 0
                            # Attempt to preview rows for SELECT
                            preview = ""
                            try:
                                if res.returns_rows:
                                    rows = res.fetchmany(5)
                                    if rows:
                                        headers = list(rows[0].keys()) if hasattr(rows[0], 'keys') else []
                                        preview_lines = []
                                        if headers:
                                            preview_lines.append(" | ".join(map(str, headers)))
                                        for r in rows:
                                            preview_lines.append(" | ".join(map(str, r)))
                                        preview = "\n".join(preview_lines)
                            except Exception as _:
                                preview = "(no preview)"
                            outputs.append((stmt, rc, preview))
                        except SQLAlchemyError as e:
                            logger.error(f"[SQLRunner] Statement failed: {e}")
                            errors.append((stmt, str(e)))
                    # Commit the transaction if session-based
                    try:
                        db_session.commit()
                    except Exception as ce:
                        logger.warning(f"[SQLRunner] Commit warning: {ce}")
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"[SQLRunner] Fatal execution error: {e}")
                errors.append(("<connection>", str(e)))

            return outputs, errors, total_rowcount

        try:
            outputs, errors, total_rowcount = await asyncio.wait_for(_execute_all(), timeout=self.TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            duration = time.time() - start
            msg = (
                f"**SQL Execution Timeout (>{self.TIMEOUT_SECONDS}s)**\n\n"
                f"The SQL execution exceeded the 5-minute limit. Logs up to this point are preserved.\n"
                f"Please consider breaking SQL into smaller steps or optimizing heavy queries."
            )
            return AgentResult(
                agent_name="SQLRunner",
                display_name="SQL Runner",
                result=msg,
                confidence=0.3,
                method="Execution Timeout",
                explanation=f"Timed out after {duration:.1f}s",
                summary="SQLRunner timed out after 5 minutes"
            )
        except Exception as e:
            duration = time.time() - start
            return AgentResult(
                agent_name="SQLRunner",
                display_name="SQL Runner",
                result=f"**SQL Execution Failed:** {e}",
                confidence=0.1,
                method="Execution Error",
                explanation=str(e),
                summary=f"SQLRunner failed: {str(e)[:80]}"
            )

        # Build formatted output
        duration = time.time() - start
        lines = []
        lines.append("**SQL Execution Report**")
        lines.append("")
        lines.append(f"Executed in {duration:.2f}s. Statements: {len(outputs)}. Total rowcount: {total_rowcount if total_rowcount else 0}.")
        lines.append("")
        if outputs:
            lines.append("### Statements")
            for i, (stmt, rc, preview) in enumerate(outputs, 1):
                lines.append(f"{i}. Rowcount: {rc if rc is not None else 'n/a'}")
                lines.append("```sql path=null start=null")
                lines.append(stmt)
                lines.append("```")
                if preview:
                    lines.append("Preview:")
                    lines.append("```text path=null start=null")
                    lines.append(preview)
                    lines.append("```")
                lines.append("")
        if errors:
            lines.append("### Errors")
            for i, (stmt, err) in enumerate(errors, 1):
                lines.append(f"{i}. Error: {err}")
                lines.append("Failed SQL:")
                lines.append("```sql path=null start=null")
                lines.append(stmt)
                lines.append("```")
                lines.append("")

        formatted = "\n".join(lines)
        confidence = 0.9 if not errors else 0.6
        return AgentResult(
            agent_name="SQLRunner",
            display_name="SQL Runner",
            result=formatted,
            confidence=confidence,
            method="Execution",
            explanation="Executed SQL statements using SQLAlchemy against the project DB. See README for DB config.",
            summary=("Executed SQL statements successfully" if not errors else "Executed SQL with errors; see details")
        )
