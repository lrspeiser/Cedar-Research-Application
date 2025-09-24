"""
Final agent - provides final answers to queries.
"""

from agents.base_agent import BaseAgent, AgentContext, AgentResult
import logging
import re

logger = logging.getLogger(__name__)

class FinalAgent(BaseAgent):
    """Agent that provides final answers"""
    
    def __init__(self, openai_client=None):
        super().__init__("final", openai_client)
    
    async def execute(self, context: AgentContext) -> AgentResult:
        """Generate a final answer based on context and thinking notes"""
        
        if not await self.validate_context(context):
            return self.create_error_result("Invalid context provided")
        
        try:
            # For simple arithmetic, calculate directly
            if self._is_simple_arithmetic(context.query):
                result = self._calculate_arithmetic(context.query)
                if result is not None:
                    return self.create_success_result(
                        output=f"The answer is {result}",
                        metadata={"calculation": context.query, "result": result},
                        display_type="text"
                    )
            
            # If we have previous results from other agents, synthesize them
            if context.previous_results:
                return await self._synthesize_results(context)
            
            # Otherwise, use LLM to generate an answer
            if self.openai_client:
                return await self._generate_llm_answer(context)
            
            # Fallback for when no LLM is available
            return self.create_success_result(
                output="I need more information to provide a complete answer.",
                metadata={"fallback": True}
            )
            
        except Exception as e:
            logger.error(f"Error in final agent: {e}")
            return self.create_error_result(str(e))
    
    def _is_simple_arithmetic(self, query: str) -> bool:
        """Check if the query is simple arithmetic"""
        # Simple pattern for basic arithmetic
        arithmetic_pattern = r'^\s*\d+\s*[\+\-\*/]\s*\d+\s*$'
        query_clean = query.lower().replace('what is', '').replace('?', '').strip()
        return bool(re.match(arithmetic_pattern, query_clean))
    
    def _calculate_arithmetic(self, query: str) -> float:
        """Calculate simple arithmetic expressions safely"""
        try:
            query_clean = query.lower().replace('what is', '').replace('?', '').strip()
            # Only allow basic arithmetic operations
            if re.match(r'^[\d\s\+\-\*/\(\)\.]+$', query_clean):
                result = eval(query_clean)
                return result
        except:
            return None
    
    async def _synthesize_results(self, context: AgentContext) -> AgentResult:
        """Synthesize results from previous agents"""
        # Collect successful results
        successful_results = [r for r in context.previous_results if r.get('success')]
        
        if not successful_results:
            return self.create_success_result(
                output="I couldn't find a satisfactory answer based on the available information.",
                metadata={"no_successful_results": True}
            )
        
        # Combine outputs
        combined_output = "\n\n".join([
            f"[{r.get('agent_name', 'unknown')}]: {r.get('output', '')}"
            for r in successful_results
        ])
        
        return self.create_success_result(
            output=combined_output,
            metadata={"synthesized": True, "source_agents": [r.get('agent_name') for r in successful_results]}
        )
    
    async def _generate_llm_answer(self, context: AgentContext) -> AgentResult:
        """Generate answer using LLM"""
        system_prompt = """You are a helpful assistant providing final answers to user queries.
        Use the thinking notes and context to provide a clear, concise answer.
        Be direct and informative."""
        
        user_prompt = f"""Query: {context.query}

Thinking Notes:
{context.thinking_notes}

Please provide a clear, final answer to the query."""
        
        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_tokens=500
            )
            
            answer = response.choices[0].message.content
            
            return self.create_success_result(
                output=answer,
                metadata={"llm_generated": True}
            )
            
        except Exception as e:
            logger.error(f"Error generating LLM answer: {e}")
            return self.create_error_result(f"Failed to generate answer: {str(e)}")