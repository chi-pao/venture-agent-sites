"""Experiment-side business rules, independent of generated renderer outputs.

The existing six-record contrasts already require these states. Keep the
production-planner experiment and diagnostic under the same declared rule;
do not alter expected counts to match an observed page or model answer.
"""

RETURNS_STATE_POLICY = '返金済み・対象外を除く未完了件数。返金済み・対象外を除く未処理件数。対応期限が今日より前かつ未完了の期限超過件数を表示する。'
