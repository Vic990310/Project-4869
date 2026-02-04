import re

def parse_title(title):
    """
    Parses the raw title to extract metadata.
    Returns a dictionary with keys: episode, resolution, container, subtitle, source_type.
    Values are None if not found.
    """
    if not title:
        return {
            'episode': None,
            'resolution': None,
            'container': None,
            'subtitle': None,
            'source_type': None
        }

    result = {
        'episode': None,
        'resolution': None,
        'container': None,
        'subtitle': None,
        'source_type': None
    }
    
    # 1. Episode
    # Prioritize Movie (Mxx or 剧场版xx or Movie xx)
    movie_match = re.search(r'(?:M|Movie|剧场版)[\s_]*(\d{1,2})', title, re.IGNORECASE)
    if movie_match:
        result['episode'] = f"M{movie_match.group(1)}"
    else:
        # Standard episode (3-4 digits), usually inside brackets or standalone
        # Avoid years like 2024
        # Look for [1190] or 【1190】 or " 1190 " or start of string "1190 ..."
        ep_match = re.search(r'(?:^|[\[【\s])(\d{3,4})(?:[\]】\s]|$)', title)
        if ep_match:
            ep_num = int(ep_match.group(1))
            if ep_num < 1990 or ep_num > 2100: # Simple heuristic to avoid years if possible, though 20xx is valid episode in future
                 result['episode'] = str(ep_num)
        
        # Fallback: look for 第xxx话
        if not result['episode']:
             ep_match_2 = re.search(r'第(\d{3,4})(?:话|集)', title)
             if ep_match_2:
                 result['episode'] = ep_match_2.group(1)

    # 2. Resolution
    res_match = re.search(r'(1080[Pp]|720[Pp]|2160[Pp]|4[Kk])', title, re.IGNORECASE)
    if res_match:
        result['resolution'] = res_match.group(1).upper()

    # 3. Container
    cont_match = re.search(r'(MKV|MP4|AVI)', title, re.IGNORECASE)
    if cont_match:
        result['container'] = cont_match.group(1).upper()

    # 4. Subtitle
    # Common patterns: CHS, CHT, JP, 简日, 繁日, 简繁
    sub_patterns = [
        (r'(CHS_JP|CHT_JP|CHS\&JP|CHT\&JP)', 'CHS_JP'), # Normalize
        (r'(简日|简日双语)', 'CHS_JP'),
        (r'(繁日|繁日双语)', 'CHT_JP'),
        (r'(CHS|简体)', 'CHS'),
        (r'(CHT|BIG5|繁体)', 'CHT'),
        (r'(JP|JAPANESE|日吉)', 'JP') # Typo in regex? JP usually implies raw if alone, but sometimes subtitles.
    ]
    
    found_sub = False
    for pat, val in sub_patterns:
        if re.search(pat, title, re.IGNORECASE):
            result['subtitle'] = val
            found_sub = True
            break
            
    # 5. Source Type
    src_match = re.search(r'(WEBRIP|HDTV|BDRIP|BLURAY|DVDISO|DVD)', title, re.IGNORECASE)
    if src_match:
        result['source_type'] = src_match.group(1).upper()

    return result

if __name__ == "__main__":
    # Test cases
    test_titles = [
        "[银色子弹][名侦探柯南][1190][1080P][MKV][简日双语]",
        "[SilverBullet][Detective Conan][Movie 27][1080P][BDRip][CHS_JP]",
        "名侦探柯南 第1000集 720P MP4",
        "[SBSUB][Conan][M26][1080P][WEBRIP][CHT]"
    ]
    for t in test_titles:
        print(f"Title: {t}\nResult: {parse_title(t)}\n")
