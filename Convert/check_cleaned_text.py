import json
import re
from pathlib import Path
from collections import defaultdict
from tqdm import tqdm


class TextQualityChecker:
    
    def __init__(self):
        # Patterns indicating uncleaned text
        self.encoding_issues = [
            r'´\s*[eéèêaàâoóòôiíìîuùûEÉÈAÀOÓÒ]',  # ´ e, ´e
            r'`\s*[eéèêaàâoóòôiíìîuùûEÉÈAÀOÓÒ]',  # ` e, `e
            r'\^\s*[eéèêaàâoóòôiíìîuùûEÉÈAÀOÓÒ]', # ^ e, ^e
            r'¨\s*[eéèêaàâoóòôiíìîuùûEÉÈAÀOÓÒ]',  # ¨ e
            r'\xa0',  # Non-breaking space
            r'\u200b', # Zero-width space
            r'\ufeff', # BOM
            r' {3,}',  # 3+ consecutive spaces
            r'\n{4,}', # 4+ consecutive newlines
        ]
        
        # Common words that should have accents (only check lowercase unaccented versions)
        # Ignore ALL CAPS versions (SYSTEME, MODELE) - those are intentional
        self.should_have_accents = {
            r'\breseau(x?)\b(?=[a-z])': 'réseau',  # Only lowercase
            r'\bmodele(s?)\b(?=[a-z])': 'modèle',
            r'\bsysteme(s?)\b(?=[a-z])': 'système',
            r'\betudiant(s?|e|es)\b(?=[a-z])': 'étudiant',
            r'\belectronique(s?)\b(?=[a-z])': 'électronique',
            r'\btelecommunication(s?)\b(?=[a-z])': 'télécommunication',
            # Skip 'informatique' - always correct
            # Skip ALL CAPS words - intentional formatting
        }
    
    def check_text(self, text: str) -> dict:
        """Check single text for issues"""
        if not text or not isinstance(text, str):
            return {'clean': True, 'issues': []}
        
        issues = []
        
        # Check encoding patterns
        for pattern in self.encoding_issues:
            matches = re.findall(pattern, text)
            if matches:
                issues.append(f"Encoding issue: {pattern[:20]}... found {len(matches)} times")
        
        # Check missing accents
        text_lower = text.lower()
        for pattern, correct in self.should_have_accents.items():
            if re.search(pattern, text_lower):
                issues.append(f"Missing accent: found pattern matching '{correct}'")
        
        return {
            'clean': len(issues) == 0,
            'issues': issues,
            'text_sample': text[:200] if issues else None
        }
    
    def check_json_recursive(self, obj, path="root") -> list:
        """Recursively check all text in JSON"""
        all_issues = []
        
        if isinstance(obj, str):
            result = self.check_text(obj)
            if not result['clean']:
                all_issues.append({
                    'path': path,
                    'issues': result['issues'],
                    'sample': result['text_sample']
                })
        
        elif isinstance(obj, dict):
            for key, value in obj.items():
                all_issues.extend(
                    self.check_json_recursive(value, f"{path}.{key}")
                )
        
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                all_issues.extend(
                    self.check_json_recursive(item, f"{path}[{i}]")
                )
        
        return all_issues
    
    def check_file(self, json_path: Path) -> dict:
        """Check single JSON file"""
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            issues = self.check_json_recursive(data)
            
            return {
                'file': json_path.name,
                'clean': len(issues) == 0,
                'issue_count': len(issues),
                'issues': issues[:5]  
            }
            
        except Exception as e:
            return {
                'file': json_path.name,
                'clean': False,
                'error': str(e)[:100]
            }
    
    def check_directory(self, dir_path: Path, sample_size: int = None):
        """Check all JSON files in directory"""
        print(" Text Quality Check")
        print("=" * 80)
        
        json_files = list(dir_path.rglob("*.json"))
        json_files = [f for f in json_files 
                     if f.name not in ['conversion_report.json', 
                                      'missing_conversions.json',
                                      'training_data_pages.json']]
        
        if sample_size:
            import random
            json_files = random.sample(json_files, min(sample_size, len(json_files)))
        
        print(f"Checking: {len(json_files)} files\n")
        
        clean_count = 0
        dirty_count = 0
        dirty_files = []
        issue_types = defaultdict(int)
        
        for json_file in tqdm(json_files, desc="Checking"):
            result = self.check_file(json_file)
            
            if result['clean']:
                clean_count += 1
            else:
                dirty_count += 1
                dirty_files.append(result)
                
                # Count issue types
                for issue_obj in result.get('issues', []):
                    for issue_msg in issue_obj.get('issues', []):
                        issue_type = issue_msg.split(':')[0]
                        issue_types[issue_type] += 1
        
        # Print summary
        print(f"\n{'='*80}")
        print(f" Clean: {clean_count} files")
        print(f" Dirty: {dirty_count} files")
    
        if issue_types:
            print(f"\nIssue breakdown:")
            for issue_type, count in sorted(issue_types.items(), key=lambda x: -x[1]):
                print(f"  - {issue_type}: {count} occurrences")
        
        if dirty_files:
            print(f"\n Sample dirty files (showing first 5):")
            for result in dirty_files[:5]:
                print(f"\n  File: {result['file']}")
                print(f"  Issues: {result['issue_count']}")
                if 'issues' in result:
                    for issue_obj in result['issues'][:2]:
                        print(f"    Path: {issue_obj['path']}")
                        for issue_msg in issue_obj['issues'][:2]:
                            print(f"      - {issue_msg}")
                        if issue_obj.get('sample'):
                            print(f"      Sample: {issue_obj['sample'][:100]}...")
        
        print("="*80)
        
        return {
            'total': len(json_files),
            'clean': clean_count,
            'dirty': dirty_count,
            'dirty_files': dirty_files
        }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--dir', default='../Data_json')
    parser.add_argument('--sample', type=int, help='Check only N random files')
    parser.add_argument('--file', help='Check single file')
    args = parser.parse_args()
    
    checker = TextQualityChecker()
    
    if args.file:
        result = checker.check_file(Path(args.file))
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        checker.check_directory(Path(args.dir), sample_size=args.sample)


if __name__ == "__main__":
    main()
