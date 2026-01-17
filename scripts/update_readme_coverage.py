import subprocess
import xml.etree.ElementTree as ET
import sys
import re

def get_coverage_data(coverage_xml_path='coverage.xml'):
    tree = ET.parse(coverage_xml_path)
    root = tree.getroot()

    total_line_rate = float(root.get('line-rate', 0)) * 100
    total_branch_rate = float(root.get('branch-rate', 0)) * 100

    packages = []
    for package in root.findall('.//package'):
        package_name = package.get('name', '')
        package_line_rate = float(package.get('line-rate', 0)) * 100
        package_branch_rate = float(package.get('branch-rate', 0)) * 100

        if package_name:
            packages.append({
                'name': package_name,
                'line_rate': package_line_rate,
                'branch_rate': package_branch_rate
            })

    return total_line_rate, total_branch_rate, packages

def get_coverage_badge_color(coverage: float) -> str:
    if coverage >= 80:
        return 'brightgreen'
    elif coverage >= 60:
        return 'green'
    elif coverage >= 40:
        return 'yellow'
    elif coverage >= 20:
        return 'orange'
    else:
        return 'red'

def generate_coverage_badge(total_line_rate: float) -> str:
    color = get_coverage_badge_color(total_line_rate)
    return f"![Coverage](https://img.shields.io/badge/coverage-{total_line_rate:.1f}%25-{color}.svg)"

def generate_coverage_table(total_line_rate: float, total_branch_rate: float, packages: list) -> str:
    markdown = "## Tests\n\n"
    markdown += f"**Overall Coverage:** {total_line_rate:.1f}% (Lines) | {total_branch_rate:.1f}% (Branches)\n\n"
    markdown += "### Coverage by Module\n\n"
    markdown += "| Module | Lines | Branches |\n"
    markdown += "|--------|-------|----------|\n"

    for package in sorted(packages, key=lambda x: x['name']):
        module_name = package['name'].replace('api/', '').replace('/', '.') or 'api'
        markdown += f"| `{module_name}` | {package['line_rate']:.1f}% | {package['branch_rate']:.1f}% |\n"

    return markdown

def normalize_content(content: str) -> str:
    """Normalize content for comparison - ensure it ends with exactly one newline."""
    return content.rstrip() + '\n'

def update_readme(readme_path='README.md', coverage_xml_path='coverage.xml'):
    with open(readme_path, 'r') as f:
        original_content = f.read()

    total_line_rate, total_branch_rate, packages = get_coverage_data(coverage_xml_path)
    coverage_badge = generate_coverage_badge(total_line_rate)
    coverage_table = generate_coverage_table(total_line_rate, total_branch_rate, packages)

    new_content = original_content

    coverage_badge_pattern = r'!\[Coverage\][^\n]*'
    if re.search(coverage_badge_pattern, new_content):
        new_content = re.sub(coverage_badge_pattern, coverage_badge, new_content)
    else:
        lines = new_content.split('\n')
        badge_line_idx = None

        for i, line in enumerate(lines):
            if line.startswith('!['):
                badge_line_idx = i
                break

        if badge_line_idx is not None:
            lines.insert(badge_line_idx, coverage_badge)
            new_content = '\n'.join(lines)
        else:
            title_match = re.search(r'^(# .+\n\n)', new_content, re.MULTILINE)
            if title_match:
                insert_pos = title_match.end()
                new_content = new_content[:insert_pos] + coverage_badge + '\n' + new_content[insert_pos:]

    if re.search(r'^## Tests\b', new_content, re.MULTILINE):
        pattern = r'(^## Tests\b.*?)(?=^## |\Z)'
        replacement = coverage_table.rstrip() + '\n'
        new_content = re.sub(pattern, replacement, new_content, flags=re.MULTILINE | re.DOTALL)
    else:
        content = new_content.rstrip()
        new_content = content + '\n\n' + coverage_table.rstrip() + '\n'

    new_content = normalize_content(new_content)
    original_normalized = normalize_content(original_content)

    if new_content != original_normalized:
        with open(readme_path, 'w') as f:
            f.write(new_content)
        subprocess.run(['git', 'add', readme_path], check=False)

if __name__ == '__main__':
    readme_path = sys.argv[1] if len(sys.argv) > 1 else 'README.md'
    coverage_xml = sys.argv[2] if len(sys.argv) > 2 else 'coverage.xml'
    update_readme(readme_path, coverage_xml)
