import json
from pathlib import Path
from tqdm import tqdm

def check_json_valid(json_path: Path) -> tuple[bool, str]:
    """Check if JSON file is valid and complete"""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Too small = truncated
        if len(content) < 100:
            return False, "Too small (< 100 bytes)"
        
        # Try parse
        data = json.loads(content)
        
        # Check if has meaningful content
        if isinstance(data, dict):
            if not data or len(data) < 2:
                return False, "Empty or incomplete"
        
        return True, "OK"
        
    except json.JSONDecodeError as e:
        return False, f"JSON decode error: {str(e)[:50]}"
    except Exception as e:
        return False, f"Error: {str(e)[:50]}"


def main():
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--dir', default='../Data_json')
    parser.add_argument('--remove', action='store_true', help='Actually remove files')
    
    args = parser.parse_args()
    
    data_dir = Path(args.dir)
    
    print("Checking JSON files for corruption...")
    print(f"Directory: {data_dir}")
    
    json_files = list(data_dir.rglob("*.json"))
    json_files = [f for f in json_files 
                 if f.name not in ['conversion_report.json', 
                                  'missing_conversions.json']]
    
    print(f"Found: {len(json_files)} files\n")
    
    corrupted = []
    
    for json_file in tqdm(json_files, desc="Checking"):
        valid, reason = check_json_valid(json_file)
        if not valid:
            corrupted.append({
                'path': json_file,
                'relative': str(json_file.relative_to(data_dir)),
                'reason': reason
            })
    
    print(f"\n{'='*80}")
    print(f" Results:")
    print(f"   Valid: {len(json_files) - len(corrupted)}")
    print(f"   Corrupted: {len(corrupted)}")
    
    if corrupted:
        print(f"\n Corrupted files:")
        for item in corrupted:
            print(f"   - {item['relative']}")
            print(f"     Reason: {item['reason']}")
        
        if args.remove:
            print(f"\n Removing {len(corrupted)} corrupted files...")
            for item in corrupted:
                item['path'].unlink()
                print(f" Removed: {item['relative']}")
            print(" Done!")
        else:
            print(f"\n To remove these files, run with --remove flag")
    
    print("="*80)


if __name__ == "__main__":
    main()
