# -*- coding: utf-8 -*-
"""
Self-Reflective Layer v0.1

最小の自己反射アルゴリズム：
- NDJSONの思想群から頻出語を抽出（停用語・短語を除去）
- alpha_stateのfocus_termsをブースト、deprioritizeを減衰
- 欠落観点の推定：頻度の低い「期待用語」をmissing_anglesとして抽出
- 1行の「反射思想」テキストを生成
"""
from __future__ import annotations
import json, re, os, collections, datetime
from dataclasses import dataclass, field
from typing import List, Dict, Any, Iterable, Tuple

JA_STOP = set(
    "これ それ あれ ため こと もの よう です ます する した して いる いく いき ある ない なる から まで また そして しかし ので にて ために など られ たり たりする でも とか とかいう のに には".split()
)
EN_STOP = set(
    """the a an and or of to in for on with as is are was were be been being by from at that this those these it its if then else than so not into about over under out up down off you we they i he she them him her our your their""".split()
)


def _tokenize(text: str) -> List[str]:
    # 単純トークナイズ（記号除去、空白分割 + 日本語の連続ひらがな/カタカナ/漢字塊）
    text = re.sub(r"[^\w一-龥ぁ-んァ-ンー]", " ", text)
    # 英数はlower、連続和字はそのまま
    tokens = []
    for tok in text.split():
        if re.match(r"[A-Za-z0-9_]+$", tok):
            t = tok.lower()
            if t not in EN_STOP and len(t) >= 2:
                tokens.append(t)
        else:
            # 日本語トークン：1文字語は除外
            if tok not in JA_STOP and len(tok) >= 2:
                tokens.append(tok)
    return tokens


@dataclass
class ReflectionResult:
    summary: str
    top_terms: List[str]
    missing_angles: List[str]
    next_actions: List[str]
    generated_at: str = field(
        default_factory=lambda: datetime.datetime.now().isoformat()
    )


class ReflectionLayer:
    def __init__(
        self, focus_terms: Iterable[str] = (), deprioritize: Iterable[str] = ()
    ):
        self.focus_terms = set([t.lower() for t in focus_terms])
        self.deprioritize = set([t.lower() for t in deprioritize])

    def reflect(
        self, thoughts: Iterable[Dict[str, Any]]
    ) -> Tuple[ReflectionResult, str]:
        """
        Returns: (result, reflection_text)
        reflection_text: ThoughtStoreへ1行で保存するための完成文
        """
        counter = collections.Counter()
        texts = []
        for row in thoughts:
            text = str(row.get("text", ""))
            texts.append(text)
            for tok in _tokenize(text):
                w = tok
                if w in self.deprioritize:  # 減衰
                    counter[w] -= 0.5
                elif w in self.focus_terms:  # ブースト
                    counter[w] += 2.0
                else:
                    counter[w] += 1.0

        # 上位語彙
        top = [w for w, c in counter.most_common(12) if c > 0][:8]

        # 欠落観点：focus_termsのうち頻度上位に出ないもの
        missing = [t for t in self.focus_terms if t not in top][:5]

        summary = " / ".join(
            text.strip().split("\n")[0] for text in texts[:3] if text.strip()
        )[:180]
        if not summary:
            summary = "No summary (empty thoughts)"
        next_actions = []
        if missing:
            next_actions.append(
                f"重点未反映: {', '.join(missing)} の観点で思想を追加記録"
            )
        if top:
            next_actions.append(f"反復テーマ深化: {', '.join(top[:3])}")

        refl_text = "[Reflection v0.1] 直近思想の反復テーマ: " + ", ".join(top[:5])
        if missing:
            refl_text += " / 欠落観点: " + ", ".join(missing)

        result = ReflectionResult(
            summary=summary,
            top_terms=top,
            missing_angles=missing,
            next_actions=next_actions,
        )
        return result, refl_text


def run_reflection(
    thoughts_ndjson_path: str, alpha_state_path: str | None, out_dir: str
) -> Dict[str, Any]:
    # 入力
    thoughts = []
    with open(thoughts_ndjson_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                thoughts.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    focus_terms: List[str] = []
    deprior: List[str] = []
    if alpha_state_path and os.path.exists(alpha_state_path):
        with open(alpha_state_path, "r", encoding="utf-8") as f:
            st = json.load(f)
        focus_terms = list(st.get("focus_terms", []))
        deprior = list(st.get("deprioritize", []))

    layer = ReflectionLayer(focus_terms=focus_terms, deprioritize=deprior)
    result, reflection_text = layer.reflect(thoughts)

    os.makedirs(out_dir, exist_ok=True)
    # JSON
    out_json = os.path.join(out_dir, "reflection_result.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(result.__dict__, f, ensure_ascii=False, indent=2)
    # NDJSON（1行）
    out_ndjson = os.path.join(out_dir, "reflection_thought.ndjson")
    ndjson_line = json.dumps(
        {
            "date": datetime.date.today().isoformat(),
            "text": reflection_text,
            "tags": ["reflection", "auto"],
        },
        ensure_ascii=False,
    )
    with open(out_ndjson, "w", encoding="utf-8") as f:
        f.write(ndjson_line + "\n")
    # Report
    report_md = os.path.join(out_dir, "reflection_report.md")
    with open(report_md, "w", encoding="utf-8") as f:
        f.write("# Reflection Report v0.1\n\n")
        f.write(f"- generated_at: {result.generated_at}\n")
        f.write(f"- top_terms: {', '.join(result.top_terms)}\n")
        f.write(f"- missing_angles: {', '.join(result.missing_angles)}\n")
        f.write("## Next Actions\n")
        for a in result.next_actions:
            f.write(f"- {a}\n")
    return {"result_json": out_json, "ndjson": out_ndjson, "report": report_md}
