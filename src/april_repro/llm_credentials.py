"""Read explicitly selected dotenv credentials without executing shell code."""
import os
from pathlib import Path
import re
import shlex

PROVIDER_KEYS = frozenset(('OPENAI_API_KEY', 'MOONSHOT_API_KEY',
                           'DEEPSEEK_API_KEY', 'DASHSCOPE_API_KEY'))


def load_provider_env(path, *, environ=None):
    result = dict(os.environ if environ is None else environ)
    selected = {}
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        match = re.match(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$', line)
        if not match or match[1] not in PROVIDER_KEYS:
            continue
        name, literal = match.groups()
        if name in selected:
            raise ValueError('Duplicate provider credential variable')
        try:
            values = shlex.split(literal, comments=True, posix=True)
        except ValueError:
            raise ValueError('Invalid provider credential quoting') from None
        if len(values) != 1 or not values[0] or any(c.isspace() for c in values[0]):
            raise ValueError('Empty or invalid provider credential')
        value = values[0]
        if any(char in value for char in ('$', '`', '\x00')):
            raise ValueError('Credential interpolation is not supported')
        selected[name] = value
    result.update(selected)
    return result
