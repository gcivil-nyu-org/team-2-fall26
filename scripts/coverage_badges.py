"""Generate badges from measured reports; publishing is handled by CI."""
import json
from pathlib import Path


def badge(label, percentage):
    color = '#4c1' if percentage >= 85 else '#e05d44'
    value = f'{percentage:.2f}%'
    width = 190
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="20" '
        f'role="img" aria-label="{label}: {value}">'
        f'<title>{label}: {value}</title>'
        '<rect width="135" height="20" fill="#555"/>'
        f'<rect x="135" width="55" height="20" fill="{color}"/>'
        '<g fill="#fff" text-anchor="middle" font-family="Verdana,sans-serif" font-size="11">'
        f'<text x="67.5" y="14">{label}</text>'
        f'<text x="162.5" y="14">{value}</text></g></svg>\n'
    )


def main():
    backend = json.loads(Path('coverage/backend/coverage.json').read_text())['totals']['percent_covered']
    frontend = json.loads(Path('frontend/coverage/coverage-summary.json').read_text())['total']['lines']['pct']
    output = Path('coverage/badges')
    output.mkdir(parents=True, exist_ok=True)
    for name, value in [('backend', backend), ('frontend', frontend)]:
        (output / f'main-{name}.svg').write_text(badge(f'{name} coverage', value), encoding='utf-8')
        print(f'{name}: {value:.2f}%')


if __name__ == '__main__':
    main()
