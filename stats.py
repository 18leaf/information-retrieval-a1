import nltk
from nltk.corpus import stopwords

from pathlib import Path
from preprocess import Preprocess
import numpy as np


# preproess text ->
# Output -> X = Doc-term matrix
# url_ids = list of pages
# vocab = word - numbe mapping
matrix = Preprocess(input_dir=Path.cwd() / "output").run()

# The number of unique words in the corpus.
print(f"There are {len(matrix.vocab.keys())}distinct words in the vocab")
# The number of words in the corpus.
print(f"There are {np.sum(matrix.X)} words in the corpus")
# The average page length (in words).
print(f"The average page length is {matrix.X.sum(axis=1).mean()}")
# List the top 30 most frequent words in the corpus and their frequencies (collection frequency and document frequency) ordered by their collection frequency.
# Document frequency is the number of documents that contain the word.
# Collection frequency is the total number of times the word appears in the corpus.
# collection_freq, document_freq
collection_freq = matrix.X.sum(axis=0) # column sum
document_freq = (matrix.X > 0).sum(axis=0) # sum where column > 0

# id -> word mapping
id_to_word: dict[int, str] = {}
for word, tid in matrix.vocab.items():
    id_to_word[tid] = word

# top 30 words by collection frequency
top_idx = np.argsort(collection_freq)[::-1][:30]
print("Top 30 used words")
for idx in top_idx:
    print(f"\tcollection frequency {collection_freq[idx]}")
    print(id_to_word[idx])
    print(f"\tdocument frequency {document_freq[idx]}")
    print("-------------------------------------")
# Remove stop words from the vocabulary and show the top 30 most frequent words again. You can use the stopwords list from NLTK or any other source.

nltk.download("stopwords", quiet=True)
stop = set(stopwords.words("english"))


non_stop_term_ids: list[int] = []
for term_id, word in id_to_word.items():
    # length larger than 1 .. got a lot fo j, k, etc.
    if word not in stop and len(word) > 1:
        non_stop_term_ids.append(term_id)


non_stop_idx = np.array(non_stop_term_ids, dtype=int)

# get the collection frequencies for just those term-ids
non_stop_cf = collection_freq[non_stop_idx]

# ranks (indices into non_stop_idx) from highest cf -> lowest
rank = np.argsort(non_stop_cf)[::-1]

# take top 30 term-ids
top_idx_ns = non_stop_idx[rank[:30]]

print("Top 30 used words (STOPWORDS REMOVED)")
for idx in top_idx_ns:
    print(f"|\tcollection frequency {collection_freq[idx]}")
    print("|  " + id_to_word[idx])
    print(f"|\tdocument frequency {document_freq[idx]}")
    print("-------------------------------------")
