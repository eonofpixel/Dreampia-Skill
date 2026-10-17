#!/usr/bin/env python3
import argparse
import json
import pathlib
import sys
try:
    from . import core
except ImportError:
    import core

VERSION='0.7.0'
def main(argv=None) -> int:
    p=argparse.ArgumentParser(description='Local development harness; provider calls are opt-in')
    p.add_argument('--version',action='version',version=VERSION)
    p.add_argument('action',choices=['run','status','cancel','validate','trace','recover','reverify','authorize-replay','doctor'])
    p.add_argument('project')
    p.add_argument('--retry-failed',action='store_true')
    p.add_argument('--allow-provider',action='store_true',help='allow configured provider execution; may consume paid usage')
    p.add_argument('--task')
    p.add_argument('--accept-side-effects',action='store_true')
    p.add_argument('--executable',default='codex',help='doctor only: CLI executable to probe without inference')
    a=p.parse_args(argv)
    try:
        if a.action=='cancel': core.cancel(a.project);out={'cancel_requested':True}
        elif a.action=='validate': core.load(pathlib.Path(a.project).resolve());out={'valid':True}
        elif a.action=='recover': out=core.recover(a.project)
        elif a.action=='authorize-replay': out=core.authorize_replay(a.project,a.task,a.accept_side_effects)
        elif a.action=='doctor':
            try: from . import codex_adapter
            except ImportError: import codex_adapter
            out=codex_adapter.probe(a.executable)
            print(json.dumps(out,indent=2));return 0 if out['available'] else 2
        elif a.action=='trace':
            out={'rows':core.trace(a.project)}
            print(json.dumps(out,indent=2));return 0 if all(r['current'] for r in out['rows']) else 1
        else:
            out=core.run(a.project,retry_failed=a.retry_failed,allow_provider=a.allow_provider) if a.action=='run' else core.reverify(a.project) if a.action=='reverify' else core.status(a.project)
            print(json.dumps(out,indent=2));return 0 if all(t['status']=='verified' for t in out['tasks'].values()) else 1
        print(json.dumps(out,indent=2));return 0
    except (ValueError,KeyError,TypeError,OSError,RuntimeError,AttributeError) as e:
        print(json.dumps({'error':{'code':getattr(e,'code','INVALID_INPUT_OR_ENVIRONMENT'),'type':type(e).__name__},'rows':[]}))
        return 2
if __name__=='__main__': sys.exit(main())
