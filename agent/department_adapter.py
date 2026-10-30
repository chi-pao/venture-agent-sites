"""App-specific handlers. Embedded after department_manager by bundle_departments.py."""


def product_departments():
    return DepartmentManager(query, execute, OUT / 'departments', now)


def department_configuration(cfg, department):
    role = dict(cfg)
    overrides = cfg.get('department_models') or {}
    if overrides.get(department):
        role['model'] = str(overrides[department])
        if department == 'development': role['code_model'] = role['model']
        # Textual test planning and image review are separate capabilities.
        # A text-role override must not replace the configured vision model.
    return role


def department_failure_target(report, stage):
    phase = str(report.get('failed_step') or '')
    detail = str(report.get('details') or '')
    # A planner unable to write a test because the feature is absent is a
    # product defect, not a reason to keep regenerating the same QA plan.
    if '実装不足' in detail or report.get('blocked_features'): return 'development'
    if '初回画面に対象者と使い方' in detail: return 'design'
    if report.get('local_qa_passed') and report.get('passed') is not True: return 'research'
    if stage in ('検証環境の準備待ち', '自動検証の再試行待ち'):
        return 'verification'
    if phase == '競合比較': return 'research'
    if phase in ('製品設計', '実装計画', '画像デザイン審査'): return 'design'
    if phase in ('操作シナリオ設計', '環境準備'): return 'verification'
    return 'development'


