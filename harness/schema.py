"""JSON input is fail-closed: duplicate keys and nonfinite tokens are invalid."""
import json

def loads(raw) -> object:
    def unique(pairs) -> dict[str, object]:
        value={}
        for key,item in pairs:
            if key in value:raise ValueError('duplicate JSON key')
            value[key]=item
        return value
    def reject(_) -> None:raise ValueError('nonfinite JSON token')
    return json.loads(raw,object_pairs_hook=unique,parse_constant=reject)
