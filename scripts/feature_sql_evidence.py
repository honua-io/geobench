"""SQL-source evidence for the pinned feature-query profiles."""
import re
from collections import Counter

from feature_contract import HONUA_PROFILES

HEADER = re.compile(r'^\d{4}-\d\d-\d\d .*?\[(?P<pid>\d+)\] ')
EXECUTION = re.compile(r'LOG:\s+.*?(?:execute [^:]+|statement):\s*(.*)$')
TOKEN = re.compile(
    r"(?P<comment>--[^\n]*|/\*.*?\*/)"
    r"|(?P<string>'(?:''|\\.|[^'\\])*')"
    r"|(?P<dollar>(?P<tag>\$[A-Za-z_][A-Za-z_0-9]*\$|\$\$).*?(?P=tag))"
    r'|(?P<quoted>"(?:""|[^"])*")'
    r'|(?P<word>[A-Za-z_][A-Za-z_0-9$]*)'
    r'|(?P<punct>[.(),;])', re.DOTALL)


def executed_records(trace):
    """Read PostgreSQL duration-log executions, excluding parse/bind/DETAIL messages."""
    current = []
    backend = None
    for line in trace.splitlines():
        header = HEADER.match(line)
        if header:
            if current:
                yield backend, '\n'.join(current)
            match = EXECUTION.search(line)
            current = [match[1]] if match else []
            backend = header['pid']
        elif current and line.startswith('\t'):
            current.append(line[1:])
    if current:
        yield backend, '\n'.join(current)


def executed_statements(trace):
    for _, statement in executed_records(trace):
        yield statement


def query_tokens(statement):
    # This is deliberately a recognizer for the pinned profiles, not a general
    # PostgreSQL parser. Strings/comments never provide table or function evidence.
    tokens = []
    for match in TOKEN.finditer(statement):
        kind, value = match.lastgroup, match[0]
        if kind == 'quoted':
            tokens.append(('identifier', value[1:-1].replace('""', '"')))
        elif kind == 'word':
            tokens.append(('word', value.lower()))
        elif kind == 'punct':
            tokens.append(('punct', value))
    return tokens


def relations(tokens):
    result = set()
    depth = 0
    from_depths = set()
    expecting_relation = False
    for index, token in enumerate(tokens):
        if token == ('punct', '('):
            depth += 1
            expecting_relation = False
        elif token == ('punct', ')'):
            from_depths.discard(depth)
            depth -= 1
            expecting_relation = False
        elif token == ('word', 'from'):
            from_depths.add(depth)
            expecting_relation = True
        elif token == ('word', 'join') or (token == ('punct', ',') and depth in from_depths):
            expecting_relation = True
        elif token[0] == 'word' and token[1] in {'where', 'group', 'order', 'having', 'limit', 'offset', 'union', 'except', 'intersect', 'fetch', 'for'}:
            from_depths.discard(depth)
            expecting_relation = False
        elif expecting_relation and token not in {('word', 'only'), ('word', 'lateral')}:
            expecting_relation = False
            if token[0] not in {'word', 'identifier'}:
                raise ValueError('Unrecognized source relation syntax')
            name = (token[1],)
            while index + 2 < len(tokens) and tokens[index + 1] == ('punct', '.'):
                name += (tokens[index + 2][1],)
                index += 2
            result.add(name)
    return result


