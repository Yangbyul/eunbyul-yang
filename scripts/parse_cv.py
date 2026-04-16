#!/usr/bin/env python3
"""
parse_cv.py — CV.docx → JSON data files for the academic website.

Usage:
    python scripts/parse_cv.py cv/YANG_CV.docx

Outputs:
    data/publications.json  — citation list from CV
    data/papers.json        — research dashboard data (auto-adds new papers)
    data/stats.json         — summary statistics
"""
import json, re, sys, os
from docx import Document


def extract_publications(doc):
    """Parse publications from the CV docx with bold/italic info from runs."""
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

        matched_cat = None
        for key, val in categories.items():
            if text == key:
                matched_cat = val
                break
        if matched_cat:
            current_category = matched_cat
            continue

        if text.startswith('PRESENTATIONS') or text.startswith('RELEVANT PRESENTATION'):
            break

        if current_category is None:
            continue
        if re.match(r'^\d+ Peer reviewed', text):
            continue
        if len(text) < 30:
            continue

        # Extract year
        year_match = re.search(r'\((\d{4})', text)
        year = int(year_match.group(1)) if year_match else 0

        # Determine index type
        index_tag = current_category
        tag_match = re.search(r'\[(SSCI|SCIE|SCOPUS|KCI|국내 기타|국외 기타|기타)\]', text)
        if tag_match:
            index_tag = tag_match.group(1)

        # Check if first author
        is_first = text.startswith(('Yang, E.', '양은별'))

        # Detect language
        has_korean = any('\uac00' <= c <= '\ud7a3' for c in text[:20])
        lang = 'ko' if has_korean else 'en'

        # Extract title: between "year). " and the journal (italic text)
        title = ''
        # Try to get italic text from runs (= journal name), then title is between year and journal
        italic_texts = []
        for run in para.runs:
            if run.italic and run.text.strip():
                italic_texts.append(run.text.strip())

        if italic_texts:
            journal_start = italic_texts[0]
            # Title is between "). " and the journal
            pattern = re.escape(')') + r'[.\s]+(.+?)' + re.escape(journal_start[:15])
            m = re.search(pattern, text)
            if m:
                title = m.group(1).strip().rstrip('.')

        if not title:
            # Fallback: grab text between year and period+space+Capital
            m = re.search(r'\d{4}\)[.\s]+(.+?)[.]\s+[A-Z가-힣]', text)
            if m:
                title = m.group(1).strip().rstrip('.')

        if not title:
            # Last fallback: take a chunk
            m = re.search(r'\d{4}\)[.\s]+(.{20,120})', text)
            if m:
                title = m.group(1).strip().rstrip('.')

        # Extract journal name from italic runs
        journal_name = ' '.join(italic_texts).strip(' .,') if italic_texts else ''

        # Extract coauthors
        author_part = text.split('(')[0] if '(' in text else ''
        coauthors = []
        if author_part:
            authors = re.split(r'[,&]', author_part)
            for a in authors:
                a = a.strip().strip('.')
                if a and a not in ('Yang, E', 'Yang, E.', '양은별', ''):
                    coauthors.append(a)

        # Determine role
        if not coauthors:
            role = '단독'
        elif is_first:
            role = '1저자'
        else:
            role = '공저자'

        # Journal with index tag for dashboard
        if index_tag in ('SSCI', 'SCIE', 'SCOPUS'):
            journal_display = f"{journal_name} ({index_tag})" if journal_name else f"({index_tag})"
        elif current_category == 'KCI':
            journal_display = f"{journal_name} (KCI)" if journal_name else "(KCI)"
        elif index_tag in ('국내 기타', '국외 기타', '기타'):
            journal_display = f"{journal_name} ({index_tag})" if journal_name else f"({index_tag})"
        elif current_category == 'PROCEEDINGS':
            journal_display = journal_name or "(Conference proceeding)"
        elif current_category == 'BOOK CHAPTER':
            journal_display = journal_name or "(Book chapter)"
        else:
            journal_display = journal_name

        pub_type = 'journal'
        if current_category == 'PROCEEDINGS':
            pub_type = 'conference'
        elif current_category == 'BOOK CHAPTER':
            pub_type = 'book_chapter'

        pubs.append({
            'citation': text,
            'year': year,
            'category': current_category,
            'index': index_tag,
            'first_author': is_first,
            'title': title,
            'journal_display': journal_display,
            'lang': lang,
            'type': pub_type,
            'coauthors': coauthors,
            'role': role,
        })

    return pubs


