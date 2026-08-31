"""
AI explanation layer -- extension point, not a requirement.

The rest of this application (metrics, comparisons, investigation,
recommendations) produces plain-English text using deterministic rules,
with zero dependency on any AI provider. This module exists so a future
version can hand those same structured facts to a language model for
more natural, executive-ready prose -- without touching the analysis
code at all.

The default explainer (RuleBasedExplainer) does no network calls and
requires no API key: it just returns the deterministic text it's given.
A future AnthropicExplainer (sketched below, not implemented) would
read its API key from an environment variable and never receive
secrets/credentials as part of the "facts" payload -- only marketing
performance data.
"""

from abc import ABC, abstractmethod


class Explainer(ABC):
    @abstractmethod
    def explain(self, facts: dict) -> str:
        """Turn a structured facts dict (e.g. an investigation report or
        a list of recommendations) into prose. Must not require network
        access to have a usable default implementation."""


class RuleBasedExplainer(Explainer):
    """Default, always-available explainer. Facts already contain
    deterministically generated text (e.g. investigation['conclusion']);
    this just returns it. No API key, no network call."""

    def explain(self, facts: dict) -> str:
        if "conclusion" in facts:
            return facts["conclusion"]
        if "text" in facts:
            return facts["text"]
        return str(facts)


# --- Future extension point (not implemented) -----------------------------
#
# class AnthropicExplainer(Explainer):
#     """Would call the Claude API to turn `facts` into a richer executive
#     summary. Reads ANTHROPIC_API_KEY from the environment (see
#     .env.example) -- never required for the app to run, and never given
#     any secret/credential as part of the prompt, only performance facts
#     already computed by the deterministic layer above."""
#
#     def __init__(self, api_key=None):
#         import os
#         self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
#
#     def explain(self, facts: dict) -> str:
#         raise NotImplementedError("Wire up the Anthropic SDK here in a future sprint.")


def get_explainer() -> Explainer:
    """Single place the rest of the app asks for 'the current explainer'.
    Swapping in a real AI backend later is a one-line change here."""
    return RuleBasedExplainer()
