# Shell Agent and Code Agent Enhancements

## Overview
Two major enhancements to the agent system:
1. **New Shell Agent**: Full shell access for system commands
2. **Enhanced Code Agent**: Shows generated code before execution

## Shell Agent

### Capabilities
The Shell Agent provides full shell access to execute system commands:
- **Package Installation**: `brew install`, `pip install`, `npm install`
- **File Operations**: `grep`, `find`, `ls`, `cat`, `mkdir`, `rm`, `cp`, `mv`
- **System Commands**: Any shell command with full access
- **Multi-line Commands**: Supports complex multi-line shell scripts
- **Output Analysis**: LLM analyzes command results and provides insights

### Features
- **Command Detection**: Automatically extracts commands from natural language
- **Timeout Protection**: 30-second timeout prevents hanging
- **Output Truncation**: Limits output to 3000 characters for analysis
- **Error Handling**: Gracefully handles failures with detailed error messages
- **LLM Analysis**: Explains what happened and suggests next steps

### Usage Examples

#### Install a Package
```
User: "Install pandas using pip"
Shell Agent: Executes `pip install pandas`
Returns: Installation status, package details, and next steps
```

#### Search for Files
```
User: "grep for 'TODO' in all Python files"
Shell Agent: Executes `grep -r "TODO" --include="*.py" .`
Returns: Matching lines with file locations
```

#### Run Complex Commands
```
User: "Check disk usage and show largest directories"
Shell Agent: Executes `du -sh * | sort -hr | head -10`
Returns: Top 10 directories by size
```

### Command Detection Methods
1. **Backticks**: `command in backticks`
2. **Keywords**: "run ls -la", "execute pwd", "install numpy"
3. **Direct Commands**: Detects common commands like grep, find, brew
4. **LLM Extraction**: Falls back to LLM to extract command from natural language

### Security Considerations
- Full shell access - be careful with destructive commands
- Environment variables are passed through
- Commands run with user's permissions
- Timeout prevents infinite loops

## Enhanced Code Agent

### New Features
The Code Agent now:
1. **Shows Generated Code**: Displays the Python code before execution
2. **Better Error Reporting**: Shows both code and error message on failure
3. **Structured Output**: Clear sections for code, results, and errors

### Output Format

#### Successful Execution
```
**Code to execute:**
```python
import math
result = math.sqrt(144)
print(f"The square root of 144 is {result}")
```

Answer: The square root of 144 is 12.0

Why: Generated and executed Python code to compute the exact result
```

#### Failed Execution
```
**Code to execute:**
```python
result = undefined_variable * 2
print(result)
```

Answer: Unable to complete the calculation due to an error

**Execution Error:** name 'undefined_variable' is not defined

Why: The generated code encountered an execution error

Suggested Next Steps: Review the code and error, then provide a more specific query
```

### Benefits
- **Transparency**: Users see exactly what code will run
- **Debugging**: Errors are easier to understand with code context
- **Learning**: Users can learn from the generated code
- **Trust**: No hidden code execution

## Integration with Chief Agent

### Shell Agent in Orchestration
- **Priority**: Shell commands are detected first in query analysis
- **Trigger Words**: "run", "execute", "install", "grep", "shell", "terminal"
- **Selection**: Chief Agent knows Shell Agent handles system commands

### Code Agent Improvements
- **Error Context**: Chief Agent receives both code and error for better decisions
- **Iteration Support**: Failed code can be refined in subsequent iterations
- **Clarity**: Code preview helps Chief Agent understand what was attempted

## Implementation Details

### Shell Agent Class
```python
class ShellAgent:
    - process(task): Executes shell commands
    - Command extraction via regex and LLM
    - subprocess.run with timeout
    - LLM analysis of results
```

### Code Agent Updates
```python
class CodeAgent:
    - Added code_preview variable
    - Shows code in all responses
    - Enhanced error messages with code context
```

### Query Type Detection
```python
# In think() method:
has_shell_command = bool(re.search(r'`[^`]+`', message)) or 
                   any(cmd in message.lower() for cmd in shell_commands)

if has_shell_command:
    thinking_process["identified_type"] = "shell_command"
    thinking_process["agents_to_use"] = ["ShellAgent"]
```

## Safety and Best Practices

### Shell Agent Safety
1. **Review Commands**: Always review commands before execution
2. **Avoid Destructive**: Be careful with `rm -rf`, `dd`, etc.
3. **Check Permissions**: Some commands may need sudo
4. **Test First**: Use `--dry-run` or `-n` flags when available

### Code Agent Safety
1. **Review Code**: Check generated code before trusting results
2. **Sandboxing**: Code runs in limited environment
3. **No System Access**: Code Agent can't modify system files
4. **Import Limits**: Only safe modules are available

## Testing

### Test Shell Agent
```bash
# Simple command
"Run `ls -la`"

# Package installation
"Install requests package with pip"

# Complex grep
"grep for 'class' in all Python files"

# Multi-line script
"Create a directory called test and add a README file to it"
```

### Test Code Agent
```bash
# Mathematical calculation
"Calculate the factorial of 10"

# Data processing
"Create a list of prime numbers up to 50"

# Error handling
"Divide 10 by zero" (should show code and error)
```

## Future Enhancements

### Shell Agent
- [ ] Persistent shell sessions
- [ ] Command history tracking
- [ ] Sudo support with safety checks
- [ ] Command validation before execution
- [ ] Resource usage monitoring

### Code Agent
- [ ] Code versioning within iterations
- [ ] Syntax highlighting in UI
- [ ] Code explanation mode
- [ ] Import additional safe libraries
- [ ] Execution profiling

## Troubleshooting

### Shell Agent Issues
- **Command not found**: Check PATH environment variable
- **Permission denied**: Command needs elevated privileges
- **Timeout**: Command taking too long, try simpler version
- **No output**: Command may output to stderr instead of stdout

### Code Agent Issues
- **Import errors**: Module not available in sandbox
- **Syntax errors**: LLM generated invalid Python
- **Execution errors**: Logic errors in generated code
- **No output**: Code may not include print statements