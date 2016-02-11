# coding: utf-8

from collections import Counter
import glob
import re
import logging


import csv
#logging.basicConfig(format='%(levelname)s %(asctime)s:%(message)s', level=logging.INFO)

print "Reloaded Ext."
logger = logging.getLogger("DeepSequenceClassification")
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
formatter = logging.Formatter('%(name)s %(levelname)s %(asctime)s:%(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)
logger.info("Started Logger")

class WordToken:
    START = 0
    END = 1
    OOV = 2
    VOCAB = 3
    def __init__(self, token_type, value="", b_label="", c_label=""):
        self.token_type = token_type
        if self.token_type == WordToken.START:
            self.word_value = ""
            self.word_index = WordToken.START
            self.char_value = "<^>"
        elif self.token_type == WordToken.END:
            self.word_value = ""
            self.word_index = WordToken.END
            self.char_value = "<$>"
        else:
            self.word_value = value.lower()
            self.char_value = value
            if self.word_value not in WordToken.word_dict:
                self.token_type = WordToken.OOV
                self.word_index = WordToken.OOV
            else:
                self.word_index = WordToken.word_dict[self.word_value] + WordToken.VOCAB
        self.char_seq = [1 + WordToken.char_dict.get(k, -1) for k in self.char_value] # 0 for OOV char
        self.b_label = b_label
        self.c_label = c_label
    
    @staticmethod
    def set_vocab(word_dict = {}, char_dict={}):
        logger.info("Initializing WordToken word_dict with %s items and char_dict with %s items" % (len(word_dict), len(char_dict)))
        WordToken.word_dict = word_dict
        WordToken.char_dict = char_dict
    
    def get_type(self):
        if self.token_type == WordToken.START:
            return "START"
        if self.token_type == WordToken.END:
            return "END"
        if self.token_type == WordToken.OOV:
            return "OOV"
        return "VOCAB"
    def __repr__(self):
        return "WordToken(%s, %s, '%s', '%s', %s, %s)" % (self.get_type(), self.word_index, self.word_value, self.char_value, self.b_label, self.c_label)

# Helper functions to read the data
def get_sequences(doc):
    logger.debug("Reading Document: %s" % doc)
    tokens = []
    start = WordToken(WordToken.START, value="", b_label="NO_ENTITY", c_label="NO_ENTITY")
    tokens.append(start)
    for token, b_label, c_label in doc:
        word = WordToken(WordToken.VOCAB, value=token, b_label=b_label, c_label=c_label)
        tokens.append(word)
    end = WordToken(WordToken.END, value="", b_label="NO_ENTITY", c_label="NO_ENTITY")
    tokens.append(end)
    return tokens

def get_documents(filename):
    """
    Document format: DOCID\tTOKEN\tPOS\tBOUNDARY\tCATEGORY
    DOCIDs should be same for continous set of tokens.
    """
    DOCID = None
    doc = []
    with open(filename, "rb") as fp:
        reader = csv.reader(fp, delimiter="\t")
        for row in reader:
            if DOCID is None:
                DOCID = row[0]
            if row[0] != DOCID:
                yield DOCID, doc
                DOCID = row[0]
                doc = []
            else:
                doc.append((row[1], row[3], row[4]))


def gen_vocab(filenames, n_words = 10000, min_freq=1):
    vocab_words = Counter()
    for i, filename in enumerate(filenames):
        for docid, doc in get_documents(filename):
            seq = get_sequences(doc)
            for token in seq:
                if token.token_type not in [WordToken.START, WordToken.END]:
                    vocab_words[token.word_value] += 1
        if i % 10 == 0:
            logger.info("Finished reading %s files with %s tokens" % (i + 1, len(vocab_words)))
    index_word = map(lambda x: x[0], filter(lambda x: x[1] > min_freq, vocab_words.most_common(n_words)))
    word_dict = dict(zip(index_word, xrange(len(index_word))))
    
    index_char= [chr(k) for k in xrange(32, 127)]
    char_dict = dict((k, v) for v,k in enumerate(index_char))
    return index_word, word_dict, index_char, char_dict


def save_vocab(vocab_dict, save_file=None):
    if save_file is not None:
        # SAVE VOCB TO FILE
        with open(save_file, "wb+") as fp:
            for k,v in vocab_dict.iteritems():
                print >> fp, "%s\t%s" % (k, v)

#WordToken.set_vocab(word_dict=word_dict)
def load_vocab(save_file):
    vocab_tuples = []
    with open(save_file) as fp:
        for line in fp:
            word, index = line[:-1].split("\t")
            vocab_tuples.append((word, int(index)))
    word_dict = dict(vocab_tuples)
    index_word = map(lambda x: x[0], vocab_tuples)
    return index_word, word_dict

if __name__ == "__main__":
    import json
    CONFIG = json.load(open("config.json"))
    DIR_NAME = "%s/%s" % (CONFIG["BASE_DATA_DIR"], CONFIG["DATA_DIR"])
    CV_filenames = [glob.glob("%s/%s/*.xml" % (DIR_NAME, i)) for i in range(1,6)]
    filenames = reduce(lambda x, y: x + y, CV_filenames[0:])
    WordToken.set_vocab() # Initialize an empty vocab
    index_word, word_dict, index_char, char_dict = gen_vocab(filenames, n_words = 50000, min_freq=3)
    save_vocab(word_dict, save_file="%s/index_word.txt" % CONFIG["BASE_OUT_DIR"])
    logger.info("Saved %s index for vocab words in file %s." % (len(index_word), "%s/index_word.txt" % CONFIG["BASE_OUT_DIR"]))
    save_vocab(char_dict, save_file="%s/index_char.txt" % CONFIG["BASE_OUT_DIR"])
    logger.info("Saved %s index for vocab chars in file %s." % (len(index_char), "%s/index_char.txt" % CONFIG["BASE_OUT_DIR"]))
