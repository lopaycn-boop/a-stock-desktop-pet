"""Test async LLM functions — achat, aresearch, aanalyze import and signature verification."""
import sys
sys.path.insert(0, ".")

import inspect
from potato.llm import achat, aresearch, aanalyze, aquick_chat, chat, research, analyze


class TestAsyncLLMImports:

    def test_achat_is_async(self):
        assert inspect.iscoroutinefunction(achat), "achat must be async"

    def test_aresearch_is_async(self):
        assert inspect.iscoroutinefunction(aresearch), "aresearch must be async"

    def test_aanalyze_is_async(self):
        assert inspect.iscoroutinefunction(aanalyze), "aanalyze must be async"

    def test_aquick_chat_is_async(self):
        assert inspect.iscoroutinefunction(aquick_chat), "aquick_chat must be async"

    def test_sync_still_exists(self):
        assert callable(chat), "sync chat must still exist"
        assert callable(research), "sync research must still exist"
        assert callable(analyze), "sync analyze must still exist"

    def test_achat_signature_matches_chat(self):
        chat_params = set(inspect.signature(chat).parameters.keys())
        achat_params = set(inspect.signature(achat).parameters.keys())
        assert chat_params == achat_params, f"Signature mismatch: {chat_params} vs {achat_params}"

    def test_aresearch_signature(self):
        params = set(inspect.signature(aresearch).parameters.keys())
        assert "prompt" in params
        assert "system" in params
        assert "max_tokens" in params

    def test_aanalyze_signature(self):
        params = set(inspect.signature(aanalyze).parameters.keys())
        assert "prompt" in params
        assert "system" in params
        assert "max_tokens" in params