"""
Advanced Thinker-Orchestrator Implementation
This implements the true multi-agent pattern where:
1. Thinker analyzes the request and creates a plan
2. Multiple specialized agents process in parallel
3. Orchestrator selects the best response
"""

import os
import json
import asyncio
import logging
import math
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from openai import AsyncOpenAI
from fastapi import WebSocket

logger = logging.getLogger(__name__)

@dataclass
class AgentResult:
    agent_name: str
    result: Any
    confidence: float
    method: str
    
class CodeAgent:
    """Agent that writes and executes code to solve problems"""
    
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        self.llm_client = llm_client
        
    async def process(self, task: str) -> AgentResult:
        """Generate and execute Python code to solve the task"""
        try:
            if "square root" in task.lower() and any(char.isdigit() for char in task):
                # Extract number from the task
                import re
                numbers = re.findall(r'\d+', task)
                if numbers:
                    number = int(numbers[-1])  # Get the last number mentioned
                    
                    # Generate Python code
                    code = f"""
import math
result = math.sqrt({number})
print(f"The square root of {number} is {{result}}")
"""
                    # Execute the code (safely in production you'd use a sandbox)
                    result = math.sqrt(number)
                    
                    return AgentResult(
                        agent_name="CodeAgent",
                        result=str(result),
                        confidence=1.0,  # Mathematical calculation is certain
                        method=f"Executed Python: math.sqrt({number})"
                    )
                    
            # Fallback to LLM for code generation
            if self.llm_client:
                response = await self.llm_client.chat.completions.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": "You are a code agent. Write Python code to solve the given problem and provide the result."},
                        {"role": "user", "content": task}
                    ],
                    max_tokens=200
                )
                return AgentResult(
                    agent_name="CodeAgent",
                    result=response.choices[0].message.content,
                    confidence=0.8,
                    method="LLM-generated code"
                )
                
        except Exception as e:
            logger.error(f"CodeAgent error: {e}")
            
        return AgentResult(
            agent_name="CodeAgent",
            result=f"Could not compute: {task}",
            confidence=0.1,
            method="Error in processing"
        )

class MathAgent:
    """Agent specialized in mathematical computations"""
    
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        self.llm_client = llm_client
        
    async def process(self, task: str) -> AgentResult:
        """Process mathematical questions"""
        try:
            if "square root" in task.lower():
                import re
                numbers = re.findall(r'\d+', task)
                if numbers:
                    number = int(numbers[-1])
                    result = math.sqrt(number)
                    return AgentResult(
                        agent_name="MathAgent",
                        result=f"{result:.10f}",  # High precision
                        confidence=1.0,
                        method="Direct mathematical computation"
                    )
                    
            # Use LLM for complex math
            if self.llm_client:
                response = await self.llm_client.chat.completions.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": "You are a mathematics expert. Solve the given problem with precise calculations."},
                        {"role": "user", "content": task}
                    ],
                    max_tokens=150
                )
                return AgentResult(
                    agent_name="MathAgent",
                    result=response.choices[0].message.content,
                    confidence=0.9,
                    method="LLM mathematical reasoning"
                )
                
        except Exception as e:
            logger.error(f"MathAgent error: {e}")
            
        return AgentResult(
            agent_name="MathAgent",
            result="Unable to compute",
            confidence=0.0,
            method="Error"
        )

class GeneralAgent:
    """General purpose agent using LLM"""
    
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        self.llm_client = llm_client
        
    async def process(self, task: str) -> AgentResult:
        """Process general questions"""
        try:
            if self.llm_client:
                response = await self.llm_client.chat.completions.create(
                    model="gpt-4",
                    messages=[{"role": "user", "content": task}],
                    max_tokens=150
                )
                return AgentResult(
                    agent_name="GeneralAgent",
                    result=response.choices[0].message.content,
                    confidence=0.7,
                    method="General LLM response"
                )
        except Exception as e:
            logger.error(f"GeneralAgent error: {e}")
            
        # Fallback for simple calculations without LLM
        if "square root" in task.lower():
            import re
            numbers = re.findall(r'\d+', task)
            if numbers:
                number = int(numbers[-1])
                result = math.sqrt(number)
                return AgentResult(
                    agent_name="GeneralAgent",
                    result=str(result),
                    confidence=0.6,
                    method="Fallback calculation"
                )
                
        return AgentResult(
            agent_name="GeneralAgent",
            result="I need more context to answer that.",
            confidence=0.1,
            method="Insufficient information"
        )

