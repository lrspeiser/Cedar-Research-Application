# -*- coding: utf-8 -*-
"""
Agents route - displays information about the AI agents and their prompts (actual prompts from codebase).
Prompts are dynamically extracted from agent implementations to ensure accuracy.
"""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from cedar_app.ui_utils import layout
from html import escape
from typing import Optional
import sys
import os

# Add cedar_orchestrator to path for importing agent_prompts
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from cedar_orchestrator.agent_prompts import AGENTS_METADATA


def register_agents_route(app: FastAPI):
    """Register the /agents route on the FastAPI app"""

    @app.get("/agents", response_class=HTMLResponse)
    def view_agents(project_id: Optional[int] = None, branch_id: Optional[int] = None, thread_id: Optional[int] = None):
        """Display the list of agents and their actual system prompts (dynamically extracted from implementations)."""

        # Build agent list dynamically from actual implementations
        agents = []
        for agent_meta in AGENTS_METADATA:
            agents.append({
                "name": agent_meta["name"],
                "internal_name": agent_meta["internal_name"],
                "description": agent_meta["description"],
                "is_primary": agent_meta.get("is_primary", False),
                "prompt": agent_meta["get_prompt"]()  # Dynamically call to get the actual prompt
            })

        # Build HTML for agent cards
        agent_cards = []
        for agent in agents:
            primary_badge = ''
            if agent.get('is_primary', False):
                primary_badge = ' <span class="pill" style="background:#fef3c7;color:#92400e;margin-left:8px;">Primary</span>'
            card_html = f"""
            <div class="card" style="margin-bottom:16px;">
              <h3>{escape(agent['name'])}{primary_badge}</h3>
              <div class="small muted">Internal: <span class="pill">{escape(agent['internal_name'])}</span></div>
              <p class="muted" style="margin-top:8px;">{escape(agent['description'])}</p>
              <details style="margin-top:8px;">
                <summary style="cursor:pointer;font-weight:600;">System Prompt</summary>
                <pre class="small" style="white-space:pre-wrap;background:#f8fafc;padding:12px;border-radius:6px;">{escape(agent['prompt'])}</pre>
              </details>
            </div>
            """
            agent_cards.append(card_html)

        body = f"""
        <h1>AI Agents</h1>
        <div class="muted" style="margin-bottom:12px;">
            These are the actual prompts used by Cedar's agents, dynamically extracted from the implementation.
        </div>
        <div style="max-width: 1000px;">
          {''.join(agent_cards)}
        </div>
        """
        return layout("Agents", body)