def run_product_departments(job, name, cfg):
    manager = product_departments()
    try:spec = ensure_department_product_spec(name, department_configuration(cfg, 'proposal'))
    except Exception as exc:
        detail=type(exc).__name__+': '+str(exc)[:1600]
        scope=product_scope_sha(name) or 'requirements-pending'
        pending=manager.load(name,scope)
        pending['departments']['proposal']=dict(status='blocked',details=detail)
        pending.update(stage='企画・完成条件の修正待ち',details=detail)
        manager.note(pending,'proposal','blocked',detail)
        product_development_state(name,pending['stage'],detail)
        event(job,name+': '+pending['stage']+' / '+detail)
        return pending
    scope = product_scope_sha(name)
    initial = manager.load(name, scope)
    context_cfg = dict(cfg)

    def require_keys(item, keys):
        if not isinstance(item, dict) or any(k not in item for k in keys):
            raise ValueError('担当の成果物に必須項目がありません: ' + ','.join(keys))
        return item

    def research(context):
        event(job, name + ': 調査担当が公式機能・実画面の比較を作成')
        brief = ensure_competitive_brief(name, department_configuration(context_cfg, 'research'))
        if not competitive_design_ready(brief) or not competitive_visual_ready(brief):
            raise AutoQAPlanError('公式の機能説明と実画面2件以上の比較が未完了')
        return dict(verified=True, brief=brief)

    def design(context):
        event(job, name + ': 設計担当が対象者・利用手順・画面・機能の契約を作成')
        feedback = context['feedback'].get('design', {})
        design_cfg = dict(department_configuration(context_cfg, 'design'), _department_feedback=feedback.get('detail', ''))
        if feedback:
            # These are derived caches only; accepted artifacts remain immutable
            # in the manager's receipt folders and product checkpoint files.
            for key in ('product_blueprint:', 'implementation_plan:'):
                execute('DELETE FROM agent_settings WHERE key=?', (key + name + ':' + scope,))
        evidence = context.get('research', {})
        brief = evidence.get('brief') or development_design_reference_bundle(name, evidence.get('gap', '調査待ち'))
        blueprint = ensure_product_blueprint(name, design_cfg, allow_unverified=not evidence.get('verified'), competitive_brief=brief)
        plan = ensure_implementation_plan(name, design_cfg, blueprint)
        return dict(brief=brief, blueprint=blueprint, implementation_plan=plan)

    def validate_design(item):
        require_keys(item, ('brief', 'blueprint', 'implementation_plan'))
        validate_product_blueprint(item['blueprint'], spec, item['brief'])
        validate_implementation_plan(item['implementation_plan'], spec, item['blueprint'])

    def development(context):
        event(job, name + ': 開発担当が承認された設計成果物から制作・修正')
        previous = ''
        candidate = initial.get('candidate')
        if candidate:
            try:
                previous = Path(candidate['path']).read_text(encoding='utf-8')
                if hashlib.sha256(previous.encode()).hexdigest() != candidate['content_sha']: previous = ''
            except OSError: pass
        if previous and candidate.get('preliminary_passed') is True and not any(
                role in context['feedback'] for role in ('development','design')):
            # A provisional research refresh, QA-planning failure or transient
            # environment failure is not evidence of a product defect. Keep
            # the exact same-scope candidate and run the stronger QA against it.
            # Actual feature/visual failures return explicit development/design
            # feedback and therefore still enter the repair path below.
            event(job,name+': 機能・画面の不具合は未検出。保存候補を保持し、独立検査から再開')
            return dict(candidate)
        if not previous:
            assets = query("SELECT path FROM agent_assets WHERE idea=? AND kind='品質改善候補HTML' ORDER BY id DESC LIMIT 1", (name,))
            if assets and Path(assets[0]['path']).is_file(): previous = Path(assets[0]['path']).read_text(encoding='utf-8')
            else: previous = product_source(name)
        feedback = '\n'.join(DEPARTMENT_NAMES[k] + 'からの修正指示: ' + v['detail'] for k,v in context['feedback'].items())
        plan = quality_requirements_text(name) + '\n' + feedback
        page, verdict, passed = build(job, name, dict(department_configuration(context_cfg, 'development'), _department_documents=context['design'],
                _department_repair_feedback='\n'.join(v['detail'] for k,v in context['feedback'].items() if k in ('development','design'))),
            plan, asset_kind='品質改善候補HTML', existing_page=previous,
            allow_partial=spec['delivery_mode']=='connected')
        if not page: raise ValueError(verdict)
        # Retain the exact candidate even if a preliminary gate failed, so the
        # next repair uses the failing source rather than an unrelated old page.
        save(job, name, '部署引継候補HTML', page, 'html', verdict)
        asset = query("SELECT path FROM agent_assets WHERE idea=? AND kind='部署引継候補HTML' ORDER BY id DESC LIMIT 1", (name,))[0]
        return dict(path=asset['path'], content_sha=hashlib.sha256(page.encode()).hexdigest(),
                    preliminary_passed=bool(passed), details=verdict)

    def validate_candidate(item):
        require_keys(item, ('path', 'content_sha', 'preliminary_passed', 'details'))
        page = Path(item['path']).read_text(encoding='utf-8')
        if hashlib.sha256(page.encode()).hexdigest() != item['content_sha']:
            raise ValueError('候補の版が引継ぎ時点から変更されています')

    def verification(context):
        candidate = context['development']
        page = Path(candidate['path']).read_text(encoding='utf-8')
        if not candidate['preliminary_passed'] and '画面検査: 合格' not in candidate['details']:
            return dict(passed=False, return_to='development', details=candidate['details'], content_sha=candidate['content_sha'])
        event(job, name + ': 検証担当が同じ候補をPC・スマホで実操作・画像比較')
        passed, detail, stage = automated_product_qa(job, name, page,
            dict(department_configuration(context_cfg, 'verification'), _department_documents=context['design'],
                _department_independent_qa=True,qa_probe_units=True,
                _department_feedback=context['feedback'].get('verification',{}).get('detail','')))
        rows = query("SELECT path FROM agent_assets WHERE idea=? AND kind='自動品質検査レポート' ORDER BY id DESC LIMIT 1", (name,))
        report = json.loads(Path(rows[0]['path']).read_text(encoding='utf-8')) if rows else {}
        if report.get('content_sha') != candidate['content_sha']:
            raise ValueError('候補と実ブラウザ検証レポートの版が一致しません')
        return dict(passed=bool(passed), return_to=department_failure_target(report, stage),
                    details=detail, content_sha=candidate['content_sha'], report=rows[0]['path'])

    def validate_verification(item):
        require_keys(item, ('passed', 'return_to', 'details', 'content_sha'))
        if type(item['passed']) is not bool or item['return_to'] not in DEPARTMENT_NAMES:
            raise ValueError('検証結果の形式が不正です')
        if item['passed'] and not production_acceptance(name, item['content_sha']):
            raise ValueError('実操作・画面検査の合格証拠がありません')

    configuration = {
        'research': dict(policy=COMPETITIVE_POLICY, model=cfg['model']),
        'design': dict(policy=PRODUCT_BLUEPRINT_POLICY, implementation=IMPLEMENTATION_PLAN_POLICY, model=cfg['model']),
        'development': dict(version=APP_VERSION, model=coding_config(cfg)['model']),
        'verification': dict(policy=AUTO_QA_POLICY, independent_qa=CHECKPOINT_QA_POLICY, vision=cfg.get('qa_vision_model'), model=cfg['model']),
    }
    for department, settings in configuration.items():
        settings['role_model'] = (cfg.get('department_models') or {}).get(department, '')
    result = manager.run(name, scope, spec,
        dict(research=research, design=design, development=development, verification=verification),
        dict(proposal=validate_product_spec, research=lambda x: require_keys(x, ('verified','brief')),
             design=validate_design, development=validate_candidate, verification=validate_verification),
        configuration, enabled=lambda: bool(state()['enabled'] and development_allowed(name) and product_scope_sha(name)==scope))
    candidate = result.get('candidate', {})
    product_development_state(name, result['stage'], result['details'],
        sum(1 for x in result['history'] if x['department']=='development' and x['status']=='running'), candidate.get('path', ''))
    event(job, name + ': 統括 / ' + result['stage'] + ' / ' + result['details'][:600])
    return result


