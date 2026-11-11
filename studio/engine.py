# -*- coding: utf-8 -*-
"""Claude Code を「部門の担当者」として動かす部分。

各部門は `claude -p`（Claude Code のヘッドレス実行）で動く。
今の Claude Code の契約の範囲で動き、Anthropic API の従量課金は使わない。
テスト用に、AIを呼ばずに決まった答えを返す「練習モード（mock）」がある。
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path


class EngineError(RuntimeError):
    pass


def extract_json(text):
    """返事から JSON（オブジェクト）を取り出す。```json の囲みを優先し、なければ最後の {...}。"""
    blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
    for block in reversed(blocks):
        try:
            return json.loads(block)
        except ValueError:
            pass
    decoder = json.JSONDecoder()
    found, skip_until = None, -1
    for m in re.finditer(r"\{", text):
        if m.start() < skip_until:  # すでに読んだオブジェクトの内側は飛ばす
            continue
        try:
            value, end = decoder.raw_decode(text[m.start():])
        except ValueError:
            continue
        if isinstance(value, dict):
            found = value  # 最後に見つかった完全なオブジェクトを使う
            skip_until = m.start() + end
    if found is None:
        raise EngineError("返事に JSON が見つからない")
    return found


def check_required(data, required):
    """required: {"key": type or (types)}。足りない項目の一覧を返す。"""
    missing = []
    for key, typ in required.items():
        if key not in data:
            missing.append(key)
        elif typ is not None and not isinstance(data[key], typ):
            missing.append(f"{key}（形が違う）")
    return missing


class Engine:
    def __init__(self, cfg, log_path):
        self.cfg = cfg
        self.log_path = Path(log_path)
        self.mock = bool(cfg.get("mock")) or os.environ.get("STUDIO_MOCK") == "1"
        self.mock_answers = None
        self.total_cost = 0.0

    # ---- 共通 ----
    def _log(self, dept, prompt, result, cost):
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"dept": dept, "prompt": prompt[:4000], "result": result[:20000],
                                "cost_usd": cost}, ensure_ascii=False) + "\n")

    def claude_cmd(self):
        name = self.cfg.get("claude_cmd") or "claude"
        path = shutil.which(name)
        if not path:
            raise EngineError(
                f"Claude Code の CLI（{name}）が見つからない。"
                "README の「準備」に沿って入れるか、config.json の claude_cmd に場所を書く。")
        return path

    def _run(self, prompt, tools, cwd, max_turns, permission_mode=None, resume=None):
        cmd = [self.claude_cmd(), "-p", "--output-format", "json",
               "--max-turns", str(max_turns)]
        if self.cfg.get("model"):
            cmd += ["--model", self.cfg["model"]]
        if tools:
            cmd += ["--allowedTools", ",".join(tools)]
        if permission_mode:
            cmd += ["--permission-mode", permission_mode]
        if resume:
            cmd += ["--resume", resume]
        try:
            proc = subprocess.run(cmd, input=prompt, text=True, encoding="utf-8",
                                  capture_output=True, cwd=str(cwd),
                                  timeout=int(self.cfg.get("timeout_minutes", 60)) * 60)
        except subprocess.TimeoutExpired as e:
            raise EngineError("時間切れ（timeout_minutes を見直す）") from e
        if proc.returncode != 0 and not proc.stdout.strip():
            raise EngineError(f"Claude Code が失敗: {proc.stderr.strip()[:800]}")
        try:
            out = json.loads(proc.stdout)
        except ValueError as e:
            raise EngineError(f"Claude Code の出力を読めない: {proc.stdout[:500]}") from e
        if out.get("is_error"):
            raise EngineError(f"Claude Code がエラーで終了: {str(out.get('result'))[:800]}")
        cost = float(out.get("total_cost_usd") or 0)
        self.total_cost += cost
        return str(out.get("result") or ""), out.get("session_id"), cost

    # ---- 部門から呼ぶ入口 ----
    def ask_json(self, dept, prompt, required, *, tools, cwd, max_turns=30, permission_mode=None):
        """部門に仕事を頼み、JSON の答えを受け取る。形が崩れたら1回だけ出し直してもらう。"""
        if self.mock:
            return self._mock(dept)
        Path(cwd).mkdir(parents=True, exist_ok=True)
        text, sid, cost = self._run(prompt, tools, cwd, max_turns, permission_mode)
        self._log(dept, prompt, text, cost)
        try:
            data = extract_json(text)
            missing = check_required(data, required)
        except EngineError:
            data, missing = None, ["JSON"]
        if missing and sid:
            fix = ("さきほどの答えの形が足りません（不足: " + "、".join(missing) +
                   "）。調べ直しは不要です。指定の JSON だけを ```json で囲んで出し直してください。")
            text, _, cost = self._run(fix, [], cwd, 3, resume=sid)
            self._log(dept + "（出し直し）", fix, text, cost)
            data = extract_json(text)
            missing = check_required(data, required)
        if missing:
            raise EngineError(f"{dept}の答えに不足: {'、'.join(missing)}")
        return data

    # ---- 練習モード ----
    def _mock(self, dept):
        if self.mock_answers is None:
            path = Path(__file__).with_name("tests") / "mock_answers.json"
            self.mock_answers = json.loads(path.read_text(encoding="utf-8"))
        key = dept.split("（")[0]
        if key not in self.mock_answers:
            raise EngineError(f"練習モードの答えがない: {key}")
        answer = self.mock_answers[key]
        if isinstance(answer, list):  # 呼ばれた順に答えを変える（最後のものを使い回す）
            self.mock_calls = getattr(self, "mock_calls", {})
            n = self.mock_calls.get(key, 0)
            self.mock_calls[key] = n + 1
            answer = answer[min(n, len(answer) - 1)]
        return json.loads(json.dumps(answer, ensure_ascii=False))
