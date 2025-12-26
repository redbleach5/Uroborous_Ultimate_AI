"""
Centralized constants for AILLM system.

This module contains magic numbers and configuration values
that are used across multiple modules.
"""

# ==============================================================================
# Model Scoring Weights
# ==============================================================================

class ScoringWeights:
    """Weights for model selection scoring."""
    
    # Default weights for balanced selection
    CAPABILITY = 0.35
    PERFORMANCE = 0.30
    SPEED = 0.20
    QUALITY = 0.15
    
    # Weights when speed is preferred
    SPEED_PREFERRED_CAPABILITY = 0.20
    SPEED_PREFERRED_PERFORMANCE = 0.20
    SPEED_PREFERRED_SPEED = 0.50
    SPEED_PREFERRED_QUALITY = 0.10


# ==============================================================================
# Model Capability Thresholds
# ==============================================================================

class CapabilityThresholds:
    """Thresholds for model capability detection."""
    
    # Size thresholds (in billions of parameters)
    SMALL_MODEL_MAX_SIZE = 3.0   # Models <= 3B are considered small/fast
    MEDIUM_MODEL_MAX_SIZE = 7.0  # Models <= 7B are considered medium
    LARGE_MODEL_MIN_SIZE = 14.0  # Models >= 14B are considered large
    
    # Capability scores
    HIGH_CAPABILITY = 0.9
    GOOD_CAPABILITY = 0.85
    MEDIUM_CAPABILITY = 0.7
    DEFAULT_CAPABILITY = 0.5
    LOW_CAPABILITY = 0.3
    
    # Quality thresholds
    HIGH_QUALITY_MIN = 0.8
    MEDIUM_QUALITY_MIN = 0.5
    LOW_QUALITY_MIN = 0.3


# ==============================================================================
# Task Complexity
# ==============================================================================

class ComplexityThresholds:
    """Thresholds for task complexity detection."""
    
    # Text length thresholds
    SIMPLE_TASK_MAX_LENGTH = 50
    MEDIUM_TASK_MAX_LENGTH = 200
    
    # Token estimation
    CHARS_PER_TOKEN = 4
    COMPLEXITY_MULTIPLIER_LOW = 1.0
    COMPLEXITY_MULTIPLIER_MEDIUM = 2.0
    COMPLEXITY_MULTIPLIER_HIGH = 4.0
    
    # Complexity scores
    TRIVIAL_COMPLEXITY = 0.2
    SIMPLE_COMPLEXITY = 0.4
    MEDIUM_COMPLEXITY = 0.6
    COMPLEX_COMPLEXITY = 0.8
    VERY_COMPLEX_COMPLEXITY = 1.0


# ==============================================================================
# Performance Metrics
# ==============================================================================

class PerformanceThresholds:
    """Thresholds for performance evaluation."""
    
    # Minimum requests for reliable metrics
    MIN_REQUESTS_FOR_METRICS = 3
    
    # Success rate weights
    SUCCESS_RATE_WEIGHT = 0.6
    PERFORMANCE_WEIGHT = 0.4
    
    # Model speed (tokens per second)
    FAST_MODEL_SPEED = 50
    MEDIUM_MODEL_SPEED = 20
    SLOW_MODEL_SPEED = 10
    
    # Server response time thresholds (ms)
    GOOD_RESPONSE_TIME = 100
    ACCEPTABLE_RESPONSE_TIME = 500
    
    # Retry limits
    MAX_RETRY_COUNT = 3
    MAX_FALLBACK_ATTEMPTS = 3


# ==============================================================================
# Timeouts and Intervals
# ==============================================================================

class Timeouts:
    """Timeout values in seconds."""
    
    # Server discovery
    DISCOVERY_TIMEOUT = 2.0
    DISCOVERY_INTERVAL = 30
    
    # LLM requests
    DEFAULT_REQUEST_TIMEOUT = 300
    STREAM_TIMEOUT = 600
    CHAT_TIMEOUT = 120  # Chat endpoint timeout
    
    # Cache
    CACHE_TTL_SECONDS = 3600
    
    # Health checks
    HEALTH_CHECK_INTERVAL = 60


# ==============================================================================
# Model Penalties and Bonuses
# ==============================================================================

class ModelAdjustments:
    """Score adjustments for specific models/scenarios."""
    
    # Penalties (multipliers < 1.0)
    QWEN_NON_CODER_PENALTY = 0.85  # -15% for qwen in non-code tasks
    
    # Bonuses (multipliers > 1.0)
    GEMMA_CHAT_BONUS = 1.10        # +10% for gemma in chat tasks
    PREFERRED_MODEL_BONUS = 1.10   # +10% for user-preferred model


# ==============================================================================
# Confidence Thresholds
# ==============================================================================

class ConfidenceThresholds:
    """Thresholds for confidence scores in classification."""
    
    HIGH_CONFIDENCE = 0.8
    MEDIUM_CONFIDENCE = 0.5
    LOW_CONFIDENCE = 0.3
    DEFAULT_CONFIDENCE = 0.5
    
    # Minimum confidence for agent selection
    MIN_AGENT_CONFIDENCE = 0.4


# ==============================================================================
# Resource Levels
# ==============================================================================

class ResourceLevels:
    """System resource level definitions."""
    
    # GPU memory thresholds (GB)
    LOW_GPU_MEMORY = 8
    MEDIUM_GPU_MEMORY = 24
    HIGH_GPU_MEMORY = 48
    
    # CPU cores
    MIN_CPU_CORES = 4
    
    # Memory (GB)
    MIN_MEMORY_GB = 8

