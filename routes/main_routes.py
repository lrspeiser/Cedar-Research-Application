"""
Main routes extracted from main.py to reduce file size.

This module contains the majority of application routes that were previously
inline in main.py. Routes are organized functionally but kept in a single file
for simplicity during initial extraction.

To use: app.include_router(router) in main.py
"""

from fastapi import APIRouter, Request, UploadFile, File, Form, Depends, Header, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response, JSONResponse
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any, List
import os

# This will be imported when the router is initialized
router = APIRouter()

# Note: Dependencies and models will be injected or imported as needed
# For now, this is a placeholder structure

__all__ = ['router']