import yaml
import os
import re
from collections import defaultdict

# Directory containing mob YAML files
mobs_dir = 'mobs'
skills_dir = 'skills'

# Get all q1-q10 files for difficulties inf, hell, blood
files = {}
for q in range(1, 11):
    for diff in ['inf', 'hell', 'blood']:
        fname = f"q{q}_{diff}.yml"
        path = os.path.join(mobs_dir, fname)
        if os.path.exists(path):
            files.setdefault(q, {})[diff] = path

# Files for non-Q maps (expowiska)
exp_files = {}
for fname in os.listdir(mobs_dir):
    if not fname.endswith('.yml') or fname.startswith('test'):
        continue
    if re.match(r'q\d+_', fname):
        continue
    rng = re.search(r'(\d+-\d+)', fname)
    rng_key = rng.group(1) if rng else 'other'
    exp_files.setdefault(rng_key, []).append(os.path.join(mobs_dir, fname))

# Rarity detection

def get_rarity(display):
    if display is None:
        return 'Unknown'
    if '&4<&skull>' in display or '&4 <&skull>' in display:
        return 'Boss'
    if '&5&l' in display:
        return 'Mini Boss'
    if '&e&l' in display:
        return 'Elite'
    if '&l' in display:
        return 'Normal'
    return 'Unknown'

rarity_order = ['Boss', 'Mini Boss', 'Elite', 'Normal', 'Unknown']

# regex helpers for cleaning display names
COLOR_CODE = re.compile(r'&[0-9a-fk-or]')
BRACKET_HP = re.compile(r'\[[^\]]*caster\.hp[^\]]*\]')
ANGLE = re.compile(r'<[^>]+>')

def clean_name(display: str) -> str:
    if not display:
        return ''
    name = COLOR_CODE.sub('', display)
    name = BRACKET_HP.sub('', name)
    name = ANGLE.sub('', name)
    name = ' '.join(name.split())
    return name.strip()

# Collect data
quests = defaultdict(lambda: defaultdict(list))
mob_skill_map = defaultdict(list)

# Load skills information
skill_defs = {}
for fname in os.listdir(skills_dir):
    if not fname.endswith('.yml'):
        continue
    path = os.path.join(skills_dir, fname)
    with open(path, 'r') as f:
        try:
            data = yaml.safe_load(f) or {}
        except Exception:
            # Fallback simple parser for non-standard YAML
            f.seek(0)
            data = {}
            current = None
            cooldown = None
            actions = []
            for line in f:
                if not line.strip() or line.lstrip().startswith('#'):
                    continue
                if not line.startswith(' '):
                    if current:
                        data[current] = {'Cooldown': cooldown, 'Skills': actions}
                    current = line.strip().rstrip(':')
                    cooldown = None
                    actions = []
                else:
                    l = line.strip()
                    if l.startswith('Cooldown:'):
                        try:
                            cooldown = int(l.split(':',1)[1].strip())
                        except ValueError:
                            cooldown = None
                    elif l.startswith('-'):
                        actions.append(l[1:].strip())
            if current:
                data[current] = {'Cooldown': cooldown, 'Skills': actions}
    for sname, sinfo in data.items():
        if not isinstance(sinfo, dict):
            continue
        cd = sinfo.get('Cooldown')
        lines = sinfo.get('Skills', [])
        if isinstance(lines, str):
            lines = [lines]
        skill_defs[sname] = {'cooldown': cd, 'actions': lines}

# Recursively compute damage of a skill, following references to other skills
def compute_damage(name, visited=None):
    if visited is None:
        visited = set()
    if name in visited:
        return None
    visited.add(name)
    info = skill_defs.get(name)
    if not info:
        return None
    dmg_pattern = re.compile(r'damage[^0-9{=]*[=\{][^0-9]*([0-9]+)')
    max_dmg = None
    for line in info.get('actions', []):
        for m in dmg_pattern.finditer(str(line)):
            val = int(m.group(1))
            if max_dmg is None or val > max_dmg:
                max_dmg = val
        for ref in re.findall(r'(?:onHit|onTick|skill|skills?|s)[=:]([A-Za-z0-9_#-]+)', str(line)):
            sub = ref.strip()
            sub_dmg = compute_damage(sub, visited)
            if sub_dmg is not None and (max_dmg is None or sub_dmg > max_dmg):
                max_dmg = sub_dmg
    return max_dmg

# Final mapping of skills to cooldown and damage
skill_info = {}
for sname, sinfo in skill_defs.items():
    skill_info[sname] = {
        'cooldown': sinfo.get('cooldown'),
        'damage': compute_damage(sname)
    }

