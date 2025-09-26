# Agent Selection System - Current Analysis and Improvements

## Current System Behavior

The CedarPy orchestrator doesn't always use exactly 3 agents. The number varies based on query type:

### Current Agent Selection Logic:

1. **Mathematical Derivation**: 3 agents (MathAgent, ReasoningAgent, CodeAgent)
2. **Research Task**: 3 agents (ResearchAgent, GeneralAgent, NotesAgent) 
3. **Strategic Planning**: 3 agents (StrategyAgent, ReasoningAgent, GeneralAgent)
4. **Mathematical Computation**: 4 agents (CodeAgent, MathAgent, ReasoningAgent, GeneralAgent)
5. **Coding Task**: 3 agents (CodeAgent, StrategyAgent, GeneralAgent)
6. **Database Query**: 3 agents (DataAgent, SQLAgent, GeneralAgent)
7. **Note Taking**: 2 agents (NotesAgent, GeneralAgent)
8. **Explanation Query**: 3 agents (ReasoningAgent, ResearchAgent, GeneralAgent)
9. **General Query**: 3 agents (GeneralAgent, ReasoningAgent, StrategyAgent)

## Issues with Current System:

1. **Fixed Agent Selection**: The `think()` function uses hardcoded rules based on keyword matching
2. **No Transparency**: The system doesn't explain WHY it chose specific agents
3. **No Flexibility**: Chief Agent can't dynamically select different agents mid-process
4. **Limited Adaptability**: Can't adjust based on query complexity

## Proposed Improvements:

### 1. Dynamic Agent Selection by Chief Agent
Instead of hardcoded rules, let the Chief Agent analyze the query and select agents:

```python
async def think_with_chief(self, message: str) -> Dict[str, Any]:
    """Let Chief Agent analyze and select appropriate agents"""
    
    # Ask Chief Agent to analyze and select agents
    chief_analysis = await self.chief_agent.analyze_and_select_agents(message)
    
    return {
        "input": message,
        "analysis": chief_analysis["reasoning"],
        "identified_type": chief_analysis["query_type"],
        "agents_to_use": chief_analysis["selected_agents"],
        "selection_reasoning": chief_analysis["why_these_agents"]
    }
```

### 2. Transparent Agent Selection Display
Show users why specific agents were chosen:

```python
# In the processing bubble
await websocket.send_json({
    "type": "action", 
    "function": "processing",
    "text": f"""Analyzing request...
Type: {thinking['identified_type']}
Engaging {len(thinking['agents_to_use'])} specialized agents:
{', '.join(thinking['agents_to_use'])}

Selection Reasoning: {thinking['selection_reasoning']}"""
})
```

### 3. Chief Agent Can Request Additional Agents
Allow the Chief Agent to request more agents after initial results:

```python
# In Chief Agent review
if chief_decision.get('request_additional_agents'):
    additional_agents = chief_decision['additional_agents']
    logger.info(f"Chief Agent requesting additional agents: {additional_agents}")
    # Process with additional agents...
```

### 4. Query Complexity Analysis
Determine number of agents based on complexity:

```python
def assess_query_complexity(message: str) -> int:
    """Assess query complexity to determine agent count"""
    complexity_score = 0
    
    # Multi-part questions
    if any(word in message for word in ['and', 'also', 'then', 'additionally']):
        complexity_score += 1
    
    # Technical depth
    if any(word in message.lower() for word in ['derive', 'proof', 'implement', 'analyze']):
        complexity_score += 2
        
    # Data/research needs
    if any(word in message.lower() for word in ['research', 'find', 'search', 'database']):
        complexity_score += 1
        
    # Planning/strategy
    if any(word in message.lower() for word in ['plan', 'strategy', 'coordinate']):
        complexity_score += 1
    
    # Return suggested agent count (2-6 agents)
    return min(max(2, complexity_score + 2), 6)
```

## Implementation Plan:

1. **Phase 1**: Add selection reasoning to current system
2. **Phase 2**: Allow Chief Agent to dynamically select agents
3. **Phase 3**: Enable mid-process agent additions
4. **Phase 4**: Implement complexity-based agent scaling

## Benefits:

1. **Transparency**: Users understand why specific agents were chosen
2. **Efficiency**: Only necessary agents are engaged
3. **Flexibility**: System adapts to query complexity
4. **Learning**: Chief Agent improves selection over time
5. **Control**: Users could potentially request specific agents

## Example Enhanced Output:

```
[Processing Bubble]
Analyzing request...
Query Type: Complex Mathematical Derivation with Research
Complexity Assessment: High (score: 5/6)

Selecting 5 specialized agents for this task:
• Math Agent - For mathematical derivation from first principles
• Research Agent - To find relevant sources and prior work
• Coding Agent - To verify calculations programmatically  
• Reasoning Agent - For step-by-step logical analysis
• Notes Agent - To document important findings

Chief Agent Reasoning: "This query requires both theoretical derivation and 
practical verification. The combination of mathematical proof with research 
requirements suggests we need comprehensive coverage from multiple perspectives."
```

This would make the system much more transparent and adaptive!