def validate_honua_planner_profile(trace, profile):
    """Require executed, transaction-local tuning followed by the matching source read.

    This recognizes the pinned Honua batch shapes, not arbitrary PostgreSQL SQL.
    Backend IDs keep concurrent health checks from breaking batch attribution.
    """
    if profile not in HONUA_PROFILES:
        raise ValueError(f'Unknown Honua planner profile: {profile}')
    flags = HONUA_PROFILES[profile]
    expected_settings = {
        'count': {name for key, name in (
            ('Database__DisableJitForSourceSpatialCounts', 'jit'),
            ('Database__PreferSerialSourceSpatialCounts', 'max_parallel_workers_per_gather'),
        ) if key in flags},
        'feature': ({'max_parallel_workers_per_gather'}
                    if 'Database__PreferSerialBoundedSpatialReads' in flags else set()),
    }
    expected = {kind for kind, settings in expected_settings.items() if settings}
    call = (r"(?:pg_catalog\.)?set_config\(\s*'(jit|max_parallel_workers_per_gather)'"
            r"\s*,\s*'(off|0)'\s*,\s*true\s*\)")
    setting_statement = re.compile(rf"SELECT\s+{call}(?:\s*,\s*{call})*\s*;?", re.IGNORECASE)
    setting_call = re.compile(call, re.IGNORECASE)
    pending = {}
    observed = Counter()
    for backend, statement in executed_records(trace):
        statement = statement.strip()
        if setting_statement.fullmatch(statement):
            pairs = [(name.lower(), value.lower()) for name, value in setting_call.findall(statement)]
            settings = {name for name, _ in pairs}
            valid = all((name, value) in {('jit', 'off'), ('max_parallel_workers_per_gather', '0')}
                        for name, value in pairs)
            if (not valid or len(settings) != len(pairs) or backend in pending or
                    settings not in expected_settings.values()):
                raise ValueError('Unexpected or unpaired Honua planner setting')
            pending[backend] = settings
            continue
        if re.match(r"SELECT\s+(?:\w+\.)?set_config\(\s*'(?:jit|max_parallel_workers_per_gather)'|"
                    r"SET\s+(?:(?:LOCAL|SESSION)\s+)?(?:jit|max_parallel_workers_per_gather)\b",
                    statement, re.IGNORECASE):
            raise ValueError('Unrecognized or non-local Honua planner setting')
        if backend not in pending:
            continue
        settings = pending.pop(backend)
        tokens = query_tokens(statement)
        functions = {token[1] for index, token in enumerate(tokens[:-1])
                     if token[0] in {'word', 'identifier'} and tokens[index + 1] == ('punct', '(')}
        kind = 'count' if 'count' in functions else 'feature'
        scoped = tokens[:2] == [('word', 'select'), ('word', 'all')]
        source = relations(tokens) == {('public', 'bench_points')}
        spatial = 'st_makeenvelope' in functions
        projection = kind == 'count' or bool(functions & {'st_asbinary', 'st_asewkb'})
        identity = True
        if kind == 'count' and 'max_parallel_workers_per_gather' in settings:
            tag = 'serial-jit-off-source-count' if 'jit' in settings else 'serial-source-count'
            # Fixed server-generated policy identities separate prepared counts.
            # The marker alone never proves a setting, source relation or predicate.
            identity = statement.startswith(f'SELECT ALL /* honua:{tag} */ COUNT(*)')
        if not (scoped and source and spatial and projection and identity and settings == expected_settings[kind]):
            raise ValueError(f'Planner {kind} setting did not precede its scoped spatial source query')
        observed[kind] += 1
    if pending or set(observed) != expected:
        raise ValueError('Missing executed Honua planner-profile evidence')
    return {'profile': profile, 'scoped_count_queries': observed['count'],
            'scoped_feature_queries': observed['feature']}


def validate_source_trace(trace, honua_profile=None):
    source = ('public', 'bench_points')
    geometry_functions = {'st_asbinary', 'st_asewkb', 'st_asgeojson', 'st_astext', 'st_asewkt'}
    feature_queries = source_counts = 0
    observed = set()
    for statement in executed_statements(trace):
        tokens = query_tokens(statement)
        if not tokens or tokens[0] != ('word', 'select'):
            continue
        tables = relations(tokens)
        if any(table[-1] == 'features' or (table[-1] == 'bench_points' and table != source) for table in tables):
            raise ValueError(f'Unexpected feature storage in SQL trace: {sorted(tables)}')
        functions = {token[1] for index, token in enumerate(tokens[:-1])
                     if token[0] in {'word', 'identifier'} and tokens[index + 1] == ('punct', '(')}
        if functions & geometry_functions:
            if tables != {source}:
                raise ValueError(f'Feature projection did not read only public.bench_points: {sorted(tables)}')
            feature_queries += 1
            observed.update(tables)
        if 'count' in functions and tables == {source}:
            source_counts += 1
    if not feature_queries or not source_counts:
        raise ValueError('SQL trace requires executed source feature projections and source counts')
    result = {'feature_queries': feature_queries, 'source_count_queries': source_counts,
              'feature_relations': sorted('.'.join(table) for table in observed),
              'scope': 'Executed geometry-encoding SELECT statements in the pinned source-backed profiles'}
    if honua_profile is not None:
        result['planner_profile'] = validate_honua_planner_profile(trace, honua_profile)
    return result