def department_quality_development_cycle(job, cfg):
    rows = query('''SELECT a.name,d.updated,d.stage FROM autonomous_ideas a
        LEFT JOIN venture_product_development d ON d.idea=a.name
        LEFT JOIN venture_value_state v ON v.idea=a.name
        LEFT JOIN venture_owner_decisions o ON o.idea=a.name
        WHERE (a.attempts>0 OR d.idea IS NOT NULL) AND COALESCE(o.decision,'') NOT IN ('中止','保留')
          AND (o.decision='継続' OR COALESCE(v.phase,'') NOT IN ('中止','保留'))
        ORDER BY CASE WHEN d.stage='修正依頼あり' THEN 0 ELSE 1 END,COALESCE(d.updated,'')''')
    for row in rows:
        if not state()['enabled']: return
        name = row['name']
        if not development_allowed(name) or candidate_production_acceptance(name): continue
        if row['updated'] and row['stage']!='修正依頼あり':
            try:
                if (policy_clock()-datetime.fromisoformat(row['updated'])).total_seconds()<180: continue
            except (ValueError,TypeError): pass
        try: run_product_departments(job, name, cfg)
        except Exception as exc:
            detail=type(exc).__name__+': '+str(exc)[:1600]
            product_development_state(name, '統括・完成条件の修正待ち', detail)
            event(job, name+': 統括処理で停止 / '+detail)
        return
    event(job, '部署別開発: 対象は確認待ち・停止中・再試行間隔内です')


def render_department_status(name):
    manager = product_departments()
    data = manager.load(name, product_scope_sha(name))
    if not data['departments']: return
    with st.expander('担当部署と引き継ぎ状況', expanded=True):
        labels = dict(pending='未着手', running='作業中', completed='担当範囲を通過',
            blocked='問題の解決待ち', rework='差し戻し・改善待ち', approval_wait='この版への承認待ち')
        st.dataframe([{'担当': label, '状況': labels.get(data['departments'].get(key,{}).get('status','pending'), '未着手'),
            '問題・次の対応': data['feedback'].get(key,{}).get('detail') or data['departments'].get(key,{}).get('details','')}
            for key,label in DEPARTMENT_NAMES.items()], hide_index=True, width='stretch')
        st.caption('担当範囲の通過と製品全体の完成は別です。成果物を保持し、不合格の担当から再開します。')
