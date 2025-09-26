"""
LEGACY MODULE (not used by the current WebSocket multi-agent orchestrator)

Agent module initialization and stub agents.

Notes:
- This older agent framework is retained only for historical tests (e.g., test_new_flow.py)
- The live chat UI uses cedar_orchestrator/advanced_orchestrator.py with its own agent classes
- To avoid confusion, do not add new features here; migrate to cedar_orchestrator agents instead
"""

from agents.base_agent import BaseAgent, AgentContext, AgentResult
from agents.final import FinalAgent
from agents.code import CodeAgent

class PlanAgent(BaseAgent):
    """Agent that creates structured execution plans"""
    def __init__(self, openai_client=None):
        super().__init__("plan", openai_client)
    
    async def execute(self, context: AgentContext) -> AgentResult:
        return self.create_success_result(
            output="Plan agent not yet implemented",
            metadata={"stub": True}
        )

class WebAgent(BaseAgent):
    """Agent that searches and retrieves web content"""
    def __init__(self, openai_client=None):
        super().__init__("web", openai_client)
    
    async def execute(self, context: AgentContext) -> AgentResult:
        return self.create_success_result(
            output="Web agent not yet implemented",
            metadata={"stub": True}
        )

class FileAgent(BaseAgent):
    """Agent that reads, writes, and manipulates files"""
    def __init__(self, openai_client=None):
        super().__init__("file", openai_client)
    
    async def execute(self, context: AgentContext) -> AgentResult:
        return self.create_success_result(
            output="File agent not yet implemented",
            metadata={"stub": True}
        )

class DbAgent(BaseAgent):
    """Agent that queries and manipulates databases"""
    def __init__(self, openai_client=None):
        super().__init__("db", openai_client)
    
    async def execute(self, context: AgentContext) -> AgentResult:
        return self.create_success_result(
            output="Database agent not yet implemented",
            metadata={"stub": True}
        )

class NotesAgent(BaseAgent):
    """Agent that creates and retrieves notes"""
    def __init__(self, openai_client=None):
        super().__init__("notes", openai_client)
    
    async def execute(self, context: AgentContext) -> AgentResult:
        return self.create_success_result(
            output="Notes agent not yet implemented",
            metadata={"stub": True}
        )

class ImagesAgent(BaseAgent):
    """Agent that processes and analyzes images"""
    def __init__(self, openai_client=None):
        super().__init__("images", openai_client)
    
    async def execute(self, context: AgentContext) -> AgentResult:
        return self.create_success_result(
            output="Images agent not yet implemented",
            metadata={"stub": True}
        )

class QuestionAgent(BaseAgent):
    """Agent that asks clarifying questions"""
    def __init__(self, openai_client=None):
        super().__init__("question", openai_client)
    
    async def execute(self, context: AgentContext) -> AgentResult:
        if self.openai_client:
            # Generate a clarifying question
            system_prompt = "Generate a single clarifying question to better understand the user's request."
            user_prompt = f"Query: {context.query}\nThinking: {context.thinking_notes}"
            
            try:
                response = await self.openai_client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.7,
                    max_tokens=100
                )
                question = response.choices[0].message.content
                return self.create_success_result(
                    output=question,
                    metadata={"type": "clarification"},
                    display_type="question"
                )
            except:
                pass
        
        return self.create_success_result(
            output="Could you provide more details about what you're looking for?",
            metadata={"default": True},
            display_type="question"
        )

# Agent registry
AGENT_REGISTRY = {
    "plan": PlanAgent,
    "code": CodeAgent,
    "web": WebAgent,
    "file": FileAgent,
    "db": DbAgent,
    "notes": NotesAgent,
    "images": ImagesAgent,
    "question": QuestionAgent,
    "final": FinalAgent
}

def get_agent(name: str, openai_client=None) -> BaseAgent:
    """Get an agent instance by name"""
    agent_class = AGENT_REGISTRY.get(name)
    if agent_class:
        return agent_class(openai_client)
    raise ValueError(f"Unknown agent: {name}")