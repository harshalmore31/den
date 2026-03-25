"""Memory system configuration for Den agents."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DenMemoryConfig:
    """Configuration for Den's always-on memory system."""

    db_path: str = "/den/memory/memory.db"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384
    use_fastembed: bool = True
    theta_gate: float = 0.35
    beta_gate: float = 6.0
    initial_strength: float = 1.0
    decay_rate: float = 0.995
    reinforce_amount: float = 0.1

    category_importance: dict[str, float] = field(default_factory=lambda: {
        "fact": 1.0,
        "preference": 1.2,
        "task_result": 1.3,
        "error": 1.4,
        "learned": 1.5,
        "progress": 1.3,
    })

    contradiction_key_threshold: float = 0.70
    contradiction_value_threshold: float = 0.50
    top_k: int = 10
    min_relevance: float = 0.10
    edge_threshold: float = 0.3
    edge_decay_rate: float = 0.02
    n_hops: int = 2

    anchors: dict[str, list[str]] = field(default_factory=lambda: {
        "fact": [
            "The project uses Python 3.12",
            "The API endpoint is /api/v2/users",
            "The deployment target is AWS Lambda",
            "The stock market closed up 2% today",
        ],
        "preference": [
            "I prefer dark mode",
            "Always use TypeScript instead of JavaScript",
            "I like concise responses",
            "Use bullet points for summaries",
        ],
        "task_result": [
            "The weekly report was generated successfully",
            "The data analysis found 3 trends",
            "The research identified 5 competitors",
            "Task completed in 2 iterations",
        ],
        "error": [
            "The API call failed with a 500 error",
            "File not found when trying to read data",
            "The search returned no results",
            "Memory limit exceeded during processing",
        ],
        "learned": [
            "Using Brave Search gives better results than DuckDuckGo",
            "The user prefers reports in markdown format",
            "Breaking research into phases improves quality",
            "Adding sources increases report credibility",
        ],
        "progress": [
            "Currently working on the market analysis section",
            "Need to finish the competitor comparison next",
            "The first draft is done, review pending",
            "Data collection is 80% complete",
        ],
    })