def sync_papers_json(pubs, papers_path):
    """Auto-add new papers from CV to papers.json. New entries have empty tags."""
    existing = []
    if os.path.exists(papers_path):
        with open(papers_path, 'r', encoding='utf-8') as f:
            existing = json.load(f)

    # Index existing papers by year+title_fragment for matching
    existing_index = set()
    for p in existing:
        # Use first 15 chars of title (lowered, stripped) + year as key
        key = f"{p['year']}:{re.sub(r'[^a-z가-힣0-9]', '', p['title'].lower())[:12]}"
        existing_index.add(key)

    # Find max id per year
    max_id = {}
    for p in existing:
        y = p['year']
        suffix = p['id'].split('-')[-1] if '-' in p['id'] else '0'
        num = int(suffix) if suffix.isdigit() else 0
        max_id[y] = max(max_id.get(y, 0), num)

    added = 0
    for pub in pubs:
        title = pub['title']
        if not title or len(title) < 10:
            continue

        year = pub['year']
        key = f"{year}:{re.sub(r'[^a-z가-힣0-9]', '', title.lower())[:12]}"

        if key in existing_index:
            continue

        # New paper — create entry with empty tags
        max_id[year] = max_id.get(year, 0) + 1
        new_id = f"{year}-{max_id[year]}"

        new_entry = {
            'year': year,
            'id': new_id,
            'title': title,
            'journal': pub['journal_display'],
            'lang': pub['lang'],
            'type': pub['type'],
            'coauthors': pub['coauthors'],
            'role': pub['role'],
            'keywords': [],
            'tech': [],
            'method': [],
            'target': [],
            'dv': [],
            'line': '',
        }
        existing.append(new_entry)
        existing_index.add(key)
        added += 1
        print(f"    + NEW: [{year}] {title[:60]}...")

    # Sort by year, then id
    existing.sort(key=lambda p: (p['year'], p['id']))

    with open(papers_path, 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    return added


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

    if presentations_path and os.path.exists(presentations_path):
        with open(presentations_path, 'r', encoding='utf-8') as f:
            pres = json.load(f)
        stats['total_presentations'] = len(pres)
        stats['intl_presentations'] = len([p for p in pres if p.get('scope') == 'intl'])
        stats['domestic_presentations'] = len([p for p in pres if p.get('scope') == 'domestic'])

    return stats


def main():
    if len(sys.argv) < 2:
        print("Usage: python parse_cv.py <path_to_cv.docx>")
        sys.exit(1)

    cv_path = sys.argv[1]
    doc = Document(cv_path)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(script_dir)
    data_dir = os.path.join(repo_root, 'data')
    os.makedirs(data_dir, exist_ok=True)

    # 1. Parse publications from CV
    pubs = extract_publications(doc)
    pubs_path = os.path.join(data_dir, 'publications.json')
    with open(pubs_path, 'w', encoding='utf-8') as f:
        json.dump(pubs, f, ensure_ascii=False, indent=2)
    print(f"  publications.json: {len(pubs)} entries")

    # 2. Sync papers.json (auto-add new papers with empty tags)
    papers_path = os.path.join(data_dir, 'papers.json')
    added = sync_papers_json(pubs, papers_path)
    if added:
        print(f"  papers.json: {added} new paper(s) auto-added (tags empty, fill later)")
    else:
        print(f"  papers.json: in sync, no new papers")

    # 3. Compute stats
    pres_path = os.path.join(repo_root, 'presentations.json')
    stats = compute_stats(pubs, pres_path)
    stats_path = os.path.join(data_dir, 'stats.json')
    with open(stats_path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"  stats.json: pubs={stats['total_publications']}, SSCI={stats['ssci']}, SCOPUS={stats['scopus']}, KCI={stats['kci']}, pres={stats['total_presentations']}")

    print("\nDone!")


if __name__ == '__main__':
    main()
