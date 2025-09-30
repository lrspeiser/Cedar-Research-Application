#!/usr/bin/env python3
"""
Fix indentation issues in orchestrator.py

The problem: Lines 1031-1145+ should be indented to be inside the
"if iteration == 0:" block that starts at line 1029.
"""

import sys

file_path = '/Users/leonardspeiser/Projects/cedarpy/cedar_orchestrator/orchestrator.py'

# Read the file
with open(file_path, 'r') as f:
    lines = f.readlines()

# The if statement is at line 1029 (0-indexed: 1028)
# Lines starting from 1031 (0-indexed: 1030) need to be indented by 4 spaces
# We need to find where this block ends - it should end before the next Phase 3 or similar

# We'll indent from line 1031 until we find a line that starts Phase 3 or another
# major section at the same indentation level as "if iteration == 0:"

start_indent_line = 1030  # 0-indexed (line 1031 in file)
indent_to_add = "    "  # 4 spaces

# Find the end of the block that needs indenting
# We'll look for lines that are at the same or less indentation as line 1028
if_line_indent = len(lines[1028]) - len(lines[1028].lstrip())

fixed_lines = lines[:start_indent_line]  # Keep everything before line 1031

# Process lines from 1031 onwards
i = start_indent_line
while i < len(lines):
    line = lines[i]
    
    # Check if this line marks the end of the if block
    # (it's at the same or less indentation as the if statement, and not blank/comment)
    current_indent = len(line) - len(line.lstrip())
    
    # If we hit a line at the same indentation level as the if statement,
    # and it's not empty/whitespace, we've found the end
    if current_indent <= if_line_indent and line.strip() and not line.strip().startswith('#'):
        # Check if this looks like a new section (Phase 3, else, elif, etc.)
        if any(line.lstrip().startswith(keyword) for keyword in ['# Phase 3', 'else:', 'elif ', 'def ', 'class ', '# Phase']):
            # Don't indent this and subsequent lines
            fixed_lines.extend(lines[i:])
            break
    
    # Add indentation to this line (unless it's blank)
    if line.strip():
        fixed_lines.append(indent_to_add + line)
    else:
        fixed_lines.append(line)
    
    i += 1

# Write the fixed file
with open(file_path, 'w') as f:
    f.writelines(fixed_lines)

print(f"✅ Fixed indentation in {file_path}")
print(f"   Indented lines {start_indent_line + 1} onwards")

# Try to compile it to check for errors
try:
    import py_compile
    py_compile.compile(file_path, doraise=True)
    print("✅ File compiles successfully!")
except py_compile.PyCompileError as e:
    print(f"⚠️  Compilation error: {e}")
    sys.exit(1)
