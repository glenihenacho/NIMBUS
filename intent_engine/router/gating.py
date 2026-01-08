"""
Confidence-based gating policy for escalation decisions.

This module implements the core logic that determines when to escalate
from cheap classifiers (Rasa/Mistral) to expensive long-chain reasoning (DeepSeek).
"""

from typing import Dict, Any
from ..models.intent_models import (
    ClassifierOutput,
    GatingDecision,
    GatingConfig,
    RiskLevel,
    IntentType,
    HIGH_RISK_INTENTS,
    Session
)


class GatingPolicy:
    """
    Implements the escalation gating policy.

    Escalation rules (applied in order):
    1. Low cheap confidence (< 0.70)
    2. High-risk intent with medium confidence (< 0.85)
    3. High-value session with medium confidence (< 0.80)
    4. Small margin between top 2 predictions (< 0.10)
    """

    def __init__(self, config: GatingConfig = None):
        self.config = config or GatingConfig()

    def should_escalate(
        self,
        classifier_output: ClassifierOutput,
        session: Session
    ) -> GatingDecision:
        """
        Determine if inference should escalate to DeepSeek.

        Args:
            classifier_output: Output from cheap classifier (Rasa/Mistral)
            session: Current session metadata

        Returns:
            GatingDecision with escalation verdict and reasoning
        """
        confidence = classifier_output.confidence
        top2_margin = classifier_output.top2_margin
        intent = classifier_output.intent
        risk_level = session.risk_level

        # Check if high-value session
        high_value_session = self._is_high_value_session(session)

        # Rule 1: Low confidence
        if confidence < self.config.default_threshold:
            return GatingDecision(
                should_escalate=True,
                reason=f"Low confidence ({confidence:.2f} < {self.config.default_threshold})",
                cheap_confidence=confidence,
                top2_margin=top2_margin,
                risk_level=risk_level,
                high_value_session=high_value_session
            )

        # Rule 2: High-risk intent with medium confidence
        if intent in HIGH_RISK_INTENTS and confidence < self.config.high_risk_threshold:
            return GatingDecision(
                should_escalate=True,
                reason=f"High-risk intent {intent.value} with medium confidence ({confidence:.2f} < {self.config.high_risk_threshold})",
                cheap_confidence=confidence,
                top2_margin=top2_margin,
                risk_level=risk_level,
                high_value_session=high_value_session
            )

        # Rule 3: High-value session with medium confidence
        if high_value_session and confidence < self.config.high_value_threshold:
            return GatingDecision(
                should_escalate=True,
                reason=f"High-value session with medium confidence ({confidence:.2f} < {self.config.high_value_threshold})",
                cheap_confidence=confidence,
                top2_margin=top2_margin,
                risk_level=risk_level,
                high_value_session=high_value_session
            )

        # Rule 4: Small margin between top 2 predictions
        if top2_margin < self.config.top2_margin_threshold:
            return GatingDecision(
                should_escalate=True,
                reason=f"Ambiguous prediction with small margin ({top2_margin:.2f} < {self.config.top2_margin_threshold})",
                cheap_confidence=confidence,
                top2_margin=top2_margin,
                risk_level=risk_level,
                high_value_session=high_value_session
            )

        # No escalation needed
        return GatingDecision(
            should_escalate=False,
            reason="Sufficient confidence from cheap classifier",
            cheap_confidence=confidence,
            top2_margin=top2_margin,
            risk_level=risk_level,
            high_value_session=high_value_session
        )

    def _is_high_value_session(self, session: Session) -> bool:
        """
        Determine if session is high-value based on engagement metrics.

        High-value criteria:
        - Minimum number of events
        - Minimum value score
        """
        return (
            session.event_count >= self.config.high_value_min_events and
            session.value_score >= self.config.high_value_min_score
        )

    def estimate_cost_savings(
        self,
        total_inferences: int,
        escalation_rate: float,
        cheap_cost_per_1k: float = 0.0001,  # Rasa/Mistral approximate
        expensive_cost_per_1k: float = 0.025  # DeepSeek approximate
    ) -> Dict[str, float]:
        """
        Estimate cost savings from gating policy vs always using expensive model.

        Args:
            total_inferences: Total number of inferences
            escalation_rate: Observed escalation rate (0-1)
            cheap_cost_per_1k: Cost per 1000 cheap inferences
            expensive_cost_per_1k: Cost per 1000 expensive inferences

        Returns:
            Dict with cost analysis
        """
        # With gating
        cheap_inferences = total_inferences * (1 - escalation_rate)
        expensive_inferences = total_inferences * escalation_rate

        gated_cost = (
            (cheap_inferences * cheap_cost_per_1k / 1000) +
            (expensive_inferences * expensive_cost_per_1k / 1000)
        )

        # Without gating (always expensive)
        always_expensive_cost = total_inferences * expensive_cost_per_1k / 1000

        savings = always_expensive_cost - gated_cost
        savings_pct = (savings / always_expensive_cost * 100) if always_expensive_cost > 0 else 0

        return {
            "total_inferences": total_inferences,
            "escalation_rate": escalation_rate,
            "cheap_inferences": cheap_inferences,
            "expensive_inferences": expensive_inferences,
            "gated_cost_usd": round(gated_cost, 4),
            "always_expensive_cost_usd": round(always_expensive_cost, 4),
            "savings_usd": round(savings, 4),
            "savings_pct": round(savings_pct, 2)
        }


