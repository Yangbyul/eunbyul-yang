#!/usr/bin/env python3
"""
parse_cv.py — CV.docx → JSON data files for the academic website.

Usage:
    python scripts/parse_cv.py cv/YANG_CV.docx

Outputs:
    data/publications.json
    data/stats.json
    (presentations.json is managed separately)
"""
import json, re, sys, os
from docx import Document

def extract_publications(doc):
    """Parse publications from the CV docx."""
    pubs = []
    current_category = None
    categories = {
        'PUBLICATIONS (SSCI & SCOPUS)': 'SSCI & SCOPUS',
        'PUBLICATIONS (SSCI)': 'SSCI',
        'PUBLICATIONS (KCI)': 'KCI',
        'PUBLICATIONS (OTHERS)': 'OTHERS',
        'CONFERENCE PROCEEDINGS': 'PROCEEDINGS',
        'BOOK CHAPTER': 'BOOK CHAPTER',
    }

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        # Check if this is a category header
        matched_cat = None
        for key, val in categories.items():
            if text == key:
                matched_cat = val
                break
        if matched_cat:
            current_category = matched_cat
            continue

        # Stop at presentations section
        if text.startswith('PRESENTATIONS') or text.startswith('RELEVANT PRESENTATION'):
            break

        # Skip non-publication lines
        if current_category is None:
            continue
        if text.startswith(('PUBLICATIONS AND', 'LAST UPDATED', 'EDUCATION', 'PROFESSIONAL',
                           '38 Peer', '36 Peer', '32 Peer', '31 Peer')):
            continue
        if len(text) < 30:
            continue

        # Extract year
        year_match = re.search(r'\((\d{4})', text)
        year = int(year_match.group(1)) if year_match else 0

        # Determine index type tag
        index_tag = current_category
        tag_match = re.search(r'\[(SSCI|SCIE|SCOPUS|KCI)\]', text)
        if tag_match:
            index_tag = tag_match.group(1)

        # Check if first author (Yang, E. or 양은별 at the start)
        is_first = text.startswith(('Yang, E.', '양은별'))

        pubs.append({
            'citation': text,
            'year': year,
            'category': current_category,
            'index': index_tag,
            'first_author': is_first,
        })

    return pubs


def compute_stats(pubs, presentations_path=None):
    """Compute summary statistics."""
    stats = {
        'total_publications': len(pubs),
        'ssci': len([p for p in pubs if p['index'] == 'SSCI']),
        'scie': len([p for p in pubs if p['index'] == 'SCIE']),
        'scopus': len([p for p in pubs if p['index'] == 'SCOPUS']),
        'kci': len([p for p in pubs if p['category'] == 'KCI']),
        'others': len([p for p in pubs if p['category'] == 'OTHERS']),
        'proceedings': len([p for p in pubs if p['category'] == 'PROCEEDINGS']),
        'book_chapter': len([p for p in pubs if p['category'] == 'BOOK CHAPTER']),
        'ssci_scopus_total': 0,
        'total_presentations': 0,
        'intl_presentations': 0,
        'domestic_presentations': 0,
    }
    stats['ssci_scopus_total'] = stats['ssci'] + stats['scie'] + stats['scopus']

    # Load presentations count if available
    if presentations_path and os.path.exists(presentations_path):
        with open(presentations_path, 'r', encoding='utf-8') as f:
            pres = json.load(f)
        stats['total_presentations'] = len(pres)
        stats['intl_presentations'] = len([p for p in pres if p.get('scope') == 'intl'])
        stats['domestic_presentations'] = len([p for p in pres if p.get('scope') == 'domestic'])

    return stats


def check_papers_sync(pubs, papers_path):
    """Compare CV publication count with papers.json and warn if out of sync."""
    if not os.path.exists(papers_path):
        print("  WARNING: papers.json not found. Copy from research-dashboard first.")
        return

    with open(papers_path, 'r', encoding='utf-8') as f:
        existing = json.load(f)

    cv_count = len(pubs)
    db_count = len(existing)

    if cv_count > db_count:
        diff = cv_count - db_count
        print(f"  WARNING: CV has {cv_count} publications but papers.json has {db_count}.")
        print(f"  → {diff} new paper(s) need to be added to data/papers.json manually.")
        print(f"  → Add entries with keywords, tech, method, target, dv, line fields.")
    elif cv_count == db_count:
        print(f"  papers.json: {db_count} entries (in sync with CV)")
    else:
        print(f"  NOTE: papers.json ({db_count}) has more entries than CV ({cv_count}).")


def main():
    if len(sys.argv) < 2:
        print("Usage: python parse_cv.py <path_to_cv.docx>")
        sys.exit(1)

    cv_path = sys.argv[1]
    doc = Document(cv_path)

    # Determine output directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(script_dir)
    data_dir = os.path.join(repo_root, 'data')
    os.makedirs(data_dir, exist_ok=True)

    # Parse publications
    pubs = extract_publications(doc)
    pubs_path = os.path.join(data_dir, 'publications.json')
    with open(pubs_path, 'w', encoding='utf-8') as f:
        json.dump(pubs, f, ensure_ascii=False, indent=2)
    print(f"  publications.json: {len(pubs)} entries")

    # Check papers.json sync
    papers_path = os.path.join(data_dir, 'papers.json')
    check_papers_sync(pubs, papers_path)

    # Compute stats
    pres_path = os.path.join(repo_root, 'presentations.json')
    stats = compute_stats(pubs, pres_path)
    stats_path = os.path.join(data_dir, 'stats.json')
    with open(stats_path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"  stats.json: {json.dumps(stats)}")

    print("\nDone!")


if __name__ == '__main__':
    main()
