import sys
import re
from pathlib import Path

def slugify(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '_', text)
    return text.strip('_')

def refactor_skill(skill_dir):
    skill_path = Path(skill_dir) / 'SKILL.md'
    if not skill_path.exists():
        return
        
    with open(skill_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Check if already refactored
    if 'Dynamic Resources' in content or 'resources/' in content and 'view_file' in content:
        print(f"Skipping {skill_dir} - already refactored")
        return
        
    # Check if explicitly opted out
    if 'keep_inline: true' in content:
        print(f"Skipping {skill_dir} - keep_inline flag set")
        return
        
    # If the file is relatively short, don't refactor
    if len(content.splitlines()) < 80:
        print(f"Skipping {skill_dir} - too short ({len(content.splitlines())} lines)")
        return
        
    print(f"Refactoring {skill_dir}...")
    
    # Simple markdown parser
    # We want to extract YAML frontmatter, then H1 and the introduction
    # Then split on H2 (##)
    lines = content.splitlines()
    
    yaml_lines = []
    intro_lines = []
    sections = {}
    
    in_yaml = False
    yaml_done = False
    
    current_section = None
    current_lines = []
    
    for line in lines:
        if not yaml_done and line.strip() == '---':
            if not in_yaml:
                in_yaml = True
                yaml_lines.append(line)
            else:
                in_yaml = False
                yaml_done = True
                yaml_lines.append(line)
            continue
            
        if in_yaml:
            yaml_lines.append(line)
            continue
            
        if line.startswith('## '):
            if current_section:
                sections[current_section] = current_lines
            elif len(current_lines) > 0:
                intro_lines = current_lines
                
            current_section = line[3:].strip()
            current_lines = [line]
        else:
            if current_section is None:
                current_lines.append(line)
            else:
                current_lines.append(line)
                
    if current_section:
        sections[current_section] = current_lines
    elif current_section is None and len(current_lines) > 0:
        intro_lines = current_lines
        
    # Create resources dir
    resources_dir = Path(skill_dir) / 'resources'
    resources_dir.mkdir(exist_ok=True)
    
    # Write sections to resources
    pointers = []
    for title, s_lines in sections.items():
        slug = slugify(title)
        res_file = f"{slug}.md"
        res_path = resources_dir / res_file
        
        with open(res_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(s_lines))
            
        pointers.append(f"- **[resources/{res_file}](file:///{res_path.absolute().as_posix()})**: Read this to understand {title}.")
        
    # Rewrite SKILL.md
    with open(skill_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(yaml_lines))
        f.write("\n")
        f.write("\n".join(intro_lines))
        f.write("\n\n## Dynamic Resources (Progressive Disclosure)\n\n")
        f.write("This skill is large. To save context, its detailed instructions are split into separate files in the `resources/` directory.\n")
        f.write("**You MUST use your `view_file` tool to read the relevant file when you reach that stage of the process.**\n\n")
        f.write("\n".join(pointers))
        f.write("\n")

def main():
    skills_dir = Path("D:/GIT/graph-orchestrator-smolagents/skills")
    if len(sys.argv) > 1:
        skills_dir = Path(sys.argv[1])
        
    for item in skills_dir.iterdir():
        if item.is_dir():
            refactor_skill(item)

if __name__ == '__main__':
    main()
