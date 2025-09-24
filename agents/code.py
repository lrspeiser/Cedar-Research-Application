"""
Code agent - writes and executes code.
"""

from agents.base_agent import BaseAgent, AgentContext, AgentResult
import logging
import subprocess
import tempfile
import os
import asyncio

logger = logging.getLogger(__name__)

class CodeAgent(BaseAgent):
    """Agent that writes and executes code"""
    
    def __init__(self, openai_client=None):
        super().__init__("code", openai_client)
    
    async def execute(self, context: AgentContext) -> AgentResult:
        """Generate and optionally execute code"""
        
        if not await self.validate_context(context):
            return self.create_error_result("Invalid context provided")
        
        try:
            # Determine if code generation is needed based on thinking notes
            if "code" not in context.thinking_notes.lower() and "program" not in context.thinking_notes.lower():
                return self.create_success_result(
                    output="No code generation needed for this query.",
                    metadata={"skipped": True}
                )
            
            # Generate code using LLM if available
            if self.openai_client:
                code_result = await self._generate_code(context)
                if code_result:
                    # Optionally execute the code (with safety checks)
                    if self._is_safe_to_execute(code_result):
                        execution_result = await self._execute_code(code_result)
                        return self.create_success_result(
                            output=f"```python\n{code_result}\n```\n\nExecution result:\n{execution_result}",
                            metadata={"code": code_result, "execution": execution_result},
                            display_type="code"
                        )
                    else:
                        return self.create_success_result(
                            output=f"```python\n{code_result}\n```",
                            metadata={"code": code_result, "execution_skipped": "Safety check failed"},
                            display_type="code"
                        )
            
            return self.create_success_result(
                output="Code agent requires LLM to generate code.",
                metadata={"no_llm": True}
            )
            
        except Exception as e:
            logger.error(f"Error in code agent: {e}")
            return self.create_error_result(str(e))
    
    async def _generate_code(self, context: AgentContext) -> str:
        """Generate code using LLM"""
        system_prompt = """You are a code generation assistant.
        Generate clean, well-commented Python code to solve the given problem.
        Return ONLY the code, no explanations or markdown formatting."""
        
        user_prompt = f"""Query: {context.query}

Thinking Notes:
{context.thinking_notes}

Generate Python code to address this query."""
        
        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=1000
            )
            
            code = response.choices[0].message.content
            # Clean up any markdown formatting if present
            code = code.replace("```python", "").replace("```", "").strip()
            return code
            
        except Exception as e:
            logger.error(f"Error generating code: {e}")
            return None
    
    def _is_safe_to_execute(self, code: str) -> bool:
        """Check if code is safe to execute"""
        # Basic safety checks - in production, use more sophisticated sandboxing
        dangerous_patterns = [
            "import os",
            "import subprocess",
            "import sys",
            "__import__",
            "exec",
            "eval",
            "open(",
            "file(",
            "input(",
            "raw_input"
        ]
        
        code_lower = code.lower()
        for pattern in dangerous_patterns:
            if pattern.lower() in code_lower:
                logger.warning(f"Code contains potentially dangerous pattern: {pattern}")
                return False
        
        return True
    
    async def _execute_code(self, code: str) -> str:
        """Execute Python code safely and return output"""
        try:
            # Create a temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(code)
                temp_file = f.name
            
            # Execute with timeout
            process = await asyncio.create_subprocess_exec(
                'python3', temp_file,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=5.0
                )
                
                output = stdout.decode() if stdout else ""
                error = stderr.decode() if stderr else ""
                
                if error:
                    return f"Error: {error}"
                return output if output else "Code executed successfully (no output)"
                
            except asyncio.TimeoutError:
                process.terminate()
                await process.wait()
                return "Execution timed out (5 seconds)"
            
        except Exception as e:
            return f"Execution error: {str(e)}"
        finally:
            # Clean up temp file
            if 'temp_file' in locals():
                try:
                    os.unlink(temp_file)
                except:
                    pass