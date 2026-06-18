import asyncio
import logging
import re
from sqlalchemy import select
from app.models.db import AsyncSessionLocal, AtlasNode, AtlasEdge
from app.services.memory import get_qdrant, COLLECTION_NAME

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Stop words to filter out noise from keyword matching
STOP_WORDS = {
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

async def run_backfill():
	logger.info("Initializing Memory Atlas backfill from Qdrant...")
	client = get_qdrant()
	
	try:
		# 1. Fetch points from Qdrant
		results, _ = client.scroll(
			collection_name=COLLECTION_NAME,
			limit=500,
			with_payload=True,
			with_vectors=False,
		)
		logger.info(f"Retrieved {len(results)} memory points from Qdrant.")
	except Exception as e:
		logger.error(f"Failed to scroll Qdrant: {e}")
		return

	if not results:
		logger.info("No memory points to backfill.")
		return

	async with AsyncSessionLocal() as session:
		# 2. Insert into atlas_nodes
		inserted_nodes = []
		word_sets = {}
		
		for p in results:
			text_val = p.payload.get("text", "")
			if not text_val:
				continue
			
			# Check if node already exists to prevent duplication
			existing = await session.execute(
				select(AtlasNode).where(AtlasNode.label == text_val)
			)
			node = existing.scalar_one_or_none()
			
			if not node:
				node = AtlasNode(
					type="memory",
					label=text_val,
					payload={"qdrant_id": str(p.id)},
					confidence=0.8
				)
				session.add(node)
				await session.flush() # Populate ID without committing yet
				
			inserted_nodes.append(node)
			
			# Tokenize keywords
			words = re.findall(r'\b[a-zA-ZäöüßÄÖÜ]{4,}\b', text_val.lower())
			keywords = {w for w in words if w not in STOP_WORDS}
			word_sets[node.id] = keywords

		logger.info(f"Staged {len(inserted_nodes)} AtlasNode objects in Postgres.")

		# 3. Build & Insert edges
		edge_count = 0
		for i in range(len(inserted_nodes)):
			for j in range(i + 1, len(inserted_nodes)):
				n1 = inserted_nodes[i]
				n2 = inserted_nodes[j]
				
				words1 = word_sets.get(n1.id, set())
				words2 = word_sets.get(n2.id, set())
				
				if not words1 or not words2:
					continue
					
				intersection = words1.intersection(words2)
				if intersection:
					union = words1.union(words2)
					weight = len(intersection) / len(union)
					weight = round(0.3 + 0.7 * weight, 3)
					
					# Check if edge already exists
					existing_edge = await session.execute(
						select(AtlasEdge).where(
							((AtlasEdge.source_node_id == n1.id) & (AtlasEdge.target_node_id == n2.id)) |
							((AtlasEdge.source_node_id == n2.id) & (AtlasEdge.target_node_id == n1.id))
						)
					)
					edge = existing_edge.scalar_one_or_none()
					
					if not edge:
						edge = AtlasEdge(
							source_node_id=n1.id,
							target_node_id=n2.id,
							kind="keyword_cooccurrence",
							weight=weight,
							payload={"shared_words": list(intersection)}
						)
						session.add(edge)
						edge_count += 1

		logger.info(f"Staged {edge_count} AtlasEdge objects in Postgres.")
		
		# 4. Commit transaction
		await session.commit()
		logger.info("Successfully committed backfill transaction to Postgres.")

if __name__ == "__main__":
	asyncio.run(run_backfill())
