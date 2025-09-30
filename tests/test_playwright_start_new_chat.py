"""
Test for the "Start New Chat" link functionality.

This test verifies that:
1. The "Start New Chat" link is present on the project page
2. Clicking it creates a new chat via the API
3. The chat number is displayed correctly
4. The messages area is cleared

See PREVENTING_CACHE_ISSUES.md for cache debugging.
"""

import pytest
import time
from playwright.sync_api import Page, expect


@pytest.fixture(scope="module")
def base_url():
    """Base URL for the test server."""
    return "http://localhost:8701"


def test_start_new_chat_link(page: Page, base_url: str):
    """Test that the 'Start New Chat' link creates a new chat."""
    # Navigate to the project page
    page.goto(f"{base_url}/projects")
    page.wait_for_load_state("networkidle")
    
    # Get the first project link (or create one if none exists)
    project_links = page.locator('a[href^="/project/"]')
    if project_links.count() == 0:
        # Create a test project
        page.goto(f"{base_url}/")
        page.locator('input[name="title"]').fill("Test Project for Chat")
        page.locator('button[type="submit"]').click()
        page.wait_for_load_state("networkidle")
    else:
        project_links.first.click()
        page.wait_for_load_state("networkidle")
    
    # Make sure we're on a project page
    expect(page.locator('h1')).to_be_visible()
    
    # Click the Chat tab if not already visible
    chat_tab = page.locator('.tabs .tab[data-target="main-chat"]')
    if chat_tab.is_visible():
        chat_tab.click()
        time.sleep(0.2)
    
    # Look for the "Start New Chat" link
    start_chat_link = page.locator('a:has-text("Start New Chat")')
    expect(start_chat_link).to_be_visible(timeout=5000)
    
    print("[test] Found 'Start New Chat' link")
    
    # Listen for the API call
    with page.expect_response(lambda response: "/api/chat/new" in response.url) as response_info:
        # Click the link
        start_chat_link.click()
        print("[test] Clicked 'Start New Chat' link")
    
    # Verify the response was successful
    response = response_info.value
    assert response.status == 200, f"Expected 200, got {response.status}"
    
    response_json = response.json()
    assert 'chat_number' in response_json, "Response should contain chat_number"
    chat_number = response_json['chat_number']
    print(f"[test] New chat created with number: {chat_number}")
    
    # Wait for the chat number to be displayed
    time.sleep(0.5)
    chat_number_display = page.locator('#chat-number-display')
    expect(chat_number_display).to_be_visible(timeout=5000)
    
    # Verify the chat number is shown
    chat_number_span = page.locator('#chat-number')
    expect(chat_number_span).to_have_text(str(chat_number))
    
    # Verify the messages area shows the new chat started message
    msgs_div = page.locator('#msgs')
    expect(msgs_div).to_contain_text(f"Chat {chat_number} started")
    
    print("[test] ✅ Chat created and displayed successfully")


def test_start_new_chat_button_in_history_panel(page: Page, base_url: str):
    """Test the 'New Chat' button in the History panel."""
    # Navigate to the project page
    page.goto(f"{base_url}/projects")
    page.wait_for_load_state("networkidle")
    
    # Get the first project link
    project_links = page.locator('a[href^="/project/"]')
    if project_links.count() > 0:
        project_links.first.click()
        page.wait_for_load_state("networkidle")
    else:
        pytest.skip("No projects available for testing")
    
    # Switch to the History tab
    history_tab = page.locator('.tabs .tab[data-target="main-history"]')
    if history_tab.is_visible():
        history_tab.click()
        time.sleep(0.2)
    
    # Look for the "New Chat" button in the history panel
    new_chat_button = page.locator('button.secondary:has-text("New Chat")')
    expect(new_chat_button).to_be_visible(timeout=5000)
    
    print("[test] Found 'New Chat' button in History panel")
    
    # Listen for the API call
    with page.expect_response(lambda response: "/api/chat/new" in response.url) as response_info:
        # Click the button
        new_chat_button.click()
        print("[test] Clicked 'New Chat' button")
    
    # Verify the response was successful
    response = response_info.value
    assert response.status == 200, f"Expected 200, got {response.status}"
    
    response_json = response.json()
    assert 'chat_number' in response_json, "Response should contain chat_number"
    chat_number = response_json['chat_number']
    print(f"[test] New chat created with number: {chat_number}")
    
    # The Chat tab should automatically become active
    time.sleep(0.3)
    
    print("[test] ✅ New Chat button in History panel works")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])