"""Public guide paths, without third-party dependencies (no Pillow)."""
import re


def article_path(article):
    # Same rule as the site and pin_draft.article_path: guides live under their country, Portugal by default.
    country=article.get('country','portugal')
    if not isinstance(country,str) or not re.fullmatch(r'[a-z]+(?:-[a-z]+)*',country):raise ValueError('invalid_country')
    return '/'+country+'/'+article['slug']+'/'
