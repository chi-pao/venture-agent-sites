"""Persistent handoffs for the app factory. No model, publishing, or approval authority.

Handlers run the real research, design, implementation and browser/vision engines.
Receipts only say that a particular department's contract passed, never that the
product is profitable or approved. The legacy one-file updater embeds this module.
"""
import hashlib
import json
import os
import re
from pathlib import Path


DEPARTMENT_POLICY = '2026-10-26-handoffs-1'
DEPARTMENT_NAMES = {
    'proposal': '企画・完成条件', 'research': '競合・市場調査',
    'design': '機能・UX設計', 'development': '開発・統合',
    'verification': '実操作・画面検証', 'operations': '承認後の運営',
}


def department_digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


class DepartmentManager:
    def __init__(self, query, execute, root, clock):
        self.query, self.execute = query, execute
        self.root, self.clock = Path(root), clock
        execute('''CREATE TABLE IF NOT EXISTS venture_department_state(
            idea TEXT PRIMARY KEY, scope TEXT NOT NULL, document TEXT NOT NULL, updated TEXT NOT NULL)''')

    def load(self, name, scope):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', scope):
            raise ValueError('要件の版識別子が不正です')
        rows = self.query('SELECT scope,document FROM venture_department_state WHERE idea=?', (name,))
        if rows and rows[0]['scope'] == scope:
            state = json.loads(rows[0]['document'])
            if state.get('policy') == DEPARTMENT_POLICY:
                return state
        return dict(policy=DEPARTMENT_POLICY, idea=name, scope=scope, departments={},
                    feedback={}, history=[], stage='制作待ち', details='')

    def persist(self, state):
        state['updated'] = self.clock()
        self.execute('''INSERT INTO venture_department_state(idea,scope,document,updated)
            VALUES(?,?,?,?) ON CONFLICT(idea) DO UPDATE SET scope=excluded.scope,
            document=excluded.document,updated=excluded.updated''',
                     (state['idea'], state['scope'], json.dumps(state, ensure_ascii=False), state['updated']))

    def note(self, state, department, status, detail):
        state['history'] = (state['history'] + [dict(department=department, status=status,
                                                    detail=str(detail)[:2000], at=self.clock())])[-40:]
        self.persist(state)

    def read_receipt(self, receipt):
        path = Path(receipt['path']).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise ValueError('成果物が部署フォルダーの外にあります')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != receipt['sha256']:
            raise ValueError('部署の成果物が変更されています')
        return json.loads(raw)

    def task(self, state, department, inputs, handler, validate):
        fingerprint = department_digest(dict(policy=DEPARTMENT_POLICY, inputs=inputs))
        previous = state['departments'].get(department, {})
        if previous.get('input_sha') == fingerprint and previous.get('status') == 'completed':
            try:
                output = self.read_receipt(previous)
                validate(output)
                return output
            except (OSError, ValueError, TypeError, KeyError):
                pass  # Missing/corrupt receipts must be regenerated, never trusted.
        state['departments'][department] = dict(status='running', input_sha=fingerprint)
        self.note(state, department, 'running', '前段の成果物を受け取り開始')
        try:
            output = handler()
            validate(output)
            raw = json.dumps(output, ensure_ascii=False, sort_keys=True).encode()
            digest = hashlib.sha256(raw).hexdigest()
            directory = self.root / department_digest(state['idea'])[:16] / state['scope'] / department
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / (digest + '.json')
            temporary = path.with_suffix('.tmp')
            temporary.write_bytes(raw)
            os.replace(temporary, path)
            state['departments'][department] = dict(status='completed', input_sha=fingerprint,
                path=str(path), sha256=digest, checked=self.clock())
            state['feedback'].pop(department, None)
            self.note(state, department, 'completed', '担当範囲の成果物を保存。製品全体の合格とは別')
            return output
        except Exception as exc:
            detail = type(exc).__name__ + ': ' + str(exc)[:2000]
            state['departments'][department].update(status='blocked', details=detail)
            state['stage'] = DEPARTMENT_NAMES[department] + 'の修正待ち'
            state['details'] = detail
            self.note(state, department, 'blocked', detail)
            raise

    def return_work(self, state, department, detail, source_sha):
        if department not in DEPARTMENT_NAMES or department == 'operations':
            raise ValueError('差し戻し先が不正です')
        signature = department_digest([department, detail])
        memory = state.setdefault('failures', {})
        previous = memory.get(signature, {})
        feedback = dict(detail=str(detail)[:4000], source_sha=source_sha, signature=signature,
                        repeats=previous.get('repeats', 0) + 1 if previous.get('signature') == signature else 1)
        state['feedback'][department] = feedback
        memory[signature] = feedback
        # Bound stored diagnostics; full receipts/history remain on disk.
        if len(memory)>100: memory.pop(next(iter(memory)))
        # Invalidate only the responsible department. Downstream input hashes
        # invalidate changed outputs; independent research is kept intact.
        state['departments'].setdefault(department, {})['status'] = 'rework'
        self.note(state, department, 'rework', detail)

    def run(self, name, scope, spec, handlers, validators, configuration, enabled=lambda: True):
        state = self.load(name, scope)
        context = dict(spec=spec, feedback=dict(state['feedback']))
        self.task(state, 'proposal', spec, lambda: spec, validators['proposal'])
        for department in ('research', 'design', 'development', 'verification'):
            if not enabled():
                state.update(stage='停止中', details='停止要求を受け、次の担当へ進みません')
                self.persist(state)
                return state
            # Research failure is tracked independently and does not prevent
            # offline UX/feature work. It remains required for owner review.
            inputs = dict(scope=scope, configuration=configuration.get(department, {}),
                          feedback=state['feedback'].get(department))
            if department == 'design':
                inputs.update(spec=spec, research=context.get('research'))
            elif department == 'development':
                inputs.update(design=context.get('design'))
            elif department == 'verification':
                inputs.update(development=context.get('development'), research=context.get('research'),
                              design=context.get('design'))
            try:
                output = self.task(state, department, inputs,
                                   lambda d=department: handlers[d](context), validators[department])
                context[department] = output
                if department == 'development':
                    state['candidate'] = output
                    self.persist(state)
            except Exception as exc:
                if department != 'research':
                    return state
                context['research'] = dict(verified=False, gap=type(exc).__name__ + ': ' + str(exc)[:1500])
            context['feedback'] = dict(state['feedback'])
        result = context['verification']
        candidate_sha = context['development']['content_sha']
        if result['passed'] is not True:
            target = result['return_to']
            self.return_work(state, target, result['details'], candidate_sha)
            # A rejected review cannot become a permanently cached verdict.
            state['departments']['verification']['status'] = 'rework'
            state.update(stage=DEPARTMENT_NAMES[target] + 'へ差し戻し', details=result['details'])
        elif context.get('research', {}).get('verified') is not True:
            self.return_work(state, 'research', '競合の機能・画面比較が未完了', candidate_sha)
            state.update(stage='比較調査待ち・制作検査済み', details='制作検査は通過。比較調査の完了後に同じ版を再検証')
        else:
            state.update(stage='のぼるさん確認待ち', details=result['details'])
            state['departments']['operations'] = dict(status='approval_wait', content_sha=candidate_sha,
                                                      details='この版へのユーザー承認と接続確認後に既存の運営処理へ引き継ぐ')
        state['candidate'] = context['development']
        self.persist(state)
        return state
