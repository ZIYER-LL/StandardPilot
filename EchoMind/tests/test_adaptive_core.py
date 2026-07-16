import unittest

from core.adaptive_contracts import ExecutionMode, ResponseProfile, budget_for
from core.adaptive_router import AdaptiveRouter
from core.fast_gate import FastGate


class DummyGateway:
    async def complete(self, **kwargs):
        raise AssertionError("high confidence cases should not call a model")


class AdaptiveCoreTests(unittest.TestCase):
    def setUp(self):
        self.gate = FastGate()
        self.router = AdaptiveRouter(DummyGateway())

    def test_knowledge_stats_is_zero_model(self):
        result = self.gate.match("知识库目前有多少篇文稿？")
        self.assertTrue(result.matched)
        self.assertEqual(result.action, "knowledge_stats")

    def test_exact_tdoc_lookup_is_zero_model(self):
        result = self.gate.match("帮我查找 S2-2601234 这篇 TDoc")
        self.assertTrue(result.matched)
        self.assertEqual(result.action, "document_lookup")

    def test_compound_task_uses_manager(self):
        result = self.router._heuristic("总结这些文稿，比较公司观点，判断标准化 Gap，并给出提案建议")
        self.assertEqual(result.mode, ExecutionMode.MANAGER_AGENT)
        self.assertEqual(result.response_profile, ResponseProfile.REPORT)

    def test_gap_task_uses_specialist(self):
        result = self.router._heuristic("这个问题是否存在标准化 Gap，还是实现问题？")
        self.assertEqual(result.mode, ExecutionMode.SPECIALIST_AGENT)
        self.assertEqual(result.specialist, "standard_analyst")

    def test_profiles_have_different_output_budgets(self):
        self.assertLess(budget_for(ResponseProfile.BRIEF).max_tokens, budget_for(ResponseProfile.REPORT).max_tokens)


if __name__ == "__main__":
    unittest.main()
