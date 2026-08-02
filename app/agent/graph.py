from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.agent.nodes import analyze_activity, evaluate_retrieval, generate, retrieve, route_after_evaluate
from app.agent.state import AgentState


@lru_cache
def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("analyze_activity", analyze_activity)
    graph.add_node("retrieve", retrieve)
    graph.add_node("evaluate_retrieval", evaluate_retrieval)
    graph.add_node("generate", generate)

    graph.add_edge(START, "analyze_activity")
    graph.add_edge("analyze_activity", "retrieve")
    graph.add_edge("retrieve", "evaluate_retrieval")
    graph.add_conditional_edges(
        "evaluate_retrieval", route_after_evaluate, {"retrieve": "retrieve", "generate": "generate"}
    )
    graph.add_edge("generate", END)

    return graph.compile()
