"""
Orchestrator module - manages agent execution based on thinker output.
Executes agents in parallel and decides which results to use.
"""

import asyncio
import json
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
from openai import AsyncOpenAI
import logging

from agents import get_agent
from agents.base_agent import AgentContext, AgentResult
from thinker import ThinkerOutput

logger = logging.getLogger(__name__)

@dataclass
class OrchestrationDecision:
    """Decision made by the orchestrator"""
    selected_result: Optional[AgentResult]
    should_continue: bool
    next_agents: List[str]
    reasoning: str
    needs_thinker: bool = False

class Orchestrator:
    """Orchestrates agent execution based on thinking notes"""
    
    def __init__(self, openai_client: AsyncOpenAI):
        self.client = openai_client
        self.model = "gpt-4o"
        self.iteration_count = 0
        self.max_iterations = 5
        
    async def orchestrate(self, 
                         context: AgentContext,
                         thinking_output: ThinkerOutput) -> Tuple[List[AgentResult], OrchestrationDecision]:
        """
        Execute agents based on thinker output and return results with decision.
        """
        self.iteration_count += 1
        
        # Determine which agents to run
        agents_to_run = self._select_agents(thinking_output, context)
        
        # Execute agents in parallel
        results = await self._execute_agents_parallel(agents_to_run, context)
        
        # Decide which result to use and whether to continue
        decision = await self._make_decision(results, context, thinking_output)
        
        return results, decision
    
    def _select_agents(self, thinking_output: ThinkerOutput, context: AgentContext) -> List[str]:
        """Select which agents to run based on thinking output"""
        
        # Start with suggested agents from thinker
        agents = thinking_output.suggested_agents.copy()
        
        # For the first iteration, always include 'final' if it's a simple query
        if self.iteration_count == 1 and thinking_output.initial_strategy == "direct_answer":
            if "final" not in agents:
                agents.append("final")
        
        # Limit number of parallel agents to avoid overwhelming the system
        max_parallel = 3
        if len(agents) > max_parallel:
            agents = agents[:max_parallel]
        
        # If no agents suggested, default to 'final'
        if not agents:
            agents = ["final"]
        
        logger.info(f"Orchestrator iteration {self.iteration_count}: Running agents {agents}")
        return agents
    
    async def _execute_agents_parallel(self, agent_names: List[str], context: AgentContext) -> List[AgentResult]:
        """Execute multiple agents in parallel"""
        tasks = []
        
        for agent_name in agent_names:
            try:
                agent = get_agent(agent_name, self.client)
                task = asyncio.create_task(agent.execute(context))
                tasks.append((agent_name, task))
            except Exception as e:
                logger.error(f"Failed to create agent {agent_name}: {e}")
        
        # Wait for all tasks to complete
        results = []
        for agent_name, task in tasks:
            try:
                result = await task
                results.append(result)
            except Exception as e:
                logger.error(f"Agent {agent_name} failed: {e}")
                # Create error result
                error_result = AgentResult(
                    success=False,
                    agent_name=agent_name,
                    output=None,
                    error=str(e)
                )
                results.append(error_result)
        
        return results
    
    async def _make_decision(self, 
                            results: List[AgentResult], 
                            context: AgentContext,
                            thinking_output: ThinkerOutput) -> OrchestrationDecision:
        """Decide which result to use and whether to continue"""
        
        # Find successful results
        successful_results = [r for r in results if r.success]
        
        # Smart decision logic - check final agent first for actual answers
        # If final has a real answer (not a fallback), use it
        final_results = [r for r in successful_results if r.agent_name == "final"]
        if final_results:
            final_result = final_results[0]
            # Check if it's a real answer (not a fallback or stub)
            if final_result.metadata and not final_result.metadata.get("fallback") and not final_result.metadata.get("stub"):
                selected_result = final_result
            else:
                final_result = None
        else:
            final_result = None
        
        # If no good final answer, use priority order
        if not selected_result:
            # Priority: code (if it ran) > final > question > others
            priority_order = ["code", "final", "question", "plan", "web", "file", "db", "notes", "images"]
            
            for agent_name in priority_order:
                for result in successful_results:
                    if result.agent_name == agent_name:
                        # Skip stubs unless no other option
                        if result.metadata and result.metadata.get("stub"):
                            continue
                        selected_result = result
                        break
                if selected_result:
                    break
        
        # If no successful results, pick the first error
        if not selected_result and results:
            selected_result = results[0]
        
        # Determine if we should continue
        should_continue = False
        next_agents = []
        needs_thinker = False
        
        if selected_result:
            # Stop if we have a final answer or question
            if selected_result.agent_name in ["final", "question"]:
                should_continue = False
            # Continue if we haven't reached max iterations and haven't found a satisfactory answer
            elif self.iteration_count < self.max_iterations:
                # Check if the result seems incomplete
                if selected_result.metadata and selected_result.metadata.get("stub"):
                    should_continue = True
                    next_agents = ["final"]  # Try to get a final answer
                elif selected_result.agent_name == "plan":
                    should_continue = True
                    next_agents = ["code", "final"]  # Execute the plan
                else:
                    # Ask the thinker to re-evaluate if we need more processing
                    if self.iteration_count >= thinking_output.expected_iterations:
                        should_continue = False
                    else:
                        needs_thinker = True
                        should_continue = True
        
        reasoning = self._generate_reasoning(selected_result, results, should_continue)
        
        return OrchestrationDecision(
            selected_result=selected_result,
            should_continue=should_continue,
            next_agents=next_agents,
            reasoning=reasoning,
            needs_thinker=needs_thinker
        )
    
    def _generate_reasoning(self, selected: Optional[AgentResult], all_results: List[AgentResult], continuing: bool) -> str:
        """Generate reasoning for the decision"""
        if not selected:
            return "No results available"
        
        reasoning = f"Selected {selected.agent_name} agent result"
        
        if selected.success:
            reasoning += " (successful)"
        else:
            reasoning += f" (failed: {selected.error})"
        
        if continuing:
            reasoning += f". Continuing iteration {self.iteration_count + 1}/{self.max_iterations}"
        else:
            reasoning += ". Stopping orchestration"
        
        return reasoning
    
    def reset(self):
        """Reset orchestrator state for a new query"""
        self.iteration_count = 0