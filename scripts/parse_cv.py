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


TAG_FIELDS = ('keywords', 'tech', 'method', 'target', 'dv', 'line')


def _make_key(year, title):
    """Create a matching key from year + normalized title fragment."""
    return f"{year}:{re.sub(r'[^a-z가-힣0-9]', '', title.lower())[:12]}"


def _tag_count(paper):
    """Count how many tag fields are filled in."""
    total = 0
    for f in TAG_FIELDS:
        v = paper.get(f)
        if isinstance(v, list):
            total += len(v)
        elif v:
            total += 1
    return total


def _merge_tags(dst, src):
    """Copy non-empty tag values from src into dst (only if dst's field is empty)."""
    for f in TAG_FIELDS:
        sv = src.get(f)
        dv = dst.get(f)
        if isinstance(dv, list) and not dv and isinstance(sv, list) and sv:
            dst[f] = sv
        elif not dv and sv:
            dst[f] = sv


def sync_papers_json(pubs, papers_path):
    """Sync papers.json with publications from CV.

    - Adds new papers (with empty tags).
    - Removes papers that no longer exist in CV.
    - Deduplicates entries with matching keys (keeps richer tags).
    - Updates title/metadata from CV while preserving user-edited tags.
    """
    existing = []
    if os.path.exists(papers_path):
        with open(papers_path, 'r', encoding='utf-8') as f:
            existing = json.load(f)

    # --- Deduplicate existing papers by key, keeping the one with more tags ---
    by_key = {}
    for p in existing:
        key = _make_key(p['year'], p['title'])
        if key in by_key:
            prev = by_key[key]
            if _tag_count(p) > _tag_count(prev):
                _merge_tags(p, prev)
                by_key[key] = p
            else:
                _merge_tags(prev, p)
            print(f"    ~ DEDUP: [{p['year']}] keeping one entry for key {key}")
        else:
            by_key[key] = p

    # --- Match CV publications to existing papers ---
    result = []
    added = 0
    removed_keys = set(by_key.keys())  # track which existing entries are still valid

    # Find max id per year (for assigning ids to new papers)
    max_id = {}
    for p in by_key.values():
        y = p['year']
        suffix = p['id'].split('-')[-1] if '-' in p['id'] else '0'
        num = int(suffix) if suffix.isdigit() else 0
        max_id[y] = max(max_id.get(y, 0), num)

    for pub in pubs:
        title = pub['title']
        if not title or len(title) < 10:
            continue

        year = pub['year']
        key = _make_key(year, title)

        if key in by_key:
            # Existing paper — update metadata from CV, preserve tags
            entry = by_key[key]
            entry['title'] = title
            # Only update journal if CV extracted a real name (not just index tag)
            cv_journal = pub['journal_display']
            if not re.match(r'^\(.*\)$', cv_journal.strip()):
                entry['journal'] = cv_journal
            entry['lang'] = pub['lang']
            entry['type'] = pub['type']
            entry['coauthors'] = pub['coauthors']
            entry['role'] = pub['role']
            result.append(entry)
            removed_keys.discard(key)
        else:
            # New paper — create entry with empty tags
            max_id[year] = max_id.get(year, 0) + 1
            new_id = f"{year}-{max_id[year]}"
            result.append({
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
            })
            added += 1
            print(f"    + NEW: [{year}] {title[:60]}...")

    # Report removed papers
    for key in removed_keys:
        p = by_key[key]
        print(f"    - REMOVED: [{p['year']}] {p['title'][:60]}...")

    # Sort by year, then id
    result.sort(key=lambda p: (p['year'], p['id']))

    with open(papers_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

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

    # 2. Sync papers.json (add new, remove stale, deduplicate)
    papers_path = os.path.join(data_dir, 'papers.json')
    added = sync_papers_json(pubs, papers_path)
    with open(papers_path, 'r', encoding='utf-8') as f:
        final_count = len(json.load(f))
    print(f"  papers.json: {final_count} total ({added} added, synced with {len(pubs)} publications)")

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
