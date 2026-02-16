"""
LLM-Based Few-Shot Classifier

Generic few-shot classification using local LLM.
Accepts dynamic intent labels and examples from agent configuration.
"""

import logging
import httpx
from typing import List, Dict, Optional

from framework.config.constants import LLM_TIMEOUT_CLASSIFICATION

logger = logging.getLogger(__name__)

LLM_TIMEOUT = LLM_TIMEOUT_CLASSIFICATION


class LLMClassifier:
    """
    Few-shot classifier using a local LLM.

    Classifies text into categories using few-shot examples.
    Works with any set of labels and examples defined in agent.json.
    """

    def __init__(self, endpoint: str = "http://localhost:8000"):
        self.endpoint = endpoint

    def classify(
        self,
        text: str,
        labels: List[str],
        examples: Optional[List[Dict[str, str]]] = None,
        context: str = "",
    ) -> str:
        """
        Classify text into one of the given labels.

        Args:
            text: Text to classify
            labels: List of possible category labels
            examples: Optional few-shot examples [{"text": ..., "label": ...}]
            context: Additional context for classification

        Returns:
            str: Predicted label (one of the provided labels)
        """
        # Build prompt
        labels_str = ", ".join(labels)
        prompt = f"Classify the following text into exactly one category.\n\nCategories: {labels_str}\n"

        if context:
            prompt += f"\nContext: {context}\n"

        if examples:
            prompt += "\nExamples:\n"
            for ex in examples[:5]:  # Limit to 5 examples
                prompt += f'- "{ex["text"]}" -> {ex["label"]}\n'

        prompt += f'\nText: "{text}"\n\nCategory:'

        try:
            response = httpx.post(
                f"{self.endpoint}/generate",
                json={
                    "prompt": prompt,
                    "max_tokens": 20,
                    "temperature": 0.1,
                    "stop": ["\n"],
                },
                timeout=LLM_TIMEOUT,
            )
            response.raise_for_status()

            result = response.json().get("text", "").strip().lower()

            # Match to closest label
            for label in labels:
                if label.lower() in result:
                    return label

            # Fallback to first label
            return labels[0]

        except Exception as e:
            logger.error(f"Classification error: {e}")
            return labels[0]

    def classify_response_type(
        self,
        text: str,
        types: List[str] = None,
    ) -> str:
        """
        Classify a user response type.

        Default types: affirmative, negative, information, question, unclear
        """
        if types is None:
            types = ["affirmative", "negative", "information", "question", "unclear"]

        return self.classify(text, types, context="User response to a question")
