#!/usr/bin/env python3
"""
Test script to verify preview streaming and comprehensive logging
Captures all logs and checks log files
"""

import asyncio
import websockets
import json
import logging
import sys
import time
from pathlib import Path

# Set up logging to capture all output
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

logger = logging.getLogger(__name__)

async def test_preview_streaming():
    """Connect to WebSocket and send a test query to trigger preview streaming"""
    
    uri = "ws://localhost:8000/ws/chat"
    
    logger.info("=" * 80)
    logger.info("PREVIEW STREAMING TEST")
    logger.info("=" * 80)
    logger.info(f"Connecting to: {uri}")
    
    try:
        async with websockets.connect(uri) as websocket:
            logger.info("✅ WebSocket connected")
            
            # Send a simple test query
            test_message = {
                "type": "message",
                "content": "What is 2+2?"
            }
            
            logger.info(f"📤 Sending test message: {test_message['content']}")
            await websocket.send(json.dumps(test_message))
            
            # Track what we receive
            preview_events_seen = []
            other_events_seen = []
            
            logger.info("\n" + "=" * 80)
            logger.info("RECEIVING WEBSOCKET EVENTS:")
            logger.info("=" * 80)
            
            # Receive messages for 30 seconds or until complete
            timeout = 30
            start_time = asyncio.get_event_loop().time()
            
            while True:
                try:
                    # Check timeout
                    elapsed = asyncio.get_event_loop().time() - start_time
                    if elapsed > timeout:
                        logger.warning(f"⏱️  Timeout reached ({timeout}s)")
                        break
                    
                    # Receive message with timeout
                    message = await asyncio.wait_for(
                        websocket.recv(), 
                        timeout=timeout - elapsed
                    )
                    
                    data = json.loads(message)
                    event_type = data.get("type", "unknown")
                    
                    # Track preview events
                    if "preview" in event_type:
                        preview_events_seen.append(event_type)
                        logger.info(f"🎯 PREVIEW EVENT: {event_type}")
                        if event_type == "preview_start":
                            logger.info(f"   Phase: {data.get('phase')}")
                            logger.info(f"   Model: {data.get('model')}")
                        elif event_type == "preview_token":
                            text = data.get('text', '')
                            logger.info(f"   Text: {text[:50]}...")
                        elif event_type == "preview_complete":
                            logger.info(f"   Total length: {data.get('total_length')}")
                    else:
                        other_events_seen.append(event_type)
                        logger.info(f"📨 Event: {event_type}")
                    
                    # Stop on completion
                    if event_type in ["complete", "error"]:
                        logger.info("✅ Chat completed")
                        break
                        
                except asyncio.TimeoutError:
                    logger.warning("⏱️  Receive timeout")
                    break
                except Exception as e:
                    logger.error(f"❌ Error receiving message: {e}")
                    break
            
            # Summary
            logger.info("\n" + "=" * 80)
            logger.info("TEST SUMMARY")
            logger.info("=" * 80)
            logger.info(f"Preview events seen: {len(preview_events_seen)}")
            logger.info(f"  {preview_events_seen}")
            logger.info(f"Other events seen: {len(other_events_seen)}")
            logger.info(f"  {other_events_seen}")
            
            if preview_events_seen:
                logger.info("\n✅ SUCCESS: Preview streaming is working!")
                logger.info(f"✅ Captured preview events: {preview_events_seen}")
            else:
                logger.warning("\n⚠️  WARNING: No preview events detected")
                logger.warning("This suggests preview streaming may not be working")
            
            logger.info("=" * 80)
            
    except Exception as e:
        logger.error(f"❌ Connection error: {e}")
        logger.error("Make sure the backend is running on http://localhost:8000")
        sys.exit(1)

def check_log_files():
    """Check and display contents of latest log files"""
    log_dir = Path.home() / "Library" / "Logs" / "CedarPy"
    
    logger.info("\n" + "="*80)
    logger.info("CHECKING LOG FILES")
    logger.info("="*80)
    logger.info(f"Log directory: {log_dir}")
    
    if not log_dir.exists():
        logger.warning("Log directory does not exist!")
        return
    
    # Find the most recent backend log
    backend_logs = sorted(log_dir.glob("backend_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    
    if backend_logs:
        latest_log = backend_logs[0]
        logger.info(f"\n📄 Latest backend log: {latest_log.name}")
        logger.info("-" * 80)
        
        with open(latest_log, 'r') as f:
            lines = f.readlines()
            if lines:
                logger.info(f"Total lines: {len(lines)}")
                logger.info("\nLast 50 lines:")
                for line in lines[-50:]:
                    print(line.rstrip())
            else:
                logger.warning("Log file is empty!")
    else:
        logger.warning("No backend log files found!")
    
    # Check for component-specific logs
    logger.info("\n" + "-" * 80)
    logger.info("Component-specific log files:")
    for log_file in sorted(log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)[:10]:
        size = log_file.stat().st_size
        logger.info(f"  {log_file.name}: {size} bytes")

if __name__ == "__main__":
    logger.info("Starting comprehensive logging test...")
    logger.info("This will test WebSocket connection and verify all logging is working.")
    logger.info("")
    
    # Wait a moment for backend to be ready
    logger.info("Waiting 2 seconds for backend...")
    time.sleep(2)
    
    # Run the test
    asyncio.run(test_preview_streaming())
    
    # Check log files after test
    logger.info("\n")
    logger.info("="*80)
    logger.info("Test complete. Now checking log files...")
    logger.info("="*80)
    time.sleep(1)  # Give logs time to flush
    check_log_files()