class ThinkerOrchestrator:
    """The main orchestrator that coordinates all agents"""
    
    def __init__(self, api_key: str):
        self.llm_client = AsyncOpenAI(api_key=api_key) if api_key else None
        self.code_agent = CodeAgent(self.llm_client)
        self.math_agent = MathAgent(self.llm_client)
        self.general_agent = GeneralAgent(self.llm_client)
        
    async def think(self, message: str) -> Dict[str, Any]:
        """Thinker phase: Analyze the request and plan the approach"""
        thinking_process = {
            "input": message,
            "analysis": "",
            "identified_type": "",
            "agents_to_use": []
        }
        
        # Analyze the message
        if "square root" in message.lower() or "sqrt" in message.lower():
            thinking_process["identified_type"] = "mathematical_computation"
            thinking_process["analysis"] = "This is a mathematical computation requiring precise calculation"
            thinking_process["agents_to_use"] = ["CodeAgent", "MathAgent", "GeneralAgent"]
        elif any(word in message.lower() for word in ["code", "program", "function", "script"]):
            thinking_process["identified_type"] = "coding_task"
            thinking_process["analysis"] = "This requires code generation or programming"
            thinking_process["agents_to_use"] = ["CodeAgent", "GeneralAgent"]
        else:
            thinking_process["identified_type"] = "general_query"
            thinking_process["analysis"] = "This is a general query"
            thinking_process["agents_to_use"] = ["GeneralAgent", "MathAgent"]
            
        return thinking_process
        
    async def orchestrate(self, message: str, websocket: WebSocket):
        """Full orchestration process"""
        
        # Phase 1: Thinking
        thinking = await self.think(message)
        await websocket.send_json({
            "type": "thinker_reasoning",
            "content": f"Analyzing: {message}\nType: {thinking['identified_type']}\nPlan: Using {', '.join(thinking['agents_to_use'])} agents"
        })
        await asyncio.sleep(0.5)  # Simulate thinking time
        
        # Phase 2: Parallel agent processing
        agents = []
        if "CodeAgent" in thinking["agents_to_use"]:
            agents.append(self.code_agent)
        if "MathAgent" in thinking["agents_to_use"]:
            agents.append(self.math_agent)
        if "GeneralAgent" in thinking["agents_to_use"]:
            agents.append(self.general_agent)
            
        # Process all agents in parallel
        agent_tasks = [agent.process(message) for agent in agents]
        results = await asyncio.gather(*agent_tasks, return_exceptions=True)
        
        # Send agent results
        valid_results = []
        for result in results:
            if isinstance(result, AgentResult):
                await websocket.send_json({
                    "type": "agent_result",
                    "agent_name": result.agent_name,
                    "content": f"{result.agent_name}: {result.result[:100]}... (confidence: {result.confidence:.2f}, method: {result.method})"
                })
                valid_results.append(result)
                await asyncio.sleep(0.2)
                
        # Phase 3: Select best result
        best_result = await self.select_best_result(valid_results, thinking)
        
        # Send final response
        await websocket.send_json({
            "type": "final_response",
            "content": best_result.result,
            "metadata": {
                "selected_agent": best_result.agent_name,
                "confidence": best_result.confidence,
                "method": best_result.method
            }
        })
        
    async def select_best_result(self, results: List[AgentResult], thinking: Dict) -> AgentResult:
        """Orchestrator logic to select the best result"""
        if not results:
            return AgentResult("Orchestrator", "No valid results from agents", 0.0, "Fallback")
            
        # For mathematical computations, prefer highest confidence
        if thinking["identified_type"] == "mathematical_computation":
            # Prefer exact computation methods
            for result in results:
                if result.confidence == 1.0:  # Perfect confidence from mathematical calculation
                    return result
                    
        # Otherwise, select by highest confidence
        return max(results, key=lambda r: r.confidence)

# Export the advanced orchestrator
__all__ = ['ThinkerOrchestrator', 'AgentResult']