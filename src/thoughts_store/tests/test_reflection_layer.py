# -*- coding: utf-8 -*-
import json, os, tempfile
from reflection_layer import run_reflection

def test_basic():
    tmp = tempfile.mkdtemp()
    thoughts = os.path.join(tmp, "sample.ndjson")
    with open(thoughts, "w", encoding="utf-8") as f:
        f.write(json.dumps({"date":"2025-11-11","text":"memory_map と gravity の連携を強化したい。alpha 補正も動作確認。","tags":["dev"]}, ensure_ascii=False)+"\n")
        f.write(json.dumps({"date":"2025-11-11","text":"Self-Reflective Layer の雛形設計を開始する。","tags":["design"]}, ensure_ascii=False)+"\n")
    alpha = os.path.join(tmp, "alpha.json")
    with open(alpha, "w", encoding="utf-8") as f:
        json.dump({"focus_terms":["memory_map","gravity","reflection"], "deprioritize":["雑談"]}, f, ensure_ascii=False)
    out = os.path.join(tmp, "artifacts")
    outputs = run_reflection(thoughts, alpha, out)
    assert os.path.exists(outputs["result_json"])
    assert os.path.exists(outputs["ndjson"])
    assert os.path.exists(outputs["report"])
