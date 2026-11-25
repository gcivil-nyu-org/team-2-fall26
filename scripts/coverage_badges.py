"""Generate badges from measured reports; publishing is handled by CI."""
import argparse
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


def combined_coverage(backend, frontend):
    """Weight executed lines by their counts, not by averaging percentages."""
    covered = backend['covered_lines'] + frontend['covered']
    total = backend['num_statements'] + frontend['total']
    if total <= 0 or not 0 <= covered <= total:
        raise ValueError('Invalid coverage line counts')
    return covered / total * 100


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--branch', choices=['main', 'develop'], required=True)
    args = parser.parse_args()
    backend = json.loads(Path('coverage/backend/coverage.json').read_text())['totals']
    frontend = json.loads(Path('frontend/coverage/coverage-summary.json').read_text())['total']['lines']
    percentage = combined_coverage(backend, frontend)
    output = Path('coverage/badges')
    output.mkdir(parents=True, exist_ok=True)
    (output / f'{args.branch}.svg').write_text(
        badge(f'{args.branch} coverage', percentage), encoding='utf-8',
    )
    print(f'{args.branch} combined line coverage: {percentage:.2f}%')


if __name__ == '__main__':
    main()