class AdaptiveGatingPolicy(GatingPolicy):
    """
    Adaptive gating policy that adjusts thresholds based on observed performance.

    This can be used to dynamically tune gating parameters based on:
    - Actual model performance metrics
    - Cost constraints
    - Latency requirements
    """

    def __init__(
        self,
        config: GatingConfig = None,
        target_escalation_rate: float = 0.20,
        adjustment_step: float = 0.02
    ):
        super().__init__(config)
        self.target_escalation_rate = target_escalation_rate
        self.adjustment_step = adjustment_step

    def adjust_thresholds(
        self,
        current_escalation_rate: float,
        cheap_model_accuracy: float,
        expensive_model_accuracy: float
    ):
        """
        Adjust gating thresholds based on observed metrics.

        Args:
            current_escalation_rate: Observed escalation rate (0-1)
            cheap_model_accuracy: Accuracy of cheap model (0-1)
            expensive_model_accuracy: Accuracy of expensive model (0-1)
        """
        # If escalating too much, tighten thresholds
        if current_escalation_rate > self.target_escalation_rate:
            self.config.default_threshold -= self.adjustment_step
            self.config.high_risk_threshold -= self.adjustment_step
            self.config.high_value_threshold -= self.adjustment_step

        # If escalating too little and cheap model accuracy is low, loosen thresholds
        elif (
            current_escalation_rate < self.target_escalation_rate and
            cheap_model_accuracy < 0.85
        ):
            self.config.default_threshold += self.adjustment_step
            self.config.high_risk_threshold += self.adjustment_step
            self.config.high_value_threshold += self.adjustment_step

        # Ensure thresholds stay in reasonable bounds
        self.config.default_threshold = max(0.50, min(0.85, self.config.default_threshold))
        self.config.high_risk_threshold = max(0.70, min(0.95, self.config.high_risk_threshold))
        self.config.high_value_threshold = max(0.60, min(0.90, self.config.high_value_threshold))


# Pre-configured policies for different use cases

def get_conservative_policy() -> GatingPolicy:
    """Conservative policy: escalate more often for higher accuracy"""
    return GatingPolicy(GatingConfig(
        default_threshold=0.80,
        high_risk_threshold=0.90,
        high_value_threshold=0.85,
        top2_margin_threshold=0.15
    ))


def get_aggressive_policy() -> GatingPolicy:
    """Aggressive policy: minimize escalation for lower cost"""
    return GatingPolicy(GatingConfig(
        default_threshold=0.60,
        high_risk_threshold=0.75,
        high_value_threshold=0.70,
        top2_margin_threshold=0.05
    ))


def get_balanced_policy() -> GatingPolicy:
    """Balanced policy: default recommended settings"""
    return GatingPolicy(GatingConfig())
