"""Metrics collection for Prometheus/Grafana"""

from prometheus_client import Counter, Histogram, Gauge
import time

# Define metrics
queries_total = Counter(
    'rag_queries_total',
    'Total queries processed',
    ['retrieval_approach']
)

query_latency = Histogram(
    'rag_query_latency_seconds',
    'Query latency in seconds',
    ['retrieval_approach']
)

retrieval_scores = Histogram(
    'rag_retrieval_score',
    'Retrieval similarity scores',
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

user_feedback = Counter(
    'rag_user_feedback',
    'User feedback count',
    ['feedback_type']  # positive, neutral, negative
)

active_users = Gauge(
    'rag_active_users',
    'Number of active users'
)
