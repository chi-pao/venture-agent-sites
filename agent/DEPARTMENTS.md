# Department pipeline — development version

This replaces the production-improvement scheduler with persistent handoffs, using the existing real engines. It does not establish universal app-generation quality. `release.json` is intentionally unchanged until real proof passes.

| Department | Real engine | Output / return path |
| --- | --- | --- |
| Proposal | `ensure_product_spec` | Audience, workflow, must-have functions, acceptance cases, dependencies |
| Research | `ensure_competitive_brief` | Official feature sources and actual desktop/mobile references; unavailable research remains a gap |
| Design | `ensure_product_blueprint`, `ensure_implementation_plan` | Screen hierarchy, core journeys, feature/data/error contracts and concrete tests |
| Development | `build` | Exact candidate source plus preliminary validation; failing candidates are retained for repair |
| Verification | `automated_product_qa` | Real browser workflow and visual comparisons, bound to the candidate and requirement hashes |
| Operations | Existing owner-approval and publication checks | Approval wait; this manager does not publish, approve, post, or create accounts |

## Coordination

`department_manager.py` owns state and immutable JSON receipts. `department_adapter.py` supplies real app engines. `bundle_departments.py` embeds both into the single program used by the current Windows checksum-verified updater. Run `python agent/bundle_departments.py --check` in CI to catch a stale bundle.

Receipts live under `venture_outputs/departments/<product hash>/<requirement hash>/<department>/`. The database stores current task states and feedback. Reopening the program revalidates receipt bytes before reuse. A requirements change starts a new scope; old receipts remain on disk. A verifier/environment failure reuses the exact development candidate. A design failure returns to design, then rebuilds and rechecks. An unavailable market/competitor source does not stop independent prototyping; owner review still requires research evidence. Repeated diagnostic signatures are remembered independently of temporary feedback.

The coordinator asks the independent QA planner to derive browser cases from the requirements and visible screen, rather than reusing the renderer's own expected-value compiler. This avoids treating agreement with a template as proof that all requested workflows exist.

Different models can be assigned through configuration `department_models` (`proposal`, `research`, `design`, `development`, `verification`); unspecified roles retain existing models. This is role separation, not a claim that six different models or six simultaneous processes are running. CPU/GPU work is sequential to avoid exhausting local resources. Configuration/model changes invalidate affected receipts. Model weights are not trained by these records.

The dashboard shows six department states and the current return instructions beside the app preview. Department completion means only its contract passed. No preliminary screen check can override the existing final functional, visual or owner-approval checks.

## Validation and limits

The first real-model department runs failed: independent QA planning timed out
when generating five base scenarios or several feature cases together. The new
`qa_checkpoint_planner.py` generates one scenario/case at a time from compact
actual controls and result selectors. It saves each validated unit with an input
hash, retains successful units across timeouts, independently audits each pair
of requirement tests, and runs the unchanged final plan/browser/visual gates.
It does not reuse the renderer's expected-value compiler. Research transport
errors also no longer invalidate provisional offline design just because the
error text changes. The live workflow resumes the latest real checkpoint
artifact instead of regenerating completed design and source from zero.

These changes have resumption, cache invalidation, prompt-budget and rejection
unit tests. Real model success is still a separate required result.

`test_department_manager.py` exercises restart/resume, targeted returns, independent research gaps, changed requirements/configuration, receipt tampering, stop requests and repeated failure memory. `test_department_adapter.py` verifies wiring and approval protection with substituted engines; these tests are not real model evidence.

`tests/department_live_smoke.py` runs real models and Chromium through this coordinator for attendance, workday and a new returns workflow. The workflow fails if any product cannot reach the unchanged quality bar. Its artifacts keep the source, model results, task receipts and browser reports. Three successful examples would establish only those tested cases, not every future business or commercial viability. Low design/function quality requires improving the responsible engine and testing again; adding departments alone does not guarantee quality.

The saved workday specification also contained instruction text and unrequested collaborative-editing criteria. The proposal handler now detects these known contamination patterns and reconstructs acceptance conditions one original must-have requirement at a time, with persisted partial results. User-authored contracts are not silently overwritten. The general spec prompt no longer instructs every product to add search or collaboration. Original must-have/workflow/dependency fields remain intact; replacement acceptance conditions are still hypotheses until exercised by independent browser tests.

The 4aed971 real replay exposed two additional model-format failures: the workday acceptance repair omitted required fields, and attendance QA emitted invalid acceptance indices. The next revision constrains these short responses with JSON Schema, bounds retries without increasing the output budget, persists rejected responses, and records proposal failures as resumable state rather than crashing the proof run. HTTP 400 schema transport fallback retains the same small token budget. Full unit/browser success still does not establish real-model product quality.
