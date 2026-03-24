import os, logging, re
from transformers import pipeline, Pipeline

logger = logging.getLogger(__name__)

INTRO_VERBS = {
    "bghit","bghi","bghiit","bgit","wach","wasch","wash",
    "nchri","nshri","3tini","atini","fin","feen",
    "kayn","kayna","kain","3andi","3endo","3ndo","3endi","endi",
    "kan","knt","fe","fi","f","mn","b","bi","l","dial",
    "kan9eleb","9eleb","3la","nchri",
    "عطيني","بغيت","واش","فين","كاين","نشري",
}
class NERAgent:

    def __init__(self):
        model_name = os.getenv("HF_MODEL_NAME", "your-username/darija-ner-xlmroberta")
        logger.info(f"Loading NER model: {model_name}")
        self._pipe: Pipeline = pipeline(
            task="ner",
            model=model_name,
            tokenizer=model_name,
            aggregation_strategy="simple",
            device=-1,
        )
        logger.info("NER model loaded successfully")

    def extract(self, query: str) -> dict:
        if not query or not query.strip():
            return self._empty(query)

        query_for_model = query.lower().strip()

        try:
            raw_results = self._pipe(query_for_model)
        except Exception as e:
            logger.error(f"NER inference failed: {e}")
            return self._empty(query)

        # Merge consecutive same-label entities that are adjacent
        # "s"(PRODUCT) + "21"(PRODUCT) + "ultra"(PRODUCT) → "s21 ultra"(PRODUCT)
        merged = []
        for ent in raw_results:
            if (merged
                    and merged[-1]["entity_group"] == ent["entity_group"]
                    and ent["start"] - merged[-1]["end"] <= 1):
                merged[-1]["word"]  = query_for_model[merged[-1]["start"]:ent["end"]]
                merged[-1]["end"]   = ent["end"]
                merged[-1]["score"] = (merged[-1]["score"] + ent["score"]) / 2
            else:
                merged.append(dict(ent))

        entities = {
            "product": None, "brand": None,
            "city": None, "price": None, "color": None,
        }

        for ent in merged:
            label = ent["entity_group"].lower()
            word  = ent["word"].strip()
            score = ent["score"]

            if score < 0.65:
                continue
            if len(word) < 2:
                continue
            if word.lower() in INTRO_VERBS:
                continue
            if label in ("city", "brand") and re.match(r"^\d+$", word):
                continue
            if len(word) <= 3 and score < 0.90:
                continue

            if label in entities and entities[label] is None:
                entities[label] = word

        logger.info(f"Extracted: {entities}")
        return {"query": query, **entities, "raw": raw_results}

    @staticmethod
    def _empty(query):
        return {"query": query, "product": None, "brand": None,
                "city": None, "price": None, "color": None, "raw": []}

    def format_summary(self, entities: dict) -> str:
        lines = [f"Query: {entities['query']}"]
        for k in ["product","brand","city","price","color"]:
            if entities.get(k):
                lines.append(f"  {k.upper()}: {entities[k]}")
        if not any(entities.get(k) for k in ["product","brand","city","price","color"]):
            lines.append("  (no entities detected)")
        return "\n".join(lines)