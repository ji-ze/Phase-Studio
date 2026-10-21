"""Report a verified runtime content identity without modifying the runtime.

This report is build evidence, not an authenticated release manifest. Runtime
compatibility must be bound to signed release metadata before EXE-only download.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from phase_studio.update_transaction import runtime_files,runtime_generation


def report(runtime):
    runtime=Path(runtime).resolve()
    generation=runtime_generation(runtime)
    files=runtime_files(runtime)
    return {'schema':1,'algorithm':'sha256-canonical-path-hash-map-v1',
        'runtime_generation':generation,'file_count':len(files),'files':files}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    runtime=args.runtime.resolve();output=args.output.resolve()
    if output==runtime or output.is_relative_to(runtime):
        parser.error('Evidence output must be outside the immutable runtime.')
    evidence=report(runtime)
    with output.open('x',encoding='utf8') as stream:
        json.dump(evidence,stream,sort_keys=True,indent=2)
    print(evidence['runtime_generation'])


if __name__=='__main__':main()
