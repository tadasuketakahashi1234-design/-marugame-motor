"""Canonical official finishing-method labels; unknown stays unknown."""
import re
import unicodedata

KNOWN=('逃げ','差し','まくり','まくり差し','抜き','恵まれ')
def normalize_method(value):
    label=re.sub(r'\s+','',unicodedata.normalize('NFKC',str(value or '')))
    return label if label in KNOWN else None
