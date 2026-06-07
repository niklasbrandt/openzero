import logging
import re
from fastapi import APIRouter, Query
from app.services.memory import get_qdrant, COLLECTION_NAME

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/atlas", tags=["atlas"])

# Stop words to filter out noise from keyword matching
STOP_WORDS = {
	# English
	"about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are", "aren't", "as", "at",
	"be", "because", "been", "before", "being", "below", "between", "both", "but", "by", "can't", "cannot",
	"could", "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during", "each",
	"few", "for", "from", "further", "had", "hadn't", "has", "hasn't", "have", "haven't", "having", "he",
	"he'd", "he'll", "he's", "her", "here", "here's", "hers", "herself", "him", "himself", "his", "how",
	"how's", "i", "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's", "its",
	"itself", "let's", "me", "more", "most", "mustn't", "my", "myself", "no", "nor", "not", "of", "off",
	"on", "once", "only", "or", "other", "ought", "our", "ours", "ourselves", "out", "over", "own", "same",
	"shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such", "than", "that",
	"that's", "the", "their", "theirs", "them", "themselves", "then", "there", "there's", "these", "they",
	"they'd", "they'll", "they're", "they've", "this", "those", "through", "to", "too", "under", "until",
	"up", "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were", "weren't", "what",
	"what's", "when", "when's", "where", "where's", "which", "while", "who", "who's", "whom", "why",
	"why's", "with", "won't", "would", "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your",
	"yours", "yourself", "yourselves",
	# German
	"aber", "alle", "allem", "allen", "aller", "alles", "als", "also", "ander", "andere",
	"anderem", "anderen", "anderer", "anderes", "anderm", "andern", "anders", "auch", "auf", "aus",
	"bei", "bin", "bis", "bist", "da", "damit", "dann", "der", "den", "dem", "des", "das", "dass",
	"daß", "derselbe", "derselben", "denselben", "dasselbe", "dazu", "dein", "deine",
	"deinem", "deinen", "deiner", "deines", "demnach", "denn", "derer", "dessen", "dies", "diese",
	"diesem", "diesen", "dieser", "dieses", "doch", "dort", "durch", "ein", "eine", "einem", "einen",
	"einer", "eines", "einig", "einige", "einigem", "einigen", "einiger", "einiges", "einmal", "er",
	"ihn", "ihm", "es", "etwas", "euer", "eure", "eurem", "euren", "eurer", "eures", "für", "gegen",
	"gewesen", "hab", "habe", "haben", "hat", "hatte", "hatten", "hier", "hin", "hinter", "ich",
	"mich", "mir", "ihr", "ihre", "ihrem", "ihren", "ihrer", "ihres", "euch", "im", "indem",
	"ins", "ist", "jede", "jedem", "jeden", "jeder", "jedes", "jene", "jenem", "jenen", "jener",
	"jenes", "jetzt", "kann", "kein", "keine", "keinem", "keinen", "keiner", "keines", "können",
	"könnte", "machen", "man", "manche", "manchem", "manchen", "mancher", "manches", "mein", "meine",
	"meinem", "meinen", "meiner", "meines", "mit", "muss", "musste", "nach", "nicht", "nichts", "noch",
	"nun", "nur", "ob", "oder", "ohne", "sehr", "sein", "seine", "seinem", "seinen", "seiner", "seines",
	"selbst", "sich", "sie", "ihnen", "sind", "solche", "solchem", "solchen", "solcher", "solches",
	"soll", "sollte", "sondern", "sonst", "über", "um", "und", "uns", "unsere", "unserem", "unseren",
	"unseres", "unter", "vom", "von", "vor", "während", "war", "waren", "warst", "weg", "weil",
	"weiter", "welche", "welchem", "welchen", "welcher", "welches", "wenn", "werde", "werden", "werdet",
	"weshalb", "wie", "wieder", "will", "wir", "wird", "wirst", "wo", "wollen", "wollte", "würde",
	"würden", "zu", "zum", "zur", "zwar", "zwischen"
}

def clean_label(text: str) -> str:
	# Keep label clean and readable
	return text.strip()

@router.get("/graph")
async def get_atlas_graph(limit: int = Query(80, ge=1, le=200)):
	client = get_qdrant()
	nodes = []
	edges = []

	try:
		# Scroll the latest limit points from Qdrant
		results, _ = client.scroll(
			collection_name=COLLECTION_NAME,
			limit=limit,
			with_payload=True,
			with_vectors=False,
		)

		word_sets = {}
		for p in results:
			text_val = p.payload.get("text", "")
			if not text_val:
				continue

			node_id = str(p.id)
			label = clean_label(text_val)

			nodes.append({
				"id": node_id,
				"label": label,
				"type": "memory",
				"confidence": 0.8
			})

			# Tokenize and extract keywords for edge building
			# Extract words of length >= 4, lowercase, remove punctuation, exclude stop words
			words = re.findall(r'\b[a-zA-ZäöüßÄÖÜ]{4,}\b', text_val.lower())
			keywords = {w for w in words if w not in STOP_WORDS}
			word_sets[node_id] = keywords

		# Construct edges based on shared keywords
		for i in range(len(nodes)):
			for j in range(i + 1, len(nodes)):
				id1 = nodes[i]["id"]
				id2 = nodes[j]["id"]
				words1 = word_sets.get(id1, set())
				words2 = word_sets.get(id2, set())

				if not words1 or not words2:
					continue

				intersection = words1.intersection(words2)
				if intersection:
					union = words1.union(words2)
					weight = len(intersection) / len(union)
					weight = round(0.3 + 0.7 * weight, 3)
					edges.append({
						"source": id1,
						"target": id2,
						"weight": weight
					})

		# Cap the number of edges to prevent the graph from being too crowded
		# Keep top 150 edges by weight
		if len(edges) > 150:
			edges = sorted(edges, key=lambda e: e["weight"], reverse=True)[:150]

	except Exception as e:
		logger.error("Failed to build dynamic openZero atlas graph: %s", e)

	return {"nodes": nodes, "edges": edges}
