"""TrainedRetrievalStrategyClassifier 运行时类测试。

mock transformers 内部 import + 推理，保证：
- 模型缺失 / 加载失败 / forward 异常 / label 非法 / 推理超时不破主流程
- 任何异常路径都返回 stub 等价结果（event_primary / low / stub_fallback）
- 协议签名与 Protocol 保持一致
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"
for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


class _FakeTokenizer:
    def __call__(self, text, *, truncation, max_length, return_tensors):
        del text, truncation, max_length, return_tensors
        return {"input_ids": [[0]], "attention_mask": [[1]]}


class _FakeModel:
    """模拟 transformers 模型：返回 magicMock 让 softmax/argmax 可链式调用。"""

    def __init__(self) -> None:
        self._logits = MagicMock()

    def __call__(self, *, input_ids, attention_mask):
        del input_ids, attention_mask
        return MagicMock(logits=self._logits)

    def eval(self) -> None:
        return None

    def to(self, device) -> None:
        del device
        return None


class TrainedClassifierFallbackTest(unittest.TestCase):
    def test_uses_fallback_when_model_dir_missing(self) -> None:
        from finsight_agent.control_plane.orchestrator.retrieval_strategy_classifier import (
            StubRetrievalStrategyClassifier,
        )
        from finsight_agent.control_plane.orchestrator.trained_strategy_classifier import (
            TrainedRetrievalStrategyClassifier,
        )

        clf = TrainedRetrievalStrategyClassifier(
            model_dir=Path("/nonexistent/path/that/does/not/exist"),
            fallback=StubRetrievalStrategyClassifier(),
        )
        payload = clf.classify(
            query="红海局势升级利好哪些A股航运股？",
            router_payload={"intent": "event_impact_analysis"},
            session_topic="",
        )
        self.assertEqual(payload["strategy"], "event_primary")
        self.assertEqual(payload["confidence"], "low")
        self.assertEqual(payload["reason"], "stub_fallback")

    def test_lazy_load_does_not_eagerly_open_model_dir(self) -> None:
        from finsight_agent.control_plane.orchestrator.trained_strategy_classifier import (
            TrainedRetrievalStrategyClassifier,
        )

        clf = TrainedRetrievalStrategyClassifier(
            model_dir=Path("/nonexistent/path/that/does/not/exist"),
        )
        # 构造完不触发任何加载
        self.assertFalse(clf._model_loaded)
        # 第一次 classify 才检查 model_dir 是否存在
        clf.classify(
            query="x",
            router_payload={"intent": "event_impact_analysis"},
            session_topic="",
        )
        self.assertTrue(clf._model_loaded)
        self.assertTrue(clf._degraded)

    def test_fallback_marker_is_stub_fallback(self) -> None:
        """fallback 路径下 reason 必须是 stub_fallback，与 stub 输出一致。"""
        from finsight_agent.control_plane.orchestrator.retrieval_strategy_classifier import (
            StubRetrievalStrategyClassifier,
        )
        from finsight_agent.control_plane.orchestrator.trained_strategy_classifier import (
            TrainedRetrievalStrategyClassifier,
        )

        clf = TrainedRetrievalStrategyClassifier(
            model_dir=Path("/nonexistent/path/that/does/not/exist"),
            fallback=StubRetrievalStrategyClassifier(),
        )
        payload = clf.classify(
            query="x",
            router_payload={"intent": "event_impact_analysis"},
            session_topic="",
        )
        # 与 StubRetrievalStrategyClassifier.classify() 的输出完全一致
        self.assertEqual(payload, StubRetrievalStrategyClassifier().classify(
            query="x", router_payload={"intent": "event_impact_analysis"}, session_topic="",
        ))


class TrainedClassifierMockedModelTest(unittest.TestCase):
    """mock transformers + torch，验证正常推理路径。"""

    def _patch_lazy_transformer(self, monkeypatch_module, *, fake_model):
        """替换模块内的 _LazyTransformer，让 from_pretrained 返回 fake_model。"""
        # 由具体测试决定 fake_model 是好的 logits 还是抛异常的
        from finsight_agent.control_plane.orchestrator import trained_strategy_classifier as mod

        class _Stub:
            @classmethod
            def from_pretrained(cls, model_dir):
                del model_dir
                return _FakeTokenizer(), fake_model

        monkeypatch_module._LazyTransformer = _Stub  # type: ignore[attr-defined]
        return mod

    def _make_fake_model_with_logits(self, logits_values):
        """构造一个 _FakeModel，模拟 transformers 2-D logits 输出 ``[batch=1, num_labels]``。"""
        import torch  # type: ignore

        # 真实 transformers 输出 2-D logits [1, num_labels]
        tensor = torch.tensor([logits_values], dtype=torch.float32)
        m = _FakeModel()
        m._logits = tensor
        return m

    def test_classify_returns_valid_label_and_confidence(self) -> None:
        import tempfile

        from finsight_agent.control_plane.orchestrator import trained_strategy_classifier as mod

        # logits: dual_primary (index 2) 概率最高
        fake_model = self._make_fake_model_with_logits([1.0, 0.5, 2.0])
        self._patch_lazy_transformer(mod, fake_model=fake_model)

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "fake_model"
            target.mkdir()
            # 写一个 labels.json，确保 _index_to_label 被正常解析
            (target / "labels.json").write_text(
                '{"0":"event_primary","1":"disclosure_primary","2":"dual_primary"}',
                encoding="utf-8",
            )
            clf = mod.TrainedRetrievalStrategyClassifier(model_dir=target)
            payload = clf.classify(
                query="红海局势升级利好哪些A股航运股？",
                router_payload={
                    "intent": "event_impact_analysis",
                    "entities": {
                        "event": "红海局势升级",
                        "themes": ["航运"],
                        "target": "A股航运股",
                    },
                },
                session_topic="",
            )
        self.assertIn(
            payload["strategy"],
            {"event_primary", "disclosure_primary", "dual_primary"},
        )
        self.assertIn(payload["confidence"], {"high", "medium", "low"})
        self.assertIn("margin=", payload["reason"])
        self.assertIn("top1=", payload["reason"])

    def test_build_input_depends_only_on_query(self) -> None:
        from finsight_agent.control_plane.orchestrator import trained_strategy_classifier as mod

        clf = mod.TrainedRetrievalStrategyClassifier(
            model_dir=Path("/nonexistent/path/that/does/not/exist"),
        )
        text_a = clf._build_input(
            query="红海局势最近怎么了？",
            router_payload={
                "intent": "event_impact_analysis",
                "entities": {
                    "event": "红海局势",
                    "themes": ["航运", "地缘"],
                    "target": "A股航运板块",
                    "time_scope": "recent",
                },
            },
            session_topic="航运主线",
        )
        text_b = clf._build_input(
            query="红海局势最近怎么了？",
            router_payload={
                "intent": "event_impact_analysis",
                "entities": {
                    "event": "完全不同的事件",
                    "themes": ["半导体"],
                    "target": "中芯国际",
                    "time_scope": "historic",
                },
            },
            session_topic="半导体主线",
        )
        self.assertEqual(text_a, "[QUERY] 红海局势最近怎么了？")
        self.assertEqual(text_a, text_b)

    def test_confidence_high_when_margin_above_high_threshold(self) -> None:
        import tempfile

        from finsight_agent.control_plane.orchestrator import trained_strategy_classifier as mod

        # logits 让 softmax 后 top1=2 (dual_primary) 概率 ~0.94，top2=0 ~0.04, margin ~0.9
        fake_model = self._make_fake_model_with_logits([1.0, 0.5, 5.0])
        self._patch_lazy_transformer(mod, fake_model=fake_model)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "fake_model"
            target.mkdir()
            (target / "labels.json").write_text(
                '{"0":"event_primary","1":"disclosure_primary","2":"dual_primary"}',
                encoding="utf-8",
            )
            clf = mod.TrainedRetrievalStrategyClassifier(model_dir=target)
            payload = clf.classify(
                query="x",
                router_payload={"intent": "event_impact_analysis"},
                session_topic="",
            )
        self.assertEqual(payload["confidence"], "high")

    def test_fallback_when_forward_raises(self) -> None:
        import tempfile

        from finsight_agent.control_plane.orchestrator import trained_strategy_classifier as mod

        class _RaisingModel(_FakeModel):
            def __call__(self, *, input_ids, attention_mask):
                raise RuntimeError("simulated forward failure")

        self._patch_lazy_transformer(mod, fake_model=_RaisingModel())
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "fake_model"
            target.mkdir()
            (target / "labels.json").write_text(
                '{"0":"event_primary","1":"disclosure_primary","2":"dual_primary"}',
                encoding="utf-8",
            )
            clf = mod.TrainedRetrievalStrategyClassifier(model_dir=target)
            payload = clf.classify(
                query="x",
                router_payload={"intent": "event_impact_analysis"},
                session_topic="",
            )
        self.assertEqual(payload["strategy"], "event_primary")
        self.assertEqual(payload["reason"], "stub_fallback")

    def test_fallback_when_labels_file_unreadable(self) -> None:
        import tempfile

        from finsight_agent.control_plane.orchestrator import trained_strategy_classifier as mod

        fake_model = self._make_fake_model_with_logits([1.0, 0.5, 2.0])
        self._patch_lazy_transformer(mod, fake_model=fake_model)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "fake_model"
            target.mkdir()
            # labels.json 故意写非法 JSON
            (target / "labels.json").write_text("not valid json", encoding="utf-8")
            clf = mod.TrainedRetrievalStrategyClassifier(model_dir=target)
            payload = clf.classify(
                query="x",
                router_payload={"intent": "event_impact_analysis"},
                session_topic="",
            )
        self.assertEqual(payload["strategy"], "event_primary")
        self.assertEqual(payload["reason"], "stub_fallback")