for q, diffs in files.items():
    for diff, path in diffs.items():
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
        for mob_id, info in data.items():
            display = info.get('Display', '')
            rarity = get_rarity(display)
            clean = clean_name(display)
            mob_entry = {
                'name': clean,
                'type': info.get('Type', ''),
                'health': info.get('Health', ''),
                'damage': info.get('Damage', ''),
                'rarity': rarity
            }
            quests[q][diff].append(mob_entry)

            skills_field = info.get('Skills')
            if isinstance(skills_field, list):
                for line in skills_field:
                    for m in re.finditer(r's=([A-Za-z0-9_#-]+)', str(line)):
                        mob_skill_map[(q, diff, clean)].append(m.group(1))
        # Sort mobs by rarity order
        quests[q][diff].sort(key=lambda m: rarity_order.index(m['rarity']))

# Generate markdown
lines = []
lines.append('# Statystyki mobów dla Q1-Q10\n')
lines.append('Plik automatycznie wygenerowany z konfiguracji MythicMobs.\n')
for q in range(1, 11):
    lines.append(f'\n## Q{q}\n')
    for diff in ['inf', 'hell', 'blood']:
        mobs = quests.get(q, {}).get(diff)
        if not mobs:
            continue
        lines.append(f'\n### Poziom trudności: {diff}\n')
        lines.append('| Nazwa | Typ | HP | DMG | Rzadkość |')
        lines.append('|-------|-----|----|-----|----------|')
        for m in mobs:
            name = m['name'].replace('|', '\\|') if m['name'] else ''
            lines.append(f"| {name} | {m['type']} | {m['health']} | {m['damage']} | {m['rarity']} |")

# Write to file
with open('mob_stats.md', 'w') as f:
    f.write('\n'.join(lines))

# Generate markdown for mob skills
skills_lines = []
skills_lines.append('# Umiejętności mobów dla Q1-Q10\n')
skills_lines.append('Plik automatycznie wygenerowany z konfiguracji MythicMobs.\n')
for q in range(1, 11):
    skills_lines.append(f'\n## Q{q}\n')
    for diff in ['inf', 'hell', 'blood']:
        mobs = quests.get(q, {}).get(diff)
        if not mobs:
            continue
        skills_lines.append(f'\n### Poziom trudności: {diff}\n')
        skills_lines.append('| Mob | Skill | DMG | Cooldown |')
        skills_lines.append('|-----|-------|-----|----------|')
        for m in mobs:
            key = (q, diff, m['name'])
            mob_skills = mob_skill_map.get(key)
            if not mob_skills:
                skills_lines.append(f"| {m['name']} | - | - | - |")
                continue
            first = True
            for s in mob_skills:
                info = skill_info.get(s, {})
                dmg = info.get('damage', '')
                cd = info.get('cooldown', '')
                if first:
                    skills_lines.append(f"| {m['name']} | {s} | {dmg} | {cd} |")
                    first = False
                else:
                    skills_lines.append(f"|  | {s} | {dmg} | {cd} |")

with open('mob_skills.md', 'w') as f:
    f.write('\n'.join(skills_lines))


# Generate stats for expowiska (non-Q maps)
exp_data = defaultdict(list)
for rng, paths in exp_files.items():
    for path in paths:
        with open(path, 'r') as f:
            data = yaml.safe_load(f) or {}
        for mob_id, info in data.items():
            display = info.get('Display', '')
            rarity = get_rarity(display)
            clean = clean_name(display)
            entry = {
                'name': clean,
                'type': info.get('Type', ''),
                'health': info.get('Health', ''),
                'damage': info.get('Damage', ''),
                'rarity': rarity,
            }
            exp_data[rng].append(entry)
    exp_data[rng].sort(key=lambda m: rarity_order.index(m['rarity']))

def range_sort_key(rng):
    m = re.match(r'(\d+)', rng)
    return int(m.group(1)) if m else 0

exp_lines = []
exp_lines.append('# Statystyki mobów z expowisk\n')
exp_lines.append('Plik automatycznie wygenerowany z konfiguracji MythicMobs.\n')
for rng in sorted(exp_data.keys(), key=range_sort_key):
    exp_lines.append(f'\n## Poziom {rng}\n')
    exp_lines.append('| Nazwa | Typ | HP | DMG | Rzadkość |')
    exp_lines.append('|-------|-----|----|-----|----------|')
    for m in exp_data[rng]:
        name = m['name'].replace('|', '\\|') if m['name'] else ''
        exp_lines.append(f"| {name} | {m['type']} | {m['health']} | {m['damage']} | {m['rarity']} |")

with open('mob_stats_exp.md', 'w') as f:
    f.write('\n'.join(exp_lines))
