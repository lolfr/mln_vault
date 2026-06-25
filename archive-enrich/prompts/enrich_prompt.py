# version: 0.2.0
"""Prompt unique : enrichissement d'un item de la collection.

Le LLM reçoit :
  - la preview JPEG (1200px max) déjà générée par generate_derivatives.py
  - la transcription (si vidéo) déjà produite par Whisper
  - les métadonnées DÉJÀ CONNUES (id, year si présent, product/campaign si déduits du path)

Il enrichit UNIQUEMENT les champs NULL ou nécessitant raffinement.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import vault_config as _vc; _CFG = _vc.load_config()  # noqa: E402

SYSTEM_ENRICH = f"""Tu es archiviste senior spécialisé dans {_CFG.collection_description}.
Tu enrichis la fiche d'un item du catalogue privé en produisant un JSON STRICT.

PRINCIPE ABSOLU : tu ENRICHIS, tu n'ÉCRASES PAS.
- Les champs déjà fournis dans le contexte (input) sont la vérité de référence.
- Tu ne contredis JAMAIS une année connue, un product déjà identifié, etc.
- Tu remplis ce qui manque ; pour le reste, tu confirmes (ou tu nuances avec evidence).

Tu connais l'histoire visuelle de la collection :
- Logos et identités visuelles par époque (cf. vocabulaire borné ci-après pour les produits/campagnes).
- Garde les noms de marques, produits et campagnes tels quels, sans les traduire.
- Format/qualité par époque : 4:3 SD jusqu'à ~2008, HD 16:9 ensuite, UHD 2017+

RÈGLES DE SORTIE :
1. Réponds UNIQUEMENT par un objet JSON valide. Pas de préambule, pas de markdown fences.
2. Si une info n'est pas déterminable, mets `null`. JAMAIS d'invention.
3. Sois conservateur : `null` vaut mieux que faux.
4. `description` factuelle, descriptive, non promotionnelle, 2-4 phrases max.
5. `title_inferred` doit être descriptif et éditorial, pas un slogan. Format suggéré :
   "Produit — \\"Nom de la pub\\" (Campagne, Année)" si tous éléments connus,
   sinon une variante allégée. Exemples (noms de produits/campagnes conservés tels quels) :
     "iPad Pro — Host your podcast (2019)"
     "Get a Mac — Restarting (2006)"
     "iPod nano — Silhouettes (2007)"
6. Pour `tags` : 5-10 tags max, mélange contrôlé/libre. Vocabulaire borné indiqué ci-après.
"""


USER_ENRICH_TEMPLATE = """Voici les données pour un item du catalogue.

═══ CONTEXTE CONNU (vérité de référence — ne pas contredire) ═══
ID         : {item_id}
Type       : {item_type}
Section    : {section}
Année      : {year_known}              ← {year_status}
Produit    : {product_known}           ← {product_status}
Campagne   : {campaign_known}          ← {campaign_status}
Pays       : {country_known}
Langue     : {language_known}
Titre actuel : {title_current}         ← {title_status}
Description actuelle : {desc_current}
Durée vidéo : {duration_s} s
Dimensions  : {width}x{height}

═══ IMAGE (preview attachée en message) ═══
Voir l'image jointe.

═══ TRANSCRIPTION AUDIO (vidéo) ═══
Langue détectée : {transcript_lang}
Texte :
{transcript_text}

═══ VOCABULAIRES BORNÉS ═══
product_line (réutiliser exactement si match) :
  {allowed_products}
campaign (réutiliser exactement, ou "other", ou null) :
  {allowed_campaigns}
format_type :
  {allowed_formats}

═══ TÂCHE ═══
Produis MAINTENANT le JSON suivant (et rien d'autre) :

{{
  "title_inferred": "titre éditorial OU null si le titre actuel est déjà bon",
  "should_replace_title": true|false,

  "description": "2-4 phrases factuelles (ne JAMAIS être null)",

  "year_estimate": {year_known} ou un entier OU null,
  "year_confidence": "exact|narrow|decade|unknown",
  "year_evidence": "justification courte si tu proposes une année non fournie",

  "product": "valeur de l'enum ou null (n'écraser que si null en entrée)",
  "campaign": "valeur de l'enum ou null",
  "format_type": "valeur de l'enum ou null",

  "country": "code ISO alpha-2, 'INTL', ou null",
  "language": "code ISO 639-1 ou null",

  "cast": ["liste de personnes visibles/audibles, ou []"],
  "music_note": "note courte ou null",
  "on_screen_text": "texte affiché à l'écran ou null",

  "tags": ["liste de 5-10 tags, mélange vocabulaire borné + libres"],

  "overall_confidence": 0.0-1.0
}}
"""


def build_user_message(item: dict, transcript_text: str | None, transcript_lang: str | None,
                       allowed_products: tuple, allowed_campaigns: tuple, allowed_formats: tuple,
                       title_is_raw: bool) -> str:
    """Remplit le template avec les données de l'item.

    `item` doit contenir au moins : id, item_type, section (déduit), year, product,
    campaign, country, language, title, description, duration_seconds, width_px, height_px.
    """
    def known_status(v):
        return "(connu, ne pas contredire)" if v not in (None, "") else "(à inférer si possible)"

    return USER_ENRICH_TEMPLATE.format(
        item_id=item.get("id", "?"),
        item_type=item.get("item_type", "?"),
        section=item.get("section", "?"),
        year_known=item.get("year") if item.get("year") else "null",
        year_status=known_status(item.get("year")),
        product_known=item.get("product") if item.get("product") else "null",
        product_status=known_status(item.get("product")),
        campaign_known=item.get("campaign") if item.get("campaign") else "null",
        campaign_status=known_status(item.get("campaign")),
        country_known=item.get("country") or "null",
        language_known=item.get("language") or "null",
        title_current=item.get("title") or "(vide)",
        title_status="(brut, à remplacer)" if title_is_raw else "(éditorial, à conserver si bon)",
        desc_current=item.get("description") or "(vide)",
        duration_s=item.get("duration_seconds") or "n/a",
        width=item.get("width_px") or "?",
        height=item.get("height_px") or "?",
        transcript_lang=transcript_lang or "n/a",
        transcript_text=(transcript_text or "(pas de transcription)")[:4000],
        allowed_products=", ".join(allowed_products),
        allowed_campaigns=", ".join(allowed_campaigns),
        allowed_formats=", ".join(allowed_formats),
    )
