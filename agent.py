import os
from typing import Dict, Any, TypedDict, Optional
from langgraph.graph import StateGraph, START, END
from langchain_google_genai import ChatGoogleGenerativeAI

try:
    from langchain_anthropic import ChatAnthropic
except ImportError:
    ChatAnthropic = None

from models import ExceptionClassification, DraftCommunication
from prompts import CLASSIFICATION_PROMPT, COMMUNICATION_PROMPTS
from rules import assign_resolution_path
import pandas as pd
import asyncio

# State Definition
class APState(TypedDict):
    invoice_row: Dict[str, Any]
    classification: ExceptionClassification
    resolution_path: str
    requires_communication: bool
    communication: Optional[DraftCommunication]
    final_output: Dict[str, Any]

# Dynamic LLM Factory
def get_llm(structured_output_schema=None):
    provider = os.environ.get("LLM_PROVIDER", "gemini").lower()
    
    if provider == "claude" and ChatAnthropic is not None:
        llm = ChatAnthropic(model="claude-3-5-sonnet-20240620", temperature=0)
    else:
        # Fallback to Gemini
        llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
        
    if structured_output_schema:
        return llm.with_structured_output(structured_output_schema)
    return llm

# Nodes
async def classify_exception(state: APState) -> APState:
    structured_llm = get_llm(ExceptionClassification)
    
    row = state["invoice_row"]
    prompt = CLASSIFICATION_PROMPT.format(
        invoice_no=row.get("invoice_no", ""),
        invoice_date=row.get("invoice_date", ""),
        supplier=row.get("supplier", ""),
        amount=row.get("amount", ""),
        o_id=row.get("O_ID", ""),
        p_id=row.get("P_id", ""),
        payment_vendor=row.get("payment_vendor", ""),
        raw_exception_type=row.get("exception_type", ""),
        raw_exception_description=row.get("exception_description", ""),
        days_outstanding=row.get("days_outstanding", "")
    )
    
    classification = await structured_llm.ainvoke(prompt)
    return {"classification": classification}

async def assign_resolution(state: APState) -> APState:
    classification = state["classification"]
    row = state["invoice_row"]
    
    try:
        amount = float(row.get("amount", 0))
    except (ValueError, TypeError):
        amount = 0.0
        
    resolution_path, requires_communication = assign_resolution_path(
        exception_type=classification.primary_exception_type,
        severity=classification.severity,
        amount=amount,
        variance_percentage=classification.variance_percentage
    )
    return {
        "resolution_path": resolution_path,
        "requires_communication": requires_communication
    }

async def draft_communication(state: APState) -> APState:
    structured_llm = get_llm(DraftCommunication)
    
    classification = state["classification"]
    row = state["invoice_row"]
    
    prompt_template = COMMUNICATION_PROMPTS.get(classification.primary_exception_type, COMMUNICATION_PROMPTS["Other"])
    prompt = prompt_template.format(
        supplier=row.get("supplier", "Vendor"),
        invoice_no=row.get("invoice_no", "Unknown"),
        p_id=row.get("P_id", "Unknown"),
        amount=row.get("amount", "0"),
        raw_exception_description=row.get("exception_description", "")
    )
    
    communication = await structured_llm.ainvoke(prompt)
    return {"communication": communication}

async def format_output(state: APState) -> APState:
    row = state["invoice_row"]
    classification = state["classification"]
    communication = state.get("communication")
    
    final_output = {
        "invoice_no": row.get("invoice_no"),
        "supplier": row.get("supplier"),
        "amount": row.get("amount"),
        "primary_exception_type": classification.primary_exception_type,
        "root_cause_hypothesis": classification.root_cause_hypothesis,
        "severity": classification.severity,
        "variance_percentage": classification.variance_percentage,
        "resolution_path": state.get("resolution_path"),
        "requires_communication": state.get("requires_communication"),
        "recipient_type": communication.recipient_type if communication else None,
        "communication_subject": communication.subject if communication else None,
        "communication_body": communication.body if communication else None,
        "days_outstanding": row.get("days_outstanding")
    }
    return {"final_output": final_output}

def route_communication(state: APState) -> str:
    """Conditional routing based on whether communication is required."""
    if state.get("requires_communication", False):
        return "draft_communication"
    return "format_output"

# Build Graph
def build_graph():
    workflow = StateGraph(APState)
    
    workflow.add_node("classify", classify_exception)
    workflow.add_node("assign_resolution", assign_resolution)
    workflow.add_node("draft_communication", draft_communication)
    workflow.add_node("format_output", format_output)
    
    workflow.add_edge(START, "classify")
    workflow.add_edge("classify", "assign_resolution")
    
    # Conditional Edge
    workflow.add_conditional_edges(
        "assign_resolution",
        route_communication,
        {
            "draft_communication": "draft_communication",
            "format_output": "format_output"
        }
    )
    
    workflow.add_edge("draft_communication", "format_output")
    workflow.add_edge("format_output", END)
    
    return workflow.compile()

# Async Process Queue Function
async def process_queue_async(df: pd.DataFrame) -> pd.DataFrame:
    graph = build_graph()
    
    # Prepare all initial states
    initial_states = [{"invoice_row": row.to_dict()} for _, row in df.iterrows()]
    
    # Run graph in batch asynchronously
    final_states = await graph.abatch(initial_states)
    
    # Extract final outputs
    results = [state["final_output"] for state in final_states]
    return pd.DataFrame(results)

def process_queue(df: pd.DataFrame) -> pd.DataFrame:
    """Synchronous wrapper for Gradio compatibility if needed."""
    try:
        # Check if there is a running event loop
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running event loop
        return asyncio.run(process_queue_async(df))
    else:
        # We are inside a running loop (like in Jupyter or ASGI)
        # However, asyncio.run won't work here. If we are in Gradio's async context,
        # Gradio functions should just be `async def`. But if this is called synchronously:
        import nest_asyncio
        nest_asyncio.apply()
        return asyncio.run(process_queue_async(df))

def process_single_exception(invoice_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Process a single exception payload through the LangGraph workflow."""
    graph = build_graph()
    initial_state = {"invoice_row": invoice_dict}
    
    try:
        loop = asyncio.get_running_loop()
        import nest_asyncio
        nest_asyncio.apply()
    except RuntimeError:
        pass
        
    final_state = asyncio.run(graph.ainvoke(initial_state))
    return final_state["final_output"]
