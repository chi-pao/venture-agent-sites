"""Embed modular departments for the existing checksum-verified single-file updater."""
from pathlib import Path
import argparse

START = '# BEGIN GENERATED DEPARTMENT ENGINE\n'
END = '# END GENERATED DEPARTMENT ENGINE\n'


def bundle(root):
    root = Path(root)
    path = root / 'venture_agent_integrated.py'
    source = path.read_text(encoding='utf-8')
    generated = START + '\n\n'.join((root / name).read_text(encoding='utf-8')
        for name in ('department_manager.py', 'department_spec_contract.py', 'qa_checkpoint_planner.py', 'department_adapter.py')) + '\n' + END
    if START in source:
        before, tail = source.split(START, 1)
        _, after = tail.split(END, 1)
        return before + generated + after
    marker = '\ndef quality_development_cycle(job,cfg):'
    if marker not in source: raise ValueError('Department insertion point not found')
    return source.replace(marker, '\n' + generated + marker, 1)


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check', action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parent;source=bundle(root);path=root/'venture_agent_integrated.py'
    if args.check:
        if source != path.read_text(encoding='utf-8'): raise SystemExit('Department bundle is stale')
    else: path.write_text(source, encoding='utf-8')
