"""Build using a local engine's own localization identities, no C++ needed."""
import argparse
import json
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / 'Content/Python'))
from xh_node_chinese import core

parser = argparse.ArgumentParser()
parser.add_argument('--engine', required=True, help='Path to UE/Engine')
parser.add_argument('--inspect', action='store_true')
args = parser.parse_args()
catalogue = core.build_catalogue(args.engine)
core.write_json(PLUGIN / 'Saved/catalogue.json', catalogue)
report = core.compile_dictionary(PLUGIN, catalogue)
report['pending_entries'] = core.export_pending(PLUGIN, catalogue, PLUGIN / 'Saved/Pending.csv')
core.write_json(PLUGIN / 'Saved/report.json', report)
print(json.dumps(report, ensure_ascii=False, indent=2))
if args.inspect:
    for group in ('Niagara', 'Material', 'Blueprint'):
        print('\n' + group)
        unique = sorted({e['source'] for e in catalogue if e['category'] == group and 3 < len(e['source']) < 55
                         and (not e['builtin'] or e['builtin'] == e['source'])})
        print(json.dumps(unique[:120], ensure_ascii=False, indent=2))
