"""Bounded candidate-only fingerprints for a built-in PostgreSQL JSONB GIN index."""
import hashlib
import re
from app.core.content_normalization import canonical_text

def formula_shape(text):
    formulas=re.findall(r"\$(.*?)\$",canonical_text(text),re.S)
    return "|".join(re.sub(r"(?<![A-Za-z])\d+(?:\.\d+)?","#",canonical_text(x)) for x in formulas)

def search_features(text):
    normalized=canonical_text(text)[:6000]
    def key(prefix,value):return prefix+hashlib.blake2s(value.encode(),digest_size=8).hexdigest()
    grams={key("g:",normalized[i:i+3]) for i in range(max(0,len(normalized)-2))}
    # Deterministic bottom-k sampling keeps the index bounded for long questions.
    out={g:True for g in sorted(grams)[:128]}
    shape=formula_shape(text)
    if shape:out[key("m:",shape)]=True
    return out
